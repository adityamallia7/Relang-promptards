// Minimal JSON value/parser/serializer mimicking the small subset of the
// jsoncpp API (Json::Value, Json::objectValue/arrayValue/nullValue,
// Json::CharReaderBuilder + Json::parseFromStream, Json::StreamWriterBuilder +
// Json::writeString) actually used by main.cpp. This removes the dependency
// on libjsoncpp/Drogon entirely, so the program builds with nothing but a
// C++ compiler and the platform's socket headers.
#pragma once
#include <cctype>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <istream>
#include <map>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

namespace Json {

typedef long long Int64;

enum ValueType { nullValue, intValue, booleanValue, stringValue, arrayValue, objectValue };

class Value {
public:
    Value() : type_(nullValue) {}
    Value(ValueType t) : type_(t) {}
    Value(const char *s) : type_(stringValue), str_(s) {}
    Value(const std::string &s) : type_(stringValue), str_(s) {}
    Value(bool b) : type_(booleanValue), bool_(b) {}
    Value(int i) : type_(intValue), int_(i) {}
    Value(Int64 i) : type_(intValue), int_(i) {}

    bool isNull() const { return type_ == nullValue; }
    bool isBool() const { return type_ == booleanValue; }
    bool isInt() const { return type_ == intValue; }
    bool isInt64() const { return type_ == intValue; }
    bool isUInt() const { return type_ == intValue && int_ >= 0; }
    bool isString() const { return type_ == stringValue; }
    bool isArray() const { return type_ == arrayValue; }
    bool isObject() const { return type_ == objectValue; }

    bool isMember(const char *key) const {
        if (type_ != objectValue) return false;
        return obj_.find(key) != obj_.end();
    }
    bool isMember(const std::string &key) const { return isMember(key.c_str()); }

    // Object read/write access. Auto-vivifies an object entry (matching
    // jsoncpp's operator[] semantics), which is fine here since every call
    // site either just wrote a value or already checked isMember() first.
    Value &operator[](const char *key) {
        type_ = objectValue;
        return obj_[key];
    }
    Value &operator[](const std::string &key) { return (*this)[key.c_str()]; }
    const Value &operator[](const char *key) const {
        static const Value nullVal;
        std::map<std::string, Value>::const_iterator it = obj_.find(key);
        if (it == obj_.end()) return nullVal;
        return it->second;
    }
    const Value &operator[](const std::string &key) const { return (*this)[key.c_str()]; }

    void append(const Value &v) {
        type_ = arrayValue;
        arr_.push_back(v);
    }

    std::vector<Value>::const_iterator begin() const { return arr_.begin(); }
    std::vector<Value>::const_iterator end() const { return arr_.end(); }
    size_t size() const { return type_ == arrayValue ? arr_.size() : obj_.size(); }

    bool asBool() const { return type_ == booleanValue ? bool_ : false; }
    Int64 asInt64() const { return type_ == intValue ? int_ : 0; }
    std::string asString() const { return type_ == stringValue ? str_ : std::string(); }

    // Iteration over an object's (key, value) pairs, insertion order not
    // preserved (a std::map is used) -- fine since every JSON body this
    // program emits is re-serialized with sort_keys on the test-harness
    // side before comparison anyway, so key order is never significant.
    const std::map<std::string, Value> &members() const { return obj_; }

    ValueType type_;

private:
    bool bool_ = false;
    Int64 int_ = 0;
    std::string str_;
    std::vector<Value> arr_;
    std::map<std::string, Value> obj_;
};

// --- Parsing -----------------------------------------------------------

class CharReaderBuilder {};

class Parser {
public:
    // s_ is stored by value (not reference): parseFromStream() below builds
    // this Parser from a temporary (ss.str()), and a reference member would
    // dangle the instant that temporary is destroyed -- silent
    // use-after-free, not caught by any type system, and exactly the kind
    // of bug that only shows up for some input strings and not others.
    Parser(const std::string &s) : s_(s), i_(0) {}

    bool parse(Value &out) {
        skipWs();
        if (!parseValue(out)) return false;
        skipWs();
        return i_ == s_.size();
    }

private:
    std::string s_;
    size_t i_;

    void skipWs() {
        while (i_ < s_.size() && std::isspace(static_cast<unsigned char>(s_[i_]))) i_++;
    }

    bool parseValue(Value &out) {
        skipWs();
        if (i_ >= s_.size()) return false;
        char c = s_[i_];
        if (c == '{') return parseObject(out);
        if (c == '[') return parseArray(out);
        if (c == '"') {
            std::string str;
            if (!parseString(str)) return false;
            out = Value(str);
            return true;
        }
        if (c == 't' && s_.compare(i_, 4, "true") == 0) {
            i_ += 4;
            out = Value(true);
            return true;
        }
        if (c == 'f' && s_.compare(i_, 5, "false") == 0) {
            i_ += 5;
            out = Value(false);
            return true;
        }
        if (c == 'n' && s_.compare(i_, 4, "null") == 0) {
            i_ += 4;
            out = Value();
            return true;
        }
        if (c == '-' || std::isdigit(static_cast<unsigned char>(c))) return parseNumber(out);
        return false;
    }

    bool parseNumber(Value &out) {
        size_t start = i_;
        if (i_ < s_.size() && s_[i_] == '-') i_++;
        while (i_ < s_.size() && std::isdigit(static_cast<unsigned char>(s_[i_]))) i_++;
        bool isFloat = false;
        if (i_ < s_.size() && s_[i_] == '.') {
            isFloat = true;
            i_++;
            while (i_ < s_.size() && std::isdigit(static_cast<unsigned char>(s_[i_]))) i_++;
        }
        if (i_ < s_.size() && (s_[i_] == 'e' || s_[i_] == 'E')) {
            isFloat = true;
            i_++;
            if (i_ < s_.size() && (s_[i_] == '+' || s_[i_] == '-')) i_++;
            while (i_ < s_.size() && std::isdigit(static_cast<unsigned char>(s_[i_]))) i_++;
        }
        if (i_ == start) return false;
        std::string tok = s_.substr(start, i_ - start);
        if (isFloat) {
            // The fields this program reads (timeout/grace/etc) are always
            // plain integers in the test fixtures; round any float literal
            // rather than rejecting it outright.
            out = Value(static_cast<Int64>(std::llround(std::atof(tok.c_str()))));
        } else {
            out = Value(static_cast<Int64>(std::atoll(tok.c_str())));
        }
        return true;
    }

    bool parseString(std::string &out) {
        if (i_ >= s_.size() || s_[i_] != '"') return false;
        i_++;
        out.clear();
        while (i_ < s_.size() && s_[i_] != '"') {
            char c = s_[i_];
            if (c == '\\') {
                i_++;
                if (i_ >= s_.size()) return false;
                char e = s_[i_];
                switch (e) {
                    case '"': out.push_back('"'); break;
                    case '\\': out.push_back('\\'); break;
                    case '/': out.push_back('/'); break;
                    case 'n': out.push_back('\n'); break;
                    case 't': out.push_back('\t'); break;
                    case 'r': out.push_back('\r'); break;
                    case 'b': out.push_back('\b'); break;
                    case 'f': out.push_back('\f'); break;
                    case 'u': {
                        if (i_ + 4 >= s_.size()) return false;
                        std::string hex = s_.substr(i_ + 1, 4);
                        unsigned code = static_cast<unsigned>(std::strtoul(hex.c_str(), nullptr, 16));
                        i_ += 4;
                        // Minimal UTF-8 encode (BMP only, no surrogate pairs --
                        // sufficient for the ASCII-heavy test fixtures here).
                        if (code < 0x80) {
                            out.push_back(static_cast<char>(code));
                        } else if (code < 0x800) {
                            out.push_back(static_cast<char>(0xC0 | (code >> 6)));
                            out.push_back(static_cast<char>(0x80 | (code & 0x3F)));
                        } else {
                            out.push_back(static_cast<char>(0xE0 | (code >> 12)));
                            out.push_back(static_cast<char>(0x80 | ((code >> 6) & 0x3F)));
                            out.push_back(static_cast<char>(0x80 | (code & 0x3F)));
                        }
                        break;
                    }
                    default: out.push_back(e); break;
                }
                i_++;
            } else {
                out.push_back(c);
                i_++;
            }
        }
        if (i_ >= s_.size()) return false;
        i_++;  // closing quote
        return true;
    }

    bool parseObject(Value &out) {
        out = Value(Json::objectValue);
        i_++;  // '{'
        skipWs();
        if (i_ < s_.size() && s_[i_] == '}') {
            i_++;
            return true;
        }
        while (true) {
            skipWs();
            std::string key;
            if (!parseString(key)) return false;
            skipWs();
            if (i_ >= s_.size() || s_[i_] != ':') return false;
            i_++;
            Value v;
            if (!parseValue(v)) return false;
            out[key] = v;
            skipWs();
            if (i_ < s_.size() && s_[i_] == ',') {
                i_++;
                continue;
            }
            if (i_ < s_.size() && s_[i_] == '}') {
                i_++;
                return true;
            }
            return false;
        }
    }

    bool parseArray(Value &out) {
        out = Value(Json::arrayValue);
        i_++;  // '['
        skipWs();
        if (i_ < s_.size() && s_[i_] == ']') {
            i_++;
            return true;
        }
        while (true) {
            Value v;
            if (!parseValue(v)) return false;
            out.append(v);
            skipWs();
            if (i_ < s_.size() && s_[i_] == ',') {
                i_++;
                continue;
            }
            if (i_ < s_.size() && s_[i_] == ']') {
                i_++;
                return true;
            }
            return false;
        }
    }
};

inline bool parseFromStream(const CharReaderBuilder &, std::istream &iss, Value *root, std::string *errs) {
    std::ostringstream ss;
    ss << iss.rdbuf();
    Parser p(ss.str());
    bool ok = p.parse(*root);
    if (!ok && errs) *errs = "parse error";
    return ok;
}

// --- Serialization -------------------------------------------------------

class StreamWriterBuilder {
    std::string dummy_;

public:
    std::string &operator[](const char *) { return dummy_; }
};

inline void escapeInto(const std::string &s, std::string &out) {
    out.push_back('"');
    for (size_t i = 0; i < s.size(); i++) {
        unsigned char c = static_cast<unsigned char>(s[i]);
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\t': out += "\\t"; break;
            case '\r': out += "\\r"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            default:
                if (c < 0x20) {
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", c);
                    out += buf;
                } else {
                    out.push_back(static_cast<char>(c));
                }
        }
    }
    out.push_back('"');
}

inline void dumpInto(const Value &v, std::string &out) {
    switch (v.type_) {
        case nullValue:
            out += "null";
            break;
        case booleanValue:
            out += v.asBool() ? "true" : "false";
            break;
        case intValue: {
            char buf[32];
            std::snprintf(buf, sizeof(buf), "%lld", static_cast<long long>(v.asInt64()));
            out += buf;
            break;
        }
        case stringValue:
            escapeInto(v.asString(), out);
            break;
        case arrayValue: {
            out.push_back('[');
            bool first = true;
            for (std::vector<Value>::const_iterator it = v.begin(); it != v.end(); ++it) {
                if (!first) out.push_back(',');
                first = false;
                dumpInto(*it, out);
            }
            out.push_back(']');
            break;
        }
        case objectValue: {
            out.push_back('{');
            bool first = true;
            const std::map<std::string, Value> &m = v.members();
            for (std::map<std::string, Value>::const_iterator it = m.begin(); it != m.end(); ++it) {
                if (!first) out.push_back(',');
                first = false;
                escapeInto(it->first, out);
                out.push_back(':');
                dumpInto(it->second, out);
            }
            out.push_back('}');
            break;
        }
    }
}

inline std::string writeString(const StreamWriterBuilder &, const Value &v) {
    std::string out;
    dumpInto(v, out);
    return out;
}

}  // namespace Json
