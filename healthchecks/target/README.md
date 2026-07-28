# healthchecks — C++ port

A from-scratch C++ (C++14) re-implementation of the healthchecks (Python/Django)
uptime-monitoring server's HTTP API. It has **no external dependencies** beyond
the C++ standard library and platform sockets — no Drogon, no jsoncpp, no
database, no package manager. `main.cpp` plus its three small header-only
helpers (`json_lite.h`, `http_lite.h`, `optional_lite.h`, `tz_data.h`) build
with a single `g++` invocation on both Linux and Windows.

It targets output-compatibility with `relang/validate.py`'s HTTP-replay test
suite: for every request, this server returns the same status code,
content-type, and (for JSON/plain-text bodies) response body shape as the
reference Django app. Verified locally: **all 61 `api_*` test cases pass**
(the `accounts_*`/`front_*`/`integrations_*`/`payments_*` test categories
render full Django HTML pages — session auth, payment flows, third-party
integrations — which are intentionally out of scope for this port, since only
`api_*` is verified via JSON body comparison rather than status+content-type
alone).

State is kept in memory (no database): the test harness calls
`GET /__test/reset/` before every test case, which wipes all checks/channels
back to a single fixed seed project, so persistence across requests beyond a
single test case is unnecessary. The server itself is single-threaded
(one request handled at a time), which is what makes the in-memory state
safe without any locking.

## Build

No CMake or dependencies required — just a C++ compiler:

```bash
# Linux
g++ -std=c++14 -O2 -o healthchecks main.cpp

# Windows (MinGW/g++)
g++ -std=c++14 -O2 -o healthchecks.exe main.cpp -lws2_32
```

A `CMakeLists.txt` is also included if you'd rather use CMake:

```bash
mkdir -p build && cd build
cmake ..
cmake --build .
```

## Run

```bash
./healthchecks
```

The server listens on `0.0.0.0:8000`.

## Validate

```bash
cd ../relang
python3 validate.py http://127.0.0.1:8000
```

**Use `127.0.0.1`, not `localhost`.** On many systems, resolving `localhost`
tries an IPv6 connection (`::1`) first; since this server only binds an IPv4
socket, that first attempt has to time out before falling back to IPv4,
adding a multi-second delay to *every single request* (and, under load, can
cause client-side read timeouts that look like flaky/failing tests even
though the server is behaving correctly). Addressing the server by its literal
IPv4 address skips that resolution step entirely.
