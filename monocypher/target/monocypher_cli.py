
"""
monocypher_cli.py — Python twin of monocypher-cli.c.

Speaks the identical stdin/stdout hex protocol, so its output can be diffed
byte-for-byte against the C binary:

    function_name
    param_hex:
    param_hex:
    ...

writes

    result_hex:
    result_hex:

Usage:  echo -e "crypto_blake2b\\n00010203:" | python3 monocypher_cli.py
"""

import sys
import monocypher as mc


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
    put_int(mc.crypto_verify16(r.hex_param(16), r.hex_param(16)))


def do_verify32(r):
    put_int(mc.crypto_verify32(r.hex_param(32), r.hex_param(32)))


def do_verify64(r):
    put_int(mc.crypto_verify64(r.hex_param(64), r.hex_param(64)))


def do_wipe(r):
    put_hex(mc.crypto_wipe(bytearray(r.hex_param())))


def do_chacha20_h(r):
    put_hex(mc.crypto_chacha20_h(r.hex_param(32), r.hex_param(16)))


def do_chacha20_djb(r):
    key, nonce = r.hex_param(32), r.hex_param(8)
    plain = r.hex_param()
    ctr = int.from_bytes(r.hex_param(8), "little")
    cipher, new_ctr = mc.crypto_chacha20_djb(plain, key, nonce, ctr)
    put_hex(cipher)
    put_u64_le(new_ctr)


def do_chacha20_ietf(r):
    key, nonce = r.hex_param(32), r.hex_param(12)
    plain = r.hex_param()
    ctr = int.from_bytes(r.hex_param(4), "little")
    cipher, new_ctr = mc.crypto_chacha20_ietf(plain, key, nonce, ctr)
    put_hex(cipher)
    put_u32_le(new_ctr)


def do_chacha20_x(r):
    key, nonce = r.hex_param(32), r.hex_param(24)
    plain = r.hex_param()
    ctr = int.from_bytes(r.hex_param(8), "little")
    cipher, new_ctr = mc.crypto_chacha20_x(plain, key, nonce, ctr)
    put_hex(cipher)
    put_u64_le(new_ctr)


def do_poly1305(r):
    key = r.hex_param(32)
    put_hex(mc.crypto_poly1305(r.hex_param(), key))


def do_aead_lock(r):
    key, nonce = r.hex_param(32), r.hex_param(24)
    ad, pt = r.hex_param(), r.hex_param()
    cipher, mac = mc.crypto_aead_lock(key, nonce, ad, pt)
    put_hex(cipher)
    put_hex(mac)


def do_aead_unlock(r):
    key, nonce = r.hex_param(32), r.hex_param(24)
    ad, ct, mac = r.hex_param(), r.hex_param(), r.hex_param(16)
    plain, status = mc.crypto_aead_unlock(key, nonce, mac, ad, ct)
    if status == 0:
        put_hex(plain)
    put_hex(bytes([status & 0xFF]))


def do_blake2b(r):
    put_hex(mc.crypto_blake2b(r.hex_param(), 64))


def do_blake2b_keyed(r):
    msg = r.hex_param()
    key = r.hex_param()[:64]
    put_hex(mc.crypto_blake2b_keyed(msg, key, 64))


def do_sha512(r):
    put_hex(mc.crypto_sha512(r.hex_param()))


def do_sha512_hmac(r):
    key = r.hex_param()
    put_hex(mc.crypto_sha512_hmac(key, r.hex_param()))


def do_sha512_hkdf(r):
    ikm, salt, info = r.hex_param(), r.hex_param(), r.hex_param()
    okm_size = len(r.hex_param())
    put_hex(mc.crypto_sha512_hkdf(ikm, salt, info, okm_size))


def do_argon2(r):
    algo = int.from_bytes(r.hex_param(4), "little")
    blocks = int.from_bytes(r.hex_param(4), "little")
    passes = int.from_bytes(r.hex_param(4), "little")
    lanes = int.from_bytes(r.hex_param(4), "little")
    pwd, salt, key, ad = (r.hex_param(), r.hex_param(),
                          r.hex_param(), r.hex_param())
    hash_size = len(r.hex_param())
    put_hex(mc.crypto_argon2(hash_size, (algo, blocks, passes, lanes),
                             (pwd, salt), (key, ad)))


def do_x25519(r):
    put_hex(mc.crypto_x25519(r.hex_param(32), r.hex_param(32)))


def do_x25519_public_key(r):
    put_hex(mc.crypto_x25519_public_key(r.hex_param(32)))


def do_x25519_inverse(r):
    put_hex(mc.crypto_x25519_inverse(r.hex_param(32), r.hex_param(32)))


def do_x25519_dirty_small(r):
    put_hex(mc.crypto_x25519_dirty_small(r.hex_param(32)))


def do_x25519_dirty_fast(r):
    put_hex(mc.crypto_x25519_dirty_fast(r.hex_param(32)))


def do_eddsa_key_pair(r):
    sk, pk = mc.crypto_eddsa_key_pair(r.hex_param(32))
    put_hex(sk)
    put_hex(pk)


def do_eddsa_sign(r):
    sk, pk = r.hex_param(64), r.hex_param(32)
    msg = r.hex_param()
    put_hex(mc.crypto_eddsa_sign(sk[0:32] + pk, msg))


def do_eddsa_check(r):
    sig, pk = r.hex_param(64), r.hex_param(32)
    msg = r.hex_param()
    put_hex(bytes([mc.crypto_eddsa_check(sig, pk, msg) & 0xFF]))


def do_ed25519_key_pair(r):
    sk, pk = mc.crypto_ed25519_key_pair(r.hex_param(32))
    put_hex(sk)
    put_hex(pk)


def do_ed25519_sign(r):
    sk, pk = r.hex_param(64), r.hex_param(32)
    msg = r.hex_param()
    put_hex(mc.crypto_ed25519_sign(sk[0:32] + pk, msg))


def do_ed25519_check(r):
    sig, pk = r.hex_param(64), r.hex_param(32)
    msg = r.hex_param()
    put_hex(bytes([mc.crypto_ed25519_check(sig, pk, msg) & 0xFF]))


def do_ed25519_ph_sign(r):
    sk, pk, h = r.hex_param(64), r.hex_param(32), r.hex_param(64)
    put_hex(mc.crypto_ed25519_ph_sign(sk[0:32] + pk, h))


def do_ed25519_ph_check(r):
    sig, pk, h = r.hex_param(64), r.hex_param(32), r.hex_param(64)
    put_hex(bytes([mc.crypto_ed25519_ph_check(sig, pk, h) & 0xFF]))


def do_elligator_map(r):
    put_hex(mc.crypto_elligator_map(r.hex_param(32)))


def do_elligator_rev(r):
    point = r.hex_param(32)
    tweak = int(r.line() or "0", 16) & 0xFF
    hidden, status = mc.crypto_elligator_rev(point, tweak)
    if status == 0:
        put_hex(hidden)
    put_hex(bytes([status & 0xFF]))


def do_elligator_key_pair(r):
    hidden, sk = mc.crypto_elligator_key_pair(r.hex_param(32))
    put_hex(hidden)
    put_hex(sk)


def do_eddsa_to_x25519(r):
    put_hex(mc.crypto_eddsa_to_x25519(r.hex_param(32)))


def do_x25519_to_eddsa(r):
    put_hex(mc.crypto_x25519_to_eddsa(r.hex_param(32)))


def do_aead_init_x(r):
    put_hex(mc.crypto_aead_init_x(r.hex_param(32), r.hex_param(24)).to_bytes())


def do_aead_init_djb(r):
    put_hex(mc.crypto_aead_init_djb(r.hex_param(32), r.hex_param(8)).to_bytes())


def do_aead_init_ietf(r):
    put_hex(mc.crypto_aead_init_ietf(r.hex_param(32), r.hex_param(12)).to_bytes())


def do_aead_write(r):
    key, nonce = r.hex_param(32), r.hex_param(12)
    ad, pt = r.hex_param(), r.hex_param()
    cipher, mac = mc.crypto_aead_write(mc.crypto_aead_init_ietf(key, nonce), ad, pt)
    put_hex(cipher)
    put_hex(mac)


def do_eddsa_trim_scalar(r):
    put_hex(mc.crypto_eddsa_trim_scalar(r.hex_param(32)))


def do_eddsa_reduce(r):
    put_hex(mc.crypto_eddsa_reduce(r.hex_param(64)))


def do_eddsa_mul_add(r):
    put_hex(mc.crypto_eddsa_mul_add(r.hex_param(32), r.hex_param(32),
                                    r.hex_param(32)))


def do_eddsa_scalarbase(r):
    put_hex(mc.crypto_eddsa_scalarbase(r.hex_param(32)))


def do_eddsa_check_equation(r):
    sig, pk, hram = r.hex_param(64), r.hex_param(32), r.hex_param(32)
    put_hex(bytes([mc.crypto_eddsa_check_equation(sig, pk, hram) & 0xFF]))


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
