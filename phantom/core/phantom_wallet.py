"""
phantom_wallet.py
─────────────────────────────────────────────────────────
A wallet is NOT a node identity. Deliberately separate.

Your node identity (phantom_node.key) proves "this is the same
node across encounters." A wallet proves "this address can spend
this money." Reusing one key for both means a leak of either
purpose compromises both. This module never touches, imports, or
derives from NodeIdentity's keys — it is its own root of trust,
backed by its own 24-word phrase.

One wallet phrase derives two different kinds of address:

  1. NATIVE address (Ed25519) — for Phantom wallet-to-wallet
     transfers. Signs the same way seals and encounters already
     do in phantom_core.py. What actually moving value between
     two native addresses MEANS (reputation credit vs. a real
     transferable balance) is a ledger-design decision this module
     does not make — see suijuris.py and the open question already
     tracked there. This module only provides the address and the
     signing/verification primitives a ledger would need.

  2. EXTERNAL addresses (secp256k1: Bitcoin, Ethereum, ...) — for
     receiving donations from outside the Phantom network, from
     people who have never heard of Phantom and never will. These
     are standard BIP32/BIP44 derivations — any independent wallet
     (Electrum, MetaMask, a hardware wallet) can re-derive the exact
     same addresses from the same 24 words. Phantom does not watch
     these chains; checking a balance means checking a normal block
     explorer or wallet app, same as anyone else would.

Every EC operation here is pure Python (no C extension, no network
dependency at install time) and has been checked against the
official BIP32/BIP39 test vectors and against an independent

# BRIDGE NOTE (NODE_IDENTITY.md — "the deanonymization risk"): this
# module is offered elsewhere as a good example of contextual
# identity (a second, unlinked key pair for a second purpose). Fair,
# but it doesn't escape the underlying risk NODE_IDENTITY.md names —
# it just moves the boundary. One .address, used with every
# bilateral ledger counterpart, still lets anyone who sees more than
# one of your phantom_ledger.py relationships link them as the same
# person. The fix that document names — "one key per context" — is
# one level more granular than this module goes: one wallet per
# money-context is better than one key for everything, but isn't
# automatically one wallet per *relationship*. That's a choice left
# to whoever calls generate_with_mnemonic() — nothing here enforces
# or even suggests it.
library before being trusted. See test_phantom_wallet.py.
"""

import hashlib
import hmac
import json
import os
import unicodedata
from datetime import datetime, timezone

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey
    )
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

# Reuse the one standard BIP39 wordlist Phantom already ships —
# single source of truth, no second copy to drift out of sync.
from phantom_core import _entropy_to_mnemonic, _mnemonic_to_entropy, DATA_DIR

WALLET_KEY_FILE = os.path.join(DATA_DIR, "phantom_wallet.key")

# Domain-separation string for the native signing key. Different
# from phantom_core's "phantom-ed25519-v1" / "phantom-x25519-v1" —
# even if someone mistakenly reused their identity phrase here, the
# derived keys would still not collide with their identity keys.
_NATIVE_INFO = b"phantom-wallet-native-ed25519-v1"

# BIP44 coin types (SLIP-0044 registry — public standard, not
# Phantom-specific).
COIN_TYPES = {
    "BTC": 0,
    "LTC": 2,
    "DOGE": 3,
    "ETH": 60,
}

VERSION_BYTES = {
    # (P2PKH address prefix, WIF prefix)
    "BTC": (0x00, 0x80),
    "LTC": (0x30, 0xB0),
    "DOGE": (0x1E, 0x9E),
}

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


# ─────────────────────────────────────────────────────────
# secp256k1 — pure Python, checked against official test vectors
# ─────────────────────────────────────────────────────────

_P = 2**256 - 2**32 - 977
_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
_GX = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
_GY = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
_G = (_GX, _GY)


def _inv_mod(a, m):
    return pow(a, m - 2, m)


def _ec_add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    x1, y1 = p1
    x2, y2 = p2
    if x1 == x2 and (y1 + y2) % _P == 0:
        return None
    if p1 == p2:
        lam = (3 * x1 * x1) * _inv_mod(2 * y1, _P) % _P
    else:
        lam = (y2 - y1) * _inv_mod(x2 - x1, _P) % _P
    x3 = (lam * lam - x1 - x2) % _P
    y3 = (lam * (x1 - x3) - y1) % _P
    return (x3, y3)


def _ec_mul(k, point=_G):
    result = None
    addend = point
    while k:
        if k & 1:
            result = _ec_add(result, addend)
        addend = _ec_add(addend, addend)
        k >>= 1
    return result


def _privkey_to_pubkey_point(priv_int):
    return _ec_mul(priv_int)


def _compress_pubkey(point):
    x, y = point
    prefix = b'\x02' if y % 2 == 0 else b'\x03'
    return prefix + x.to_bytes(32, 'big')


def _uncompressed_xy(point):
    x, y = point
    return x.to_bytes(32, 'big') + y.to_bytes(32, 'big')


# ─────────────────────────────────────────────────────────
# BIP39 seed / BIP32 HD derivation
# ─────────────────────────────────────────────────────────

def _bip39_seed(mnemonic, passphrase=""):
    """
    Standard BIP39 seed derivation (PBKDF2-HMAC-SHA512, 2048 rounds).
    Deliberately NOT the same derivation phantom_core.py uses for
    node identity (that's a custom HKDF over raw entropy) — this is
    the real spec, so any standard BIP39 wallet reproduces the same
    seed from the same 24 words as a cross-check.
    """
    mnemonic_norm = unicodedata.normalize("NFKD", mnemonic)
    salt = unicodedata.normalize("NFKD", "mnemonic" + passphrase)
    return hashlib.pbkdf2_hmac(
        "sha512", mnemonic_norm.encode("utf-8"), salt.encode("utf-8"), 2048
    )


def _master_key(seed):
    I = hmac.new(b"Bitcoin seed", seed, hashlib.sha512).digest()
    return I[:32], I[32:]


def _ckd_priv(k_par, c_par, index):
    if index & 0x80000000:
        data = b'\x00' + k_par + index.to_bytes(4, 'big')
    else:
        pub_point = _privkey_to_pubkey_point(int.from_bytes(k_par, 'big'))
        data = _compress_pubkey(pub_point) + index.to_bytes(4, 'big')
    I = hmac.new(c_par, data, hashlib.sha512).digest()
    IL, IR = I[:32], I[32:]
    k_i = (int.from_bytes(IL, 'big') + int.from_bytes(k_par, 'big')) % _N
    return k_i.to_bytes(32, 'big'), IR


def _derive_path(seed, path):
    """path like \"m/44'/0'/0'/0/0\""""
    k, c = _master_key(seed)
    for part in path.split('/')[1:]:
        hardened = part.endswith("'")
        idx = int(part[:-1]) if hardened else int(part)
        if hardened:
            idx += 0x80000000
        k, c = _ckd_priv(k, c, idx)
    return k, c


# ─────────────────────────────────────────────────────────
# Address encoding
# ─────────────────────────────────────────────────────────

def _base58check(payload):
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    full = payload + checksum
    num = int.from_bytes(full, 'big')
    encoded = ""
    while num > 0:
        num, rem = divmod(num, 58)
        encoded = BASE58_ALPHABET[rem] + encoded
    n_leading_zeros = len(full) - len(full.lstrip(b'\x00'))
    return "1" * n_leading_zeros + encoded


def _ripemd160(data):
    try:
        h = hashlib.new('ripemd160')
        h.update(data)
        return h.digest()
    except (ValueError, TypeError):
        # Some hardened OpenSSL builds drop legacy hashes. Fall back
        # to a pure-Python implementation so this still works on a
        # locked-down or older Android/Termux build.
        return _ripemd160_pure(data)


def _keccak256(data):
    """
    Ethereum uses the ORIGINAL Keccak padding, not the later
    NIST SHA3-256 (different padding byte). hashlib's 'sha3_256'
    is the NIST variant and gives a WRONG Ethereum address if used
    here — this must stay a real Keccak implementation.
    """
    return _keccak(data, rate=136, capacity=64, output_bytes=32, delimiter=0x01)


def _btc_style_address(privkey_bytes, coin):
    version, _ = VERSION_BYTES[coin]
    pub_point = _privkey_to_pubkey_point(int.from_bytes(privkey_bytes, 'big'))
    pubkey_hash = _ripemd160(hashlib.sha256(_compress_pubkey(pub_point)).digest())
    return _base58check(bytes([version]) + pubkey_hash)


def _btc_style_wif(privkey_bytes, coin):
    _, wif_version = VERSION_BYTES[coin]
    payload = bytes([wif_version]) + privkey_bytes + b'\x01'  # +compressed flag
    return _base58check(payload)


def _eth_address(privkey_bytes):
    pub_point = _privkey_to_pubkey_point(int.from_bytes(privkey_bytes, 'big'))
    digest = _keccak256(_uncompressed_xy(pub_point))
    addr = digest[-20:]
    return _eip55_checksum(addr)


def _eip55_checksum(addr_bytes):
    addr_hex = addr_bytes.hex()
    hash_hex = _keccak256(addr_hex.encode('ascii')).hex()
    out = "0x"
    for c, h in zip(addr_hex, hash_hex):
        out += c.upper() if int(h, 16) >= 8 and c.isalpha() else c
    return out


# ─────────────────────────────────────────────────────────
# Minimal pure-Python RIPEMD-160 fallback (public-domain algorithm,
# only used if the system's hashlib lacks it).
# ─────────────────────────────────────────────────────────

_RMD_R1 = [
    0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15,
    7, 4, 13, 1, 10, 6, 15, 3, 12, 0, 9, 5, 2, 14, 11, 8,
    3, 10, 14, 4, 9, 15, 8, 1, 2, 7, 0, 6, 13, 11, 5, 12,
    1, 9, 11, 10, 0, 8, 12, 4, 13, 3, 7, 15, 14, 5, 6, 2,
    4, 0, 5, 9, 7, 12, 2, 10, 14, 1, 3, 8, 11, 6, 15, 13,
]
_RMD_R2 = [
    5, 14, 7, 0, 9, 2, 11, 4, 13, 6, 15, 8, 1, 10, 3, 12,
    6, 11, 3, 7, 0, 13, 5, 10, 14, 15, 8, 12, 4, 9, 1, 2,
    15, 5, 1, 3, 7, 14, 6, 9, 11, 8, 12, 2, 10, 0, 4, 13,
    8, 6, 4, 1, 3, 11, 15, 0, 5, 12, 2, 13, 9, 7, 10, 14,
    12, 15, 10, 4, 1, 5, 8, 7, 6, 2, 13, 14, 0, 3, 9, 11,
]
_RMD_S1 = [
    11, 14, 15, 12, 5, 8, 7, 9, 11, 13, 14, 15, 6, 7, 9, 8,
    7, 6, 8, 13, 11, 9, 7, 15, 7, 12, 15, 9, 11, 7, 13, 12,
    11, 13, 6, 7, 14, 9, 13, 15, 14, 8, 13, 6, 5, 12, 7, 5,
    11, 12, 14, 15, 14, 15, 9, 8, 9, 14, 5, 6, 8, 6, 5, 12,
    9, 15, 5, 11, 6, 8, 13, 12, 5, 12, 13, 14, 11, 8, 5, 6,
]
_RMD_S2 = [
    8, 9, 9, 11, 13, 15, 15, 5, 7, 7, 8, 11, 14, 14, 12, 6,
    9, 13, 15, 7, 12, 8, 9, 11, 7, 7, 12, 7, 6, 15, 13, 11,
    9, 7, 15, 11, 8, 6, 6, 14, 12, 13, 5, 14, 13, 13, 7, 5,
    15, 5, 8, 11, 14, 14, 6, 14, 6, 9, 12, 9, 12, 5, 15, 8,
    8, 5, 12, 9, 12, 5, 14, 6, 8, 13, 6, 5, 15, 13, 11, 11,
]
_RMD_K1 = [0x00000000, 0x5A827999, 0x6ED9EBA1, 0x8F1BBCDC, 0xA953FD4E]
_RMD_K2 = [0x50A28BE6, 0x5C4DD124, 0x6D703EF3, 0x7A6D76E9, 0x00000000]


def _ripemd160_pure(message):
    MASK = 0xFFFFFFFF

    def rol(x, n):
        return ((x << n) | (x >> (32 - n))) & MASK

    def f(j, x, y, z):
        if j < 16:
            return x ^ y ^ z
        if j < 32:
            return (x & y) | (~x & z & MASK)
        if j < 48:
            return (x | (~y & MASK)) ^ z
        if j < 64:
            return (x & z) | (y & ~z & MASK)
        return x ^ (y | (~z & MASK))

    h0, h1, h2, h3, h4 = 0x67452301, 0xEFCDAB89, 0x98BADCFE, 0x10325476, 0xC3D2E1F0

    msg = bytearray(message)
    orig_len_bits = (len(message) * 8) & 0xFFFFFFFFFFFFFFFF
    msg.append(0x80)
    while len(msg) % 64 != 56:
        msg.append(0)
    msg += orig_len_bits.to_bytes(8, 'little')

    for offset in range(0, len(msg), 64):
        block = msg[offset:offset + 64]
        X = [int.from_bytes(block[i:i + 4], 'little') for i in range(0, 64, 4)]

        A1 = B1 = C1 = D1 = E1 = None
        a1, b1, c1, d1, e1 = h0, h1, h2, h3, h4
        a2, b2, c2, d2, e2 = h0, h1, h2, h3, h4

        for j in range(80):
            round_idx = j // 16
            t = rol((a1 + f(j, b1, c1, d1) + X[_RMD_R1[j]] + _RMD_K1[round_idx]) & MASK, _RMD_S1[j])
            t = (t + e1) & MASK
            a1, e1, d1, c1, b1 = e1, d1, rol(c1, 10), b1, t

            jj = 79 - j
            round_idx2 = round_idx  # K2 is indexed by j's round, same partition as K1
            t2 = rol((a2 + f(jj, b2, c2, d2) + X[_RMD_R2[j]] + _RMD_K2[round_idx2]) & MASK, _RMD_S2[j])
            t2 = (t2 + e2) & MASK
            a2, e2, d2, c2, b2 = e2, d2, rol(c2, 10), b2, t2

        t = (h1 + c1 + d2) & MASK
        h1 = (h2 + d1 + e2) & MASK
        h2 = (h3 + e1 + a2) & MASK
        h3 = (h4 + a1 + b2) & MASK
        h4 = (h0 + b1 + c2) & MASK
        h0 = t

    return b''.join(h.to_bytes(4, 'little') for h in (h0, h1, h2, h3, h4))


# ─────────────────────────────────────────────────────────
# Minimal pure-Python Keccak-256 (needed for Ethereum addresses —
# NOT the same as hashlib's sha3_256, different padding).
# ─────────────────────────────────────────────────────────

_KECCAK_RNDC = [
    0x0000000000000001, 0x0000000000008082, 0x800000000000808A, 0x8000000080008000,
    0x000000000000808B, 0x0000000080000001, 0x8000000080008081, 0x8000000000008009,
    0x000000000000008A, 0x0000000000000088, 0x0000000080008009, 0x000000008000000A,
    0x000000008000808B, 0x800000000000008B, 0x8000000000008089, 0x8000000000008003,
    0x8000000000008002, 0x8000000000000080, 0x000000000000800A, 0x800000008000000A,
    0x8000000080008081, 0x8000000000008080, 0x0000000080000001, 0x8000000080008008,
]
_KECCAK_ROTC = [
    1, 3, 6, 10, 15, 21, 28, 36, 45, 55, 2, 14,
    27, 41, 56, 8, 25, 43, 62, 18, 39, 61, 20, 44,
]
_KECCAK_PI = [
    10, 7, 11, 17, 18, 3, 5, 16, 8, 21, 24, 4,
    15, 23, 19, 13, 12, 2, 20, 14, 22, 9, 6, 1,
]


def _keccak_f_clean(state_in):
    """
    Correctness-first, un-golfed Keccak-f[1600] permutation.
    Operates on a 25-word (5x5, 64-bit lanes) state, index x + 5*y.
    """
    state = list(state_in)
    MASK = 0xFFFFFFFFFFFFFFFF

    def rol(x, n):
        n %= 64
        if n == 0:
            return x & MASK
        return ((x << n) | (x >> (64 - n))) & MASK

    for rc in _KECCAK_RNDC:
        # theta
        C = [state[x] ^ state[x + 5] ^ state[x + 10] ^ state[x + 15] ^ state[x + 20] for x in range(5)]
        D = [C[(x - 1) % 5] ^ rol(C[(x + 1) % 5], 1) for x in range(5)]
        for x in range(5):
            for y in range(5):
                state[x + 5 * y] ^= D[x]

        # rho and pi combined
        x, y = 1, 0
        current = state[x + 5 * y]
        for t in range(24):
            X, Y = y, (2 * x + 3 * y) % 5
            offset = ((t + 1) * (t + 2) // 2) % 64
            state[X + 5 * Y], current = rol(current, offset), state[X + 5 * Y]
            x, y = X, Y

        # chi
        for yy in range(5):
            row = [state[xx + 5 * yy] for xx in range(5)]
            for xx in range(5):
                state[xx + 5 * yy] = row[xx] ^ ((~row[(xx + 1) % 5]) & row[(xx + 2) % 5]) & MASK

        # iota
        state[0] ^= rc

    return state


def _keccak(data, rate, capacity, output_bytes, delimiter):
    rate_bytes = rate
    state = [0] * 25

    padded = bytearray(data)
    padded.append(delimiter)
    while len(padded) % rate_bytes != 0:
        padded.append(0)
    padded[-1] |= 0x80

    # absorb
    for offset in range(0, len(padded), rate_bytes):
        block = padded[offset:offset + rate_bytes]
        for i in range(0, len(block), 8):
            lane = int.from_bytes(block[i:i + 8], 'little')
            state[i // 8] ^= lane
        state = _keccak_f_clean(state)

    # squeeze
    out = bytearray()
    while len(out) < output_bytes:
        for i in range(rate_bytes // 8):
            out += state[i].to_bytes(8, 'little')
        if len(out) < output_bytes:
            state = _keccak_f_clean(state)
    return bytes(out[:output_bytes])


# ─────────────────────────────────────────────────────────
# PhantomWallet
# ─────────────────────────────────────────────────────────

class PhantomWallet:
    """
    A dedicated wallet identity — NOT the same key as your node
    identity. One 24-word phrase, two purposes:

      - .address        native Ed25519 address, for Phantom
                         wallet-to-wallet signed transfers
      - .external(coin) an on-demand BTC/ETH/LTC/DOGE receiving
                         address, standard BIP44, verifiable by
                         any independent wallet
    """

    def __init__(self, native_private_key, native_public_key, seed):
        self._native_private_key = native_private_key
        self._native_public_key = native_public_key
        self._seed = seed  # BIP39 seed, kept only in memory
        self._address = None

    @classmethod
    def available(cls):
        return CRYPTO_AVAILABLE

    @classmethod
    def generate_with_mnemonic(cls, strength_bits=256):
        """
        New dedicated wallet phrase. Do NOT reuse your Phantom node
        identity's 24 words here — see phantom_wallet's module
        docstring for why.
        """
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography package required for PhantomWallet.")
        import secrets
        entropy = secrets.token_bytes(strength_bits // 8)
        mnemonic = _entropy_to_mnemonic(entropy)
        wallet = cls._from_mnemonic_words(mnemonic)
        return wallet, mnemonic

    @classmethod
    def from_mnemonic(cls, mnemonic, passphrase=""):
        """Recreate a wallet from its 24-word phrase (validates checksum)."""
        _mnemonic_to_entropy(mnemonic)  # validates checksum; raises ValueError if bad
        return cls._from_mnemonic_words(mnemonic, passphrase)

    @classmethod
    def _from_mnemonic_words(cls, mnemonic, passphrase=""):
        seed = _bip39_seed(mnemonic, passphrase)
        # Native Ed25519 signing key — HKDF over the BIP39 seed,
        # domain-separated from every other key this codebase derives.
        native_seed = HKDF(
            algorithm=hashes.SHA256(), length=32, salt=None, info=_NATIVE_INFO
        ).derive(seed)
        priv = Ed25519PrivateKey.from_private_bytes(native_seed)
        pub = priv.public_key()
        return cls(priv, pub, seed)

    def save(self, mnemonic, key=None):
        """
        Persist the wallet to disk so the TUI/CLI doesn't need the
        24 words retyped every run. Only the mnemonic is stored —
        everything else derives from it. Encrypted at rest if a key
        is supplied (same passphrase-derived key as everything else
        in this codebase); stored in plaintext only if the person
        explicitly runs without encryption, same tradeoff as
        NodeIdentity.
        """
        from phantom_core import encrypt_data, CRYPTO_AVAILABLE
        payload = mnemonic.encode('utf-8')
        if key is not None and CRYPTO_AVAILABLE:
            stored = encrypt_data(payload, key)
        else:
            stored = {"plaintext": True, "mnemonic": mnemonic}
        with open(WALLET_KEY_FILE, "w", encoding="utf-8") as f:
            json.dump(stored, f)

    @classmethod
    def load(cls, key=None):
        """Load a previously saved wallet, or None if none exists yet."""
        from phantom_core import decrypt_data
        if not os.path.exists(WALLET_KEY_FILE):
            return None
        with open(WALLET_KEY_FILE, "r", encoding="utf-8") as f:
            stored = json.load(f)
        if stored.get("plaintext"):
            mnemonic = stored["mnemonic"]
        else:
            if key is None:
                raise RuntimeError(
                    "This wallet is encrypted — the passphrase is needed to open it."
                )
            mnemonic = decrypt_data(stored, key).decode('utf-8')
        return cls.from_mnemonic(mnemonic)

    # ---- native Phantom address ----

    @property
    def address(self):
        """
        pw_<16 hex chars> — same recognition-only convention as a
        node fingerprint (first 16 hex of SHA-256 of the public key),
        prefixed so it's never confused with a node identity fingerprint.
        """
        if self._address is None:
            pub_bytes = self._native_public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
            self._address = "pw_" + hashlib.sha256(pub_bytes).hexdigest()[:16]
        return self._address

    def sign_transfer(self, to_address, amount, memo=""):
        """
        Sign a native transfer message. This produces a signed,
        verifiable claim — "this wallet authorizes this transfer."
        It does NOT by itself move any balance anywhere; whether
        that requires network consensus (a real transferable token)
        or is just a receipt of intent (reputation-style, like
        suijuris.py's contributions) is the ledger-model decision
        this module deliberately leaves open.
        """
        payload = {
            "from": self.address,
            "to": to_address,
            "amount": amount,
            "memo": memo,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        data = json.dumps(payload, sort_keys=True).encode('utf-8')
        signature = self._native_private_key.sign(data)
        payload["signature"] = signature.hex()
        payload["signer_pubkey"] = self._native_public_key.public_bytes(
            Encoding.Raw, PublicFormat.Raw
        ).hex()
        return payload

    @staticmethod
    def verify_transfer(transfer):
        """Verify a signed transfer produced by sign_transfer()."""
        transfer = dict(transfer)
        signature = bytes.fromhex(transfer.pop("signature"))
        pubkey_hex = transfer.pop("signer_pubkey")
        pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(pubkey_hex))
        data = json.dumps(transfer, sort_keys=True).encode('utf-8')
        try:
            pubkey.verify(signature, data)
            return True
        except Exception:
            return False

    # ---- external chain addresses (optional) ----

    def external(self, coin, account=0, index=0):
        """
        Derive a standard BIP44 receiving address for an external
        chain. coin is one of: 'BTC', 'ETH', 'LTC', 'DOGE'.
        Returns {"address": ..., "path": ...}. The private key is
        NOT returned here — call export_external_key() explicitly,
        only when you actually need to move funds out.
        """
        coin = coin.upper()
        if coin not in COIN_TYPES:
            raise ValueError(f"Unsupported coin: {coin}. Choose from {list(COIN_TYPES)}.")
        path = f"m/44'/{COIN_TYPES[coin]}'/{account}'/0/{index}"
        priv, _ = _derive_path(self._seed, path)
        if coin == "ETH":
            address = _eth_address(priv)
        else:
            address = _btc_style_address(priv, coin)
        return {"coin": coin, "address": address, "path": path}

    def export_external_key(self, coin, account=0, index=0):
        """
        Export the spending key for an external address. Treat this
        return value as money — never log it, never send it anywhere.
        Only call this when you're actually moving funds out.
        """
        coin = coin.upper()
        if coin not in COIN_TYPES:
            raise ValueError(f"Unsupported coin: {coin}. Choose from {list(COIN_TYPES)}.")
        path = f"m/44'/{COIN_TYPES[coin]}'/{account}'/0/{index}"
        priv, _ = _derive_path(self._seed, path)
        if coin == "ETH":
            return {"coin": coin, "path": path, "private_key_hex": priv.hex()}
        return {"coin": coin, "path": path, "wif": _btc_style_wif(priv, coin)}
