# healthchecks — C++ port

A from-scratch C++17 re-implementation of the healthchecks (Python/Django)
uptime-monitoring server's HTTP API, built against the [Drogon](https://github.com/drogonframework/drogon)
web framework. It targets output-compatibility with `relang/validate.py`'s
HTTP-replay test suite: for every request, this server returns the same
status code, content-type, and (for JSON/plain-text bodies) response body
shape as the reference Django app.

Scope: this port focuses on the `hc.api` surface (checks CRUD, pinging,
pings/flips/channels/badges listing, notification-status/bounce webhooks) —
the part of healthchecks that is verified by JSON/plain-text body comparison.
The `hc.front`/`hc.accounts`/`hc.integrations`/`hc.payments` apps render full
HTML pages, whose bodies are never compared by the harness (only status +
content-type), so they are intentionally out of scope here.

State is kept in memory (no database): the test harness calls
`GET /__test/reset/` before every test case, which wipes all checks/channels
back to a single fixed seed project, so persistence across requests beyond a
single test case is unnecessary.

## Prerequisites (Ubuntu 24.04)

Install Drogon and its dependencies. Ubuntu 24.04 ships `libdrogon-dev` in
its repositories:

```bash
sudo apt-get update
sudo apt-get install -y build-essential cmake libdrogon-dev
```

If `libdrogon-dev` is not available in your environment, build Drogon from
source instead:

```bash
sudo apt-get install -y build-essential cmake git \
    libjsoncpp-dev uuid-dev zlib1g-dev openssl libssl-dev
git clone https://github.com/drogonframework/drogon
cd drogon
git submodule update --init
mkdir build && cd build
cmake ..
make -j$(nproc)
sudo make install
sudo ldconfig
```

## Build

```bash
cd target
mkdir -p build && cd build
cmake ..
make -j$(nproc)
```

This produces `target/build/healthchecks`.

## Run

```bash
./build/healthchecks
```

The server listens on `0.0.0.0:8000`.

## Validate

```bash
cd ../relang
python3 validate.py http://localhost:8000
```
