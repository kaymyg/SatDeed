"""BIP-340 Schnorr signatures over secp256k1, in pure Python.

This module exists so the reference implementation has no third party
dependencies and can be read end to end by anyone evaluating the standard. It
is written for clarity rather than speed and it is NOT constant time.

Do not use this module to handle production private keys. Use libsecp256k1
through coincurve, or a hardware signer, or a wallet. It is here so that the
worked examples in this repository can be regenerated and checked by anyone
with a Python interpreter and nothing else.
"""

from __future__ import annotations

import hashlib
import secrets

from .hashing import tagged_hash

__all__ = [
    "P",
    "N",
    "pubkey_from_seckey",
    "sign",
    "verify",
    "generate_seckey",
]

# secp256k1 domain parameters.
P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
G = (Gx, Gy)

Point = tuple[int, int] | None


def _inv(a: int, m: int = P) -> int:
    return pow(a, m - 2, m)


def point_add(p1: Point, p2: Point) -> Point:
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    if p1[0] == p2[0] and (p1[1] + p2[1]) % P == 0:
        return None
    if p1 == p2:
        lam = (3 * p1[0] * p1[0] * _inv(2 * p1[1])) % P
    else:
        lam = ((p2[1] - p1[1]) * _inv(p2[0] - p1[0])) % P
    x3 = (lam * lam - p1[0] - p2[0]) % P
    return (x3, (lam * (p1[0] - x3) - p1[1]) % P)


def point_mul(p: Point, k: int) -> Point:
    result: Point = None
    addend = p
    while k:
        if k & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        k >>= 1
    return result


def _bytes_from_int(x: int) -> bytes:
    return x.to_bytes(32, "big")


def _int_from_bytes(b: bytes) -> int:
    return int.from_bytes(b, "big")


def _has_even_y(p: Point) -> bool:
    assert p is not None
    return p[1] % 2 == 0


def _lift_x(x: int) -> Point:
    """Recover the even y point for an x only public key, per BIP-340."""
    if x >= P:
        return None
    y_sq = (pow(x, 3, P) + 7) % P
    y = pow(y_sq, (P + 1) // 4, P)
    if pow(y, 2, P) != y_sq:
        return None
    return (x, y if y % 2 == 0 else P - y)


def generate_seckey() -> bytes:
    """Return a fresh 32 byte secret key from the OS entropy source."""
    while True:
        candidate = secrets.token_bytes(32)
        if 0 < _int_from_bytes(candidate) < N:
            return candidate


def pubkey_from_seckey(seckey: bytes) -> bytes:
    """Return the 32 byte x only public key for ``seckey``."""
    d0 = _int_from_bytes(seckey)
    if not 0 < d0 < N:
        raise ValueError("secret key is not in the range [1, n-1]")
    point = point_mul(G, d0)
    assert point is not None
    return _bytes_from_int(point[0])


def sign(msg32: bytes, seckey: bytes, aux_rand: bytes | None = None) -> bytes:
    """Produce a 64 byte BIP-340 signature over the 32 byte message."""
    if len(msg32) != 32:
        raise ValueError("message must be exactly 32 bytes")
    if aux_rand is None:
        aux_rand = secrets.token_bytes(32)
    if len(aux_rand) != 32:
        raise ValueError("auxiliary randomness must be exactly 32 bytes")

    d0 = _int_from_bytes(seckey)
    if not 0 < d0 < N:
        raise ValueError("secret key is not in the range [1, n-1]")
    point = point_mul(G, d0)
    assert point is not None
    d = d0 if _has_even_y(point) else N - d0
    px = _bytes_from_int(point[0])

    t = d ^ _int_from_bytes(tagged_hash("BIP0340/aux", aux_rand))
    rand = tagged_hash("BIP0340/nonce", _bytes_from_int(t), px, msg32)
    k0 = _int_from_bytes(rand) % N
    if k0 == 0:
        raise RuntimeError("derived nonce was zero, which has negligible probability")
    r_point = point_mul(G, k0)
    assert r_point is not None
    k = k0 if _has_even_y(r_point) else N - k0
    rx = _bytes_from_int(r_point[0])

    e = _int_from_bytes(tagged_hash("BIP0340/challenge", rx, px, msg32)) % N
    sig = rx + _bytes_from_int((k + e * d) % N)
    if not verify(msg32, px, sig):
        raise RuntimeError("signature failed self verification")
    return sig


def verify(msg32: bytes, pubkey32: bytes, sig64: bytes) -> bool:
    """Verify a 64 byte BIP-340 signature. Returns False rather than raising."""
    if len(msg32) != 32 or len(pubkey32) != 32 or len(sig64) != 64:
        return False
    point = _lift_x(_int_from_bytes(pubkey32))
    if point is None:
        return False
    r = _int_from_bytes(sig64[:32])
    s = _int_from_bytes(sig64[32:])
    if r >= P or s >= N:
        return False
    e = _int_from_bytes(
        tagged_hash("BIP0340/challenge", sig64[:32], pubkey32, msg32)
    ) % N
    candidate = point_add(point_mul(G, s), point_mul(point, N - e))
    if candidate is None:
        return False
    if not _has_even_y(candidate):
        return False
    return candidate[0] == r


# Convenience alias used by the verification pipeline.
def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()
