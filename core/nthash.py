"""NT hash of a password (MD4 of the UTF-16LE text), the NT-Password FreeRADIUS needs for MS-CHAP / MS-CHAPv2.

MikroTik RouterOS sends its management logins (SSH, Winbox, web) with MS-CHAPv2, which cannot be checked
against a salted SHA-256. OpenSSL 3 (Ubuntu 22.04 and later) no longer offers MD4 to hashlib, so a small pure
Python MD4 (RFC 1320) is used when hashlib has none.
"""
import hashlib
import struct


def _rotl(x, n):
    x &= 0xFFFFFFFF
    return ((x << n) | (x >> (32 - n))) & 0xFFFFFFFF


def _md4(data):
    msg = bytearray(data)
    bit_len = (len(msg) * 8) & 0xFFFFFFFFFFFFFFFF
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += struct.pack("<Q", bit_len)
    a, b, c, d = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476
    for off in range(0, len(msg), 64):
        x = struct.unpack("<16I", bytes(msg[off:off + 64]))
        aa, bb, cc, dd = a, b, c, d

        def f(x_, y, z):
            return (x_ & y) | (~x_ & z)

        def g(x_, y, z):
            return (x_ & y) | (x_ & z) | (y & z)

        def h(x_, y, z):
            return x_ ^ y ^ z

        for i in (0, 4, 8, 12):          # round 1
            a = _rotl(a + f(b, c, d) + x[i], 3)
            d = _rotl(d + f(a, b, c) + x[i + 1], 7)
            c = _rotl(c + f(d, a, b) + x[i + 2], 11)
            b = _rotl(b + f(c, d, a) + x[i + 3], 19)
        for i in (0, 1, 2, 3):           # round 2
            a = _rotl(a + g(b, c, d) + x[i] + 0x5A827999, 3)
            d = _rotl(d + g(a, b, c) + x[i + 4] + 0x5A827999, 5)
            c = _rotl(c + g(d, a, b) + x[i + 8] + 0x5A827999, 9)
            b = _rotl(b + g(c, d, a) + x[i + 12] + 0x5A827999, 13)
        for i in (0, 2, 1, 3):           # round 3
            a = _rotl(a + h(b, c, d) + x[i] + 0x6ED9EBA1, 3)
            d = _rotl(d + h(a, b, c) + x[i + 8] + 0x6ED9EBA1, 9)
            c = _rotl(c + h(d, a, b) + x[i + 4] + 0x6ED9EBA1, 11)
            b = _rotl(b + h(c, d, a) + x[i + 12] + 0x6ED9EBA1, 15)
        a, b, c, d = (a + aa) & 0xFFFFFFFF, (b + bb) & 0xFFFFFFFF, (c + cc) & 0xFFFFFFFF, (d + dd) & 0xFFFFFFFF
    return struct.pack("<4I", a, b, c, d)


def md4(data):
    try:
        return hashlib.new("md4", data).digest()
    except (ValueError, TypeError):
        return _md4(data)


def nt_hash(password):
    """32 upper-case hex characters, the form FreeRADIUS reads for NT-Password."""
    return md4(password.encode("utf-16-le")).hex().upper()
