// Minimal std::optional replacement for compilers without full C++17 library
// support (e.g. GCC < 7's libstdc++, which lacks <optional>). Value semantics
// via an internal unique_ptr, so no manual placement-new bookkeeping needed.
#pragma once
#include <memory>
#include <utility>

template <typename T>
class Optional {
    std::unique_ptr<T> ptr_;

public:
    Optional() {}
    Optional(const T &v) : ptr_(new T(v)) {}
    Optional(const Optional &o) : ptr_(o.ptr_ ? new T(*o.ptr_) : nullptr) {}
    Optional(Optional &&o) : ptr_(std::move(o.ptr_)) {}

    Optional &operator=(const Optional &o) {
        ptr_.reset(o.ptr_ ? new T(*o.ptr_) : nullptr);
        return *this;
    }
    Optional &operator=(Optional &&o) {
        ptr_ = std::move(o.ptr_);
        return *this;
    }
    Optional &operator=(const T &v) {
        ptr_.reset(new T(v));
        return *this;
    }

    bool has_value() const { return static_cast<bool>(ptr_); }
    explicit operator bool() const { return has_value(); }

    T &operator*() { return *ptr_; }
    const T &operator*() const { return *ptr_; }
    T *operator->() { return ptr_.get(); }
    const T *operator->() const { return ptr_.get(); }

    void reset() { ptr_.reset(); }
};

template <typename T>
bool operator==(const Optional<T> &a, const Optional<T> &b) {
    if (a.has_value() != b.has_value()) return false;
    if (!a.has_value()) return true;
    return *a == *b;
}

template <typename T>
bool operator!=(const Optional<T> &a, const Optional<T> &b) {
    return !(a == b);
}
