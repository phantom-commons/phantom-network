import os
import shutil
import tempfile
import unittest

import phantom_wallet as pw
import phantom_ledger as pl


class TestBilateralLedger(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.alice, _ = pw.PhantomWallet.generate_with_mnemonic()
        self.bob, _ = pw.PhantomWallet.generate_with_mnemonic()
        self.alice_ledger = pl.BilateralLedger(self.alice, self.bob.address, storage_dir=self.tmpdir)
        self.bob_ledger = pl.BilateralLedger(self.bob, self.alice.address, storage_dir=self.tmpdir)

    def tearDown(self):
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _round_trip(self, proposer_ledger, confirmer_ledger, debtor_address, amount, memo=""):
        proposal = proposer_ledger.propose(debtor_address, amount, memo)
        finalized = confirmer_ledger.confirm_and_append(proposal)
        proposer_ledger.append_confirmed(finalized)
        return finalized

    def test_basic_debt_and_balance(self):
        # Alice proposes: Alice owes Bob 20 (coffee)
        self._round_trip(self.alice_ledger, self.bob_ledger, self.alice.address, 20, "coffee")
        self.assertEqual(self.alice_ledger.balance(), -20)
        self.assertEqual(self.bob_ledger.balance(), 20)

    def test_repayment_nets_out(self):
        self._round_trip(self.alice_ledger, self.bob_ledger, self.alice.address, 20, "coffee")
        # Repayment: modeled as Bob now owing Alice the same amount — nets to zero
        self._round_trip(self.bob_ledger, self.alice_ledger, self.bob.address, 20, "repaid coffee")
        self.assertEqual(self.alice_ledger.balance(), 0)
        self.assertEqual(self.bob_ledger.balance(), 0)

    def test_partial_repayment(self):
        self._round_trip(self.alice_ledger, self.bob_ledger, self.alice.address, 50, "dinner")
        self._round_trip(self.bob_ledger, self.alice_ledger, self.bob.address, 30, "partial repay")
        self.assertEqual(self.alice_ledger.balance(), -20)
        self.assertEqual(self.bob_ledger.balance(), 20)

    def test_cannot_confirm_own_proposal(self):
        proposal = self.alice_ledger.propose(self.alice.address, 20, "coffee")
        with self.assertRaises(pl.LedgerError):
            self.alice_ledger.confirm_and_append(proposal)

    def test_self_dealing_blocked(self):
        with self.assertRaises(pl.LedgerError):
            pl.propose_entry(self.alice, self.alice.address, self.alice.address, 10, "x", "deadbeef")

    def test_tampered_amount_rejected(self):
        proposal = self.alice_ledger.propose(self.alice.address, 20, "coffee")
        finalized = self.bob_ledger.confirm_and_append(proposal)
        tampered = dict(finalized)
        tampered["amount"] = 9999
        self.assertFalse(pl.verify_entry(tampered))

    def test_forged_proposer_pubkey_rejected(self):
        mallory, _ = pw.PhantomWallet.generate_with_mnemonic()
        proposal = self.alice_ledger.propose(self.alice.address, 20, "coffee")
        # Swap in a different pubkey claiming to be the same proposer address
        proposal["proposer_pubkey"] = mallory._native_public_key.public_bytes(
            __import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.Raw,
            __import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.Raw,
        ).hex()
        with self.assertRaises(pl.LedgerError):
            self.bob_ledger.confirm_and_append(proposal)

    def test_out_of_sync_prev_hash_rejected(self):
        self._round_trip(self.alice_ledger, self.bob_ledger, self.alice.address, 10, "one")
        # Bob tries to confirm a new proposal built against a stale head
        stale_proposal = pl.propose_entry(
            self.alice, self.bob.address, self.alice.address, 5, "two",
            pl._chain_root(self.alice.address, self.bob.address),  # wrong: stale root, not current head
        )
        stale_proposal["proposer_pubkey"] = self.alice._native_public_key.public_bytes(
            __import__("cryptography.hazmat.primitives.serialization", fromlist=["Encoding"]).Encoding.Raw,
            __import__("cryptography.hazmat.primitives.serialization", fromlist=["PublicFormat"]).PublicFormat.Raw,
        ).hex()
        with self.assertRaises(pl.LedgerError):
            self.bob_ledger.confirm_and_append(stale_proposal)

    def test_chain_replay_verifies(self):
        self._round_trip(self.alice_ledger, self.bob_ledger, self.alice.address, 20, "coffee")
        self._round_trip(self.bob_ledger, self.alice_ledger, self.bob.address, 5, "partial")
        self.assertTrue(self.alice_ledger.verify_chain())
        self.assertTrue(self.bob_ledger.verify_chain())

    def test_negative_amount_rejected(self):
        with self.assertRaises(pl.LedgerError):
            self.alice_ledger.propose(self.alice.address, -5, "nope")

    def test_persists_and_reloads(self):
        self._round_trip(self.alice_ledger, self.bob_ledger, self.alice.address, 20, "coffee")
        reloaded = pl.BilateralLedger(self.alice, self.bob.address, storage_dir=self.tmpdir)
        self.assertEqual(reloaded.balance(), -20)


if __name__ == "__main__":
    unittest.main(verbosity=2)
