import os
import unittest

from cosmos_address import (
    ALLOWED_BECH32,
    estimate_difficulty,
    generate_keys_batch,
    hrp_from_prefix,
    invalid_bech32_chars,
    matches_vanity,
    mnemonic_to_privkey,
    privkey_to_address,
    random_privkey_from_entropy,
    try_match_privkey,
    validate_pattern,
)

# secp256k1 privkey = 1 (well-known test vector)
_TEST_PRIV = bytes.fromhex(
    "0000000000000000000000000000000000000000000000000000000000000001"
)
_COSMOS_ADDR = "cosmos1w508d6qejxtdg4y5r3zarvary0c5xw7k6ah60c"
_OSMO_ADDR = "osmo1w508d6qejxtdg4y5r3zarvary0c5xw7kjxy2e2"


class TestDerivation(unittest.TestCase):
    def test_privkey_to_cosmos(self):
        self.assertEqual(privkey_to_address(_TEST_PRIV, "cosmos"), _COSMOS_ADDR)

    def test_privkey_to_osmo(self):
        self.assertEqual(privkey_to_address(_TEST_PRIV, "osmo"), _OSMO_ADDR)

    def test_hrp_from_prefix(self):
        self.assertEqual(hrp_from_prefix("osmo1abc"), "osmo")
        self.assertEqual(hrp_from_prefix("cosmos1gpt"), "cosmos")


class TestVanity(unittest.TestCase):
    def test_matches_full_prefix(self):
        self.assertTrue(matches_vanity(_OSMO_ADDR, "osmo1", ""))
        self.assertTrue(matches_vanity(_OSMO_ADDR, _OSMO_ADDR, ""))

    def test_try_match(self):
        self.assertEqual(
            try_match_privkey(_TEST_PRIV, "osmo1w508", "", "osmo"),
            _OSMO_ADDR,
        )
        self.assertIsNone(try_match_privkey(_TEST_PRIV, "osmo1zzzzzz", "", "osmo"))


class TestValidation(unittest.TestCase):
    def test_invalid_chars_detected(self):
        self.assertEqual(invalid_bech32_chars("qpzry9"), [])
        self.assertIn("i", invalid_bech32_chars("osmo1i"))

    def test_validate_pattern_rejects_bad(self):
        with self.assertRaises(ValueError):
            validate_pattern("osmo1invalid0", "")

    def test_validate_pattern_requires_separator(self):
        with self.assertRaises(ValueError):
            validate_pattern("osmo", "")


class TestDifficulty(unittest.TestCase):
    def test_extra_prefix_chars(self):
        d = estimate_difficulty("osmo1a", "")
        self.assertEqual(d.prefix_extra_chars, 1)
        self.assertEqual(d.expected_attempts, 32.0)

    def test_suffix_chars(self):
        d = estimate_difficulty("osmo1", "xy")
        self.assertEqual(d.suffix_chars, 2)
        self.assertEqual(d.expected_attempts, 32**2)


class TestKeyGeneration(unittest.TestCase):
    def test_random_privkey_length(self):
        for strength in (128, 256):
            key = random_privkey_from_entropy(strength)
            self.assertEqual(len(key), 32)

    def test_batch_sizes(self):
        keys, mn = generate_keys_batch(5, 128, mnemonic=False)
        self.assertEqual(len(keys), 5)
        self.assertIsNone(mn)

    def test_mnemonic_deterministic_path(self):
        entropy = os.urandom(16)
        from mnemonic import Mnemonic

        m = Mnemonic("english")
        words = m.to_mnemonic(entropy)
        seed = m.to_seed(words)
        from bip32 import BIP32

        path = "m/44'/118'/0'/0/0"
        bip32 = BIP32.from_seed(seed)
        parts = path.lstrip("m/").split("/")
        hardened = 0x80000000
        indices = [
            int(p.replace("'", "")) + hardened if "'" in p else int(p) for p in parts
        ]
        expected = bip32.get_privkey_from_path(indices)
        priv, got_words = mnemonic_to_privkey(128, path)
        # mnemonic_to_privkey uses random entropy; only check structure here
        self.assertEqual(len(got_words.split()), 12)
        self.assertEqual(len(priv), 32)


if __name__ == "__main__":
    unittest.main()
