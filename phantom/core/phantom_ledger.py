"""
phantom_ledger.py
─────────────────────────────────────────────────────────
Modelo 1 — crédito mutuo bilateral. No reserve, no central
authority, no token that "exists" anywhere: just a signed history
of who acknowledged owing whom, between exactly two wallets.

Every entry means the same thing regardless of direction: "debtor
increases their obligation to creditor by amount." A repayment is
just an entry in the opposite direction — nets out automatically,
same as it works on paper between two people who trust each other.
No separate "payment" type needed.

Design, matching what phantom_core.py already does for receipts:
  - EVERY entry needs both parties' signatures before it's final.
    One-sided entries are proposals, not history.
  - A wallet cannot be both debtor and creditor on the same entry
    (self-dealing check, same principle as "a node cannot be its
    own carrier" in assemble_receipt()).
  - Entries hash-chain (prev_hash), same principle as Phantom's
    conversation sealing: tampering with or reordering history is
    detectable, and the chain is scoped to exactly these two
    addresses so it can't be replayed against a different pair.

This module deliberately does NOT decide what a "unit" of credit
is worth, whether it's redeemable for anything, or how far it can
travel past these two people. That's the harder, still-open
question (see phantom_wallet.py's module docstring).
"""

import hashlib
import json
import os
import threading
from datetime import datetime, timezone

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey
    )
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False

LEDGER_DIR = "phantom_ledgers"

GENESIS_MARKER = "genesis"


def _canonical(entry_without_sigs):
    return json.dumps(entry_without_sigs, sort_keys=True, separators=(',', ':')).encode('utf-8')


def _entry_hash(entry):
    """Hash of the finalized entry (with both signatures) — used as
    the next entry's prev_hash."""
    data = json.dumps(entry, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(data).hexdigest()


def _chain_root(address_a, address_b):
    """
    Deterministic starting point for a pair's chain, independent of
    who proposes first. Sorted so (A,B) and (B,A) give the same root.
    """
    pair = "|".join(sorted([address_a, address_b]))
    return hashlib.sha256((GENESIS_MARKER + ":" + pair).encode('utf-8')).hexdigest()


class LedgerError(ValueError):
    pass


def propose_entry(wallet, counterparty_address, debtor_address, amount, memo, prev_hash):
    """
    Step 1. Either party can propose — the proposer signs first.
    debtor_address is whichever of the two addresses is taking on
    the obligation in THIS entry (use the counterparty's address
    here to record a repayment — see module docstring).
    """
    if amount <= 0:
        raise LedgerError("Amount must be positive. Use the other direction for repayments.")
    if debtor_address not in (wallet.address, counterparty_address):
        raise LedgerError("debtor_address must be one of the two parties on this ledger.")
    creditor_address = counterparty_address if debtor_address == wallet.address else wallet.address
    if debtor_address == creditor_address:
        raise LedgerError("A wallet cannot owe itself.")

    body = {
        "debtor": debtor_address,
        "creditor": creditor_address,
        "amount": amount,
        "memo": memo,
        "prev_hash": prev_hash,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    signature = wallet._native_private_key.sign(_canonical(body))
    body["proposer"] = wallet.address
    body["proposer_sig"] = signature.hex()
    return body


def confirm_entry(wallet, proposed_entry):
    """
    Step 2. The other party verifies and countersigns. Only after
    this does the entry become part of the chain.
    """
    entry = dict(proposed_entry)
    proposer = entry.pop("proposer")
    proposer_sig = bytes.fromhex(entry.pop("proposer_sig"))
    if "proposer_pubkey" not in entry:
        raise LedgerError(
            "proposed_entry must include 'proposer_pubkey' (hex) so the "
            "counterparty can verify the signature — get it once via a "
            "contact-card style exchange, same as node identities do."
        )
    proposer_pubkey_hex = entry.pop("proposer_pubkey")

    if wallet.address not in (entry["debtor"], entry["creditor"]):
        raise LedgerError("This wallet is not a party to this entry.")
    if proposer not in (entry["debtor"], entry["creditor"]):
        raise LedgerError("Proposer is not one of the two parties named in the entry.")
    if entry["debtor"] == entry["creditor"]:
        raise LedgerError("A wallet cannot owe itself.")
    if proposer == wallet.address:
        raise LedgerError("Cannot confirm your own proposal — needs the other party.")

    body_bytes = _canonical(entry)
    pubkey = Ed25519PublicKey.from_public_bytes(bytes.fromhex(proposer_pubkey_hex))
    expected_addr = "pw_" + hashlib.sha256(bytes.fromhex(proposer_pubkey_hex)).hexdigest()[:16]
    if expected_addr != proposer:
        raise LedgerError("proposer_pubkey does not match the claimed proposer address.")
    try:
        pubkey.verify(proposer_sig, body_bytes)
    except Exception:
        raise LedgerError("Proposer signature is invalid.")

    confirmer_sig = wallet._native_private_key.sign(body_bytes)
    finalized = dict(entry)
    finalized["proposer"] = proposer
    finalized["proposer_sig"] = proposer_sig.hex()
    finalized["proposer_pubkey"] = proposer_pubkey_hex
    finalized["confirmer"] = wallet.address
    finalized["confirmer_sig"] = confirmer_sig.hex()
    finalized["confirmer_pubkey"] = wallet._native_public_key.public_bytes(
        Encoding.Raw, PublicFormat.Raw
    ).hex()
    return finalized


def verify_entry(entry):
    """Re-verify a finalized (both-signed) entry from scratch."""
    try:
        required = ("debtor", "creditor", "amount", "memo", "prev_hash", "timestamp",
                    "proposer", "proposer_sig", "proposer_pubkey",
                    "confirmer", "confirmer_sig", "confirmer_pubkey")
        if not all(k in entry for k in required):
            return False
        if entry["debtor"] == entry["creditor"]:
            return False
        if entry["proposer"] not in (entry["debtor"], entry["creditor"]):
            return False
        if entry["confirmer"] not in (entry["debtor"], entry["creditor"]):
            return False
        if entry["proposer"] == entry["confirmer"]:
            return False

        body = {k: entry[k] for k in
                 ("debtor", "creditor", "amount", "memo", "prev_hash", "timestamp")}
        body_bytes = _canonical(body)

        proposer_pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(entry["proposer_pubkey"]))
        expected_proposer_addr = "pw_" + hashlib.sha256(
            bytes.fromhex(entry["proposer_pubkey"])).hexdigest()[:16]
        if expected_proposer_addr != entry["proposer"]:
            return False
        proposer_pub.verify(bytes.fromhex(entry["proposer_sig"]), body_bytes)

        confirmer_pub = Ed25519PublicKey.from_public_bytes(bytes.fromhex(entry["confirmer_pubkey"]))
        expected_confirmer_addr = "pw_" + hashlib.sha256(
            bytes.fromhex(entry["confirmer_pubkey"])).hexdigest()[:16]
        if expected_confirmer_addr != entry["confirmer"]:
            return False
        confirmer_pub.verify(bytes.fromhex(entry["confirmer_sig"]), body_bytes)

        return True
    except Exception:
        return False


class BilateralLedger:
    """
    One wallet's view of its credit relationship with ONE
    counterparty. Create one instance per peer address.
    """

    def __init__(self, wallet, counterparty_address, storage_dir=LEDGER_DIR):
        self.wallet = wallet
        self.counterparty_address = counterparty_address
        self._lock = threading.RLock()
        self._storage_dir = storage_dir
        self._chain = None  # lazy-loaded list of finalized entries

    @property
    def _path(self):
        pair_key = "_".join(sorted([self.wallet.address, self.counterparty_address]))
        return os.path.join(self._storage_dir, f"{pair_key}.json")

    def _load(self):
        with self._lock:
            if self._chain is not None:
                return self._chain
            if not os.path.exists(self._path):
                self._chain = []
                return self._chain
            with open(self._path, "r", encoding="utf-8") as f:
                self._chain = json.load(f)
            return self._chain

    def _save(self):
        with self._lock:
            os.makedirs(self._storage_dir, exist_ok=True)
            with open(self._path, "w", encoding="utf-8") as f:
                json.dump(self._chain, f, indent=2)

    @property
    def head_hash(self):
        chain = self._load()
        if not chain:
            return _chain_root(self.wallet.address, self.counterparty_address)
        return _entry_hash(chain[-1])

    def propose(self, debtor_address, amount, memo=""):
        """Propose a new entry, to be sent to the counterparty out of band."""
        with self._lock:
            entry = propose_entry(
                self.wallet, self.counterparty_address, debtor_address,
                amount, memo, self.head_hash,
            )
            entry["proposer_pubkey"] = self.wallet._native_public_key.public_bytes(
                Encoding.Raw, PublicFormat.Raw
            ).hex()
            return entry

    def confirm_and_append(self, proposed_entry):
        """Counterparty side: verify, countersign, append, save."""
        with self._lock:
            chain = self._load()
            expected_prev = self.head_hash
            if proposed_entry["prev_hash"] != expected_prev:
                raise LedgerError(
                    "This entry doesn't chain from your current head — "
                    "you may be out of sync with the counterparty. "
                    "Re-sync before confirming."
                )
            finalized = confirm_entry(self.wallet, proposed_entry)
            chain.append(finalized)
            self._chain = chain
            self._save()
            return finalized

    def append_confirmed(self, finalized_entry):
        """
        Proposer side, after the counterparty sends back their
        countersignature: verify once more and append locally.
        """
        with self._lock:
            if not verify_entry(finalized_entry):
                raise LedgerError("This entry's signatures don't check out.")
            expected_prev = self.head_hash
            if finalized_entry["prev_hash"] != expected_prev:
                raise LedgerError("This entry doesn't chain from your current head.")
            chain = self._load()
            chain.append(finalized_entry)
            self._chain = chain
            self._save()

    def balance(self):
        """
        Positive = counterparty owes wallet.
        Negative = wallet owes counterparty.
        """
        chain = self._load()
        net = 0
        for entry in chain:
            if entry["creditor"] == self.wallet.address:
                net += entry["amount"]
            elif entry["debtor"] == self.wallet.address:
                net -= entry["amount"]
        return net

    def verify_chain(self):
        """Replay the whole chain: every entry signed correctly, and
        every prev_hash actually points at the entry before it."""
        chain = self._load()
        expected_prev = _chain_root(self.wallet.address, self.counterparty_address)
        for entry in chain:
            if not verify_entry(entry):
                return False
            if entry["prev_hash"] != expected_prev:
                return False
            expected_prev = _entry_hash(entry)
        return True
