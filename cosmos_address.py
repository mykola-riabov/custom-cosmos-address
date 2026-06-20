"""Cosmos SDK Bech32 address derivation and vanity matching helpers."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

import ecdsa
from bech32 import bech32_encode, convertbits
from bip32_pure import BIP32
from mnemonic import Mnemonic

VERSION = "1.3.2-cpu"
HARDENED_OFFSET = 0x80000000
ALLOWED_BECH32 = "qpzry9x8gf2tvdw0s3jn54khce6mua7l"
ALLOWED_STRENGTHS = [128, 160, 192, 224, 256]
BECH32_CHARSET_SIZE = 32

_CURVE_ORDER = ecdsa.SECP256k1.order
_MNEMO = Mnemonic("english")


def _ripemd160(data: bytes) -> bytes:
    try:
        return hashlib.new("ripemd160", data).digest()
    except ValueError:
        from Crypto.Hash import RIPEMD160

        return RIPEMD160.new(data).digest()


@dataclass(frozen=True)
class DifficultyEstimate:
    """Rough vanity search difficulty (independent-char approximation)."""

    prefix_extra_chars: int
    suffix_chars: int
    constrained_chars: int
    expected_attempts: float
    overlap_warning: bool


def invalid_bech32_chars(part: str) -> list[str]:
    return [ch for ch in part if ch not in ALLOWED_BECH32]


def validate_pattern(prefix: str, suffix: str) -> None:
    prefix_body = prefix.split("1", 1)[-1]
    bad = set(invalid_bech32_chars(prefix_body) + invalid_bech32_chars(suffix))
    if bad:
        raise ValueError(
            f"Invalid Bech32 character(s): {', '.join(sorted(bad))}. "
            f"Allowed: {ALLOWED_BECH32}"
        )
    if "1" not in prefix:
        raise ValueError(f"Prefix must contain separator '1' (got {prefix!r})")


def hrp_from_prefix(prefix: str) -> str:
    return prefix.split("1", 1)[0]


def privkey_to_address(priv_bytes: bytes, hrp: str) -> str:
    sk = ecdsa.SigningKey.from_string(priv_bytes, curve=ecdsa.SECP256k1)
    vk = sk.get_verifying_key()
    pub_raw = vk.to_string()
    pubkey = (b"\x02" + pub_raw[:32]) if (pub_raw[-1] % 2 == 0) else (b"\x03" + pub_raw[:32])
    h1 = hashlib.sha256(pubkey).digest()
    h2 = _ripemd160(h1)
    return bech32_encode(hrp, convertbits(h2, 8, 5))


def matches_vanity(addr: str, prefix: str, suffix: str) -> bool:
    return addr.startswith(prefix) and addr.endswith(suffix)


def try_match_privkey(
    priv_bytes: bytes,
    prefix: str,
    suffix: str,
    hrp: str | None = None,
) -> str | None:
    hrp = hrp or hrp_from_prefix(prefix)
    try:
        addr = privkey_to_address(priv_bytes, hrp)
    except Exception:
        return None
    return addr if matches_vanity(addr, prefix, suffix) else None


def estimate_difficulty(prefix: str, suffix: str) -> DifficultyEstimate:
    """Approximate expected attempts (~32^-n per constrained char)."""
    prefix_body = prefix.split("1", 1)[-1]
    prefix_extra = len(prefix_body)
    suffix_len = len(suffix)
    overlap = prefix_extra + suffix_len > 0 and prefix.endswith(suffix) and len(suffix) > 0
    constrained = prefix_extra + suffix_len
    expected = float(BECH32_CHARSET_SIZE**constrained) if constrained else 1.0
    return DifficultyEstimate(
        prefix_extra_chars=prefix_extra,
        suffix_chars=suffix_len,
        constrained_chars=constrained,
        expected_attempts=expected,
        overlap_warning=overlap and len(prefix) > len(suffix),
    )


def random_privkey_from_entropy(strength_bits: int) -> bytes:
    if strength_bits not in ALLOWED_STRENGTHS:
        raise ValueError("Invalid strength_bits")

    nbytes = strength_bits // 8
    while True:
        raw = os.urandom(nbytes)
        if len(raw) != 32:
            raw = hashlib.sha256(raw).digest()
        priv_int = int.from_bytes(raw, "big")
        if 1 <= priv_int < _CURVE_ORDER:
            return raw


def mnemonic_to_privkey(strength_bits: int, derivation_path: str) -> tuple[bytes, str]:
    entropy_bytes = os.urandom(strength_bits // 8)
    words = _MNEMO.to_mnemonic(entropy_bytes)
    seed = _MNEMO.to_seed(words)
    bip32 = BIP32.from_seed(seed)
    path = derivation_path.lstrip("m/").split("/")
    path = [int(p.replace("'", "")) + HARDENED_OFFSET if "'" in p else int(p) for p in path]
    return bip32.get_privkey_from_path(path), words


def generate_keys_batch(
    batch_size: int,
    strength_bits: int,
    *,
    mnemonic: bool = False,
    derivation_path: str = "m/44'/118'/0'/0/0",
) -> tuple[list[bytes], list[str] | None]:
    if mnemonic:
        keys: list[bytes] = []
        mnemonics: list[str] = []
        for _ in range(batch_size):
            privkey, words = mnemonic_to_privkey(strength_bits, derivation_path)
            keys.append(privkey)
            mnemonics.append(words)
        return keys, mnemonics
    return [random_privkey_from_entropy(strength_bits) for _ in range(batch_size)], None


def check_key_indexed(
    item: tuple[int, bytes, str, str, str],
) -> tuple[int, str | None]:
    idx, priv_bytes, prefix, suffix, hrp = item
    return idx, try_match_privkey(priv_bytes, prefix, suffix, hrp)
