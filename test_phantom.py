#!/usr/bin/env python3
"""
test_phantom.py — Test suite for Phantom Network

Tests the seal/verify cycle, encryption round-trip, bloom filter,
genesis seal verification, network helpers, and storage.

Run: python test_phantom.py
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest

# Run tests from the directory containing phantom_core.py
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phantom_core import (
    seal, verify, compute_stamp,
    encrypt_data, decrypt_data, derive_key, get_or_create_salt,
    build_bloom, bloom_probably_has, compute_delta, bloom_size_for_count,
    send_json, recv_json,
    KeyManager, SealStore, EncounterLog, NodeIdentity,
    GENESIS_SEALS, CRYPTO_AVAILABLE,
    MODE_PRIVATE, MODE_PERMANENT, MODE_EPHEMERAL,
    MAX_IDEA_LENGTH,
    SEALS_FILE, SALT_FILE, ENCOUNTER_LOG_FILE,
    NODE_KEY_FILE, NODE_IDENTITY_FILE,
)


class TestSealAndVerify(unittest.TestCase):
    """Core sealing algorithm — the thing that cannot be wrong."""

    def test_seal_returns_dict(self):
        entry = seal("test idea")
        self.assertIn("idea", entry)
        self.assertIn("moment", entry)
        self.assertIn("stamp", entry)
        self.assertIn("mode", entry)

    def test_seal_produces_64_hex_chars(self):
        entry = seal("test idea")
        self.assertEqual(len(entry["stamp"]), 64)
        # All hex characters
        int(entry["stamp"], 16)

    def test_seal_verify_round_trip(self):
        entry = seal("The woman in Lagos can verify this.")
        self.assertTrue(verify(entry["idea"], entry["moment"], entry["stamp"]))

    def test_verify_detects_modified_idea(self):
        entry = seal("original idea")
        self.assertFalse(verify("modified idea", entry["moment"], entry["stamp"]))

    def test_verify_detects_modified_moment(self):
        entry = seal("test idea")
        self.assertFalse(verify(entry["idea"], "2000-01-01T00:00:00", entry["stamp"]))

    def test_verify_detects_modified_stamp(self):
        entry = seal("test idea")
        fake_stamp = "a" * 64
        self.assertFalse(verify(entry["idea"], entry["moment"], fake_stamp))

    def test_compute_stamp_matches_seal(self):
        entry = seal("consistency check")
        recomputed = compute_stamp(entry["idea"], entry["moment"])
        self.assertEqual(entry["stamp"], recomputed)

    def test_seal_format_is_canonical(self):
        """The format {\"idea\":\"...\",\"moment\":\"...\"} is fixed. No spaces."""
        entry = seal("format check")
        data = json.dumps(
            {"idea": entry["idea"], "moment": entry["moment"]},
            separators=(',', ':')
        )
        expected = hashlib.sha256(data.encode()).hexdigest()
        self.assertEqual(entry["stamp"], expected)

    def test_default_mode_is_private(self):
        entry = seal("default mode check")
        self.assertEqual(entry["mode"], MODE_PRIVATE)

    def test_explicit_modes(self):
        for mode in [MODE_PRIVATE, MODE_PERMANENT, MODE_EPHEMERAL]:
            entry = seal("mode check", mode=mode)
            self.assertEqual(entry["mode"], mode)

    def test_empty_idea_raises(self):
        with self.assertRaises(ValueError):
            seal("")

    def test_overlong_idea_raises(self):
        with self.assertRaises(ValueError):
            seal("x" * (MAX_IDEA_LENGTH + 1))

    def test_unicode_seal(self):
        """Em-dashes, accents, CJK, emoji — all should seal and verify."""
        ideas = [
            "If she cannot use it \u2014 it is not Phantom.",
            "Caf\u00e9 au lait",
            "\u5e7b\u5f71\u7db2\u7d61",
            "Seal with emoji \U0001f512",
        ]
        for idea in ideas:
            entry = seal(idea)
            self.assertTrue(
                verify(entry["idea"], entry["moment"], entry["stamp"]),
                f"Unicode verification failed for: {idea[:30]}"
            )


class TestGenesisSealVerification(unittest.TestCase):
    """Every genesis seal must verify. This is the foundational claim."""

    def test_all_17_genesis_seals_verify(self):
        for i, gs in enumerate(GENESIS_SEALS, 1):
            with self.subTest(seal_number=i, idea=gs["idea"][:40]):
                recomputed = compute_stamp(gs["idea"], gs["moment"])
                self.assertEqual(
                    recomputed, gs["stamp"],
                    f"Genesis seal {i} failed verification!\n"
                    f"  Idea: {gs['idea'][:60]}\n"
                    f"  Expected: {gs['stamp']}\n"
                    f"  Got:      {recomputed}"
                )

    def test_genesis_stamps_are_64_hex(self):
        for i, gs in enumerate(GENESIS_SEALS, 1):
            with self.subTest(seal_number=i):
                self.assertEqual(len(gs["stamp"]), 64, f"Seal {i} stamp length is {len(gs['stamp'])}")
                int(gs["stamp"], 16)  # Must be valid hex

    def test_17_genesis_seals_exist(self):
        self.assertEqual(len(GENESIS_SEALS), 17)

    def test_no_duplicate_genesis_stamps(self):
        stamps = [gs["stamp"] for gs in GENESIS_SEALS]
        self.assertEqual(len(stamps), len(set(stamps)), "Duplicate genesis stamps found!")

    def test_genesis_seals_match_sealing_md(self):
        """The repository must not contradict itself on the foundational memory."""
        import re
        sealing_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "SEALING.md")
        if not os.path.exists(sealing_path):
            self.skipTest("SEALING.md not found")

        with open(sealing_path) as f:
            content = f.read()

        pattern = r'Idea:\s*(.+?)\nMoment:\s*(.+?)\nStamp:\s*([0-9a-f]+)'
        doc_seals = [(i.strip(), m.strip(), s.strip())
                     for i, m, s in re.findall(pattern, content)]

        self.assertEqual(len(doc_seals), len(GENESIS_SEALS),
                         "SEALING.md and phantom_core.py have different seal counts")

        for i, ((d_idea, d_moment, d_stamp), gs) in enumerate(
                zip(doc_seals, GENESIS_SEALS), 1):
            with self.subTest(seal_number=i):
                self.assertEqual(d_idea, gs["idea"],
                    f"Seal {i}: idea differs between SEALING.md and phantom_core.py")
                self.assertEqual(d_moment, gs["moment"],
                    f"Seal {i}: moment differs between SEALING.md and phantom_core.py")
                self.assertEqual(d_stamp, gs["stamp"],
                    f"Seal {i}: stamp differs between SEALING.md and phantom_core.py")


class TestEncryption(unittest.TestCase):
    """Encryption round-trip — only if cryptography package available."""

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_encrypt_decrypt_round_trip(self):
        key = derive_key("test passphrase", b"0123456789abcdef")
        plaintext = b"sealed thought content"
        encrypted = encrypt_data(plaintext, key)
        decrypted = decrypt_data(encrypted, key)
        self.assertEqual(decrypted, plaintext)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_wrong_key_fails(self):
        key1 = derive_key("correct passphrase", b"0123456789abcdef")
        key2 = derive_key("wrong passphrase", b"0123456789abcdef")
        encrypted = encrypt_data(b"secret", key1)
        with self.assertRaises(ValueError):
            decrypt_data(encrypted, key2)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_tampered_ciphertext_fails(self):
        key = derive_key("passphrase", b"0123456789abcdef")
        encrypted = encrypt_data(b"secret", key)
        # Flip a byte in the ciphertext
        ct = encrypted["ciphertext"]
        tampered = ct[:10] + ("0" if ct[10] != "0" else "1") + ct[11:]
        encrypted["ciphertext"] = tampered
        with self.assertRaises(ValueError):
            decrypt_data(encrypted, key)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_unique_nonces(self):
        key = derive_key("passphrase", b"0123456789abcdef")
        e1 = encrypt_data(b"same plaintext", key)
        e2 = encrypt_data(b"same plaintext", key)
        self.assertNotEqual(e1["nonce"], e2["nonce"])
        self.assertNotEqual(e1["ciphertext"], e2["ciphertext"])


class TestBloomFilter(unittest.TestCase):
    """Bloom filter correctness — false positives OK, false negatives never."""

    def test_inserted_stamps_found(self):
        stamps = {f"stamp_{i}" for i in range(50)}
        bloom, size = build_bloom(stamps)
        for stamp in stamps:
            self.assertTrue(
                bloom_probably_has(bloom, stamp, size),
                f"False negative: {stamp} not found in bloom filter"
            )

    def test_unknown_stamps_mostly_absent(self):
        stamps = {f"stamp_{i}" for i in range(50)}
        bloom, size = build_bloom(stamps)
        false_positives = 0
        test_count = 1000
        for i in range(test_count):
            if bloom_probably_has(bloom, f"unknown_{i}", size):
                false_positives += 1
        # At 50 items in 8192-bit bloom with k=5, FP rate should be < 5%
        self.assertLess(false_positives / test_count, 0.05,
                        f"False positive rate too high: {false_positives}/{test_count}")

    def test_empty_bloom(self):
        bloom, size = build_bloom(set())
        self.assertFalse(bloom_probably_has(bloom, "anything", size))

    def test_compute_delta(self):
        my_stamps = {"A", "B", "C", "D"}
        their_stamps = {"B", "C"}
        their_bloom, their_size = build_bloom(their_stamps)
        delta = compute_delta(my_stamps, their_bloom, their_size)
        # A and D are definitely not in their bloom
        self.assertIn("A", delta)
        self.assertIn("D", delta)

    def test_bloom_size_scales(self):
        self.assertEqual(bloom_size_for_count(10), 8192)
        self.assertGreater(bloom_size_for_count(1000), 8192)
        self.assertGreater(bloom_size_for_count(10000), bloom_size_for_count(1000))


class TestSealStore(unittest.TestCase):
    """Storage layer — save, load, dedup, caching."""

    def setUp(self):
        self._orig_dir = os.getcwd()
        self._tmpdir = tempfile.mkdtemp()
        os.chdir(self._tmpdir)

    def tearDown(self):
        os.chdir(self._orig_dir)
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_save_and_load(self):
        km = KeyManager()
        store = SealStore(km)
        entry = seal("test save")
        store.save(entry)
        loaded = store.load()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["idea"], "test save")

    def test_dedup_by_stamp(self):
        km = KeyManager()
        store = SealStore(km)
        entry = seal("dedup test")
        self.assertTrue(store.save(entry))
        self.assertFalse(store.save(entry))  # duplicate
        self.assertEqual(store.count(), 1)

    def test_ephemeral_not_on_disk(self):
        km = KeyManager()
        store = SealStore(km)
        entry = seal("ephemeral test", mode=MODE_EPHEMERAL)
        store.save(entry)
        # Should NOT create a file (or file should be empty)
        if os.path.exists(SEALS_FILE):
            with open(SEALS_FILE) as f:
                data = json.load(f)
            self.assertEqual(len(data), 0)

    def test_stamps_index(self):
        km = KeyManager()
        store = SealStore(km)
        entry = seal("index test")
        store.save(entry)
        self.assertTrue(store.has_stamp(entry["stamp"]))
        self.assertFalse(store.has_stamp("nonexistent"))

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_encrypted_round_trip(self):
        km = KeyManager()
        salt = b"0123456789abcdef"
        with open(SALT_FILE, 'wb') as f:
            f.write(salt)
        km.set_key(derive_key("test", salt))
        store = SealStore(km)
        entry = seal("encrypted test")
        store.save(entry)

        # Load fresh
        store2 = SealStore(km)
        loaded = store2.load()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["idea"], "encrypted test")


class TestEncounterLog(unittest.TestCase):
    """Encounter log — storage and optional encryption."""

    def setUp(self):
        self._orig_dir = os.getcwd()
        self._tmpdir = tempfile.mkdtemp()
        os.chdir(self._tmpdir)

    def tearDown(self):
        os.chdir(self._orig_dir)
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def test_log_and_load(self):
        km = KeyManager()
        el = EncounterLog(km)
        stamp = el.log("192.168.1.1", 3, 2, {"abc", "def"})
        self.assertEqual(len(stamp), 64)
        encounters = el.load()
        self.assertEqual(len(encounters), 1)
        self.assertEqual(encounters[0]["peer"], "192.168.1.1")

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_encrypted_encounter_log(self):
        km = KeyManager()
        salt = b"0123456789abcdef"
        with open(SALT_FILE, 'wb') as f:
            f.write(salt)
        km.set_key(derive_key("test", salt))
        el = EncounterLog(km)
        el.log("192.168.1.1", 1, 1, {"abc"})

        # Verify file is encrypted (not readable as plain JSON list)
        with open(ENCOUNTER_LOG_FILE) as f:
            raw = json.load(f)
        self.assertTrue(raw.get("encrypted"), "Encounter log should be encrypted")

        # But loadable with the key
        encounters = el.load()
        self.assertEqual(len(encounters), 1)


class TestNodeIdentity(unittest.TestCase):
    """Node identity — key generation, signing, verification, persistence."""

    def setUp(self):
        self._orig_dir = os.getcwd()
        self._tmpdir = tempfile.mkdtemp()
        os.chdir(self._tmpdir)

    def tearDown(self):
        os.chdir(self._orig_dir)
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_generate_identity(self):
        identity = NodeIdentity.generate(node_name="TestNode")
        self.assertTrue(identity.has_private_key)
        self.assertEqual(identity.node_name, "TestNode")
        self.assertIsNotNone(identity.fingerprint)
        self.assertEqual(len(identity.fingerprint), 16)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_sign_and_verify(self):
        identity = NodeIdentity.generate(node_name="Signer")
        data = b"test data to sign"
        sig = identity.sign(data)
        self.assertTrue(identity.verify_signature(data, sig))

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_tampered_data_fails_verification(self):
        identity = NodeIdentity.generate()
        data = b"original data"
        sig = identity.sign(data)
        self.assertFalse(identity.verify_signature(b"tampered data", sig))

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_wrong_key_fails_verification(self):
        id1 = NodeIdentity.generate()
        id2 = NodeIdentity.generate()
        data = b"test data"
        sig = id1.sign(data)
        # id2 should not verify id1's signature
        self.assertFalse(id2.verify_signature(data, sig))

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_sign_seal(self):
        identity = NodeIdentity.generate(node_name="Sealer")
        entry = seal("signed idea")
        signed = identity.sign_seal(entry)
        self.assertIn("node_pubkey", signed)
        self.assertIn("node_sig", signed)
        self.assertEqual(signed["idea"], entry["idea"])
        self.assertEqual(signed["stamp"], entry["stamp"])

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_verify_signed_seal(self):
        identity = NodeIdentity.generate()
        entry = seal("verifiable idea")
        signed = identity.sign_seal(entry)
        self.assertTrue(NodeIdentity.verify_signed_seal(signed))

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_tampered_signed_seal_fails(self):
        identity = NodeIdentity.generate()
        entry = seal("original idea")
        signed = identity.sign_seal(entry)
        signed["idea"] = "tampered idea"
        self.assertFalse(NodeIdentity.verify_signed_seal(signed))

    def test_unsigned_seal_returns_none(self):
        entry = seal("unsigned idea")
        result = NodeIdentity.verify_signed_seal(entry)
        self.assertIsNone(result)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_save_and_load_unencrypted(self):
        identity = NodeIdentity.generate(node_name="Persistent")
        identity.save()

        loaded = NodeIdentity.load()
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.node_name, "Persistent")
        self.assertEqual(loaded.fingerprint, identity.fingerprint)
        self.assertTrue(loaded.has_private_key)

        # Verify loaded key can sign and the original can verify
        data = b"round trip test"
        sig = loaded.sign(data)
        self.assertTrue(identity.verify_signature(data, sig))

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_save_and_load_encrypted(self):
        km = KeyManager()
        salt = b"0123456789abcdef"
        with open(SALT_FILE, 'wb') as f:
            f.write(salt)
        km.set_key(derive_key("test", salt))

        identity = NodeIdentity.generate(node_name="Encrypted")
        identity.save(key=km.key)

        loaded = NodeIdentity.load(key=km.key)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.fingerprint, identity.fingerprint)
        self.assertTrue(loaded.has_private_key)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_from_public_key_b64(self):
        identity = NodeIdentity.generate(node_name="Full")
        pub_b64 = identity.public_key_b64

        public_only = NodeIdentity.from_public_key_b64(pub_b64, node_name="PublicOnly")
        self.assertFalse(public_only.has_private_key)
        self.assertEqual(public_only.fingerprint, identity.fingerprint)

        # Can verify signatures made by the full identity
        data = b"cross verification"
        sig = identity.sign(data)
        self.assertTrue(public_only.verify_signature(data, sig))

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_public_key_is_32_bytes(self):
        identity = NodeIdentity.generate()
        self.assertEqual(len(identity.public_key_bytes), 32)

    @unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not installed")
    def test_two_identities_have_different_fingerprints(self):
        id1 = NodeIdentity.generate()
        id2 = NodeIdentity.generate()
        self.assertNotEqual(id1.fingerprint, id2.fingerprint)


# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n PHANTOM NETWORK — Test Suite")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    unittest.main(verbosity=2)
