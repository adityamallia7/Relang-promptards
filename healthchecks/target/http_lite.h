// Minimal HTTP/1.1 server + request/response types mimicking the small
// subset of Drogon's API (HttpRequestPtr/HttpResponsePtr, HttpMethod,
// HttpStatusCode, CT_* constants) actually used by main.cpp. This removes
// the dependency on Drogon (and, transitively, on Drogon's cmake config
// requiring MySQL/PostgreSQL/Redis/Brotli dev packages) entirely -- the
// program builds with nothing but a C++11 compiler and platform sockets.
//
// Single-threaded, blocking accept loop. That's plenty for a test harness
// that replays HTTP requests sequentially; it is not meant for production
// traffic.
#pragma once
#include <cstdio>
#include <cstring>
#include <functional>
#include <memory>
#include <sstream>
#include <string>
#include <vector>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
typedef SOCKET SocketFd;
#define CLOSESOCK closesocket
#else
#include <arpa/inet.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>
typedef int SocketFd;
#define CLOSESOCK close
#endif

enum HttpMethod { Get, Post, Head, Put, Delete, Options, Patch, InvalidMethod };

enum HttpStatusCode {
    k200OK = 200,
    k201Created = 201,
    k204NoContent = 204,
    k400BadRequest = 400,
    k401Unauthorized = 401,
    k403Forbidden = 403,
    k404NotFound = 404,
    k405MethodNotAllowed = 405,
    k409Conflict = 409,
    k503ServiceUnavailable = 503,
};

enum ContentType { CT_APPLICATION_JSON, CT_TEXT_HTML, CT_TEXT_PLAIN };

struct PeerAddrShim {
    std::string ip;
    std::string toIp() const { return ip; }
};

class HttpRequest {
public:
    std::string pathVal;
    std::string queryVal;
    std::string bodyVal;
    HttpMethod methodVal = Get;
    std::vector<std::pair<std::string, std::string> > headersVal;
    PeerAddrShim peer;

    const std::string &path() const { return pathVal; }
    const std::string &query() const { return queryVal; }
    const std::string &getBody() const { return bodyVal; }
    HttpMethod method() const { return methodVal; }
    const std::vector<std::pair<std::string, std::string> > &getHeaders() const { return headersVal; }
    PeerAddrShim getPeerAddr() const { return peer; }
};
typedef std::shared_ptr<HttpRequest> HttpRequestPtr;

class HttpResponse {
public:
    int statusCode = 200;
    std::string contentType = "text/html; charset=utf-8";
    std::string bodyVal;

    static std::shared_ptr<HttpResponse> newHttpResponse() { return std::make_shared<HttpResponse>(); }
    void setStatusCode(HttpStatusCode c) { statusCode = static_cast<int>(c); }
    void setContentTypeCodeAndCustomString(ContentType, const std::string &s) { contentType = s; }
    void setBody(const std::string &b) { bodyVal = b; }
};
typedef std::shared_ptr<HttpResponse> HttpResponsePtr;

namespace http_lite_detail {

inline std::string toLowerStr(std::string s) {
    for (size_t i = 0; i < s.size(); i++) s[i] = static_cast<char>(std::tolower(static_cast<unsigned char>(s[i])));
    return s;
}

inline HttpMethod parseMethod(const std::string &m) {
    if (m == "GET") return Get;
    if (m == "POST") return Post;
    if (m == "HEAD") return Head;
    if (m == "PUT") return Put;
    if (m == "DELETE") return Delete;
    if (m == "OPTIONS") return Options;
    if (m == "PATCH") return Patch;
    return InvalidMethod;
}

inline const char *reasonPhrase(int code) {
    switch (code) {
        case 200: return "OK";
        case 201: return "Created";
        case 204: return "No Content";
        case 400: return "Bad Request";
        case 401: return "Unauthorized";
        case 403: return "Forbidden";
        case 404: return "Not Found";
        case 405: return "Method Not Allowed";
        case 409: return "Conflict";
        case 503: return "Service Unavailable";
        default: return "OK";
    }
}

// Reads exactly n bytes (or fewer at EOF) from the socket into out.
inline bool recvExact(SocketFd fd, char *buf, int n) {
    int got = 0;
    while (got < n) {
        int r = recv(fd, buf + got, n - got, 0);
        if (r <= 0) return false;
        got += r;
    }
    return true;
}

// Reads until the "\r\n\r\n" header terminator, returning the header block
// (without the terminator) and anything read past it (start of body).
inline bool readHeaderBlock(SocketFd fd, std::string &headerBlock, std::string &spillover) {
    std::string buf;
    char chunk[4096];
    while (true) {
        size_t pos = buf.find("\r\n\r\n");
        if (pos != std::string::npos) {
            headerBlock = buf.substr(0, pos);
            spillover = buf.substr(pos + 4);
            return true;
        }
        int r = recv(fd, chunk, sizeof(chunk), 0);
        if (r <= 0) return false;
        buf.append(chunk, r);
        if (buf.size() > 1 << 20) return false;  // guard against pathological input
    }
}

}  // namespace http_lite_detail

typedef std::function<void(const HttpRequestPtr &, std::function<void(const HttpResponsePtr &)> &&)> RequestHandler;

inline void runHttpServer(int port, const RequestHandler &handler) {
#ifdef _WIN32
    WSADATA wsaData;
    WSAStartup(MAKEWORD(2, 2), &wsaData);
#endif

    SocketFd listenFd = socket(AF_INET, SOCK_STREAM, 0);
    int opt = 1;
#ifdef _WIN32
    setsockopt(listenFd, SOL_SOCKET, SO_REUSEADDR, reinterpret_cast<const char *>(&opt), sizeof(opt));
#else
    setsockopt(listenFd, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));
#endif

    sockaddr_in addr;
    std::memset(&addr, 0, sizeof(addr));
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = INADDR_ANY;
    addr.sin_port = htons(static_cast<unsigned short>(port));

    if (bind(listenFd, reinterpret_cast<sockaddr *>(&addr), sizeof(addr)) != 0) {
        std::fprintf(stderr, "bind() failed on port %d\n", port);
        return;
    }
    listen(listenFd, 64);
    std::printf("Listening on 0.0.0.0:%d\n", port);
    std::fflush(stdout);

    while (true) {
        sockaddr_in clientAddr;
#ifdef _WIN32
        int clientLen = sizeof(clientAddr);
#else
        socklen_t clientLen = sizeof(clientAddr);
#endif
        SocketFd clientFd = accept(listenFd, reinterpret_cast<sockaddr *>(&clientAddr), &clientLen);
        if (clientFd < 0) continue;

        std::string headerBlock, spillover;
        if (!http_lite_detail::readHeaderBlock(clientFd, headerBlock, spillover)) {
            CLOSESOCK(clientFd);
            continue;
        }

        std::istringstream hs(headerBlock);
        std::string requestLine;
        std::getline(hs, requestLine);
        if (!requestLine.empty() && requestLine.back() == '\r') requestLine.pop_back();

        std::istringstream rl(requestLine);
        std::string methodStr, target, httpVersion;
        rl >> methodStr >> target >> httpVersion;

        auto req = std::make_shared<HttpRequest>();
        req->methodVal = http_lite_detail::parseMethod(methodStr);
        size_t qpos = target.find('?');
        if (qpos == std::string::npos) {
            req->pathVal = target;
        } else {
            req->pathVal = target.substr(0, qpos);
            req->queryVal = target.substr(qpos + 1);
        }
        // inet_ntoa (not inet_ntop) for compatibility with older Windows
        // toolchains/SDK headers that may not declare InetNtopA; this
        // program only ever handles IPv4 loopback traffic from the test
        // harness, so inet_ntoa's lack of IPv6 support is not a concern.
        req->peer.ip = inet_ntoa(clientAddr.sin_addr);

        long long contentLength = 0;
        std::string line;
        while (std::getline(hs, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            if (line.empty()) continue;
            size_t colon = line.find(':');
            if (colon == std::string::npos) continue;
            std::string key = line.substr(0, colon);
            size_t vstart = colon + 1;
            while (vstart < line.size() && line[vstart] == ' ') vstart++;
            std::string val = line.substr(vstart);
            req->headersVal.push_back(std::make_pair(key, val));
            if (http_lite_detail::toLowerStr(key) == "content-length") {
                contentLength = std::atoll(val.c_str());
            }
        }

        std::string body = spillover;
        if (static_cast<long long>(body.size()) < contentLength) {
            long long remaining = contentLength - static_cast<long long>(body.size());
            std::vector<char> extra(static_cast<size_t>(remaining));
            if (http_lite_detail::recvExact(clientFd, extra.data(), static_cast<int>(remaining))) {
                body.append(extra.data(), extra.size());
            }
        } else if (static_cast<long long>(body.size()) > contentLength) {
            body.resize(static_cast<size_t>(contentLength));
        }
        req->bodyVal = body;

        HttpResponsePtr respHolder;
        handler(req, [&](const HttpResponsePtr &r) { respHolder = r; });
        if (!respHolder) respHolder = HttpResponse::newHttpResponse();

        bool isHead = req->methodVal == Head;
        std::ostringstream out;
        out << "HTTP/1.1 " << respHolder->statusCode << " "
            << http_lite_detail::reasonPhrase(respHolder->statusCode) << "\r\n";
        out << "Content-Type: " << respHolder->contentType << "\r\n";
        out << "Content-Length: " << respHolder->bodyVal.size() << "\r\n";
        out << "Connection: close\r\n\r\n";
        if (!isHead) out << respHolder->bodyVal;

        std::string outStr = out.str();
        send(clientFd, outStr.data(), static_cast<int>(outStr.size()), 0);
        CLOSESOCK(clientFd);
    }
}
