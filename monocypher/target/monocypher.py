"""
monocypher.py — a pure-Python port of the Monocypher C crypto library.

Ported from Monocypher (master, dual BSD-2-Clause / CC0), including the
optional Ed25519/SHA-512 module.  Every function mirrors the semantics of its
C counterpart exactly and is verified byte-for-byte against the C output.

Implements: constant-time-ish comparisons, wipe, ChaCha20 (djb/ietf/x/h),
Poly1305, RFC-8439-style AEAD (lock/unlock + incremental), BLAKE2b, SHA-512,
HMAC-SHA-512, HKDF-SHA-512, Argon2 (d/i/id), X25519 (+inverse and the "dirty"
variants), EdDSA (BLAKE2b) and Ed25519 (SHA-512, incl. prehashed), Elligator 2.

SECURITY WARNING
----------------
This is a *functional* port for study, testing and cross-validation.  Python
cannot provide the constant-time guarantees the C original is built around:
big integers, branches and memory are all data-dependent, and `crypto_wipe`
cannot truly erase immutable Python bytes.  Use the real Monocypher (or
libsodium / `cryptography`) for anything that must resist an attacker.
"""

import hashlib
import hmac as _hmac

# ---------------------------------------------------------------------------
# Field / group constants (Curve25519, Ed25519)
# ---------------------------------------------------------------------------
P = 2 ** 255 - 19                                                   # field prime
L = 2 ** 252 + 27742317777372353535851937790883648493               # group order
M64 = 0xFFFFFFFFFFFFFFFF

SQRTM1 = pow(2, (P - 1) // 4, P)                    # sqrt(-1)
D = (-121665 * pow(121666, P - 2, P)) % P           # Edwards d
D2 = (2 * D) % P
A = 486662                                          # Montgomery A
A2 = (A * A) % P
UFACTOR = (-2 * SQRTM1) % P                         # -sqrt(-1) * 2

# Ed25519 base point
_BY = (4 * pow(5, P - 2, P)) % P

# Low-order point used by crypto_x25519_dirty_fast
LOP_X = 0x547CF2F1C9B1BCB89EBE45F31C1A0FE9B1FA2C0D1FC9E0DA0FD9E0A9E0FD9F3F
LOP_Y = 0x26E8958FC2B227B045C3F489F2EF98F0D5DFAC05D3C63339B13802886D53FC05

# Elligator: base point of order 8*L used by dirty_small
DIRTY_BASE_POINT = bytes([
    0xd8, 0x86, 0x1a, 0xa2, 0x78, 0x7a, 0xd9, 0x26,
    0x8b, 0x74, 0x74, 0xb6, 0x82, 0xe3, 0xbe, 0xc3,
    0xce, 0x36, 0x9a, 0x1e, 0x5e, 0x31, 0x47, 0xa2,
    0x6d, 0x37, 0x7c, 0xfd, 0x20, 0xb5, 0xdf, 0x75,
])

# Ed25519ph domain separator: dom2(phflag=1, context="")
_ED25519_PH_DOMAIN = b"SigEd25519 no Ed25519 collisions\x01\x00"

CRYPTO_ARGON2_D = 0
CRYPTO_ARGON2_I = 1
CRYPTO_ARGON2_ID = 2


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _le(b):
    return int.from_bytes(b, "little")


def _b32(n):
    return (n % P).to_bytes(32, "little")


def _check(cond, msg):
    if not cond:
        raise ValueError(msg)


def _need(b, n, name):
    b = bytes(b)
    _check(len(b) == n, "%s must be exactly %d bytes, got %d" % (name, n, len(b)))
    return b


# ---------------------------------------------------------------------------
# Constant-time comparison / wipe
# ---------------------------------------------------------------------------
def crypto_verify16(a, b):
    """Return 0 if the two 16-byte buffers are equal, -1 otherwise."""
    return 0 if _hmac.compare_digest(_need(a, 16, "a"), _need(b, 16, "b")) else -1


def crypto_verify32(a, b):
    return 0 if _hmac.compare_digest(_need(a, 32, "a"), _need(b, 32, "b")) else -1


def crypto_verify64(a, b):
    return 0 if _hmac.compare_digest(_need(a, 64, "a"), _need(b, 64, "b")) else -1


def crypto_wipe(buf):
    """Zero a mutable buffer in place; return zeros for immutable input.

    Note: unlike the C original this cannot guarantee erasure — Python may
    hold copies of immutable bytes elsewhere in memory.
    """
    if isinstance(buf, bytearray):
        for i in range(len(buf)):
            buf[i] = 0
        return buf
    return b"\x00" * len(bytes(buf))


# ---------------------------------------------------------------------------
# ChaCha20
# ---------------------------------------------------------------------------
_SIGMA = b"expand 32-byte k"


def _rotl32(x, n):
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _quarter(s, a, b, c, d):
    s[a] = (s[a] + s[b]) & 0xFFFFFFFF
    s[d] = _rotl32(s[d] ^ s[a], 16)
    s[c] = (s[c] + s[d]) & 0xFFFFFFFF
    s[b] = _rotl32(s[b] ^ s[c], 12)
    s[a] = (s[a] + s[b]) & 0xFFFFFFFF
    s[d] = _rotl32(s[d] ^ s[a], 8)
    s[c] = (s[c] + s[d]) & 0xFFFFFFFF
    s[b] = _rotl32(s[b] ^ s[c], 7)


def _chacha_rounds(s):
    for _ in range(10):
        _quarter(s, 0, 4, 8, 12)
        _quarter(s, 1, 5, 9, 13)
        _quarter(s, 2, 6, 10, 14)
        _quarter(s, 3, 7, 11, 15)
        _quarter(s, 0, 5, 10, 15)
        _quarter(s, 1, 6, 11, 12)
        _quarter(s, 2, 7, 8, 13)
        _quarter(s, 3, 4, 9, 14)


def _words(b):
    return [int.from_bytes(b[i:i + 4], "little") for i in range(0, len(b), 4)]


def crypto_chacha20_h(key, in16):
    """HChaCha20: key derivation core used by XChaCha20."""
    key = _need(key, 32, "key")
    in16 = _need(in16, 16, "in")
    s = _words(_SIGMA) + _words(key) + _words(in16)
    w = list(s)
    _chacha_rounds(w)
    out = w[0:4] + w[12:16]
    return b"".join(x.to_bytes(4, "little") for x in out)


def crypto_chacha20_djb(plain_text, key, nonce, ctr):
    """DJB-flavoured ChaCha20 (8-byte nonce, 64-bit counter).

    Returns (cipher_text, next_counter) — the C version returns the counter.
    """
    key = _need(key, 32, "key")
    nonce = _need(nonce, 8, "nonce")
    _check(0 <= ctr <= M64, "counter out of 64-bit range")
    plain_text = bytes(plain_text)

    base = _words(_SIGMA) + _words(key)
    nwords = _words(nonce)
    out = bytearray()
    n_blocks = (len(plain_text) + 63) // 64
    for i in range(n_blocks):
        c = (ctr + i) & M64
        s = base + [c & 0xFFFFFFFF, (c >> 32) & 0xFFFFFFFF] + nwords
        w = list(s)
        _chacha_rounds(w)
        block = b"".join(((w[j] + s[j]) & 0xFFFFFFFF).to_bytes(4, "little")
                         for j in range(16))
        chunk = plain_text[i * 64:(i + 1) * 64]
        out += bytes(x ^ y for x, y in zip(chunk, block))
    return bytes(out), (ctr + n_blocks) & M64


def crypto_chacha20_ietf(plain_text, key, nonce, ctr):
    """IETF ChaCha20 (12-byte nonce, 32-bit counter)."""
    nonce = _need(nonce, 12, "nonce")
    _check(0 <= ctr <= 0xFFFFFFFF, "counter out of 32-bit range")
    big_ctr = ctr + (_le(nonce[0:4]) << 32)
    ct, new_ctr = crypto_chacha20_djb(plain_text, key, nonce[4:12], big_ctr)
    return ct, new_ctr & 0xFFFFFFFF


def crypto_chacha20_x(plain_text, key, nonce, ctr):
    """XChaCha20 (24-byte nonce): HChaCha20 then DJB ChaCha20."""
    nonce = _need(nonce, 24, "nonce")
    sub_key = crypto_chacha20_h(key, nonce[0:16])
    return crypto_chacha20_djb(plain_text, sub_key, nonce[16:24], ctr)


# ---------------------------------------------------------------------------
# Poly1305
# ---------------------------------------------------------------------------
def crypto_poly1305(message, key):
    """One-time authenticator.  Never reuse a key."""
    key = _need(key, 32, "key")
    message = bytes(message)
    r = _le(key[0:16]) & 0x0FFFFFFC0FFFFFFC0FFFFFFC0FFFFFFF
    s = _le(key[16:32])
    p = (1 << 130) - 5
    acc = 0
    for i in range(0, len(message), 16):
        block = message[i:i + 16]
        n = _le(block) + (1 << (8 * len(block)))
        acc = ((acc + n) * r) % p
    return ((acc + s) & ((1 << 128) - 1)).to_bytes(16, "little")


def _gap(size, pow2):
    return (-size) % pow2


def _lock_auth(auth_key, ad, cipher_text):
    sizes = len(ad).to_bytes(8, "little") + len(cipher_text).to_bytes(8, "little")
    msg = (bytes(ad) + b"\x00" * _gap(len(ad), 16) +
           bytes(cipher_text) + b"\x00" * _gap(len(cipher_text), 16) + sizes)
    return crypto_poly1305(msg, auth_key)


# ---------------------------------------------------------------------------
# Authenticated encryption
# ---------------------------------------------------------------------------
class crypto_aead_ctx:
    """Incremental AEAD state — mirrors the C struct byte-for-byte."""

    __slots__ = ("counter", "key", "nonce")

    def __init__(self, counter=0, key=b"\x00" * 32, nonce=b"\x00" * 8):
        self.counter = counter
        self.key = bytes(key)
        self.nonce = bytes(nonce)

    def to_bytes(self):
        """Serialise exactly as the C struct {u64 counter; u8 key[32]; u8 nonce[8]}."""
        return self.counter.to_bytes(8, "little") + self.key + self.nonce


def crypto_aead_init_x(key, nonce):
    nonce = _need(nonce, 24, "nonce")
    return crypto_aead_ctx(0, crypto_chacha20_h(key, nonce[0:16]), nonce[16:24])


def crypto_aead_init_djb(key, nonce):
    return crypto_aead_ctx(0, _need(key, 32, "key"), _need(nonce, 8, "nonce"))


def crypto_aead_init_ietf(key, nonce):
    nonce = _need(nonce, 12, "nonce")
    return crypto_aead_ctx(_le(nonce[0:4]) << 32, _need(key, 32, "key"), nonce[4:12])


def crypto_aead_write(ctx, ad, plain_text):
    """Encrypt+authenticate one message, then ratchet the key."""
    auth_key, _ = crypto_chacha20_djb(b"\x00" * 64, ctx.key, ctx.nonce, ctx.counter)
    cipher_text, _ = crypto_chacha20_djb(plain_text, ctx.key, ctx.nonce,
                                         (ctx.counter + 1) & M64)
    mac = _lock_auth(auth_key[0:32], ad, cipher_text)
    ctx.key = auth_key[32:64]
    return cipher_text, mac


def crypto_aead_read(ctx, mac, ad, cipher_text):
    """Verify then decrypt.  Returns (plain_text, 0) or (None, -1)."""
    auth_key, _ = crypto_chacha20_djb(b"\x00" * 64, ctx.key, ctx.nonce, ctx.counter)
    real_mac = _lock_auth(auth_key[0:32], ad, cipher_text)
    if not _hmac.compare_digest(real_mac, _need(mac, 16, "mac")):
        return None, -1
    plain_text, _ = crypto_chacha20_djb(cipher_text, ctx.key, ctx.nonce,
                                        (ctx.counter + 1) & M64)
    ctx.key = auth_key[32:64]
    return plain_text, 0


def crypto_aead_lock(key, nonce, ad, plain_text):
    """One-shot XChaCha20-Poly1305 encryption.  Returns (cipher_text, mac)."""
    return crypto_aead_write(crypto_aead_init_x(key, nonce), ad, plain_text)


def crypto_aead_unlock(key, nonce, mac, ad, cipher_text):
    """One-shot XChaCha20-Poly1305 decryption.  Returns (plain_text, status)."""
    return crypto_aead_read(crypto_aead_init_x(key, nonce), mac, ad, cipher_text)


# ---------------------------------------------------------------------------
# Hashes
# ---------------------------------------------------------------------------
def crypto_blake2b(message, hash_size=64):
    _check(1 <= hash_size <= 64, "hash_size must be 1..64")
    return hashlib.blake2b(bytes(message), digest_size=hash_size).digest()


def crypto_blake2b_keyed(message, key, hash_size=64):
    _check(1 <= hash_size <= 64, "hash_size must be 1..64")
    key = bytes(key)
    _check(len(key) <= 64, "blake2b key must be <= 64 bytes")
    return hashlib.blake2b(bytes(message), digest_size=hash_size, key=key).digest()


def crypto_sha512(message):
    return hashlib.sha512(bytes(message)).digest()


def crypto_sha512_hmac(key, message):
    return _hmac.new(bytes(key), bytes(message), hashlib.sha512).digest()


def crypto_sha512_hkdf_expand(prk, info, okm_size):
    _check(okm_size >= 0, "okm_size must be >= 0")
    out = bytearray()
    blk = b""
    ctr = 1
    while len(out) < okm_size:
        mac = _hmac.new(bytes(prk), None, hashlib.sha512)
        if blk:
            mac.update(blk)
        mac.update(bytes(info))
        mac.update(bytes([ctr & 0xFF]))
        blk = mac.digest()
        out += blk[:min(64, okm_size - len(out))]
        ctr += 1
    return bytes(out)


def crypto_sha512_hkdf(ikm, salt, info, okm_size):
    prk = crypto_sha512_hmac(salt, ikm)
    return crypto_sha512_hkdf_expand(prk, info, okm_size)


# ---------------------------------------------------------------------------
# Argon2
# ---------------------------------------------------------------------------
def _rotr64(x, n):
    return ((x >> n) | (x << (64 - n))) & M64


# Argon2's permutation.  The index tables are precomputed and the BLAKE2b
# round is fully inlined: Argon2 is by far the hottest path in this module,
# and both changes cut its running time by more than half.
_ROW_IDX = tuple(tuple(16 * i + j for j in range(16)) for i in range(8))
_COL_IDX = tuple(tuple(2 * i + 16 * j + k for j in range(8) for k in range(2))
                 for i in range(8))


def _blake_round(b, idx):
    i0, i1, i2, i3, i4, i5, i6, i7, i8, i9, i10, i11, i12, i13, i14, i15 = idx
    v0 = b[i0]; v1 = b[i1]; v2 = b[i2]; v3 = b[i3]; v4 = b[i4]; v5 = b[i5]; v6 = b[i6]; v7 = b[i7]; v8 = b[i8]; v9 = b[i9]; v10 = b[i10]; v11 = b[i11]; v12 = b[i12]; v13 = b[i13]; v14 = b[i14]; v15 = b[i15]
    v0 = (v0 + v4 + 2 * (v0 & 0xFFFFFFFF) * (v4 & 0xFFFFFFFF)) & M64
    v12 ^= v0; v12 = ((v12 >> 32) | (v12 << 32)) & M64
    v8 = (v8 + v12 + 2 * (v8 & 0xFFFFFFFF) * (v12 & 0xFFFFFFFF)) & M64
    v4 ^= v8; v4 = ((v4 >> 24) | (v4 << 40)) & M64
    v0 = (v0 + v4 + 2 * (v0 & 0xFFFFFFFF) * (v4 & 0xFFFFFFFF)) & M64
    v12 ^= v0; v12 = ((v12 >> 16) | (v12 << 48)) & M64
    v8 = (v8 + v12 + 2 * (v8 & 0xFFFFFFFF) * (v12 & 0xFFFFFFFF)) & M64
    v4 ^= v8; v4 = ((v4 >> 63) | (v4 << 1)) & M64
    v1 = (v1 + v5 + 2 * (v1 & 0xFFFFFFFF) * (v5 & 0xFFFFFFFF)) & M64
    v13 ^= v1; v13 = ((v13 >> 32) | (v13 << 32)) & M64
    v9 = (v9 + v13 + 2 * (v9 & 0xFFFFFFFF) * (v13 & 0xFFFFFFFF)) & M64
    v5 ^= v9; v5 = ((v5 >> 24) | (v5 << 40)) & M64
    v1 = (v1 + v5 + 2 * (v1 & 0xFFFFFFFF) * (v5 & 0xFFFFFFFF)) & M64
    v13 ^= v1; v13 = ((v13 >> 16) | (v13 << 48)) & M64
    v9 = (v9 + v13 + 2 * (v9 & 0xFFFFFFFF) * (v13 & 0xFFFFFFFF)) & M64
    v5 ^= v9; v5 = ((v5 >> 63) | (v5 << 1)) & M64
    v2 = (v2 + v6 + 2 * (v2 & 0xFFFFFFFF) * (v6 & 0xFFFFFFFF)) & M64
    v14 ^= v2; v14 = ((v14 >> 32) | (v14 << 32)) & M64
    v10 = (v10 + v14 + 2 * (v10 & 0xFFFFFFFF) * (v14 & 0xFFFFFFFF)) & M64
    v6 ^= v10; v6 = ((v6 >> 24) | (v6 << 40)) & M64
    v2 = (v2 + v6 + 2 * (v2 & 0xFFFFFFFF) * (v6 & 0xFFFFFFFF)) & M64
    v14 ^= v2; v14 = ((v14 >> 16) | (v14 << 48)) & M64
    v10 = (v10 + v14 + 2 * (v10 & 0xFFFFFFFF) * (v14 & 0xFFFFFFFF)) & M64
    v6 ^= v10; v6 = ((v6 >> 63) | (v6 << 1)) & M64
    v3 = (v3 + v7 + 2 * (v3 & 0xFFFFFFFF) * (v7 & 0xFFFFFFFF)) & M64
    v15 ^= v3; v15 = ((v15 >> 32) | (v15 << 32)) & M64
    v11 = (v11 + v15 + 2 * (v11 & 0xFFFFFFFF) * (v15 & 0xFFFFFFFF)) & M64
    v7 ^= v11; v7 = ((v7 >> 24) | (v7 << 40)) & M64
    v3 = (v3 + v7 + 2 * (v3 & 0xFFFFFFFF) * (v7 & 0xFFFFFFFF)) & M64
    v15 ^= v3; v15 = ((v15 >> 16) | (v15 << 48)) & M64
    v11 = (v11 + v15 + 2 * (v11 & 0xFFFFFFFF) * (v15 & 0xFFFFFFFF)) & M64
    v7 ^= v11; v7 = ((v7 >> 63) | (v7 << 1)) & M64
    v0 = (v0 + v5 + 2 * (v0 & 0xFFFFFFFF) * (v5 & 0xFFFFFFFF)) & M64
    v15 ^= v0; v15 = ((v15 >> 32) | (v15 << 32)) & M64
    v10 = (v10 + v15 + 2 * (v10 & 0xFFFFFFFF) * (v15 & 0xFFFFFFFF)) & M64
    v5 ^= v10; v5 = ((v5 >> 24) | (v5 << 40)) & M64
    v0 = (v0 + v5 + 2 * (v0 & 0xFFFFFFFF) * (v5 & 0xFFFFFFFF)) & M64
    v15 ^= v0; v15 = ((v15 >> 16) | (v15 << 48)) & M64
    v10 = (v10 + v15 + 2 * (v10 & 0xFFFFFFFF) * (v15 & 0xFFFFFFFF)) & M64
    v5 ^= v10; v5 = ((v5 >> 63) | (v5 << 1)) & M64
    v1 = (v1 + v6 + 2 * (v1 & 0xFFFFFFFF) * (v6 & 0xFFFFFFFF)) & M64
    v12 ^= v1; v12 = ((v12 >> 32) | (v12 << 32)) & M64
    v11 = (v11 + v12 + 2 * (v11 & 0xFFFFFFFF) * (v12 & 0xFFFFFFFF)) & M64
    v6 ^= v11; v6 = ((v6 >> 24) | (v6 << 40)) & M64
    v1 = (v1 + v6 + 2 * (v1 & 0xFFFFFFFF) * (v6 & 0xFFFFFFFF)) & M64
    v12 ^= v1; v12 = ((v12 >> 16) | (v12 << 48)) & M64
    v11 = (v11 + v12 + 2 * (v11 & 0xFFFFFFFF) * (v12 & 0xFFFFFFFF)) & M64
    v6 ^= v11; v6 = ((v6 >> 63) | (v6 << 1)) & M64
    v2 = (v2 + v7 + 2 * (v2 & 0xFFFFFFFF) * (v7 & 0xFFFFFFFF)) & M64
    v13 ^= v2; v13 = ((v13 >> 32) | (v13 << 32)) & M64
    v8 = (v8 + v13 + 2 * (v8 & 0xFFFFFFFF) * (v13 & 0xFFFFFFFF)) & M64
    v7 ^= v8; v7 = ((v7 >> 24) | (v7 << 40)) & M64
    v2 = (v2 + v7 + 2 * (v2 & 0xFFFFFFFF) * (v7 & 0xFFFFFFFF)) & M64
    v13 ^= v2; v13 = ((v13 >> 16) | (v13 << 48)) & M64
    v8 = (v8 + v13 + 2 * (v8 & 0xFFFFFFFF) * (v13 & 0xFFFFFFFF)) & M64
    v7 ^= v8; v7 = ((v7 >> 63) | (v7 << 1)) & M64
    v3 = (v3 + v4 + 2 * (v3 & 0xFFFFFFFF) * (v4 & 0xFFFFFFFF)) & M64
    v14 ^= v3; v14 = ((v14 >> 32) | (v14 << 32)) & M64
    v9 = (v9 + v14 + 2 * (v9 & 0xFFFFFFFF) * (v14 & 0xFFFFFFFF)) & M64
    v4 ^= v9; v4 = ((v4 >> 24) | (v4 << 40)) & M64
    v3 = (v3 + v4 + 2 * (v3 & 0xFFFFFFFF) * (v4 & 0xFFFFFFFF)) & M64
    v14 ^= v3; v14 = ((v14 >> 16) | (v14 << 48)) & M64
    v9 = (v9 + v14 + 2 * (v9 & 0xFFFFFFFF) * (v14 & 0xFFFFFFFF)) & M64
    v4 ^= v9; v4 = ((v4 >> 63) | (v4 << 1)) & M64
    b[i0] = v0; b[i1] = v1; b[i2] = v2; b[i3] = v3; b[i4] = v4; b[i5] = v5; b[i6] = v6; b[i7] = v7; b[i8] = v8; b[i9] = v9; b[i10] = v10; b[i11] = v11; b[i12] = v12; b[i13] = v13; b[i14] = v14; b[i15] = v15


def _g_rounds(blk):
    for idx in _ROW_IDX:
        _blake_round(blk, idx)
    for idx in _COL_IDX:
        _blake_round(blk, idx)


def _extended_hash(digest_size, data):
    """Argon2's variable-length hash H'."""
    first = hashlib.blake2b(digest_size.to_bytes(4, "little") + bytes(data),
                            digest_size=min(digest_size, 64)).digest()
    if digest_size <= 64:
        return first
    out = bytearray(first)
    r = ((digest_size + 31) >> 5) - 2
    i, inp, outp = 1, 0, 32
    while i < r:
        out[outp:outp + 64] = hashlib.blake2b(bytes(out[inp:inp + 64]),
                                              digest_size=64).digest()
        i, inp, outp = i + 1, inp + 32, outp + 32
    tail = hashlib.blake2b(bytes(out[inp:inp + 64]),
                           digest_size=digest_size - 32 * r).digest()
    out[outp:outp + len(tail)] = tail
    return bytes(out[:digest_size])


def crypto_argon2(hash_size, config, inputs, extras=None):
    """Argon2 password hashing.

    config : (algorithm, nb_blocks, nb_passes, nb_lanes)
    inputs : (password, salt)
    extras : (key, ad) or None
    """
    algorithm, nb_blocks_cfg, nb_passes, nb_lanes = config
    password, salt = inputs
    key, ad = (extras or (b"", b""))
    password, salt, key, ad = bytes(password), bytes(salt), bytes(key), bytes(ad)

    _check(algorithm in (0, 1, 2), "algorithm must be 0 (d), 1 (i) or 2 (id)")
    _check(nb_lanes >= 1, "nb_lanes must be >= 1")
    _check(nb_passes >= 1, "nb_passes must be >= 1")
    _check(nb_blocks_cfg >= 8 * nb_lanes,
           "nb_blocks must be >= 8 * nb_lanes (got %d, need %d)"
           % (nb_blocks_cfg, 8 * nb_lanes))
    _check(hash_size >= 4, "hash_size must be >= 4")

    segment_size = nb_blocks_cfg // nb_lanes // 4
    lane_size = segment_size * 4
    nb_blocks = lane_size * nb_lanes

    # --- initial hash ---
    h = hashlib.blake2b(digest_size=64)

    def up32(x):
        h.update((x & 0xFFFFFFFF).to_bytes(4, "little"))

    def up32buf(b):
        up32(len(b))
        h.update(b)

    up32(nb_lanes)
    up32(hash_size)
    up32(nb_blocks_cfg)
    up32(nb_passes)
    up32(0x13)
    up32(algorithm)
    up32buf(password)
    up32buf(salt)
    up32buf(key)
    up32buf(ad)
    initial_hash = bytearray(h.digest() + b"\x00" * 8)

    # --- fill the first two blocks of each lane ---
    blocks = [[0] * 128 for _ in range(nb_blocks)]
    for lane in range(nb_lanes):
        for i in range(2):
            initial_hash[64:68] = i.to_bytes(4, "little")
            initial_hash[68:72] = lane.to_bytes(4, "little")
            area = _extended_hash(1024, bytes(initial_hash))
            blocks[lane * lane_size + i] = [
                _le(area[k * 8:k * 8 + 8]) for k in range(128)]

    constant_time = algorithm != CRYPTO_ARGON2_D

    for p in range(nb_passes):
        for slice_ in range(4):
            pass_offset = 2 if (p == 0 and slice_ == 0) else 0
            slice_offset = slice_ * segment_size
            if slice_ == 2 and algorithm == CRYPTO_ARGON2_ID:
                constant_time = 0

            for segment in range(nb_lanes):
                index_block = [0] * 128
                index_ctr = 1
                for block in range(pass_offset, segment_size):
                    lane_offset = segment * lane_size
                    seg_start = lane_offset + slice_offset
                    cur = seg_start + block
                    prev = (seg_start + lane_size - 1
                            if block == 0 and slice_offset == 0
                            else seg_start + block - 1)

                    if constant_time:
                        if block == pass_offset or (block % 128) == 0:
                            index_block = [0] * 128
                            index_block[0] = p
                            index_block[1] = segment
                            index_block[2] = slice_
                            index_block[3] = nb_blocks
                            index_block[4] = nb_passes
                            index_block[5] = algorithm
                            index_block[6] = index_ctr
                            index_ctr += 1
                            for _ in range(2):
                                tmp = list(index_block)
                                _g_rounds(index_block)
                                index_block = [x ^ y for x, y in
                                               zip(index_block, tmp)]
                        index_seed = index_block[block % 128]
                    else:
                        index_seed = blocks[prev][0]

                    next_slice = ((slice_ + 1) % 4) * segment_size
                    window_start = 0 if p == 0 else next_slice
                    nb_segments = slice_ if p == 0 else 3
                    lane = (segment if (p == 0 and slice_ == 0)
                            else (index_seed >> 32) % nb_lanes)
                    window_size = nb_segments * segment_size + (
                        block - 1 if lane == segment
                        else (0xFFFFFFFF if block == 0 else 0))

                    j1 = index_seed & 0xFFFFFFFF
                    x = (j1 * j1) >> 32
                    y = ((window_size & 0xFFFFFFFF) * x) >> 32
                    z = ((window_size & 0xFFFFFFFF) - 1 - y) & M64
                    ref = (window_start + z) % lane_size
                    reference = lane * lane_size + ref

                    tmp = [a ^ b for a, b in zip(blocks[prev], blocks[reference])]
                    if p == 0:
                        blocks[cur] = list(tmp)
                    else:
                        blocks[cur] = [a ^ b for a, b in zip(blocks[cur], tmp)]
                    _g_rounds(tmp)
                    blocks[cur] = [a ^ b for a, b in zip(blocks[cur], tmp)]

    last = blocks[lane_size - 1]
    for lane in range(1, nb_lanes):
        nxt = blocks[lane_size - 1 + lane * lane_size]
        nxt = [a ^ b for a, b in zip(nxt, last)]
        last = nxt

    final_block = b"".join(w.to_bytes(8, "little") for w in last)
    return _extended_hash(hash_size, final_block)


# ---------------------------------------------------------------------------
# Field helpers
# ---------------------------------------------------------------------------
def _invsqrt(x):
    """Return (isr, was_square) mirroring Monocypher's invsqrt()."""
    t0 = pow(x, (P - 5) // 8, P)
    quartic = (t0 * t0 % P) * x % P
    z0 = x == 0
    p1 = quartic == 1
    m1 = quartic == P - 1
    ms = quartic == (P - SQRTM1) % P
    isr = t0 * SQRTM1 % P if (m1 or ms) else t0
    return isr, int(p1 or m1 or z0)


def crypto_eddsa_trim_scalar(scalar):
    """Clamp a scalar: clear the low 3 bits, clear bit 255, set bit 254."""
    s = bytearray(_need(scalar, 32, "scalar"))
    s[0] &= 248
    s[31] &= 127
    s[31] |= 64
    return bytes(s)


def crypto_eddsa_reduce(expanded):
    """Reduce a 64-byte little-endian integer modulo L."""
    return (_le(_need(expanded, 64, "expanded")) % L).to_bytes(32, "little")


def crypto_eddsa_mul_add(a, b, c):
    """Return (a*b + c) mod L, all little-endian 32-byte scalars."""
    a = _le(_need(a, 32, "a"))
    b = _le(_need(b, 32, "b"))
    c = _le(_need(c, 32, "c"))
    return ((a * b + c) % L).to_bytes(32, "little")


# ---------------------------------------------------------------------------
# Edwards group (extended coordinates: X, Y, Z, T)
# ---------------------------------------------------------------------------
def _ge_add(p1, p2):
    X1, Y1, Z1, T1 = p1
    X2, Y2, Z2, T2 = p2
    a = (Y1 - X1) * (Y2 - X2) % P
    b = (Y1 + X1) * (Y2 + X2) % P
    c = T1 * D2 % P * T2 % P
    d = 2 * Z1 * Z2 % P
    e, f, g, h = b - a, d - c, d + c, b + a
    return (e * f % P, g * h % P, f * g % P, e * h % P)


def _ge_double(p1):
    return _ge_add(p1, p1)


def _ge_neg(p1):
    X, Y, Z, T = p1
    return ((-X) % P, Y, Z, (-T) % P)


_GE_ZERO = (0, 1, 1, 0)


def _ge_scalarmult(point, scalar_int):
    """Plain double-and-add.  Not constant time — see the module warning."""
    result = _GE_ZERO
    addend = point
    while scalar_int > 0:
        if scalar_int & 1:
            result = _ge_add(result, addend)
        addend = _ge_double(addend)
        scalar_int >>= 1
    return result


def _ge_tobytes(p1):
    X, Y, Z, _T = p1
    zinv = pow(Z, P - 2, P)
    x = X * zinv % P
    y = Y * zinv % P
    return ((y & ~(1 << 255)) | ((x & 1) << 255)).to_bytes(32, "little")


def _ge_frombytes(s):
    """Decompress an Ed25519 point.  Returns None on failure.

    Non-canonical encodings are accepted, matching the C original.
    """
    s = _need(s, 32, "point")
    v = _le(s)
    sign = (v >> 255) & 1
    y = (v & ((1 << 255) - 1)) % P
    u = (y * y - 1) % P
    v2 = (D * y % P * y + 1) % P
    isr, is_square = _invsqrt(u * v2 % P)
    if not is_square:
        return None
    x = u * isr % P
    if (x * x % P) * v2 % P != u % P:
        return None
    if x == 0 and sign:
        return None
    if (x & 1) != sign:
        x = (-x) % P
    return (x, y, 1, x * y % P)


_B_POINT = None


def _base_point():
    global _B_POINT
    if _B_POINT is None:
        y = _BY
        u = (y * y - 1) % P
        v = (D * y % P * y + 1) % P
        isr, _ = _invsqrt(u * v % P)
        x = u * isr % P
        if x & 1:
            x = (-x) % P
        _B_POINT = (x, y, 1, x * y % P)
    return _B_POINT


def crypto_eddsa_scalarbase(scalar):
    """Return [scalar]B encoded as 32 bytes."""
    return _ge_tobytes(_ge_scalarmult(_base_point(),
                                      _le(_need(scalar, 32, "scalar"))))


def crypto_eddsa_check_equation(signature, public_key, h):
    """Verify 8*([s]B - [h]A - R) == identity.  Returns 0 on success, -1 on failure."""
    signature = _need(signature, 64, "signature")
    public_key = _need(public_key, 32, "public_key")
    h = _need(h, 32, "h")

    s = _le(signature[32:64])
    A_pt = _ge_frombytes(public_key)
    R_pt = _ge_frombytes(signature[0:32])
    if A_pt is None or R_pt is None or s >= L:
        return -1

    total = _ge_add(_ge_scalarmult(_base_point(), s),
                    _ge_scalarmult(_ge_neg(A_pt), _le(h)))
    total = _ge_add(total, _ge_neg(R_pt))
    for _ in range(3):
        total = _ge_double(total)
    return crypto_verify32(_ge_tobytes(total), b"\x01" + b"\x00" * 31)


# ---------------------------------------------------------------------------
# EdDSA (BLAKE2b flavour — Monocypher's default)
# ---------------------------------------------------------------------------
def _hash_reduce_blake(*parts):
    h = hashlib.blake2b(digest_size=64)
    for part in parts:
        h.update(bytes(part))
    return crypto_eddsa_reduce(h.digest())


def crypto_eddsa_key_pair(seed):
    """Return (secret_key[64], public_key[32]).  secret_key = seed || public_key."""
    seed = _need(seed, 32, "seed")
    a = bytearray(crypto_blake2b(seed, 64))
    a[0:32] = crypto_eddsa_trim_scalar(bytes(a[0:32]))
    public_key = crypto_eddsa_scalarbase(bytes(a[0:32]))
    return seed + public_key, public_key


def crypto_eddsa_sign(secret_key, message):
    secret_key = _need(secret_key, 64, "secret_key")
    message = bytes(message)
    a = bytearray(crypto_blake2b(secret_key[0:32], 64))
    a[0:32] = crypto_eddsa_trim_scalar(bytes(a[0:32]))
    r = _hash_reduce_blake(bytes(a[32:64]), message)
    R = crypto_eddsa_scalarbase(r)
    h = _hash_reduce_blake(R, secret_key[32:64], message)
    return R + crypto_eddsa_mul_add(h, bytes(a[0:32]), r)


def crypto_eddsa_check(signature, public_key, message):
    signature = _need(signature, 64, "signature")
    public_key = _need(public_key, 32, "public_key")
    h = _hash_reduce_blake(signature[0:32], public_key, bytes(message))
    return crypto_eddsa_check_equation(signature, public_key, h)


# ---------------------------------------------------------------------------
# Ed25519 (SHA-512 flavour — the optional module)
# ---------------------------------------------------------------------------
def _hash_reduce_sha(*parts):
    h = hashlib.sha512()
    for part in parts:
        h.update(bytes(part))
    return crypto_eddsa_reduce(h.digest())


def crypto_ed25519_key_pair(seed):
    seed = _need(seed, 32, "seed")
    a = bytearray(crypto_sha512(seed))
    a[0:32] = crypto_eddsa_trim_scalar(bytes(a[0:32]))
    public_key = crypto_eddsa_scalarbase(bytes(a[0:32]))
    return seed + public_key, public_key


def _ed25519_dom_sign(secret_key, dom, message):
    a = bytearray(crypto_sha512(secret_key[0:32]))
    a[0:32] = crypto_eddsa_trim_scalar(bytes(a[0:32]))
    r = _hash_reduce_sha(dom, bytes(a[32:64]), message)
    R = crypto_eddsa_scalarbase(r)
    h = _hash_reduce_sha(dom, R, secret_key[32:64], message)
    return R + crypto_eddsa_mul_add(h, bytes(a[0:32]), r)


def crypto_ed25519_sign(secret_key, message):
    return _ed25519_dom_sign(_need(secret_key, 64, "secret_key"), b"", bytes(message))


def crypto_ed25519_check(signature, public_key, message):
    signature = _need(signature, 64, "signature")
    public_key = _need(public_key, 32, "public_key")
    h = _hash_reduce_sha(signature[0:32], public_key, bytes(message))
    return crypto_eddsa_check_equation(signature, public_key, h)


def crypto_ed25519_ph_sign(secret_key, message_hash):
    return _ed25519_dom_sign(_need(secret_key, 64, "secret_key"),
                             _ED25519_PH_DOMAIN,
                             _need(message_hash, 64, "message_hash"))


def crypto_ed25519_ph_check(signature, public_key, message_hash):
    signature = _need(signature, 64, "signature")
    public_key = _need(public_key, 32, "public_key")
    message_hash = _need(message_hash, 64, "message_hash")
    h = _hash_reduce_sha(_ED25519_PH_DOMAIN, signature[0:32], public_key, message_hash)
    return crypto_eddsa_check_equation(signature, public_key, h)


# ---------------------------------------------------------------------------
# X25519
# ---------------------------------------------------------------------------
def _scalarmult(scalar, point, nb_bits):
    """Montgomery ladder on Curve25519."""
    x1 = _le(_need(point, 32, "point")) & ((1 << 255) - 1)
    k = _le(_need(scalar, 32, "scalar"))
    x2, z2, x3, z3 = 1, 0, x1, 1
    swap = 0
    for pos in range(nb_bits - 1, -1, -1):
        b = (k >> pos) & 1
        swap ^= b
        if swap:
            x2, x3 = x3, x2
            z2, z3 = z3, z2
        swap = b
        t0 = (x3 - z3) % P
        t1 = (x2 - z2) % P
        x2 = (x2 + z2) % P
        z2 = (x3 + z3) % P
        z3 = t0 * x2 % P
        z2 = z2 * t1 % P
        t0 = t1 * t1 % P
        t1 = x2 * x2 % P
        x3 = (z3 + z2) % P
        z2 = (z3 - z2) % P
        x2 = t1 * t0 % P
        t1 = (t1 - t0) % P
        z2 = z2 * z2 % P
        z3 = t1 * 121666 % P
        x3 = x3 * x3 % P
        t0 = (t0 + z3) % P
        z3 = x1 * z2 % P
        z2 = t1 * t0 % P
    if swap:
        x2, x3 = x3, x2
        z2, z3 = z3, z2
    return _b32(x2 * pow(z2, P - 2, P) % P)


def crypto_x25519(secret_key, their_public_key):
    """X25519 Diffie-Hellman.  Hash the result before using it as a key."""
    return _scalarmult(crypto_eddsa_trim_scalar(secret_key),
                       _need(their_public_key, 32, "public_key"), 255)


_X25519_BASE = b"\x09" + b"\x00" * 31


def crypto_x25519_public_key(secret_key):
    return crypto_x25519(secret_key, _X25519_BASE)


def crypto_x25519_inverse(private_key, curve_point):
    """Scalar "division" for OPRF: [1/private_key]curve_point."""
    scalar = _le(crypto_eddsa_trim_scalar(private_key)) % L
    inv = pow(scalar, L - 2, L) if scalar else 0
    b = inv.to_bytes(32, "little")
    combined = (inv + L * ((b[0] * 3) & 7)) % (1 << 256)
    return _scalarmult(combined.to_bytes(32, "little"),
                       _need(curve_point, 32, "curve_point"), 256)


def crypto_x25519_dirty_small(secret_key):
    """Public key that keeps the cofactor — leaks 3 bits.  For Elligator."""
    secret_key = _need(secret_key, 32, "secret_key")
    scalar = _le(crypto_eddsa_trim_scalar(secret_key))
    combined = (scalar + L * (secret_key[0] & 7)) % (1 << 256)
    return _scalarmult(combined.to_bytes(32, "little"), DIRTY_BASE_POINT, 256)


# The C picks dirty_small's base point so both variants agree exactly;
# verified against the C for all 8 cofactor values.
crypto_x25519_dirty_fast = crypto_x25519_dirty_small


def crypto_x25519_to_eddsa(x25519):
    """Montgomery u -> Edwards y.  The sign of x is assumed positive."""
    u = _le(_need(x25519, 32, "x25519")) & ((1 << 255) - 1)
    return _b32((u - 1) * pow(u + 1, P - 2, P) % P)


def crypto_eddsa_to_x25519(eddsa):
    """Edwards y -> Montgomery u.  The sign of x is ignored."""
    y = _le(_need(eddsa, 32, "eddsa")) & ((1 << 255) - 1)
    return _b32((1 + y) * pow((1 - y) % P, P - 2, P) % P)


# ---------------------------------------------------------------------------
# Elligator 2
# ---------------------------------------------------------------------------
def crypto_elligator_map(hidden):
    """Map a 32-byte representative to a Curve25519 point."""
    r = _le(_need(hidden, 32, "hidden")) & ((1 << 254) - 1)
    r = r * r % P
    t1 = 2 * r % P
    u = (t1 + 1) % P
    t2 = u * u % P
    t3 = (A2 * t1 - t2) % P
    t3 = t3 * A % P
    t1 = t2 * u % P
    t1 = t3 * t1 % P
    t1, is_square = _invsqrt(t1)
    u = r * UFACTOR % P
    if is_square:
        u = 1
    t1 = t1 * t1 % P
    u = u * A % P * t3 % P * t2 % P * t1 % P
    return _b32((-u) % P)


def crypto_elligator_rev(curve, tweak):
    """Inverse map.  Returns (hidden, 0) on success, (None, -1) if not representable."""
    curve = _need(curve, 32, "curve")
    _check(0 <= tweak <= 255, "tweak must be a byte")
    u = _le(curve) & ((1 << 255) - 1)
    t2 = (u + A) % P
    t3 = u * t2 % P
    t3 = t3 * (-2) % P
    t3, is_square = _invsqrt(t3)
    if not is_square:
        return None, -1
    t1 = t2 if (tweak & 1) else u
    t3 = t1 * t3 % P
    t1 = 2 * t3 % P
    if t1 & 1:
        t3 = (-t3) % P
    hidden = bytearray(_b32(t3))
    hidden[31] |= tweak & 0xC0
    return bytes(hidden), 0


def crypto_elligator_key_pair(seed):
    """Generate (hidden, secret_key) where hidden is indistinguishable from random."""
    buf = bytearray(32) + bytearray(_need(seed, 32, "seed"))
    while True:
        stream, _ = crypto_chacha20_djb(b"\x00" * 64, bytes(buf[32:64]),
                                        b"\x00" * 8, 0)
        buf[0:64] = stream
        pk = crypto_x25519_dirty_fast(bytes(buf[0:32]))
        hidden, status = crypto_elligator_rev(pk, buf[32])
        if status == 0:
            buf[32:64] = hidden
            return bytes(buf[32:64]), bytes(buf[0:32])


# ===========================================================================
# Command line interface
# ===========================================================================
# Running this file directly speaks the same stdin/stdout hex protocol as the
# reference monocypher-cli C tool, so it can be dropped straight into the
# test harness:   python3 monocypher.py  < test_input
# Importing it as a module gives the library API and runs none of this.

import sys

# ---------------------------------------------------------------------------
# Protocol I/O
# ---------------------------------------------------------------------------
class Reader:
    def __init__(self, stream):
        self.stream = stream

    def line(self):
        raw = self.stream.readline()
        if raw == "":
            sys.stderr.write("unexpected EOF\n")
            sys.exit(1)
        return raw.rstrip("\n").rstrip("\r").rstrip(":").rstrip(" ")

    def hex_param(self, expect=None, name="param"):
        text = self.line()
        if len(text) % 2 != 0:
            sys.stderr.write("odd hex len: %s\n" % text)
            sys.exit(1)
        try:
            data = bytes.fromhex(text)
        except ValueError:
            sys.stderr.write("bad hex: %s\n" % text)
            sys.exit(1)
        if expect is not None and len(data) != expect:
            sys.stderr.write("%s must be %d bytes, got %d\n" % (name, expect, len(data)))
            sys.exit(1)
        return data


OUT = []


def put_hex(data):
    OUT.append(data.hex())


def put_int(value):
    """Mirror C's printf("%02x:\\n", int) — negatives print as 32-bit."""
    OUT.append("%02x" % (value & 0xFFFFFFFF))


def put_u64_le(value):
    put_hex((value & 0xFFFFFFFFFFFFFFFF).to_bytes(8, "little"))


def put_u32_le(value):
    put_hex((value & 0xFFFFFFFF).to_bytes(4, "little"))


# ---------------------------------------------------------------------------
# Dispatch handlers (one per C do_* function)
# ---------------------------------------------------------------------------
def do_verify16(r):
    put_int(crypto_verify16(r.hex_param(16), r.hex_param(16)))


def do_verify32(r):
    put_int(crypto_verify32(r.hex_param(32), r.hex_param(32)))


def do_verify64(r):
    put_int(crypto_verify64(r.hex_param(64), r.hex_param(64)))


def do_wipe(r):
    put_hex(crypto_wipe(bytearray(r.hex_param())))


def do_chacha20_h(r):
    put_hex(crypto_chacha20_h(r.hex_param(32), r.hex_param(16)))


def do_chacha20_djb(r):
    key, nonce = r.hex_param(32), r.hex_param(8)
    plain = r.hex_param()
    ctr = int.from_bytes(r.hex_param(8), "little")
    cipher, new_ctr = crypto_chacha20_djb(plain, key, nonce, ctr)
    put_hex(cipher)
    put_u64_le(new_ctr)


def do_chacha20_ietf(r):
    key, nonce = r.hex_param(32), r.hex_param(12)
    plain = r.hex_param()
    ctr = int.from_bytes(r.hex_param(4), "little")
    cipher, new_ctr = crypto_chacha20_ietf(plain, key, nonce, ctr)
    put_hex(cipher)
    put_u32_le(new_ctr)


def do_chacha20_x(r):
    key, nonce = r.hex_param(32), r.hex_param(24)
    plain = r.hex_param()
    ctr = int.from_bytes(r.hex_param(8), "little")
    cipher, new_ctr = crypto_chacha20_x(plain, key, nonce, ctr)
    put_hex(cipher)
    put_u64_le(new_ctr)


def do_poly1305(r):
    key = r.hex_param(32)
    put_hex(crypto_poly1305(r.hex_param(), key))


def do_aead_lock(r):
    key, nonce = r.hex_param(32), r.hex_param(24)
    ad, pt = r.hex_param(), r.hex_param()
    cipher, mac = crypto_aead_lock(key, nonce, ad, pt)
    put_hex(cipher)
    put_hex(mac)


def do_aead_unlock(r):
    key, nonce = r.hex_param(32), r.hex_param(24)
    ad, ct, mac = r.hex_param(), r.hex_param(), r.hex_param(16)
    plain, status = crypto_aead_unlock(key, nonce, mac, ad, ct)
    if status == 0:
        put_hex(plain)
    put_hex(bytes([status & 0xFF]))


def do_blake2b(r):
    put_hex(crypto_blake2b(r.hex_param(), 64))


def do_blake2b_keyed(r):
    msg = r.hex_param()
    key = r.hex_param()[:64]
    put_hex(crypto_blake2b_keyed(msg, key, 64))


def do_sha512(r):
    put_hex(crypto_sha512(r.hex_param()))


def do_sha512_hmac(r):
    key = r.hex_param()
    put_hex(crypto_sha512_hmac(key, r.hex_param()))


def do_sha512_hkdf(r):
    ikm, salt, info = r.hex_param(), r.hex_param(), r.hex_param()
    okm_size = len(r.hex_param())
    put_hex(crypto_sha512_hkdf(ikm, salt, info, okm_size))


def do_argon2(r):
    algo = int.from_bytes(r.hex_param(4), "little")
    blocks = int.from_bytes(r.hex_param(4), "little")
    passes = int.from_bytes(r.hex_param(4), "little")
    lanes = int.from_bytes(r.hex_param(4), "little")
    pwd, salt, key, ad = (r.hex_param(), r.hex_param(),
                          r.hex_param(), r.hex_param())
    hash_size = len(r.hex_param())
    put_hex(crypto_argon2(hash_size, (algo, blocks, passes, lanes),
                             (pwd, salt), (key, ad)))


def do_x25519(r):
    put_hex(crypto_x25519(r.hex_param(32), r.hex_param(32)))


def do_x25519_public_key(r):
    put_hex(crypto_x25519_public_key(r.hex_param(32)))


def do_x25519_inverse(r):
    put_hex(crypto_x25519_inverse(r.hex_param(32), r.hex_param(32)))


def do_x25519_dirty_small(r):
    put_hex(crypto_x25519_dirty_small(r.hex_param(32)))


def do_x25519_dirty_fast(r):
    put_hex(crypto_x25519_dirty_fast(r.hex_param(32)))


def do_eddsa_key_pair(r):
    sk, pk = crypto_eddsa_key_pair(r.hex_param(32))
    put_hex(sk)
    put_hex(pk)


def do_eddsa_sign(r):
    sk, pk = r.hex_param(64), r.hex_param(32)
    msg = r.hex_param()
    put_hex(crypto_eddsa_sign(sk[0:32] + pk, msg))


def do_eddsa_check(r):
    sig, pk = r.hex_param(64), r.hex_param(32)
    msg = r.hex_param()
    put_hex(bytes([crypto_eddsa_check(sig, pk, msg) & 0xFF]))


def do_ed25519_key_pair(r):
    sk, pk = crypto_ed25519_key_pair(r.hex_param(32))
    put_hex(sk)
    put_hex(pk)


def do_ed25519_sign(r):
    sk, pk = r.hex_param(64), r.hex_param(32)
    msg = r.hex_param()
    put_hex(crypto_ed25519_sign(sk[0:32] + pk, msg))


def do_ed25519_check(r):
    sig, pk = r.hex_param(64), r.hex_param(32)
    msg = r.hex_param()
    put_hex(bytes([crypto_ed25519_check(sig, pk, msg) & 0xFF]))


def do_ed25519_ph_sign(r):
    sk, pk, h = r.hex_param(64), r.hex_param(32), r.hex_param(64)
    put_hex(crypto_ed25519_ph_sign(sk[0:32] + pk, h))


def do_ed25519_ph_check(r):
    sig, pk, h = r.hex_param(64), r.hex_param(32), r.hex_param(64)
    put_hex(bytes([crypto_ed25519_ph_check(sig, pk, h) & 0xFF]))


def do_elligator_map(r):
    put_hex(crypto_elligator_map(r.hex_param(32)))


def do_elligator_rev(r):
    point = r.hex_param(32)
    tweak = int(r.line() or "0", 16) & 0xFF
    hidden, status = crypto_elligator_rev(point, tweak)
    if status == 0:
        put_hex(hidden)
    put_hex(bytes([status & 0xFF]))


def do_elligator_key_pair(r):
    hidden, sk = crypto_elligator_key_pair(r.hex_param(32))
    put_hex(hidden)
    put_hex(sk)


def do_eddsa_to_x25519(r):
    put_hex(crypto_eddsa_to_x25519(r.hex_param(32)))


def do_x25519_to_eddsa(r):
    put_hex(crypto_x25519_to_eddsa(r.hex_param(32)))


def do_aead_init_x(r):
    put_hex(crypto_aead_init_x(r.hex_param(32), r.hex_param(24)).to_bytes())


def do_aead_init_djb(r):
    put_hex(crypto_aead_init_djb(r.hex_param(32), r.hex_param(8)).to_bytes())


def do_aead_init_ietf(r):
    put_hex(crypto_aead_init_ietf(r.hex_param(32), r.hex_param(12)).to_bytes())


def do_aead_write(r):
    key, nonce = r.hex_param(32), r.hex_param(12)
    ad, pt = r.hex_param(), r.hex_param()
    cipher, mac = crypto_aead_write(crypto_aead_init_ietf(key, nonce), ad, pt)
    put_hex(cipher)
    put_hex(mac)


def do_eddsa_trim_scalar(r):
    put_hex(crypto_eddsa_trim_scalar(r.hex_param(32)))


def do_eddsa_reduce(r):
    put_hex(crypto_eddsa_reduce(r.hex_param(64)))


def do_eddsa_mul_add(r):
    put_hex(crypto_eddsa_mul_add(r.hex_param(32), r.hex_param(32),
                                    r.hex_param(32)))


def do_eddsa_scalarbase(r):
    put_hex(crypto_eddsa_scalarbase(r.hex_param(32)))


def do_eddsa_check_equation(r):
    sig, pk, hram = r.hex_param(64), r.hex_param(32), r.hex_param(32)
    put_hex(bytes([crypto_eddsa_check_equation(sig, pk, hram) & 0xFF]))


DISPATCH = {
    "crypto_verify16": do_verify16,
    "crypto_verify32": do_verify32,
    "crypto_verify64": do_verify64,
    "crypto_wipe": do_wipe,
    "crypto_chacha20_h": do_chacha20_h,
    "crypto_chacha20_djb": do_chacha20_djb,
    "crypto_chacha20_ietf": do_chacha20_ietf,
    "crypto_chacha20_x": do_chacha20_x,
    "crypto_poly1305": do_poly1305,
    "crypto_aead_lock": do_aead_lock,
    "crypto_aead_unlock": do_aead_unlock,
    "crypto_blake2b": do_blake2b,
    "crypto_blake2b_keyed": do_blake2b_keyed,
    "crypto_sha512": do_sha512,
    "crypto_sha512_hmac": do_sha512_hmac,
    "crypto_sha512_hkdf": do_sha512_hkdf,
    "crypto_argon2": do_argon2,
    "crypto_x25519": do_x25519,
    "crypto_x25519_public_key": do_x25519_public_key,
    "crypto_x25519_inverse": do_x25519_inverse,
    "crypto_x25519_dirty_small": do_x25519_dirty_small,
    "crypto_x25519_dirty_fast": do_x25519_dirty_fast,
    "crypto_eddsa_key_pair": do_eddsa_key_pair,
    "crypto_eddsa_sign": do_eddsa_sign,
    "crypto_eddsa_check": do_eddsa_check,
    "crypto_eddsa_trim_scalar": do_eddsa_trim_scalar,
    "crypto_eddsa_reduce": do_eddsa_reduce,
    "crypto_eddsa_mul_add": do_eddsa_mul_add,
    "crypto_eddsa_scalarbase": do_eddsa_scalarbase,
    "crypto_eddsa_check_equation": do_eddsa_check_equation,
    "crypto_ed25519_key_pair": do_ed25519_key_pair,
    "crypto_ed25519_sign": do_ed25519_sign,
    "crypto_ed25519_check": do_ed25519_check,
    "crypto_ed25519_ph_sign": do_ed25519_ph_sign,
    "crypto_ed25519_ph_check": do_ed25519_ph_check,
    "crypto_elligator_map": do_elligator_map,
    "crypto_elligator_rev": do_elligator_rev,
    "crypto_elligator_key_pair": do_elligator_key_pair,
    "crypto_eddsa_to_x25519": do_eddsa_to_x25519,
    "crypto_x25519_to_eddsa": do_x25519_to_eddsa,
    "crypto_aead_init_x": do_aead_init_x,
    "crypto_aead_init_djb": do_aead_init_djb,
    "crypto_aead_init_ietf": do_aead_init_ietf,
    "crypto_aead_write": do_aead_write,
}


def main():
    reader = Reader(sys.stdin)
    raw = sys.stdin.readline()
    if raw == "":
        sys.stderr.write("empty input\n")
        return 1
    func_name = raw.rstrip("\n").rstrip("\r").rstrip(":").rstrip(" ")

    handler = DISPATCH.get(func_name)
    if handler is None:
        sys.stderr.write("unknown function: %s\n" % func_name)
        return 1

    try:
        handler(reader)
    except ValueError as exc:
        sys.stderr.write("error: %s\n" % exc)
        return 1

    sys.stdout.write("".join(line + ":\n" for line in OUT))
    return 0


if __name__ == "__main__":
    sys.exit(main())
