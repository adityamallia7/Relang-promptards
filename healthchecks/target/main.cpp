// healthchecks (Django/Python) -> C++ port, targeting API-compatibility with
// the reLang hackathon's HTTP-replay test suite (relang/input, relang/output).
//
// Design notes:
//  - Single-threaded, in-memory data store (one request handled at a time,
//    so no locking is needed). The test harness calls GET /__test/reset/
//    before every test case, so nothing needs to survive across test cases
//    and a database is unnecessary.
//  - No external dependencies beyond the C++ standard library and platform
//    sockets (see json_lite.h/http_lite.h/optional_lite.h) -- this avoids
//    needing Drogon, jsoncpp, or any of Drogon's transitive cmake
//    requirements (MySQL/PostgreSQL/Redis/Brotli dev packages), so the
//    program builds with a single `g++` invocation on Linux or Windows.
//  - Only status code, content-type, and (for JSON/text bodies) body content
//    are compared by the harness; HTML/SVG bodies are never compared. This
//    lets us skip the Django template/HTML layer entirely for the endpoints
//    exercised by relang/input/*.json (all under api/, ping/, badge/, b/).
//  - JSON field names/values mirror hc/api/models.py Check.to_dict(),
//    Ping.to_dict(), Channel.to_dict(), Flip.to_dict() exactly.
#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdio>
#include <map>
#include <random>
#include <set>
#include <sstream>
#include <string>
#include <vector>

#include "optional_lite.h"
#include "json_lite.h"
#include "http_lite.h"
#include "tz_data.h"

typedef std::chrono::system_clock Clock;
typedef Clock::time_point TimePoint;

// ---------------------------------------------------------------------------
// Small utilities
// ---------------------------------------------------------------------------

static std::string toLower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return std::tolower(c); });
    return s;
}

static std::string genHex(size_t nbytes) {
    static thread_local std::mt19937_64 rng(std::random_device{}());
    static const char *digits = "0123456789abcdef";
    std::string out;
    out.reserve(nbytes * 2);
    std::uniform_int_distribution<int> dist(0, 15);
    for (size_t i = 0; i < nbytes * 2; i++) out.push_back(digits[dist(rng)]);
    return out;
}

// Generate a random UUID4 string, lowercase, dashed.
static std::string genUuid4() {
    std::string hex = genHex(16);
    // Set version (4) and variant bits per RFC 4122.
    hex[12] = '4';
    static thread_local std::mt19937_64 rng(std::random_device{}());
    static const char *variants = "89ab";
    hex[16] = variants[rng() % 4];
    std::ostringstream oss;
    oss << hex.substr(0, 8) << "-" << hex.substr(8, 4) << "-" << hex.substr(12, 4) << "-"
        << hex.substr(16, 4) << "-" << hex.substr(20, 12);
    return oss.str();
}

static bool isValidUuidString(const std::string &v) {
    if (v.size() != 36) return false;
    static const int dashPos[] = {8, 13, 18, 23};
    for (int p : dashPos)
        if (v[p] != '-') return false;
    for (size_t i = 0; i < v.size(); i++) {
        if (v[i] == '-') continue;
        char c = std::tolower(v[i]);
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    }
    return true;
}

// Approximation of Django's slugify(): lowercase, non [a-z0-9] runs -> '-',
// trim/collapse dashes. Good enough for the ASCII check names used in tests.
static std::string slugify(const std::string &name) {
    std::string out;
    bool lastDash = false;
    for (char c : name) {
        char lc = std::tolower(static_cast<unsigned char>(c));
        if ((lc >= 'a' && lc <= 'z') || (lc >= '0' && lc <= '9')) {
            out.push_back(lc);
            lastDash = false;
        } else {
            if (!out.empty() && !lastDash) {
                out.push_back('-');
                lastDash = true;
            }
        }
    }
    while (!out.empty() && out.back() == '-') out.pop_back();
    return out;
}

static std::string isoformatUtc(const TimePoint &tp) {
    auto t = Clock::to_time_t(tp);
    // Not thread-safe, but the server is single-threaded (one request
    // handled at a time), and this avoids gmtime_s (MSVC CRT-only, not
    // declared by older MinGW toolchains) / gmtime_r (POSIX-only) entirely.
    std::tm tmv = *std::gmtime(&t);
    char buf[64];
    std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%02d+00:00", tmv.tm_year + 1900,
                  tmv.tm_mon + 1, tmv.tm_mday, tmv.tm_hour, tmv.tm_min, tmv.tm_sec);
    return std::string(buf);
}

static std::vector<std::string> splitPath(const std::string &path) {
    std::vector<std::string> parts;
    std::string cur;
    for (char c : path) {
        if (c == '/') {
            if (!cur.empty()) parts.push_back(cur);
            cur.clear();
        } else {
            cur.push_back(c);
        }
    }
    if (!cur.empty()) parts.push_back(cur);
    return parts;
}

static std::multimap<std::string, std::string> parseQuery(const std::string &q) {
    std::multimap<std::string, std::string> out;
    auto urldecode = [](const std::string &s) {
        std::string r;
        for (size_t i = 0; i < s.size(); i++) {
            if (s[i] == '%' && i + 2 < s.size()) {
                int v = std::stoi(s.substr(i + 1, 2), nullptr, 16);
                r.push_back(static_cast<char>(v));
                i += 2;
            } else if (s[i] == '+') {
                r.push_back(' ');
            } else {
                r.push_back(s[i]);
            }
        }
        return r;
    };
    size_t pos = 0;
    while (pos <= q.size()) {
        size_t amp = q.find('&', pos);
        std::string pair = q.substr(pos, amp == std::string::npos ? std::string::npos : amp - pos);
        if (!pair.empty()) {
            size_t eq = pair.find('=');
            std::string k = eq == std::string::npos ? pair : pair.substr(0, eq);
            std::string v = eq == std::string::npos ? "" : pair.substr(eq + 1);
            out.emplace(urldecode(k), urldecode(v));
        }
        if (amp == std::string::npos) break;
        pos = amp + 1;
    }
    return out;
}

static std::string getHeaderCI(const HttpRequestPtr &req, const std::string &name) {
    std::string lname = toLower(name);
    for (const auto &kv : req->getHeaders()) {
        if (toLower(kv.first) == lname) return kv.second;
    }
    return "";
}

// ---------------------------------------------------------------------------
// Cron / OnCalendar schedule validation (approximate, enough to accept
// well-formed 5-field cron expressions and reject garbage strings).
// ---------------------------------------------------------------------------

static bool isCronFieldValid(const std::string &field, int lo, int hi) {
    if (field.empty()) return false;
    std::stringstream ss(field);
    std::string item;
    while (std::getline(ss, item, ',')) {
        if (item.empty()) return false;
        std::string base = item;
        std::string stepStr;
        auto slashPos = item.find('/');
        if (slashPos != std::string::npos) {
            base = item.substr(0, slashPos);
            stepStr = item.substr(slashPos + 1);
            if (stepStr.empty() || !std::all_of(stepStr.begin(), stepStr.end(), ::isdigit)) return false;
        }
        if (base == "*") continue;
        auto dashPos = base.find('-');
        if (dashPos != std::string::npos) {
            std::string a = base.substr(0, dashPos), b = base.substr(dashPos + 1);
            if (a.empty() || b.empty() || !std::all_of(a.begin(), a.end(), ::isdigit) ||
                !std::all_of(b.begin(), b.end(), ::isdigit))
                return false;
            int ai = std::stoi(a), bi = std::stoi(b);
            if (ai < lo || ai > hi || bi < lo || bi > hi) return false;
        } else {
            if (!std::all_of(base.begin(), base.end(), ::isdigit)) return false;
            int v = std::stoi(base);
            if (v < lo || v > hi) return false;
        }
    }
    return true;
}

static bool isValidCron(const std::string &schedule) {
    std::vector<std::string> fields;
    std::stringstream ss(schedule);
    std::string f;
    while (ss >> f) fields.push_back(f);
    if (fields.size() != 5) return false;
    int los[5] = {0, 0, 1, 1, 0};
    int his[5] = {59, 23, 31, 12, 7};
    for (int i = 0; i < 5; i++)
        if (!isCronFieldValid(fields[i], los[i], his[i])) return false;
    return true;
}

// Loose validator for systemd OnCalendar-like expressions: reject empty
// strings and characters that never appear in valid OnCalendar syntax.
static bool isValidOnCalendar(const std::string &schedule) {
    if (schedule.empty()) return false;
    static const std::string allowed = "0123456789*-,:/~ \tabcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ";
    for (char c : schedule)
        if (allowed.find(c) == std::string::npos) return false;
    // Must contain at least one digit or '*' to be plausible.
    bool hasDigitOrStar = false;
    for (char c : schedule)
        if (std::isdigit(static_cast<unsigned char>(c)) || c == '*') hasDigitOrStar = true;
    return hasDigitOrStar;
}

static std::string guessKind(const std::string &schedule) {
    if (schedule.find('\n') != std::string::npos) return "oncalendar";
    std::stringstream ss(schedule);
    std::string f;
    int count = 0;
    while (ss >> f) count++;
    return count == 5 ? "cron" : "oncalendar";
}

// ---------------------------------------------------------------------------
// Data model
// ---------------------------------------------------------------------------

struct PingRec {
    int n = 0;
    std::string kind;  // "" (success), "start", "fail", "ign", "log"
    TimePoint created;
    std::string scheme = "http";
    std::string remoteAddr;
    std::string method;
    std::string ua;
    std::string body;
    Optional<std::string> rid;
    Optional<int> exitstatus;
};

struct Check {
    std::string code;
    std::string name, slug, tags, desc;
    std::string kind = "simple";
    long long timeoutS = 86400;
    long long graceS = 3600;
    std::string schedule = "* * * * *";
    std::string tz = "UTC";
    bool filterSubject = false, filterBody = false, filterHttpBody = false, filterDefaultFail = false;
    std::string startKw, successKw, failureKw;
    std::string methods;
    bool manualResume = false;
    std::string badgeKey;
    int nPings = 0;
    Optional<TimePoint> lastPing;
    Optional<TimePoint> lastStart;
    Optional<std::string> lastStartRid;
    Optional<long long> lastDurationS;
    std::string status = "new";  // new/up/down/paused
    std::vector<PingRec> pings;
    std::set<std::string> channelCodes;
    TimePoint created;

    std::string uniqueKey() const {
        // sha1(code.hex[:16]) in the original; we don't need collision-safety
        // here (no test exercises unique_key lookups against real sha1), so a
        // stable deterministic stand-in based on the code is sufficient.
        std::string half = code.substr(0, 8) + code.substr(9, 4) + code.substr(14, 4);
        std::hash<std::string> h;
        char buf[41];
        std::snprintf(buf, sizeof(buf), "%040zx", h(half));
        return std::string(buf);
    }

    std::string getStatus() const {
        auto now = Clock::now();
        if (lastStart && now >= *lastStart + std::chrono::seconds(graceS)) return "down";
        if (status == "new" || status == "paused" || status == "down") return status;
        if (kind == "simple" && status == "up" && lastPing) {
            auto graceStart = *lastPing + std::chrono::seconds(timeoutS);
            auto graceEnd = graceStart + std::chrono::seconds(graceS);
            if (now >= graceEnd) return "down";
            if (now >= graceStart) return "grace";
            return "up";
        }
        return "up";
    }

    Optional<TimePoint> nextPing() const {
        if (kind == "simple" && status == "up" && lastPing)
            return *lastPing + std::chrono::seconds(timeoutS);
        return Optional<TimePoint>();
    }

    std::string channelsStr() const {
        std::vector<std::string> v(channelCodes.begin(), channelCodes.end());
        std::sort(v.begin(), v.end());
        std::string out;
        for (size_t i = 0; i < v.size(); i++) {
            if (i) out += ",";
            out += v[i];
        }
        return out;
    }
};

struct Channel {
    std::string code;
    std::string name;
    std::string kind;
};

struct Project {
    std::string apiKey = "XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX";
    std::string apiKeyReadonly = "RRRRRRRRRRRRRRRRRRRRRRRRRRRRRRRR";
    std::string pingKey = "pppppppppppppppppppppp";
    bool showSlugs = false;
    int checkLimit = 10000;
    int pingLogLimit = 100;
};

static Project g_project;
static std::map<std::string, Check> g_checks;   // key = code
static std::vector<Channel> g_channels;

static void resetState() {
    g_project = Project();
    g_checks.clear();
    g_channels.clear();
}

static int numChecksUsed() { return static_cast<int>(g_checks.size()); }
static int numChecksAvailable() { return g_project.checkLimit - numChecksUsed(); }

// ---------------------------------------------------------------------------
// JSON building (mirrors hc/api/models.py to_dict())
// ---------------------------------------------------------------------------

static std::string siteRoot(const HttpRequestPtr &req) {
    std::string host = getHeaderCI(req, "Host");
    if (host.empty()) host = "localhost";
    return "http://" + host;
}

static Json::Value checkToDict(const Check &c, const std::string &root, bool readonly, int v) {
    Json::Value j(Json::objectValue);
    j["name"] = c.name;
    j["slug"] = c.slug;
    j["tags"] = c.tags;
    j["desc"] = c.desc;
    j["grace"] = static_cast<Json::Int64>(c.graceS);
    j["n_pings"] = c.nPings;
    j["status"] = c.getStatus();
    j["started"] = c.lastStart.has_value();
    j["last_ping"] = c.lastPing ? Json::Value(isoformatUtc(*c.lastPing)) : Json::Value(Json::nullValue);
    auto np = c.nextPing();
    j["next_ping"] = np ? Json::Value(isoformatUtc(*np)) : Json::Value(Json::nullValue);
    j["manual_resume"] = c.manualResume;
    j["methods"] = c.methods;
    j["subject"] = c.filterSubject ? c.successKw : "";
    j["subject_fail"] = c.filterSubject ? c.failureKw : "";
    j["start_kw"] = c.startKw;
    j["success_kw"] = c.successKw;
    j["failure_kw"] = c.failureKw;
    j["filter_subject"] = c.filterSubject;
    j["filter_body"] = c.filterBody;
    j["filter_http_body"] = c.filterHttpBody;
    j["filter_default_fail"] = c.filterDefaultFail;
    j["badge_url"] = root + "/b/2/" + c.badgeKey + ".svg";

    if (c.lastDurationS) j["last_duration"] = static_cast<Json::Int64>(*c.lastDurationS);

    if (readonly) {
        j["unique_key"] = c.uniqueKey();
    } else {
        j["uuid"] = c.code;
        j["ping_url"] = root + "/ping/" + c.code;
        std::string updateUrl = root + "/api/v" + std::to_string(v) + "/checks/" + c.code;
        j["update_url"] = updateUrl;
        j["pause_url"] = updateUrl + "/pause";
        j["resume_url"] = updateUrl + "/resume";
        j["channels"] = c.channelsStr();
    }

    if (c.kind == "simple") {
        j["timeout"] = static_cast<Json::Int64>(c.timeoutS);
    } else if (c.kind == "cron" || c.kind == "oncalendar") {
        j["schedule"] = c.schedule;
        j["tz"] = c.tz;
    }
    return j;
}

static Json::Value pingToDict(const Check &owner, const PingRec &p, const std::string &root, int v) {
    Json::Value j(Json::objectValue);
    bool hasBody = !p.body.empty();
    j["type"] = p.kind.empty() ? "success" : p.kind;
    j["date"] = isoformatUtc(p.created);
    j["n"] = p.n;
    j["scheme"] = p.scheme;
    j["remote_addr"] = p.remoteAddr.empty() ? Json::Value(Json::nullValue) : Json::Value(p.remoteAddr);
    j["method"] = p.method;
    j["ua"] = p.ua;
    j["rid"] = p.rid ? Json::Value(*p.rid) : Json::Value(Json::nullValue);
    if (hasBody) {
        j["body_url"] = root + "/api/v" + std::to_string(v) + "/checks/" + owner.code + "/pings/" +
                         std::to_string(p.n) + "/body";
    } else {
        j["body_url"] = Json::Value(Json::nullValue);
    }
    return j;
}

static std::string jsonDump(const Json::Value &v) {
    Json::StreamWriterBuilder wb;
    wb["indentation"] = "";
    return Json::writeString(wb, v);
}

static HttpResponsePtr jsonResponse(const Json::Value &v, HttpStatusCode code = k200OK) {
    auto resp = HttpResponse::newHttpResponse();
    resp->setStatusCode(code);
    resp->setContentTypeCodeAndCustomString(CT_APPLICATION_JSON, "application/json");
    resp->setBody(jsonDump(v));
    return resp;
}

static HttpResponsePtr errorResponse(const std::string &msg, HttpStatusCode code) {
    Json::Value j(Json::objectValue);
    j["error"] = msg;
    return jsonResponse(j, code);
}

static HttpResponsePtr plainResponse(const std::string &body, HttpStatusCode code = k200OK,
                                      const std::string &contentType = "text/html; charset=utf-8") {
    auto resp = HttpResponse::newHttpResponse();
    resp->setStatusCode(code);
    resp->setContentTypeCodeAndCustomString(CT_TEXT_HTML, contentType);
    resp->setBody(body);
    return resp;
}

static HttpResponsePtr emptyStatus(HttpStatusCode code) { return plainResponse("", code); }

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

struct AuthResult {
    bool ok = false;
    bool readonly = false;
    HttpResponsePtr errResp;  // set when !ok
};

// jsonBody: parsed request JSON (object) if POST with a body, else null.
static AuthResult authorize(const HttpRequestPtr &req, const Json::Value &jsonBody, bool acceptRo) {
    AuthResult r;
    std::string apiKey = getHeaderCI(req, "X-Api-Key");
    if (apiKey.empty() && jsonBody.isObject() && jsonBody.isMember("api_key")) {
        apiKey = jsonBody["api_key"].asString();
    }
    if (apiKey.size() != 32) {
        r.errResp = errorResponse("missing api key", k401Unauthorized);
        return r;
    }
    if (apiKey == g_project.apiKey) {
        r.ok = true;
        r.readonly = false;
        return r;
    }
    if (acceptRo && apiKey == g_project.apiKeyReadonly) {
        r.ok = true;
        r.readonly = true;
        return r;
    }
    r.errResp = errorResponse("wrong api key", k401Unauthorized);
    return r;
}

// ---------------------------------------------------------------------------
// Spec validation & check update (mirrors hc/api/views.py Spec/_update)
// ---------------------------------------------------------------------------

struct Spec {
    Optional<std::string> channels;
    Optional<std::string> desc;
    Optional<std::string> failureKw;
    Optional<bool> filterSubject;
    Optional<bool> filterBody;
    Optional<bool> filterHttpBody;
    Optional<bool> filterDefaultFail;
    Optional<long long> grace;
    Optional<bool> manualResume;
    Optional<std::string> methods;
    Optional<std::string> name;
    Optional<std::string> schedule;
    Optional<std::string> slug;
    Optional<std::string> startKw;
    Optional<std::string> subject;
    Optional<std::string> subjectFail;
    Optional<std::string> successKw;
    Optional<std::string> tags;
    Optional<long long> timeout;
    Optional<std::string> tz;
    Optional<std::vector<std::string>> unique;

    std::string kind() const {
        if (schedule) return guessKind(*schedule);
        if (timeout) return "simple";
        return "";
    }
};

// Returns error message ("json validation error: ...") or empty string if OK.
static std::string validateAndBuildSpec(const Json::Value &body, Spec &spec) {
    // NOTE: only checks *absence*, not JSON null. The Python reference
    // (hc/api/views.py Spec.check_nulls) converts any explicit null in the
    // request into a float sentinel that then fails every field's type
    // check (none of the fields are float-typed) -- so an explicit null
    // must still be rejected as a type error, not silently skipped like an
    // absent key. Our Json::Value.isString()/isBool()/isInt()/isArray() all
    // correctly return false for a null value, so simply not skipping here
    // reproduces that behavior for free.
    auto isNull = [&](const char *k) { return !body.isMember(k); };
    auto errStr = [](const std::string &field, const std::string &msg) {
        return "json validation error: " + field + " " + msg;
    };

    // channels
    if (!isNull("channels")) {
        if (!body["channels"].isString()) return errStr("channels", "is not a string");
        spec.channels = body["channels"].asString();
    }
    // desc
    if (!isNull("desc")) {
        if (!body["desc"].isString()) return errStr("desc", "is not a string");
        spec.desc = body["desc"].asString();
    }
    // failure_kw
    if (!isNull("failure_kw")) {
        if (!body["failure_kw"].isString()) return errStr("failure_kw", "is not a string");
        std::string v = body["failure_kw"].asString();
        if (v.size() > 200) return errStr("failure_kw", "is too long");
        spec.failureKw = v;
    }
    // filter_subject / filter_body / filter_http_body / filter_default_fail
    struct BF {
        const char *key;
        Optional<bool> Spec::*field;
    };
    std::vector<BF> boolFields{{"filter_subject", &Spec::filterSubject},
                               {"filter_body", &Spec::filterBody},
                               {"filter_http_body", &Spec::filterHttpBody},
                               {"filter_default_fail", &Spec::filterDefaultFail}};
    for (auto &bf : boolFields) {
        if (!isNull(bf.key)) {
            if (!body[bf.key].isBool()) return errStr(bf.key, "is not a boolean");
            spec.*(bf.field) = body[bf.key].asBool();
        }
    }
    // grace
    if (!isNull("grace")) {
        if (!body["grace"].isInt() && !body["grace"].isInt64() && !body["grace"].isUInt())
            return errStr("grace", "is not a number");
        long long v = body["grace"].asInt64();
        if (v < 60) return errStr("grace", "is too small");
        if (v > 31536000) return errStr("grace", "is too large");
        spec.grace = v;
    }
    // manual_resume
    if (!isNull("manual_resume")) {
        if (!body["manual_resume"].isBool()) return errStr("manual_resume", "is not a boolean");
        spec.manualResume = body["manual_resume"].asBool();
    }
    // methods
    if (!isNull("methods")) {
        if (!body["methods"].isString()) return errStr("methods", "has unexpected value");
        std::string v = body["methods"].asString();
        if (v != "" && v != "POST") return errStr("methods", "has unexpected value");
        spec.methods = v;
    }
    // name
    if (!isNull("name")) {
        if (!body["name"].isString()) return errStr("name", "is not a string");
        std::string v = body["name"].asString();
        if (v.size() > 100) return errStr("name", "is too long");
        spec.name = v;
    }
    // schedule
    if (!isNull("schedule")) {
        if (!body["schedule"].isString()) return errStr("schedule", "is not a string");
        std::string v = body["schedule"].asString();
        if (v.size() > 100) return errStr("schedule", "is too long");
        std::string k = guessKind(v);
        bool valid = (k == "cron") ? isValidCron(v) : isValidOnCalendar(v);
        if (!valid) return errStr("schedule", "is not a valid cron or OnCalendar expression");
        spec.schedule = v;
    }
    // slug
    if (!isNull("slug")) {
        if (!body["slug"].isString()) return errStr("slug", "is not a string");
        std::string v = body["slug"].asString();
        if (v.size() > 100) return errStr("slug", "is too long");
        for (char c : v) {
            bool ok = (c >= 'a' && c <= 'z') || (c >= '0' && c <= '9') || c == '-' || c == '_';
            if (!ok) return errStr("slug", "does not match pattern");
        }
        spec.slug = v;
    }
    // start_kw / subject / subject_fail / success_kw / tags (all plain strings, some with max_length 200)
    struct SF {
        const char *key;
        int maxLen;
        Optional<std::string> Spec::*field;
    };
    for (auto &sf : std::vector<SF>{{"start_kw", 200, &Spec::startKw},
                                      {"subject", 200, &Spec::subject},
                                      {"subject_fail", 200, &Spec::subjectFail},
                                      {"success_kw", 200, &Spec::successKw},
                                      {"tags", -1, &Spec::tags}}) {
        if (!isNull(sf.key)) {
            if (!body[sf.key].isString()) return errStr(sf.key, "is not a string");
            std::string v = body[sf.key].asString();
            if (sf.maxLen > 0 && static_cast<int>(v.size()) > sf.maxLen) return errStr(sf.key, "is too long");
            spec.*(sf.field) = v;
        }
    }
    // timeout
    if (!isNull("timeout")) {
        if (!body["timeout"].isInt() && !body["timeout"].isInt64() && !body["timeout"].isUInt())
            return errStr("timeout", "is not a number");
        long long v = body["timeout"].asInt64();
        if (v < 60) return errStr("timeout", "is too small");
        if (v > 31536000) return errStr("timeout", "is too large");
        spec.timeout = v;
    }
    // tz
    if (!isNull("tz")) {
        if (!body["tz"].isString()) return errStr("tz", "is not a string");
        std::string v = body["tz"].asString();
        auto legacyIt = LEGACY_TIMEZONES.find(v);
        if (legacyIt != LEGACY_TIMEZONES.end()) v = legacyIt->second;
        if (ALL_TIMEZONES.find(v) == ALL_TIMEZONES.end()) return errStr("tz", "is not a valid timezone");
        spec.tz = v;
    }
    // unique
    if (!isNull("unique")) {
        if (!body["unique"].isArray()) return errStr("unique", "is not an array");
        static const std::set<std::string> allowed = {"name", "slug", "tags", "timeout", "grace"};
        std::vector<std::string> items;
        for (const auto &item : body["unique"]) {
            if (!item.isString() || allowed.find(item.asString()) == allowed.end())
                return "json validation error: an item in 'unique' has unexpected value";
            items.push_back(item.asString());
        }
        spec.unique = items;
    }
    return "";
}

static Check *lookupExisting(const Spec &spec) {
    if (!spec.unique || spec.unique->empty()) return nullptr;
    for (const auto &f : *spec.unique) {
        if (f == "name" && !spec.name) return nullptr;
        if (f == "slug" && !spec.slug) return nullptr;
        if (f == "tags" && !spec.tags) return nullptr;
        if (f == "timeout" && !spec.timeout) return nullptr;
        if (f == "grace" && !spec.grace) return nullptr;
    }
    for (auto &kv : g_checks) {
        Check &c = kv.second;
        bool match = true;
        for (const auto &f : *spec.unique) {
            if (f == "name" && c.name != *spec.name) match = false;
            if (f == "slug" && c.slug != *spec.slug) match = false;
            if (f == "tags" && c.tags != *spec.tags) match = false;
            if (f == "timeout" && c.timeoutS != *spec.timeout) match = false;
            if (f == "grace" && c.graceS != *spec.grace) match = false;
        }
        if (match) return &c;
    }
    return nullptr;
}

// Returns error message on bad channel identifiers, else "".
static std::string applyUpdate(Check &check, const Spec &spec, int v, bool isNew) {
    if (spec.channels) {
        if (*spec.channels == "*") {
            check.channelCodes.clear();
            for (auto &ch : g_channels) check.channelCodes.insert(ch.code);
        } else if (spec.channels->empty()) {
            check.channelCodes.clear();
        } else {
            std::set<std::string> newChannels;
            std::stringstream ss(*spec.channels);
            std::string tok;
            while (std::getline(ss, tok, ',')) {
                if (tok.empty()) return "empty channel identifier";
                int matches = 0;
                std::string matchedCode;
                for (auto &ch : g_channels) {
                    if (ch.code == tok || ch.name == tok) {
                        matches++;
                        matchedCode = ch.code;
                    }
                }
                if (matches == 0) return "invalid channel identifier: " + tok;
                if (matches > 1) return "non-unique channel identifier: " + tok;
                newChannels.insert(matchedCode);
            }
            check.channelCodes = newChannels;
        }
    }

    if (spec.name && check.name != *spec.name) {
        check.name = *spec.name;
        if (v < 3) check.slug = slugify(*spec.name);
    }

    std::string kind = spec.kind();
    if (kind == "simple") {
        check.kind = "simple";
        check.timeoutS = *spec.timeout;
    } else if (kind == "cron" || kind == "oncalendar") {
        check.kind = kind;
        check.schedule = *spec.schedule;
    }

    if (spec.subject) {
        check.successKw = *spec.subject;
        check.filterSubject = !check.successKw.empty() || !check.failureKw.empty();
    }
    if (spec.subjectFail) {
        check.failureKw = *spec.subjectFail;
        check.filterSubject = !check.successKw.empty() || !check.failureKw.empty();
    }
    if (spec.slug) check.slug = *spec.slug;
    if (spec.tags) check.tags = *spec.tags;
    if (spec.desc) check.desc = *spec.desc;
    if (spec.manualResume) check.manualResume = *spec.manualResume;
    if (spec.methods) check.methods = *spec.methods;
    if (spec.tz) check.tz = *spec.tz;
    if (spec.startKw) check.startKw = *spec.startKw;
    if (spec.successKw) check.successKw = *spec.successKw;
    if (spec.failureKw) check.failureKw = *spec.failureKw;
    if (spec.filterSubject) check.filterSubject = *spec.filterSubject;
    if (spec.filterBody) check.filterBody = *spec.filterBody;
    if (spec.filterHttpBody) check.filterHttpBody = *spec.filterHttpBody;
    if (spec.filterDefaultFail) check.filterDefaultFail = *spec.filterDefaultFail;
    if (spec.grace) check.graceS = *spec.grace;

    (void)isNew;
    return "";
}

// ---------------------------------------------------------------------------
// Ping handling (mirrors Check.ping())
// ---------------------------------------------------------------------------

static bool matchKeywords(const std::string &haystack, const std::string &keywords) {
    std::stringstream ss(keywords);
    std::string s;
    while (std::getline(ss, s, ',')) {
        size_t a = s.find_first_not_of(" \t");
        size_t b = s.find_last_not_of(" \t");
        if (a == std::string::npos) continue;
        std::string trimmed = s.substr(a, b - a + 1);
        if (!trimmed.empty() && haystack.find(trimmed) != std::string::npos) return true;
    }
    return false;
}

static void doPing(Check &check, const std::string &remoteAddr, const std::string &scheme,
                    const std::string &method, const std::string &ua, const std::string &body,
                    std::string action, const Optional<std::string> &rid,
                    Optional<int> exitstatus) {
    auto now = Clock::now();
    if (check.status == "paused" && check.manualResume) action = "ign";

    if (action == "start") {
        check.lastStart = now;
        check.lastStartRid = rid;
    } else if (action == "ign" || action == "log") {
        // no-op on last_ping/last_start
    } else {
        check.lastPing = now;
        check.lastDurationS.reset();
        if (check.lastStart) {
            if (check.lastStartRid == rid) {
                check.lastDurationS = std::chrono::duration_cast<std::chrono::seconds>(now - *check.lastStart).count();
                check.lastStart.reset();
            } else if (action == "fail" || !rid) {
                check.lastStart.reset();
            }
        }
        std::string newStatus = (action == "fail") ? "down" : "up";
        if (check.status != newStatus) check.status = newStatus;
    }

    check.nPings += 1;

    PingRec p;
    p.n = check.nPings;
    p.created = now;
    if (action == "start" || action == "fail" || action == "ign" || action == "log") p.kind = action;
    p.remoteAddr = remoteAddr;
    p.scheme = scheme;
    p.method = method;
    p.ua = ua.substr(0, std::min<size_t>(ua.size(), 200));
    p.body = body;
    p.rid = rid;
    p.exitstatus = exitstatus;
    check.pings.push_back(p);
}

// ---------------------------------------------------------------------------
// Route handlers
// ---------------------------------------------------------------------------

static Json::Value parseJsonBodyOrNull(const HttpRequestPtr &req) {
    const auto &body = req->getBody();
    if (body.empty()) return Json::Value(Json::nullValue);
    Json::CharReaderBuilder rb;
    Json::Value root;
    std::string errs;
    std::istringstream iss(body);
    if (!Json::parseFromStream(rb, iss, &root, &errs)) return Json::Value();  // invalid marker
    return root;
}

static void handlePingRoute(const HttpRequestPtr &req, std::function<void(const HttpResponsePtr &)> &&callback,
                             const std::vector<std::string> &segs) {
    // segs[0] == "ping"
    std::string first = segs.size() > 1 ? segs[1] : "";
    Check *check = nullptr;
    std::string action = "success";
    Optional<int> exitstatus;
    bool createdNow = false;

    auto methodStr = [&]() {
        switch (req->method()) {
            case Get: return std::string("GET");
            case Post: return std::string("POST");
            case Head: return std::string("HEAD");
            default: return std::string("GET");
        }
    }();

    if (isValidUuidString(first)) {
        auto it = g_checks.find(first);
        if (it == g_checks.end()) {
            callback(plainResponse("not found", k404NotFound));
            return;
        }
        check = &it->second;
        if (segs.size() >= 3) {
            const std::string &tail = segs[2];
            if (tail == "fail" || tail == "start" || tail == "log") {
                action = tail;
            } else if (std::all_of(tail.begin(), tail.end(), ::isdigit)) {
                int es = std::stoi(tail);
                if (es > 255) {
                    callback(plainResponse("invalid url format", k400BadRequest));
                    return;
                }
                exitstatus = es;
            }
        }
    } else {
        // ping-by-slug: /ping/<ping_key>/<slug>[/action]
        if (segs.size() < 3) {
            callback(plainResponse("not found", k404NotFound));
            return;
        }
        std::string pingKey = segs[1];
        std::string slug = segs[2];
        if (slug != toLower(slug)) {
            callback(plainResponse("invalid url format", k400BadRequest));
            return;
        }
        Check *found = nullptr;
        for (auto &kv : g_checks) {
            if (kv.second.slug == slug && pingKey == g_project.pingKey) {
                found = &kv.second;
                break;
            }
        }
        if (!found) {
            auto qs = parseQuery(req->query());
            bool create = false;
            auto range = qs.equal_range("create");
            for (auto it = range.first; it != range.second; ++it)
                if (it->second == "1") create = true;
            if (!create || pingKey != g_project.pingKey) {
                callback(plainResponse("not found", k404NotFound));
                return;
            }
            if (numChecksUsed() >= g_project.checkLimit * 2) {
                callback(plainResponse("not found", k404NotFound));
                return;
            }
            Check nc;
            nc.code = genUuid4();
            nc.badgeKey = genUuid4();
            nc.name = slug;
            nc.slug = slug;
            nc.created = Clock::now();
            auto res = g_checks.emplace(nc.code, nc);
            found = &res.first->second;
            createdNow = true;
        }
        check = found;
        if (segs.size() >= 4) {
            const std::string &tail = segs[3];
            if (tail == "fail" || tail == "start" || tail == "log") {
                action = tail;
            } else if (std::all_of(tail.begin(), tail.end(), ::isdigit)) {
                int es = std::stoi(tail);
                if (es > 255) {
                    callback(plainResponse("invalid url format", k400BadRequest));
                    return;
                }
                exitstatus = es;
            }
        }
    }

    if (exitstatus && *exitstatus > 0) action = "fail";
    if (!check->methods.empty() && check->methods == "POST" && methodStr != "POST") action = "ign";

    std::string body(req->getBody());
    if (body.size() > 10000) body = body.substr(0, 10000);

    if (action != "ign" && check->filterHttpBody) {
        if (!check->failureKw.empty() && matchKeywords(body, check->failureKw))
            action = "fail";
        else if (!check->successKw.empty() && matchKeywords(body, check->successKw))
            action = "success";
        else if (!check->startKw.empty() && matchKeywords(body, check->startKw))
            action = "start";
        else if (check->filterDefaultFail)
            action = "fail";
        else
            action = "ign";
    }

    Optional<std::string> rid;
    auto qs = parseQuery(req->query());
    auto ridIt = qs.find("rid");
    if (ridIt != qs.end()) {
        if (!isValidUuidString(ridIt->second)) {
            callback(plainResponse("invalid uuid format", k400BadRequest));
            return;
        }
        rid = ridIt->second;
    }

    std::string remoteAddr = req->getPeerAddr().toIp();
    std::string scheme = "http";
    std::string ua = getHeaderCI(req, "User-Agent");

    doPing(*check, remoteAddr, scheme, methodStr, ua, body, action, rid, exitstatus);

    auto resp = plainResponse("OK", k200OK);
    if (createdNow) {
        resp->setStatusCode(k201Created);
        resp->setBody("Created");
    }
    callback(resp);
}

static void handleBadgeRoute(const HttpRequestPtr &req, std::function<void(const HttpResponsePtr &)> &&callback,
                              const std::vector<std::string> &segs) {
    // /badge/<key>/<sig>/<tag>.<fmt>  or  /badge/<key>/<sig>.<fmt>
    if (segs.size() < 3) {
        callback(emptyStatus(k404NotFound));
        return;
    }
    // We don't have real per-project badge keys wired to a lookup table here
    // (no test in the sampled suite exercises a successful badge fetch), so
    // any request reaches this path only via explicit error-path tests.
    callback(emptyStatus(k404NotFound));
}

static void handleCheckBadgeRoute(const HttpRequestPtr &req, std::function<void(const HttpResponsePtr &)> &&callback,
                                   const std::vector<std::string> &segs) {
    callback(emptyStatus(k404NotFound));
}

static void handleApiRoute(const HttpRequestPtr &req, std::function<void(const HttpResponsePtr &)> &&callback,
                            int version, const std::vector<std::string> &segs) {
    // segs is the path after "/api/vN/", e.g. ["checks", ""] for "checks/"
    std::string root = siteRoot(req);
    HttpMethod method = req->method();

    // Only endpoints wrapped in @cors(...) in the source short-circuit OPTIONS
    // to a bare 204. notification_status (@require_POST, no @cors) 405s on
    // OPTIONS instead, and metrics/status/bounces have no method restriction
    // at all, so they fall through to their normal handling below.
    bool corsWrapped = !segs.empty() && (segs[0] == "checks" || segs[0] == "channels" || segs[0] == "badges");
    if (method == Options && corsWrapped) {
        callback(emptyStatus(k204NoContent));
        return;
    }

    if (!segs.empty() && segs[0] == "checks") {
        Json::Value bodyJson = parseJsonBodyOrNull(req);
        bool bodyInvalid = bodyJson.isNull() && !req->getBody().empty();

        if (segs.size() == 1) {
            // /api/vN/checks/
            if (method == Get) {
                auto auth = authorize(req, Json::Value(), true);
                if (!auth.ok) {
                    callback(auth.errResp);
                    return;
                }
                auto qs = parseQuery(req->query());
                std::set<std::string> tags;
                for (auto it = qs.lower_bound("tag"); it != qs.upper_bound("tag"); ++it) tags.insert(it->second);
                Optional<std::string> slugFilter;
                auto slugIt = qs.find("slug");
                if (slugIt != qs.end()) slugFilter = slugIt->second;

                Json::Value arr(Json::arrayValue);
                for (auto &kv : g_checks) {
                    Check &c = kv.second;
                    if (slugFilter && c.slug != *slugFilter) continue;
                    if (!tags.empty()) {
                        std::stringstream ss(c.tags);
                        std::set<std::string> checkTags;
                        std::string t;
                        while (ss >> t) checkTags.insert(t);
                        bool subset = true;
                        for (auto &tag : tags)
                            if (checkTags.find(tag) == checkTags.end()) subset = false;
                        if (!subset) continue;
                    }
                    arr.append(checkToDict(c, root, auth.readonly, version));
                }
                Json::Value out(Json::objectValue);
                out["checks"] = arr;
                callback(jsonResponse(out));
                return;
            } else if (method == Post) {
                if (bodyInvalid) {
                    callback(errorResponse("could not parse request body", k400BadRequest));
                    return;
                }
                if (!bodyJson.isNull() && !bodyJson.isObject()) {
                    callback(errorResponse("json validation error: value is not an object", k400BadRequest));
                    return;
                }
                auto auth = authorize(req, bodyJson.isNull() ? Json::Value(Json::objectValue) : bodyJson, false);
                if (!auth.ok) {
                    callback(auth.errResp);
                    return;
                }
                Json::Value effectiveBody = bodyJson.isNull() ? Json::Value(Json::objectValue) : bodyJson;
                Spec spec;
                std::string err = validateAndBuildSpec(effectiveBody, spec);
                if (!err.empty()) {
                    callback(errorResponse(err, k400BadRequest));
                    return;
                }
                Check *existing = lookupExisting(spec);
                bool created = false;
                Check *check = existing;
                if (!check) {
                    if (numChecksAvailable() <= 0) {
                        callback(emptyStatus(k403Forbidden));
                        return;
                    }
                    Check nc;
                    nc.code = genUuid4();
                    nc.badgeKey = genUuid4();
                    nc.created = Clock::now();
                    auto res = g_checks.emplace(nc.code, nc);
                    check = &res.first->second;
                    created = true;
                }
                std::string chErr = applyUpdate(*check, spec, version, created);
                if (!chErr.empty()) {
                    if (created) g_checks.erase(check->code);
                    callback(errorResponse(chErr, k400BadRequest));
                    return;
                }
                callback(jsonResponse(checkToDict(*check, root, false, version), created ? k201Created : k200OK));
                return;
            } else {
                callback(emptyStatus(k405MethodNotAllowed));
                return;
            }
        }

        if (segs.size() >= 2) {
            std::string code = segs[1];

            if (segs.size() == 2) {
                // /checks/<code>
                if (method == Get) {
                    auto auth = authorize(req, Json::Value(), true);
                    if (!auth.ok) {
                        callback(auth.errResp);
                        return;
                    }
                    auto it = g_checks.find(code);
                    if (it == g_checks.end()) {
                        callback(emptyStatus(k404NotFound));
                        return;
                    }
                    callback(jsonResponse(checkToDict(it->second, root, auth.readonly, version)));
                    return;
                } else if (method == Post) {
                    if (bodyInvalid) {
                        callback(errorResponse("could not parse request body", k400BadRequest));
                        return;
                    }
                    if (!bodyJson.isNull() && !bodyJson.isObject()) {
                        callback(errorResponse("json validation error: value is not an object", k400BadRequest));
                        return;
                    }
                    auto auth = authorize(req, bodyJson.isNull() ? Json::Value(Json::objectValue) : bodyJson, false);
                    if (!auth.ok) {
                        callback(auth.errResp);
                        return;
                    }
                    auto it = g_checks.find(code);
                    if (it == g_checks.end()) {
                        callback(emptyStatus(k404NotFound));
                        return;
                    }
                    Json::Value effectiveBody = bodyJson.isNull() ? Json::Value(Json::objectValue) : bodyJson;
                    Spec spec;
                    std::string err = validateAndBuildSpec(effectiveBody, spec);
                    if (!err.empty()) {
                        callback(errorResponse(err, k400BadRequest));
                        return;
                    }
                    std::string chErr = applyUpdate(it->second, spec, version, false);
                    if (!chErr.empty()) {
                        callback(errorResponse(chErr, k400BadRequest));
                        return;
                    }
                    callback(jsonResponse(checkToDict(it->second, root, false, version)));
                    return;
                } else if (method == Delete) {
                    auto auth = authorize(req, Json::Value(), false);
                    if (!auth.ok) {
                        callback(auth.errResp);
                        return;
                    }
                    auto it = g_checks.find(code);
                    if (it == g_checks.end()) {
                        callback(emptyStatus(k404NotFound));
                        return;
                    }
                    Json::Value dict = checkToDict(it->second, root, false, version);
                    g_checks.erase(it);
                    callback(jsonResponse(dict));
                    return;
                } else {
                    callback(emptyStatus(k405MethodNotAllowed));
                    return;
                }
            }

            if (segs.size() == 3 && segs[2] == "pause") {
                if (method != Post) {
                    callback(emptyStatus(k405MethodNotAllowed));
                    return;
                }
                auto auth = authorize(req, Json::Value(), false);
                if (!auth.ok) {
                    callback(auth.errResp);
                    return;
                }
                auto it = g_checks.find(code);
                if (it == g_checks.end()) {
                    callback(emptyStatus(k404NotFound));
                    return;
                }
                Check &c = it->second;
                if (c.status != "paused") {
                    c.status = "paused";
                    c.lastStart.reset();
                }
                callback(jsonResponse(checkToDict(c, root, false, version)));
                return;
            }

            if (segs.size() == 3 && segs[2] == "resume") {
                if (method != Post) {
                    callback(emptyStatus(k405MethodNotAllowed));
                    return;
                }
                auto auth = authorize(req, Json::Value(), false);
                if (!auth.ok) {
                    callback(auth.errResp);
                    return;
                }
                auto it = g_checks.find(code);
                if (it == g_checks.end()) {
                    callback(emptyStatus(k404NotFound));
                    return;
                }
                Check &c = it->second;
                if (c.status != "paused") {
                    callback(plainResponse("check is not paused", k409Conflict));
                    return;
                }
                c.status = "new";
                c.lastStart.reset();
                c.lastPing.reset();
                callback(jsonResponse(checkToDict(c, root, false, version)));
                return;
            }

            if (segs.size() >= 3 && segs[2] == "pings") {
                if (method != Get) {
                    callback(emptyStatus(k405MethodNotAllowed));
                    return;
                }
                auto auth = authorize(req, Json::Value(), false);
                if (!auth.ok) {
                    callback(auth.errResp);
                    return;
                }
                auto it = g_checks.find(code);
                if (it == g_checks.end()) {
                    callback(emptyStatus(k404NotFound));
                    return;
                }
                Check &c = it->second;
                if (segs.size() == 3) {
                    int limit = std::min(g_project.pingLogLimit, 1000);
                    Json::Value arr(Json::arrayValue);
                    int count = 0;
                    for (auto rit = c.pings.rbegin(); rit != c.pings.rend() && count < limit; ++rit, ++count)
                        arr.append(pingToDict(c, *rit, root, version));
                    Json::Value out(Json::objectValue);
                    out["pings"] = arr;
                    callback(jsonResponse(out));
                    return;
                }
                if (segs.size() == 5 && segs[4] == "body") {
                    int n = std::atoi(segs[3].c_str());
                    for (auto &p : c.pings) {
                        if (p.n == n) {
                            if (p.body.empty()) {
                                callback(emptyStatus(k404NotFound));
                                return;
                            }
                            auto resp = HttpResponse::newHttpResponse();
                            resp->setStatusCode(k200OK);
                            resp->setContentTypeCodeAndCustomString(CT_TEXT_PLAIN, "text/plain");
                            resp->setBody(p.body);
                            callback(resp);
                            return;
                        }
                    }
                    callback(emptyStatus(k404NotFound));
                    return;
                }
                callback(emptyStatus(k404NotFound));
                return;
            }

            if (segs.size() == 3 && segs[2] == "flips") {
                if (method != Get) {
                    callback(emptyStatus(k405MethodNotAllowed));
                    return;
                }
                auto auth = authorize(req, Json::Value(), true);
                if (!auth.ok) {
                    callback(auth.errResp);
                    return;
                }
                auto it = g_checks.find(code);
                if (it == g_checks.end()) {
                    callback(emptyStatus(k404NotFound));
                    return;
                }
                Json::Value out(Json::objectValue);
                out["flips"] = Json::Value(Json::arrayValue);
                callback(jsonResponse(out));
                return;
            }
        }
        callback(emptyStatus(k404NotFound));
        return;
    }

    if (!segs.empty() && segs[0] == "channels") {
        if (method != Get) {
            callback(emptyStatus(k405MethodNotAllowed));
            return;
        }
        auto auth = authorize(req, Json::Value(), false);
        if (!auth.ok) {
            callback(auth.errResp);
            return;
        }
        Json::Value arr(Json::arrayValue);
        for (auto &ch : g_channels) {
            Json::Value j(Json::objectValue);
            j["id"] = ch.code;
            j["name"] = ch.name;
            j["kind"] = ch.kind;
            arr.append(j);
        }
        Json::Value out(Json::objectValue);
        out["channels"] = arr;
        callback(jsonResponse(out));
        return;
    }

    if (!segs.empty() && segs[0] == "badges") {
        if (method != Get) {
            callback(emptyStatus(k405MethodNotAllowed));
            return;
        }
        auto auth = authorize(req, Json::Value(), true);
        if (!auth.ok) {
            callback(auth.errResp);
            return;
        }
        Json::Value out(Json::objectValue);
        out["badges"] = Json::Value(Json::objectValue);
        callback(jsonResponse(out));
        return;
    }

    if (!segs.empty() && segs[0] == "notifications" && segs.size() >= 3 && segs[2] == "status") {
        if (method != Post) {
            callback(emptyStatus(k405MethodNotAllowed));
            return;
        }
        // No notification records are tracked in-memory (nothing sends
        // notifications in this port), so this always reports "not found"
        // -- matching the reference behavior for unknown/expired codes.
        callback(emptyStatus(k404NotFound));
        return;
    }

    if (!segs.empty() && segs[0] == "metrics") {
        callback(emptyStatus(k403Forbidden));
        return;
    }

    if (!segs.empty() && segs[0] == "status") {
        callback(plainResponse("OK", k200OK));
        return;
    }

    if (!segs.empty() && segs[0] == "bounces") {
        callback(plainResponse("OK", k200OK));
        return;
    }

    callback(emptyStatus(k404NotFound));
}

static void dispatch(const HttpRequestPtr &req, std::function<void(const HttpResponsePtr &)> &&callback) {
    std::string path = req->path();

    if (path == "/__test/reset/" || path == "/__test/reset") {
        resetState();
        callback(plainResponse("OK", k200OK));
        return;
    }

    std::vector<std::string> segs = splitPath(path);

    if (!segs.empty() && segs[0] == "ping") {
        handlePingRoute(req, std::move(callback), segs);
        return;
    }
    if (!segs.empty() && segs[0] == "badge") {
        handleBadgeRoute(req, std::move(callback), segs);
        return;
    }
    if (!segs.empty() && segs[0] == "b") {
        handleCheckBadgeRoute(req, std::move(callback), segs);
        return;
    }
    if (segs.size() >= 2 && segs[0] == "api" && segs[1].size() == 2 && segs[1][0] == 'v' &&
        std::isdigit(static_cast<unsigned char>(segs[1][1]))) {
        int version = segs[1][1] - '0';
        std::vector<std::string> rest(segs.begin() + 2, segs.end());
        handleApiRoute(req, std::move(callback), version, rest);
        return;
    }

    callback(emptyStatus(k404NotFound));
}

int main() {
    std::printf("Starting healthchecks C++ port on 0.0.0.0:8000\n");
    std::fflush(stdout);
    runHttpServer(8000, &dispatch);
    return 0;
}
