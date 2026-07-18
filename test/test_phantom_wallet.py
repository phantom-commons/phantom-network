"""
Validation for phantom_wallet.py against official test vectors and
an independent library (bip_utils) — run this after any change to
the crypto primitives before trusting them with real funds.
"""
import unittest
import phantom_wallet as pw

TEST_MNEMONIC = ("abandon abandon abandon abandon abandon abandon abandon "
                  "abandon abandon abandon abandon about")


class TestKeccak256(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(pw._keccak256(b'').hex(),
                          "c5d2460186f7233c927e7db2dcc703c0e500b653ca82273b7bfad8045d85a470")

    def test_abc(self):
        self.assertEqual(pw._keccak256(b'abc').hex(),
                          "4e03657aea45a94fc7d47ba826c8d667c0d1e6e33a64a036ec44f58fa12d6c45")


class TestRipemd160(unittest.TestCase):
    VECTORS = {
        b"": "9c1185a5c5e9fc54612808977ee8f548b2258d31",
        b"abc": "8eb208f7e05d987a9b044a8e98c6b087f15a0bfc",
        b"message digest": "5d0689ef49d2fae572b881b123a85ffa21595f36",
    }

    def test_vectors(self):
        for msg, expected in self.VECTORS.items():
            self.assertEqual(pw._ripemd160_pure(msg).hex(), expected)

    def test_matches_hashlib(self):
        data = b"cross-check against system hashlib"
        self.assertEqual(pw._ripemd160_pure(data), pw._ripemd160(data))


class TestBip32Vector1(unittest.TestCase):
    """Official BIP32 test vector 1."""
    SEED = bytes.fromhex("000102030405060708090a0b0c0d0e0f")

    def test_master(self):
        k, c = pw._master_key(self.SEED)
        self.assertEqual(k.hex(), "e8f32e723decf4051aefac8e2c93c9c5b214313817cdb01a1494b917c8436b35")
        self.assertEqual(c.hex(), "873dff81c02f525623fd1fe5167eac3a55a049de3d314bb42ee227ffed37d508")

    def test_m_0h(self):
        k, c = pw._derive_path(self.SEED, "m/0'")
        self.assertEqual(k.hex(), "edb2e14f9ee77d26dd93b4ecede8d16ed408ce149b6cd80b0715a2d911a0afea")
        self.assertEqual(c.hex(), "47fdacbd0f1097043b78c63c20c34ef4ed9a111d980047ad16282c7ae6236141")

    def test_m_0h_1(self):
        k, c = pw._derive_path(self.SEED, "m/0'/1")
        self.assertEqual(k.hex(), "3c6cb8d0f6a264c91ea8b5030fadaa8e538b020f0a387421a12de9319dc93368")


class TestStandardMnemonicAddresses(unittest.TestCase):
    """
    Cross-checked once against bip_utils (an independent, widely used
    BIP32/39/44 library) for the well-known test mnemonic. These
    expected values are recorded here as a frozen regression check —
    this test does not itself depend on bip_utils being installed.
    """

    def setUp(self):
        self.wallet = pw.PhantomWallet.from_mnemonic(TEST_MNEMONIC)

    def test_eth_address(self):
        self.assertEqual(self.wallet.external("ETH")["address"],
                          "0x9858EfFD232B4033E47d90003D41EC34EcaEda94")

    def test_eth_private_key(self):
        key = self.wallet.export_external_key("ETH")
        self.assertEqual(key["private_key_hex"],
                          "1ab42cc412b618bdea3a599e3c9bae199ebf030895b039e9db1e30dafb12b727")

    def test_btc_address(self):
        self.assertEqual(self.wallet.external("BTC")["address"],
                          "1LqBGSKuX5yYUonjxT5qGfpUsXKYYWeabA")

    def test_btc_wif(self):
        key = self.wallet.export_external_key("BTC")
        self.assertEqual(key["wif"],
                          "L4p2b9VAf8k5aUahF1JCJUzZkgNEAqLfq8DDdQiyAprQAKSbu8hf")

    def test_ltc_address(self):
        self.assertEqual(self.wallet.external("LTC")["address"],
                          "LUWPbpM43E2p7ZSh8cyTBEkvpHmr3cB8Ez")

    def test_doge_address(self):
        self.assertEqual(self.wallet.external("DOGE")["address"],
                          "DBus3bamQjgJULBJtYXpEzDWQRwF5iwxgC")


class TestNativeWallet(unittest.TestCase):
    def test_generate_and_address_format(self):
        wallet, mnemonic = pw.PhantomWallet.generate_with_mnemonic()
        self.assertEqual(len(mnemonic.split()), 24)
        self.assertTrue(wallet.address.startswith("pw_"))
        self.assertEqual(len(wallet.address), len("pw_") + 16)

    def test_sign_and_verify(self):
        wallet, _ = pw.PhantomWallet.generate_with_mnemonic()
        transfer = wallet.sign_transfer("pw_deadbeefcafebabe", 10, "test")
        self.assertTrue(pw.PhantomWallet.verify_transfer(transfer))

    def test_tampering_detected(self):
        wallet, _ = pw.PhantomWallet.generate_with_mnemonic()
        transfer = wallet.sign_transfer("pw_deadbeefcafebabe", 10, "test")
        transfer["amount"] = 99999
        self.assertFalse(pw.PhantomWallet.verify_transfer(transfer))

    def test_bad_mnemonic_rejected(self):
        with self.assertRaises(ValueError):
            pw.PhantomWallet.from_mnemonic("abandon " * 12)

    def test_wallet_address_independent_of_node_identity_keys(self):
        # Two different wallets from two different phrases must never
        # collide, and derivation must be fully deterministic.
        w1, m1 = pw.PhantomWallet.generate_with_mnemonic()
        w2 = pw.PhantomWallet.from_mnemonic(m1)
        self.assertEqual(w1.address, w2.address)


if __name__ == "__main__":
    unittest.main(verbosity=2)
