# suijuris.py — v0.1
#
# SUIJURIS — The contribution record of Phantom Network.
#
# "Sui juris." Under one's own law.
#
# This is not a currency yet. It is the ledger that makes
# a currency possible — the record of what each node has
# contributed, before any exchange mechanism exists.
#
# What this does:
#   — Records local contributions: seals created, encounters
#     completed, relay hops served, thoughts translated
#   — Seals each contribution with a SHA-256 stamp (same
#     algorithm as Phantom seals — immutable by design)
#   — Produces a verifiable contribution history that any
#     future SUIJURIS implementation can read and respect
#
# What this does NOT do:
#   — Issue tokens
#   — Connect to any server
#   — Claim any value
#   — Privilege early nodes over late ones
#
# The record is honest. The value it represents will be
# decided when the network is real enough to decide it.
# Building the ledger now means no contribution is lost.
#
# Lagos Protocol: this must work offline, on a secondhand
# Android phone, without an account, without trust in any
# authority. It does.
#
# HISTORY:
#   v0.1 — March 12, 2026. First ledger.
#          Contribution types: seal, encounter, relay, translation.
#          Local only. No network. Verifiable by anyone.
#
# GAP (Cipher Soul — "incentives determine what actually happens",
# BRIDGE.md §4): this file closes part of the gap BRIDGE.md names —
# contribution now IS a data structure (make_contribution below),
# not just a concept in ECONOMICS.md. What it does NOT close: there
# is still no transferable value (weight is not currency, see the
# module comment above — "This is not a currency yet"), and no
# answer to who validates a contribution without a central authority.
# The stamp here only proves a record wasn't tampered with locally;
# it doesn't prove the underlying claim (e.g. that a relay hop
# actually happened) to anyone who wasn't there. Byzantine-without-
# authority is still open.

import hashlib
import json
import os
import sys
from datetime import datetime, timezone

from phantom_core import (
    PHANTOM_VERSION, KeyManager, SealStore, NodeIdentity,
    encrypt_data, decrypt_data, CRYPTO_AVAILABLE, DATA_DIR,
)

SUIJURIS_VERSION = "0.1"
LEDGER_FILE = os.path.join(DATA_DIR, "phantom_suijuris.json")

# ─────────────────────────────────────────────────────────
# CONTRIBUTION TYPES
#
# Each type is a verifiable action that strengthens the network.
# The weight of each type is a placeholder — the network will
# decide actual weights when exchange mechanisms are designed.
# The hierarchy here is a starting point, not a decree.
# ─────────────────────────────────────────────────────────

CONTRIBUTION_TYPES = {
    "seal":        {"label": "Seal created",          "weight": 1},
    "encounter":   {"label": "Encounter completed",   "weight": 3},
    "relay":       {"label": "Relay hop served",      "weight": 2},
    "translation": {"label": "Thought translated",    "weight": 5},
    "genesis":     {"label": "Genesis participation", "weight": 10},
}

# ─────────────────────────────────────────────────────────
# CONTRIBUTION RECORD
# ─────────────────────────────────────────────────────────

def _stamp_contribution(entry):
    """
    Compute a deterministic stamp for a contribution entry.

    Covers every field that matters for reputation: type, moment,
    details, weight, and node. Earlier versions of this function
    left weight and node out of the stamp, which meant either could
    be silently altered on a saved record without invalidating it —
    fixed here; this changes the stamp formula, so records stamped
    before this fix will need re-stamping to verify again.
    """
    canonical = json.dumps(
        {
            "type":    entry["type"],
            "moment":  entry["moment"],
            "details": entry.get("details", ""),
            "weight":  entry.get("weight"),
            "node":    entry.get("node"),
        },
        separators=(',', ':'),
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def make_contribution(contrib_type, details="", node_fingerprint=None):
    """
    Create a new contribution record.
    Returns a dict with type, moment, details, weight, stamp.
    """
    if contrib_type not in CONTRIBUTION_TYPES:
        raise ValueError(
            f"Unknown contribution type: '{contrib_type}'. "
            f"Valid types: {', '.join(CONTRIBUTION_TYPES)}"
        )

    moment = datetime.now(timezone.utc).isoformat()
    entry = {
        "type":         contrib_type,
        "moment":       moment,
        "details":      details,
        "weight":       CONTRIBUTION_TYPES[contrib_type]["weight"],
        "node":         node_fingerprint or "anonymous",
        "suijuris_ver": SUIJURIS_VERSION,
    }
    entry["stamp"] = _stamp_contribution(entry)
    return entry


def verify_contribution(entry):
    """
    Verify that a contribution entry has not been tampered with.
    Returns True if the stamp is valid, False otherwise.
    """
    expected = _stamp_contribution(entry)
    return entry.get("stamp") == expected


# ─────────────────────────────────────────────────────────
# LEDGER — local storage, optionally encrypted
# ─────────────────────────────────────────────────────────

class Ledger:
    """
    The SUIJURIS ledger for this node.

    Stores contribution records locally, encrypted if a key
    is available. Every record is stamped and verifiable.

    The ledger is honest — it records only what actually
    happened on this device. It cannot be inflated by
    claiming contributions that did not occur.
    """

    def __init__(self, key_manager):
        self._km = key_manager
        self._cache = None

    @property
    def key(self):
        return self._km.key

    def load(self):
        """Load all contribution records. Returns list."""
        if self._cache is not None:
            return list(self._cache)

        if not os.path.exists(LEDGER_FILE):
            self._cache = []
            return []

        with open(LEDGER_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)

        # Encrypted ledger
        if isinstance(raw, dict) and raw.get("encrypted"):
            if self.key is None:
                print(" (Ledger is encrypted — enter passphrase to access)")
                self._cache = []
                return []
            plaintext = decrypt_data(raw, self.key)
            records = json.loads(plaintext.decode('utf-8'))
        else:
            records = raw

        self._cache = records
        return list(records)

    def _persist(self, records):
        """Write records to disk, encrypting if key available."""
        if self.key is not None and CRYPTO_AVAILABLE:
            plaintext = json.dumps(records, ensure_ascii=False).encode('utf-8')
            stored = encrypt_data(plaintext, self.key)
        else:
            stored = records

        with open(LEDGER_FILE, "w", encoding="utf-8") as f:
            json.dump(stored, f, indent=2, ensure_ascii=False)

    def record(self, entry):
        """
        Add a contribution to the ledger.
        Returns True if recorded, False if duplicate stamp.
        """
        records = self.load()

        # Dedup by stamp
        existing_stamps = {r.get("stamp") for r in records}
        if entry.get("stamp") in existing_stamps:
            return False

        records.append(entry)
        self._cache = records
        self._persist(records)
        return True

    def total_weight(self):
        """Sum of weights of all valid contributions."""
        records = self.load()
        return sum(
            r["weight"] for r in records
            if verify_contribution(r)
        )

    def count_by_type(self):
        """Return dict of {type: count} for all contributions."""
        records = self.load()
        counts = {t: 0 for t in CONTRIBUTION_TYPES}
        for r in records:
            t = r.get("type")
            if t in counts:
                counts[t] += 1
        return counts

    def integrity_report(self):
        """
        Check every record's stamp.
        Returns (valid_count, tampered_list).
        """
        records = self.load()
        valid = 0
        tampered = []
        for r in records:
            if verify_contribution(r):
                valid += 1
            else:
                tampered.append(r.get("stamp", "?")[:24])
        return valid, tampered

    def show(self):
        """Print a human-readable ledger summary."""
        records = self.load()

        print(f"\n SUIJURIS LEDGER — v{SUIJURIS_VERSION}")
        print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        if not records:
            print(" No contributions recorded yet.")
            print(" Contributions are recorded automatically when you")
            print(" seal thoughts, complete encounters, or relay seals.")
            print()
            return

        counts = self.count_by_type()
        total = self.total_weight()
        valid, tampered = self.integrity_report()

        print(f" Node: {records[0].get('node', 'anonymous')}")
        print(f" Total weight: {total}")
        print(f" Records: {len(records)} ({valid} verified)")
        if tampered:
            print(f" ⚠ TAMPERED: {len(tampered)} record(s) failed verification")
        print()

        for t, info in CONTRIBUTION_TYPES.items():
            c = counts.get(t, 0)
            if c > 0:
                bar = "█" * min(c, 40)
                print(f"  {info['label']:<28} {bar} {c}")
        print()

        print(" Recent contributions (last 5):")
        for r in reversed(records[-5:]):
            label = CONTRIBUTION_TYPES.get(r["type"], {}).get("label", r["type"])
            verified = "✓" if verify_contribution(r) else "✗"
            moment_short = r["moment"][:19].replace("T", " ")
            details = f" — {r['details'][:40]}" if r.get("details") else ""
            print(f"  {verified} {moment_short}  {label}{details}")
        print()

        print(" ─────────────────────────────────────────")
        print(" What this weight means:")
        print(" Nothing yet. The network will decide.")
        print(" This record will be here when it does.")
        print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print()

    def export(self, path=None):
        """
        Export the ledger as a verifiable JSON file.
        Useful for sharing contribution history with other nodes.
        Always exports plaintext (the stamps are the proof).
        """
        records = self.load()
        if not records:
            print(" Nothing to export — no contributions recorded.")
            return None

        export_data = {
            "suijuris_version": SUIJURIS_VERSION,
            "phantom_version":  PHANTOM_VERSION,
            "exported":         datetime.now(timezone.utc).isoformat(),
            "total_weight":     self.total_weight(),
            "record_count":     len(records),
            "contributions":    records,
        }

        if path is None:
            path = f"suijuris_export_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"

        with open(path, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

        print(f"\n Ledger exported: {path}")
        print(f" {len(records)} records — total weight: {self.total_weight()}")
        print(f" Each record is independently verifiable.")
        print(f" Anyone can check: python -c \"import suijuris; suijuris.verify_export('{path}')\"")
        print()
        return path


def verify_export(path):
    """
    Verify all records in an exported ledger file.
    Can be run by anyone on any machine — no keys needed.
    Returns (total, valid, tampered_stamps).
    """
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    contributions = data.get("contributions", [])
    valid = 0
    tampered = []

    for r in contributions:
        if verify_contribution(r):
            valid += 1
        else:
            tampered.append(r.get("stamp", "?"))

    total = len(contributions)
    print(f"\n SUIJURIS EXPORT VERIFICATION")
    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" File:    {path}")
    print(f" Records: {total}")
    print(f" Valid:   {valid}")
    if tampered:
        print(f" ⚠ TAMPERED: {len(tampered)} records failed")
        for s in tampered:
            print(f"   - {s[:40]}")
    else:
        print(f" ✓ All records verified — no tampering detected.")
    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print()
    return total, valid, tampered


# ─────────────────────────────────────────────────────────
# AUTO-RECORD HELPERS
#
# Called by phantom_node.py and phantom_relay.py when
# events occur. Integration is optional — if suijuris.py
# is absent, the node works without it.
# ─────────────────────────────────────────────────────────

def record_seal(ledger, idea_preview, node_fingerprint=None):
    """Record that a new seal was created on this node."""
    entry = make_contribution("seal", details=idea_preview[:60], node_fingerprint=node_fingerprint)
    return ledger.record(entry)


def record_encounter(ledger, peer_fp, sent, received, node_fingerprint=None):
    """Record a completed encounter with another node."""
    details = f"peer={peer_fp[:12]} sent={sent} recv={received}"
    entry = make_contribution("encounter", details=details, node_fingerprint=node_fingerprint)
    return ledger.record(entry)


def record_relay(ledger, stamp_preview, node_fingerprint=None):
    """Record that this node relayed a seal for another node."""
    entry = make_contribution("relay", details=f"stamp={stamp_preview[:16]}", node_fingerprint=node_fingerprint)
    return ledger.record(entry)


def record_translation(ledger, language, idea_preview, node_fingerprint=None):
    """Record a thought translated into another language."""
    details = f"lang={language} idea={idea_preview[:40]}"
    entry = make_contribution("translation", details=details, node_fingerprint=node_fingerprint)
    return ledger.record(entry)


# ─────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────

def main():
    print(f"\n SUIJURIS — v{SUIJURIS_VERSION}")
    print(" Under one's own law.\n")

    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(" Usage:")
        print("   (no args)          show your contribution ledger")
        print("   --export           export ledger to a verifiable JSON file")
        print("   --verify <file>    verify an exported ledger file")
        print("   --record <type>    manually record a contribution")
        print()
        print(" Contribution types:")
        for t, info in CONTRIBUTION_TYPES.items():
            print(f"   {t:<14} {info['label']} (weight: {info['weight']})")
        print()
        print(" Contributions are recorded automatically when you use")
        print(" phantom_node.py and phantom_relay.py.")
        print()
        return

    if "--verify" in args:
        idx = args.index("--verify")
        if idx + 1 >= len(args):
            print(" Usage: suijuris.py --verify <export_file.json>")
            return
        path = args[idx + 1]
        if not os.path.exists(path):
            print(f" File not found: {path}")
            return
        verify_export(path)
        return

    km = KeyManager()
    km.init_encryption()
    ledger = Ledger(km)

    if "--export" in args:
        ledger.export()
        return

    if "--record" in args:
        idx = args.index("--record")
        if idx + 1 >= len(args):
            print(" Usage: suijuris.py --record <type> [details]")
            print(f" Types: {', '.join(CONTRIBUTION_TYPES)}")
            return
        contrib_type = args[idx + 1]
        details = args[idx + 2] if idx + 2 < len(args) else ""
        try:
            entry = make_contribution(contrib_type, details=details)
            if ledger.record(entry):
                print(f"\n Recorded: {CONTRIBUTION_TYPES[contrib_type]['label']}")
                print(f" Stamp: {entry['stamp'][:32]}...")
                print(f" Weight: {entry['weight']}")
                print(f" Total weight now: {ledger.total_weight()}\n")
            else:
                print(" (Duplicate — already recorded)")
        except ValueError as e:
            print(f"\n {e}\n")
        return

    # Default: show ledger
    ledger.show()


if __name__ == "__main__":
    main()
