import os
import unittest

import ecdsa
from mnemonic import Mnemonic

import secp
from bip32_pure import BIP32, parse_path
from cosmos_address import make_matcher, privkey_to_address
from search_engine import Job, SearchEngine

# BIP39 test phrase; the address is the one Keplr shows for it on Cosmos Hub.
_PHRASE = "abandon " * 11 + "about"
_PHRASE_ADDR = "cosmos19rl4cm2hmr8afy4kldpxz3fka4jguq0auqdal4"
_PATH = "m/44'/118'/0'/0/0"


def _from_phrase(words: str, path: str) -> bytes:
    return BIP32.from_seed(Mnemonic("english").to_seed(words)).get_privkey_from_path(parse_path(path))


class TestCurve(unittest.TestCase):
    def test_backend_matches_python_ecdsa(self):
        for _ in range(50):
            priv = os.urandom(32)
            raw = ecdsa.SigningKey.from_string(priv, curve=ecdsa.SECP256k1).get_verifying_key().to_string()
            compressed = (b"\x02" if raw[-1] % 2 == 0 else b"\x03") + raw[:32]
            self.assertEqual(secp.pubkey_compressed(priv), compressed)
            self.assertEqual(secp.pubkey_xy(priv), raw)

    def test_invalid_key_rejected(self):
        with self.assertRaises(Exception):
            secp.pubkey_compressed(b"\x00" * 32)


class TestDerivation(unittest.TestCase):
    def test_known_phrase(self):
        self.assertEqual(privkey_to_address(_from_phrase(_PHRASE, _PATH), "cosmos"), _PHRASE_ADDR)

    def test_parse_path(self):
        h = 0x80000000
        self.assertEqual(parse_path("m/44'/118'/0'/0/7"), [44 + h, 118 + h, h, 0, 7])
        self.assertEqual(parse_path("m/44h/118h/0h/0/7"), [44 + h, 118 + h, h, 0, 7])

    def test_index_scanner_equals_full_derivation(self):
        root = BIP32.from_seed(Mnemonic("english").to_seed(_PHRASE))
        scanner = root.derive(parse_path("m/44'/118'/0'/0")).index_scanner()
        for i in (0, 1, 2, 17, 1000):
            self.assertEqual(scanner.child(i), _from_phrase(_PHRASE, f"m/44'/118'/0'/0/{i}"))


class TestEngine(unittest.TestCase):
    def _run(self, mode: str) -> dict:
        job = Job(matcher=make_matcher("osmo1q", ""), mode=mode, path=_PATH, report_every=50)
        with SearchEngine(job, 2) as engine:
            for _ in range(600):
                rec = engine.next_match(timeout=0.1)
                if rec:
                    return rec
        self.fail(f"no match in mode {mode}")

    def test_key_mode(self):
        rec = self._run("key")
        self.assertTrue(rec["address"].startswith("osmo1q"))
        self.assertEqual(privkey_to_address(bytes.fromhex(rec["private_key"]), "osmo"), rec["address"])
        self.assertNotIn("mnemonic", rec)

    def test_index_mode_is_recoverable_from_phrase(self):
        rec = self._run("index")
        self.assertTrue(rec["address"].startswith("osmo1q"))
        priv = _from_phrase(rec["mnemonic"], rec["path"])
        self.assertEqual(priv.hex(), rec["private_key"])
        self.assertEqual(privkey_to_address(priv, "osmo"), rec["address"])

    def test_mnemonic_mode_is_recoverable_from_phrase(self):
        rec = self._run("mnemonic")
        self.assertEqual(rec["path"], _PATH)
        self.assertEqual(privkey_to_address(_from_phrase(rec["mnemonic"], rec["path"]), "osmo"), rec["address"])

    def test_index_mode_needs_non_hardened_last_index(self):
        with self.assertRaises(ValueError):
            SearchEngine(Job(matcher=make_matcher("osmo1", ""), mode="index", path="m/44'/118'/0'"), 1)


if __name__ == "__main__":
    unittest.main()
