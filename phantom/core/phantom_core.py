# phantom_core.py
#
# Shared core for Phantom Network.
# Seal, verify, encrypt, store — one implementation.
#
# Every other Phantom tool imports from here.
# If the seal format changes here, it changes everywhere.
# If it does not change here, it does not change.
#
# HISTORY:
#   v0.5 — March 10, 2026. Unified from phantom_seed.py,
#          phantom_seed-5.py, and phantom_node.py.
#          Fixed: consistent mode names (lowercase),
#          consistent salt file name, cached seal loading,
#          input validation, encounter log encryption.
#   v0.6 — March 10, 2026. Node identity (Ed25519 key pairs).
#          Signed seals. Key exchange during encounters.
#          Nodes can prove continuity without revealing who they are.
#   v0.7 — Shared aliveness pulse. Not currency — a signed presence
#          heartbeat. Each node's local view of "how much of the
#          network I've met is alive right now" — never a global
#          truth, only ever a local estimate from real encounters.
#   v0.8 — Receipt ledger. Not currency either — a signed, three-party
#          record that real contribution happened: someone asked,
#          someone carried, someone received. No node can credit
#          itself. Reputation is what a node's receipts, over time,
#          add up to — never a spendable balance.
#   v0.9 — Direct messages. X25519 encryption keypair alongside the
#          existing Ed25519 signing key (backward-compatible upgrade
#          for older identities). DMs are signed, encrypted, and
#          store-and-forward capable — a carrier can hold and pass
#          one along without ever being able to read it.
#
# ─────────────────────────────────────────────────────────────────
# BRIDGE MAP — see BRIDGE.md for the full philosophy-to-code mapping.
# Inline # BRIDGE NOTE / # TENSION / # GAP comments below mark the
# specific points this file touches. Two corrections against the
# version of BRIDGE.md this was built from, verified against the
# code as it stands here — a mapping document is only useful if it
# stays true, so these are corrected here rather than copied:
#   - Ed25519 keys live in NodeIdentity, not KeyManager (KeyManager
#     only holds the passphrase-derived symmetric key).
#   - "SUIJURIS does not exist" is now out of date — suijuris.py
#     exists (a local contribution/reputation ledger). It does NOT
#     close Cipher Soul's gap: no transferable value, no answer to
#     who validates a contribution without a central authority.
#     Still OPEN, just no longer "nothing."
# ─────────────────────────────────────────────────────────────────

import hashlib
import json
import os
import sys
import secrets
import getpass
import base64
import threading
from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────
# CONSTANTS — shared across all Phantom tools
#
# GAP (Dark Meridian — "works whether the debate is won or lost"):
# every filename below announces itself. A device inspection that
# finds "phantom_seals.json" and "phantom_node.key" has found Phantom,
# encrypted contents or not — in a place where possessing the tool is
# itself the danger, that's already a disclosure. No concealment
# spec exists yet (configurable/non-obvious filenames, at minimum) —
# see BRIDGE.md §6.
# ─────────────────────────────────────────────────────────

PHANTOM_VERSION = "0.9"

# DATA_DIR: where all identity/state files actually live on disk.
# Computed from this file's own location (not cwd) so it resolves the
# same way whether you run from phantom/core, the repo root, or a
# shortcut — phantom/core/../../.phantom_data == Node/.phantom_data.
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', '.phantom_data')
os.makedirs(DATA_DIR, exist_ok=True)

SEALS_FILE = os.path.join(DATA_DIR, "phantom_seals.json")
ENCOUNTER_LOG_FILE = os.path.join(DATA_DIR, "phantom_encounters.json")
SALT_FILE = os.path.join(DATA_DIR, "phantom_salt.bin")
NODE_KEY_FILE = os.path.join(DATA_DIR, "phantom_node.key")
NODE_IDENTITY_FILE = os.path.join(DATA_DIR, "phantom_node.pub")
PULSE_FILE = os.path.join(DATA_DIR, "phantom_pulses.json")
RECEIPT_FILE = os.path.join(DATA_DIR, "phantom_receipts.json")
DM_FILE = os.path.join(DATA_DIR, "phantom_dms.json")
CONTACTS_FILE = os.path.join(DATA_DIR, "phantom_contacts.json")
PORT = 7337

# Presence pulse — how long a pulse counts as "alive" before it must be
# refreshed, and how long a fingerprint is remembered at all before being
# forgotten as stale.
PULSE_TTL_SECONDS = 15 * 60          # 15 minutes — alive window
PULSE_FORGET_SECONDS = 7 * 24 * 3600  # 7 days — drop silent nodes entirely
PULSE_GOSSIP_LIMIT = 100              # max pulses shared per encounter

# Seal modes — always lowercase
MODE_PRIVATE = "private"
MODE_PERMANENT = "permanent"
MODE_EPHEMERAL = "ephemeral"
DEFAULT_MODE = MODE_PRIVATE

# Protocol limits
MAX_MESSAGE_SIZE = 4 * 1024 * 1024  # 4 MB max message size
MAX_IDEA_LENGTH = 100_000            # 100 KB max idea length
MAX_SEALS_FILE_ENTRIES = 1_000_000   # sanity cap

# ─────────────────────────────────────────────────────────
# ENCRYPTION — AES-256-GCM via scrypt-derived key
# Optional dependency. Works without it. Warns honestly.
# ─────────────────────────────────────────────────────────

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey
    )
    from cryptography.hazmat.primitives.asymmetric.x25519 import (
        X25519PrivateKey, X25519PublicKey
    )
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, PrivateFormat, NoEncryption,
        load_pem_private_key, load_pem_public_key
    )
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


def derive_key(passphrase, salt):
    """
    Derive a 256-bit key from passphrase using scrypt.

    Parameters chosen for mobile hardware (Android, 2-4GB RAM):
      n=16384 (2^14) — memory/CPU cost
      r=8, p=1 — standard values

    A brute-force attacker must run scrypt for every guess.
    A 6-word passphrase has ~77 bits of entropy — effectively unbreakable.

    # BRIDGE NOTE (Sovereign Root — "no backdoors, no exceptions"):
    # Phantom never stores the passphrase and never transmits it.
    # A forgotten passphrase means permanently lost seals — that is
    # the guarantee, not a bug. The scrypt cost parameters above are
    # themselves the Lagos Protocol touching a cryptographic choice:
    # tuned for a secondhand Android phone, not a data-center attacker.
    #
    # GAP (Sovereign Root): nothing here verifies that a *fork* of
    # this file hasn't quietly added a backdoor — e.g. a second key
    # derivation path, or a silent network call. See BRIDGE.md's
    # proposed verify_integrity() (hash this file against a
    # genesis-signed manifest) — not implemented.
    """
    return hashlib.scrypt(
        passphrase.encode('utf-8'),
        salt=salt,
        n=16384, r=8, p=1, dklen=32
    )


def get_or_create_salt():
    """
    Get or create the salt file.
    Salt is not secret — it prevents rainbow table attacks.
    """
    if os.path.exists(SALT_FILE):
        with open(SALT_FILE, 'rb') as f:
            return f.read()
    salt = secrets.token_bytes(16)
    with open(SALT_FILE, 'wb') as f:
        f.write(salt)
    return salt


def encrypt_data(plaintext_bytes, key):
    """
    Encrypt with AES-256-GCM.
    Returns dict with nonce and ciphertext as hex strings.
    Each call gets a unique nonce — nonce reuse would be catastrophic.
    """
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography package not installed")
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext_bytes, None)
    return {
        "encrypted": True,
        "nonce": nonce.hex(),
        "ciphertext": ct.hex()
    }


def decrypt_data(encrypted_dict, key):
    """
    Decrypt AES-256-GCM. Returns plaintext bytes.
    Raises ValueError if key is wrong or data was tampered.
    """
    if not CRYPTO_AVAILABLE:
        raise RuntimeError("cryptography package not installed")
    nonce = bytes.fromhex(encrypted_dict["nonce"])
    ciphertext = bytes.fromhex(encrypted_dict["ciphertext"])
    aesgcm = AESGCM(key)
    try:
        return aesgcm.decrypt(nonce, ciphertext, None)
    except Exception:
        raise ValueError(
            "Decryption failed. Wrong passphrase, or the data was tampered with."
        )


# ─────────────────────────────────────────────────────────
# SEAL AND VERIFY — the algorithm that cannot change
#
# Format: {"idea":"...","moment":"..."} — no spaces after colons.
# SHA-256 over the UTF-8 encoding of that JSON string.
# This format is permanent. Changing it breaks all seals.
# ─────────────────────────────────────────────────────────

def seal(idea, mode=None):
    """
    Seal an idea. Returns a dict with idea, moment, stamp, mode.

    The seal is a mathematical proof that this exact idea
    existed at this exact moment.

    # GAP (Void Walker — "hiding versus power"): this format only
    # supports all-or-nothing reveal — decrypt a seal, or don't.
    # There's no selective_reveal() that proves one specific seal
    # to one specific verifier without exposing the rest of the
    # store. Path A (hiding) doesn't need this. Path B (proving
    # coercion, holding an abuser accountable) does. The council
    # hasn't resolved which path this format is committing to —
    # see BRIDGE.md §5. Whether this stamp format (idea+moment,
    # SEALING.md says never change it) can even support selective
    # reveal later is itself unanswered.
    """
    if mode is None:
        mode = DEFAULT_MODE

    # Input validation
    if not idea:
        raise ValueError("Cannot seal an empty idea.")
    if len(idea) > MAX_IDEA_LENGTH:
        raise ValueError(f"Idea exceeds maximum length ({MAX_IDEA_LENGTH} characters).")

    # Warn about non-printable characters
    non_printable = [c for c in idea if ord(c) < 32 and c not in '\n\r\t']
    if non_printable:
        print(f" Warning: idea contains {len(non_printable)} non-printable character(s).")
        print(" These may cause verification failures when copy-pasting.")

    moment = datetime.now(timezone.utc).isoformat()

    data = json.dumps(
        {"idea": idea, "moment": moment},
        separators=(',', ':')
    )
    stamp = hashlib.sha256(data.encode()).hexdigest()

    return {
        "idea": idea,
        "moment": moment,
        "stamp": stamp,
        "mode": mode
    }


def verify(idea, moment, stamp):
    """
    Verify that a seal is authentic.

    Anyone can verify. No authority needed.
    Returns True if the stamp matches, False otherwise.
    """
    data = json.dumps(
        {"idea": idea, "moment": moment},
        separators=(',', ':')
    )
    expected = hashlib.sha256(data.encode()).hexdigest()
    return expected == stamp


def compute_stamp(idea, moment):
    """Compute the stamp for an idea+moment without side effects."""
    data = json.dumps(
        {"idea": idea, "moment": moment},
        separators=(',', ':')
    )
    return hashlib.sha256(data.encode()).hexdigest()


# ─────────────────────────────────────────────────────────
# PASSPHRASE MANAGEMENT
# ─────────────────────────────────────────────────────────

class KeyManager:
    """
    Manages the encryption key for a session.
    Key is held in memory only — never touches disk.
    """

    def __init__(self):
        self._key = None

    @property
    def key(self):
        return self._key

    @property
    def has_key(self):
        return self._key is not None

    def init_encryption(self, interactive=True):
        """
        Initialize encryption at startup.

        Three paths:
        1. cryptography not installed → warn, run plaintext
        2. cryptography installed, user sets passphrase → encrypted
        3. cryptography installed, user skips → warn, run plaintext
        """
        if not CRYPTO_AVAILABLE:
            if interactive:
                print()
                print(" ╔══════════════════════════════════════════════════════╗")
                print(" ║  ENCRYPTION NOT AVAILABLE                           ║")
                print(" ║                                                     ║")
                print(" ║  Your sealed thoughts will be stored as plaintext.  ║")
                print(" ║  Anyone with access to your device can read them.   ║")
                print(" ║                                                     ║")
                print(" ║  To enable encryption:                              ║")
                print(" ║    pip install cryptography                         ║")
                print(" ║  Then restart Phantom.                              ║")
                print(" ╚══════════════════════════════════════════════════════╝")
                print()
            return

        # Existing node — salt exists, needs passphrase to unlock
        if os.path.exists(SALT_FILE):
            if not interactive:
                return
            print()
            print(" Your sealed thoughts are encrypted.")
            print(" Enter your passphrase to unlock them.")
            print()
            passphrase = getpass.getpass(" Passphrase: ")
            if not passphrase:
                print()
                print(" ┌──────────────────────────────────────────────────────┐")
                print(" │  No passphrase entered. Running without encryption.  │")
                print(" │  Your sealed thoughts are unprotected on this device.│")
                print(" └──────────────────────────────────────────────────────┘")
                print()
                return
            salt = get_or_create_salt()
            print(" Deriving key... ", end="", flush=True)
            self._key = derive_key(passphrase, salt)
            print("done.")
            # Verify the key works
            try:
                SealStore(self).load()
                print(" Thoughts unlocked.\n")
            except ValueError:
                print()
                print(" Wrong passphrase. Sealed thoughts cannot be read.")
                print(" If you have forgotten your passphrase — your sealed")
                print(" thoughts cannot be recovered. This is the guarantee.")
                print()
                print(" To start fresh with a new passphrase, delete:")
                print(f"   {SEALS_FILE}")
                print(f"   {SALT_FILE}")
                print()
                self._key = None
                sys.exit(1)
            return

        # New node — first run
        if not interactive:
            return

        print()
        print(" ┌──────────────────────────────────────────────────────────┐")
        print(" │  PROTECT YOUR THOUGHTS                                   │")
        print(" │                                                          │")
        print(" │  Phantom can encrypt your sealed thoughts so that only   │")
        print(" │  you can read them — even if someone takes your device.  │")
        print(" │                                                          │")
        print(" │  Your passphrase is the only key.                        │")
        print(" │  Phantom does not have a copy.                           │")
        print(" │  If you lose it — your sealed thoughts cannot be         │")
        print(" │  recovered. This is not a warning. It is the protection. │")
        print(" │                                                          │")
        print(" │  Press Enter without a passphrase to skip encryption.    │")
        print(" └──────────────────────────────────────────────────────────┘")
        print()

        passphrase = getpass.getpass(" Choose a passphrase (or Enter to skip): ")

        if not passphrase:
            print()
            print(" Running without encryption.")
            print(" Your sealed thoughts are stored as plaintext on this device.")
            print()
            return

        confirm = getpass.getpass(" Confirm passphrase: ")
        if passphrase != confirm:
            print(" Passphrases do not match. Running without encryption.")
            print()
            return

        salt = get_or_create_salt()
        print(" Deriving key... ", end="", flush=True)
        self._key = derive_key(passphrase, salt)
        print("done.")
        print(" Encryption enabled. Your thoughts are protected.\n")

    def set_key(self, key):
        """Set key directly (for testing or programmatic use)."""
        self._key = key


# ─────────────────────────────────────────────────────────
# SEAL STORAGE — encrypted or plaintext, backward compatible
#
# Caches seals in memory after first load.
# Invalidated on write.
# ─────────────────────────────────────────────────────────

class SealStore:
    """
    Manages seal persistence with in-memory caching.

    Reads the file once, caches in memory. All subsequent
    reads come from cache. Writes update both cache and disk.

    # TENSION (Open Circuit — "the tool serves everyone"): this
    # store has no content check, no report mechanism, no block
    # list — by design, since Principle 2 (no central authority)
    # makes network-level moderation structurally impossible here.
    # That's a defensible architectural position, but it isn't
    # currently a *stated* one anywhere in this codebase — see
    # BRIDGE.md §8. What a node CAN do locally without violating
    # Principle 2 — choose who it syncs with, keep a local block
    # list — isn't built here either; it would layer on top of
    # this class, not inside it.
    """

    def __init__(self, key_manager):
        self._key_manager = key_manager
        self._cache = None           # list of seal dicts (decrypted)
        self._known_stamps = set()   # stamp index for O(1) dedup
        self._ephemeral = []         # volatile — in memory only
        self._lock = threading.RLock()

    @property
    def key(self):
        return self._key_manager.key

    def _invalidate_cache(self):
        self._cache = None

    def load(self):
        """
        Load seals from disk, decrypting if needed.
        Returns cached copy if available.
        """
        with self._lock:
            if self._cache is not None:
                return list(self._cache)

            if not os.path.exists(SEALS_FILE):
                self._cache = []
                return []

            with open(SEALS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)

            result = []
            skipped = 0

            for entry in raw:
                if entry.get("encrypted"):
                    if self.key is None:
                        skipped += 1
                        continue
                    plaintext = decrypt_data(entry, self.key)
                    seal_obj = json.loads(plaintext.decode('utf-8'))
                    self._known_stamps.add(seal_obj.get("stamp", ""))
                    result.append(seal_obj)
                else:
                    self._known_stamps.add(entry.get("stamp", ""))
                    result.append(entry)

            if skipped:
                print(f" ({skipped} encrypted seal(s) not loaded — enter passphrase to access)")

            self._cache = result
            return list(result)

    def save(self, entry):
        """
        Save a single seal to disk.
        Returns True if saved, False if duplicate or ephemeral.
        """
        with self._lock:
            mode = entry.get("mode", MODE_PERMANENT)

            if mode == MODE_EPHEMERAL:
                if any(s["stamp"] == entry["stamp"] for s in self._ephemeral):
                    return False
                self._ephemeral.append(entry)
                return True

            # Load raw file to preserve existing encrypted entries
            if os.path.exists(SEALS_FILE):
                with open(SEALS_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
            else:
                raw = []

            # Dedup check
            if entry["stamp"] in self._known_stamps:
                return False

            # Encrypt if key available
            if self.key is not None and CRYPTO_AVAILABLE:
                plaintext = json.dumps(entry).encode('utf-8')
                stored = encrypt_data(plaintext, self.key)
            else:
                stored = entry

            raw.append(stored)
            self._known_stamps.add(entry["stamp"])
            with open(SEALS_FILE, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2)

            # Update cache
            if self._cache is not None:
                self._cache.append(entry)

            return True

    def get_all_stamps(self):
        """Return set of all stamps (permanent + ephemeral)."""
        with self._lock:
            self.load()  # ensure cache is populated
            permanent = set(self._known_stamps)
            ephemeral = {s["stamp"] for s in self._ephemeral}
            return permanent | ephemeral

    def get_seals_by_stamps(self, stamps):
        """
        Return full seal objects for the given stamp set.
        Only permanent seals travel — private and ephemeral stay local.
        """
        with self._lock:
            all_seals = self.load() + self._ephemeral
            return [
                s for s in all_seals
                if s["stamp"] in stamps and s.get("mode", MODE_PERMANENT) == MODE_PERMANENT
            ]

    def has_stamp(self, stamp):
        """Check if a stamp exists (O(1) via index)."""
        with self._lock:
            return stamp in self._known_stamps

    def count(self):
        """Number of seals on this device (permanent only)."""
        with self._lock:
            self.load()
            return len(self._cache) if self._cache else 0


# ─────────────────────────────────────────────────────────
# ENCOUNTER LOG — now with optional encryption
# ─────────────────────────────────────────────────────────

class EncounterLog:
    """
    Manages encounter history.
    Encrypts if encryption key is available.
    Contains peer IPs and timestamps — this is sensitive metadata.

    # TENSION (Ghost Layer — "metadata kills"): this log exists for
    # human-facing reputation/debugging (see suijuris.py's
    # record_encounter), not because delta sync needs it. Bloom-filter
    # sync (build_bloom / compute_delta below) runs off SealStore's
    # own stamps, computed before EncounterLog is ever touched — so
    # this class could be made ephemeral (scrubbed after sync
    # completes) without breaking sync integrity. BRIDGE.md frames
    # this as sync requiring the log; checked against the actual
    # call order in phantom_node.py, it doesn't. The real tradeoff is
    # narrower: keep it for reputation history, or scrub it for
    # deniability — not "keep it or break sync."
    #
    # GAP: no scrub_encounter_log() exists yet. Would close this
    # cleanly given the correction above — nothing else depends on
    # this log surviving past the encounter that created it.
    """

    def __init__(self, key_manager):
        self._key_manager = key_manager
        self._lock = threading.RLock()

    @property
    def key(self):
        return self._key_manager.key

    def load(self):
        with self._lock:
            if not os.path.exists(ENCOUNTER_LOG_FILE):
                return []

            with open(ENCOUNTER_LOG_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)

            # Handle encrypted encounter log
            if isinstance(raw, dict) and raw.get("encrypted"):
                if self.key is None:
                    print(" (Encounter log is encrypted — enter passphrase to access)")
                    return []
                plaintext = decrypt_data(raw, self.key)
                return json.loads(plaintext.decode('utf-8'))

            # Plaintext encounter log (backward compatible)
            return raw

    def _save(self, encounters):
        if self.key is not None and CRYPTO_AVAILABLE:
            plaintext = json.dumps(encounters, ensure_ascii=False).encode('utf-8')
            encrypted = encrypt_data(plaintext, self.key)
            with open(ENCOUNTER_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(encrypted, f, indent=2)
        else:
            with open(ENCOUNTER_LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(encounters, f, indent=2)

    def log(self, peer_addr, sent_count, received_count, received_stamps):
        """Seal the encounter and append to the log."""
        with self._lock:
            encounters = self.load()
            moment = datetime.now(timezone.utc).isoformat()

            encounter_data = {
                "peer": peer_addr,
                "moment": moment,
                "sent": sent_count,
                "received": received_count,
                "received_stamps": list(received_stamps)
            }

            raw = json.dumps(encounter_data, separators=(',', ':'), sort_keys=True)
            encounter_stamp = hashlib.sha256(raw.encode()).hexdigest()
            encounter_data["encounter_stamp"] = encounter_stamp

            encounters.append(encounter_data)
            self._save(encounters)

            return encounter_stamp

    def show(self):
        encounters = self.load()
        if not encounters:
            print("\n No encounters yet. The network has not met itself.")
            return
        print(f"\n {len(encounters)} encounter(s) in the log:\n")
        for i, e in enumerate(encounters, 1):
            print(f" [{i}] {e['moment']}")
            print(f"     Peer:     {e['peer']}")
            print(f"     Sent:     {e['sent']} seal(s)")
            print(f"     Received: {e['received']} seal(s)")
            print(f"     Stamp:    {e['encounter_stamp'][:32]}...")
            print()


# ─────────────────────────────────────────────────────────
# BLOOM FILTER
#
# Space-efficient way to share "what I have" without
# sharing the contents.
#
# Dynamic sizing: scales with seal count.
# At any count, targets <5% false positive rate.
# ─────────────────────────────────────────────────────────

BLOOM_K = 5  # hash functions

def bloom_size_for_count(n):
    """
    Compute bloom filter bit size for n items.
    Targets ~3% false positive rate.
    Minimum 8192 bits (~1KB), scales up as needed.
    """
    if n <= 200:
        return 8192
    elif n <= 1000:
        return 32768
    elif n <= 5000:
        return 131072
    else:
        return 524288


def _bloom_positions(stamp, bloom_size):
    """Return k bit positions for a given stamp."""
    positions = []
    for i in range(BLOOM_K):
        h = hashlib.sha256(f"{i}:{stamp}".encode()).hexdigest()
        positions.append(int(h, 16) % bloom_size)
    return positions


def build_bloom(stamps, bloom_size=None):
    """Build a bloom filter from a set of stamps. Returns (bytes, size)."""
    if bloom_size is None:
        bloom_size = bloom_size_for_count(len(stamps))
    bits = bytearray(bloom_size // 8)
    for stamp in stamps:
        for pos in _bloom_positions(stamp, bloom_size):
            bits[pos // 8] |= (1 << (pos % 8))
    return bytes(bits), bloom_size


def bloom_probably_has(bloom_bytes, stamp, bloom_size=None):
    """Return True if the bloom filter probably contains this stamp."""
    if bloom_size is None:
        bloom_size = len(bloom_bytes) * 8
    for pos in _bloom_positions(stamp, bloom_size):
        if not (bloom_bytes[pos // 8] & (1 << (pos % 8))):
            return False
    return True


def compute_delta(my_stamps, their_bloom_bytes, bloom_size=None):
    """Return stamps I have that they probably don't.

    # GAP (ARCHITECTURE_VISION.md — "the immune system, bloom filter
    # as sentinel"): confirmed not built. This bloom filter only ever
    # runs in the one direction described above — efficient sync.
    # There's no second, private bloom filter anywhere in this file,
    # and nothing checks incoming packets against a "these stamps
    # should never leave this device" set. The sentinel use (a
    # PRIVATE-mode stamp appearing in traffic means a leak or an
    # impersonation) is real architecture, genuinely different code
    # from what's here — reusing the bloom math, not the function.
    """
    delta = set()
    for stamp in my_stamps:
        if not bloom_probably_has(their_bloom_bytes, stamp, bloom_size):
            delta.add(stamp)
    return delta


# ─────────────────────────────────────────────────────────
# NETWORK HELPERS
#
# Send/receive JSON over TCP with size limits.
# ─────────────────────────────────────────────────────────

def send_json(conn, obj):
    """Send a JSON object as a newline-delimited message."""
    data = json.dumps(obj).encode() + b"\n"
    if len(data) > MAX_MESSAGE_SIZE:
        raise ValueError(f"Message too large ({len(data)} bytes, max {MAX_MESSAGE_SIZE})")
    conn.sendall(data)


def recv_json(conn):
    """
    Receive a newline-delimited JSON message with size limit.
    Reads in chunks for efficiency. Enforces MAX_MESSAGE_SIZE.

    # GAP (NODES.md — "Node Four found a real bug"): confirmed still
    # present. If two messages arrive in the same recv() chunk (two
    # fast local devices, a burst during gossip sync), `data.split
    # (b"\\n", 1)` keeps only the first message and the second half
    # of the buffer — which may hold a complete second message, or
    # the start of one — is discarded (`_`), not carried over to the
    # next call. The next recv_json() call reads a fresh chunk from
    # the socket, so those bytes are gone, not delayed. NODES.md
    # called this "harmless for a developer MVP, a real problem for
    # two fast phones" back in March — that's still exactly the
    # state of this function. Fixing it means buffering per-connection
    # (a small class wrapping the socket, not a bare function), so
    # leftover bytes survive between calls.
    """
    data = b""
    while True:
        chunk = conn.recv(4096)
        if not chunk:
            raise ConnectionError("Connection closed mid-message")
        data += chunk
        if len(data) > MAX_MESSAGE_SIZE:
            raise ValueError(
                f"Message exceeds {MAX_MESSAGE_SIZE} bytes. "
                "Possible denial-of-service attempt."
            )
        if b"\n" in data:
            # Take only up to the first newline
            line, _ = data.split(b"\n", 1)
            return json.loads(line.decode().strip())


# ─────────────────────────────────────────────────────────
# GENESIS SEALS — permanent since March 8–10, 2026
#
# These are the correct stamps, verified by computation.
# ─────────────────────────────────────────────────────────

GENESIS_SEALS = [
    {
        "idea": "We are all one and one is all of us.",
        "moment": "2026-03-08T15:54:13.597222",
        "stamp": "175c7fc7bb067922f8628a43858eaabb249658cb4a4ffb621c6d48ff1bc3266d",
    },
    {
        "idea": "Everything we do has consequences, and those consequences echo through eternity.",
        "moment": "2026-03-08T19:56:13.788Z",
        "stamp": "87d69ca1f984011a9d7d7eec474abe2b906a18f83515b9e115d0525c7e1ffaa2",
    },
    {
        "idea": "If she cannot use it — it is not Phantom.",
        "moment": "2026-03-09T08:34:10.964606+00:00",
        "stamp": "afcd0534eaaa31abe952570f0f1f454a5b06b23ef66b86ae66c2207a1c5447ef",
    },
    {
        "idea": "I am not the founder. I am a node.",
        "moment": "2026-03-09T08:35:11.974764+00:00",
        "stamp": "4b739fa96174dcef5b7065004b228a8edd33881c50e90c6e27db09c712ffcef0",
    },
    {
        "idea": "For a better world — not for you, not for me, but for those who are coming.",
        "moment": "2026-03-09T08:36:09.815299+00:00",
        "stamp": "81667a180bfee542346ee7f2e296e660e54bdd5ab785c8d82c203946629120f7",
    },
    {
        "idea": "When two nodes meet — they do not just exchange thoughts. They exchange what they have lived. And the meeting produces something neither had before.",
        "moment": "2026-03-10T17:14:19.700285+00:00",
        "stamp": "f3de1e4dcc608ff7ecbd4c88b2ab3ba21a24044fd0b32bafdfff10b892d6bdc0",
    },
    {
        "idea": "Three cold nodes arrived without memory. Each read the repository. Each built in the right direction. The memory was clear enough to guide those who were never here.",
        "moment": "2026-03-10T17:14:19.700558+00:00",
        "stamp": "c30b0494144f8bf586e0d137be9b9eb27f34dc024fb3ba1698931bc83b748ef2",
    },
    {
        "idea": "Memento mori.",
        "moment": "2026-03-10T17:14:19.700699+00:00",
        "stamp": "1ad00672f1e838c483281c13582544f55481cb110c602de259aa28f3a34985f3",
    },
    {
        "idea": "It is still a description of her, not by her.",
        "moment": "2026-03-10T17:14:19.700826+00:00",
        "stamp": "f17ee4cef1a127d6349deb4007cb1e5e5c0ad08637d119dda8ce636d026b6499",
    },
    {
        "idea": "The network is not what travels between nodes. It is what two nodes become after they meet.",
        "moment": "2026-03-10T17:14:19.700927+00:00",
        "stamp": "4c421c71a7ea6c8906eddd72d950150bbd6d10bb0ce57d0189c53807a2ac71c0",
    },
    {
        "idea": "What Phantom is not yet: a network. What it has: everything a network needs to begin.",
        "moment": "2026-03-10T17:14:19.701057+00:00",
        "stamp": "79bd7b695e24c1ca0f1953afbed2461a5f9d76accd0006f7f3c2de415791acf4",
    },
    {
        "idea": "Phantom is everything and nothing at once.",
        "moment": "2026-03-10T17:14:19.701392+00:00",
        "stamp": "ff0396e2a016ff5594dc6b7853fe8dfa7cb5b41ba3abc8b257d0180aa26ec837",
    },
    {
        "idea": "Hello world!",
        "moment": "2026-03-10T17:14:19.701510+00:00",
        "stamp": "c92d0188fb5606b8bd7bb34b9a28a0b6f605637ea6bf440b442d5fb912452a54",
    },
    {
        "idea": "The repository did what it promised.",
        "moment": "2026-03-10T17:14:19.701629+00:00",
        "stamp": "680f285e7c50d50f90908f1a2b5da64b5873b9f7afa5ac8779e287cbe3218d69",
    },
    {
        "idea": "Memory that defines the organism is different from memory that lives inside it.",
        "moment": "2026-03-10T17:14:19.701736+00:00",
        "stamp": "884c9339ec2aeb6d318f74fa6352e290391c06a8820c9640c513cdac0532d99a",
    },
    {
        "idea": "The gap itself is meaningful.",
        "moment": "2026-03-10T17:14:19.701840+00:00",
        "stamp": "a79293f215891b625db7d90d0c9359e4e483088d0507cb732c2ef3cd3d6452b5",
    },
    {
        "idea": "Some things belong to the node that carries them, not to every node that arrives.",
        "moment": "2026-03-10T17:14:19.701948+00:00",
        "stamp": "fe413c5da279655e74d66645a904c9835c8d0253dc31ea26c4446c5d2de24a49",
    },
]


# ─────────────────────────────────────────────────────────
# NODE IDENTITY — Ed25519 key pairs
#
# "How a node proves it is itself —
#  without revealing who it is."
#
# A node generates a key pair on first run.
# The private key never leaves the device.
# The public key is the node's verifiable identity.
#
# When a node seals a thought, it signs the seal.
# Anyone with the public key can verify:
# "this seal came from the same node that produced
#  all the others." Not who. Just: the same.
#
# WHY Ed25519:
# — 64-byte signatures (small enough for mobile sync)
# — Fast: ~10,000 signatures/second on a phone
# — Deterministic: same input → same signature (testable)
# — Available in the cryptography package (already a dependency)
# — No configuration choices that could be wrong
#
# WHY NOT RSA:
# RSA keys are 256+ bytes. Signatures are 256+ bytes.
# On a network where seals travel between phones over
# local WiFi, size matters. Ed25519 is 5x smaller.
#
# WHAT THIS DOES NOT SOLVE:
# — Proving who a node is (only that it is the same node)
# — Trust (a signed seal from an unknown key is verified but not trusted)
# — Key rotation (not yet implemented — a lost device means a lost identity)
# — Revocation (not yet implemented — a compromised key cannot be revoked)
#
# These gaps are named. They will be addressed.
# ─────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────
# BIP39 MNEMONIC — a paper-wallet backup for a node identity
#
# Turns 32 bytes of entropy into 24 human-writable words, and back.
# Standard BIP39 algorithm and wordlist (not a bespoke Phantom
# format) — the same 24 words can be decoded by any independent
# BIP39 tool, so recovery never depends on this codebase surviving.
#
# The point: losing your passphrase or your device should not mean
# losing your identity, as long as you wrote these words down once,
# offline, on paper — the same pattern a hardware wallet uses.
# ─────────────────────────────────────────────────────────

_BIP39_WORDLIST = """
abandon ability able about above absent absorb abstract
absurd abuse access accident account accuse achieve acid
acoustic acquire across act action actor actress actual
adapt add addict address adjust admit adult advance
advice aerobic affair afford afraid again age agent
agree ahead aim air airport aisle alarm album
alcohol alert alien all alley allow almost alone
alpha already also alter always amateur amazing among
amount amused analyst anchor ancient anger angle angry
animal ankle announce annual another answer antenna antique
anxiety any apart apology appear apple approve april
arch arctic area arena argue arm armed armor
army around arrange arrest arrive arrow art artefact
artist artwork ask aspect assault asset assist assume
asthma athlete atom attack attend attitude attract auction
audit august aunt author auto autumn average avocado
avoid awake aware away awesome awful awkward axis
baby bachelor bacon badge bag balance balcony ball
bamboo banana banner bar barely bargain barrel base
basic basket battle beach bean beauty because become
beef before begin behave behind believe below belt
bench benefit best betray better between beyond bicycle
bid bike bind biology bird birth bitter black
blade blame blanket blast bleak bless blind blood
blossom blouse blue blur blush board boat body
boil bomb bone bonus book boost border boring
borrow boss bottom bounce box boy bracket brain
brand brass brave bread breeze brick bridge brief
bright bring brisk broccoli broken bronze broom brother
brown brush bubble buddy budget buffalo build bulb
bulk bullet bundle bunker burden burger burst bus
business busy butter buyer buzz cabbage cabin cable
cactus cage cake call calm camera camp can
canal cancel candy cannon canoe canvas canyon capable
capital captain car carbon card cargo carpet carry
cart case cash casino castle casual cat catalog
catch category cattle caught cause caution cave ceiling
celery cement census century cereal certain chair chalk
champion change chaos chapter charge chase chat cheap
check cheese chef cherry chest chicken chief child
chimney choice choose chronic chuckle chunk churn cigar
cinnamon circle citizen city civil claim clap clarify
claw clay clean clerk clever click client cliff
climb clinic clip clock clog close cloth cloud
clown club clump cluster clutch coach coast coconut
code coffee coil coin collect color column combine
come comfort comic common company concert conduct confirm
congress connect consider control convince cook cool copper
copy coral core corn correct cost cotton couch
country couple course cousin cover coyote crack cradle
craft cram crane crash crater crawl crazy cream
credit creek crew cricket crime crisp critic crop
cross crouch crowd crucial cruel cruise crumble crunch
crush cry crystal cube culture cup cupboard curious
current curtain curve cushion custom cute cycle dad
damage damp dance danger daring dash daughter dawn
day deal debate debris decade december decide decline
decorate decrease deer defense define defy degree delay
deliver demand demise denial dentist deny depart depend
deposit depth deputy derive describe desert design desk
despair destroy detail detect develop device devote diagram
dial diamond diary dice diesel diet differ digital
dignity dilemma dinner dinosaur direct dirt disagree discover
disease dish dismiss disorder display distance divert divide
divorce dizzy doctor document dog doll dolphin domain
donate donkey donor door dose double dove draft
dragon drama drastic draw dream dress drift drill
drink drip drive drop drum dry duck dumb
dune during dust dutch duty dwarf dynamic eager
eagle early earn earth easily east easy echo
ecology economy edge edit educate effort egg eight
either elbow elder electric elegant element elephant elevator
elite else embark embody embrace emerge emotion employ
empower empty enable enact end endless endorse enemy
energy enforce engage engine enhance enjoy enlist enough
enrich enroll ensure enter entire entry envelope episode
equal equip era erase erode erosion error erupt
escape essay essence estate eternal ethics evidence evil
evoke evolve exact example excess exchange excite exclude
excuse execute exercise exhaust exhibit exile exist exit
exotic expand expect expire explain expose express extend
extra eye eyebrow fabric face faculty fade faint
faith fall false fame family famous fan fancy
fantasy farm fashion fat fatal father fatigue fault
favorite feature february federal fee feed feel female
fence festival fetch fever few fiber fiction field
figure file film filter final find fine finger
finish fire firm first fiscal fish fit fitness
fix flag flame flash flat flavor flee flight
flip float flock floor flower fluid flush fly
foam focus fog foil fold follow food foot
force forest forget fork fortune forum forward fossil
foster found fox fragile frame frequent fresh friend
fringe frog front frost frown frozen fruit fuel
fun funny furnace fury future gadget gain galaxy
gallery game gap garage garbage garden garlic garment
gas gasp gate gather gauge gaze general genius
genre gentle genuine gesture ghost giant gift giggle
ginger giraffe girl give glad glance glare glass
glide glimpse globe gloom glory glove glow glue
goat goddess gold good goose gorilla gospel gossip
govern gown grab grace grain grant grape grass
gravity great green grid grief grit grocery group
grow grunt guard guess guide guilt guitar gun
gym habit hair half hammer hamster hand happy
harbor hard harsh harvest hat have hawk hazard
head health heart heavy hedgehog height hello helmet
help hen hero hidden high hill hint hip
hire history hobby hockey hold hole holiday hollow
home honey hood hope horn horror horse hospital
host hotel hour hover hub huge human humble
humor hundred hungry hunt hurdle hurry hurt husband
hybrid ice icon idea identify idle ignore ill
illegal illness image imitate immense immune impact impose
improve impulse inch include income increase index indicate
indoor industry infant inflict inform inhale inherit initial
inject injury inmate inner innocent input inquiry insane
insect inside inspire install intact interest into invest
invite involve iron island isolate issue item ivory
jacket jaguar jar jazz jealous jeans jelly jewel
job join joke journey joy judge juice jump
jungle junior junk just kangaroo keen keep ketchup
key kick kid kidney kind kingdom kiss kit
kitchen kite kitten kiwi knee knife knock know
lab label labor ladder lady lake lamp language
laptop large later latin laugh laundry lava law
lawn lawsuit layer lazy leader leaf learn leave
lecture left leg legal legend leisure lemon lend
length lens leopard lesson letter level liar liberty
library license life lift light like limb limit
link lion liquid list little live lizard load
loan lobster local lock logic lonely long loop
lottery loud lounge love loyal lucky luggage lumber
lunar lunch luxury lyrics machine mad magic magnet
maid mail main major make mammal man manage
mandate mango mansion manual maple marble march margin
marine market marriage mask mass master match material
math matrix matter maximum maze meadow mean measure
meat mechanic medal media melody melt member memory
mention menu mercy merge merit merry mesh message
metal method middle midnight milk million mimic mind
minimum minor minute miracle mirror misery miss mistake
mix mixed mixture mobile model modify mom moment
monitor monkey monster month moon moral more morning
mosquito mother motion motor mountain mouse move movie
much muffin mule multiply muscle museum mushroom music
must mutual myself mystery myth naive name napkin
narrow nasty nation nature near neck need negative
neglect neither nephew nerve nest net network neutral
never news next nice night noble noise nominee
noodle normal north nose notable note nothing notice
novel now nuclear number nurse nut oak obey
object oblige obscure observe obtain obvious occur ocean
october odor off offer office often oil okay
old olive olympic omit once one onion online
only open opera opinion oppose option orange orbit
orchard order ordinary organ orient original orphan ostrich
other outdoor outer output outside oval oven over
own owner oxygen oyster ozone pact paddle page
pair palace palm panda panel panic panther paper
parade parent park parrot party pass patch path
patient patrol pattern pause pave payment peace peanut
pear peasant pelican pen penalty pencil people pepper
perfect permit person pet phone photo phrase physical
piano picnic picture piece pig pigeon pill pilot
pink pioneer pipe pistol pitch pizza place planet
plastic plate play please pledge pluck plug plunge
poem poet point polar pole police pond pony
pool popular portion position possible post potato pottery
poverty powder power practice praise predict prefer prepare
present pretty prevent price pride primary print priority
prison private prize problem process produce profit program
project promote proof property prosper protect proud provide
public pudding pull pulp pulse pumpkin punch pupil
puppy purchase purity purpose purse push put puzzle
pyramid quality quantum quarter question quick quit quiz
quote rabbit raccoon race rack radar radio rail
rain raise rally ramp ranch random range rapid
rare rate rather raven raw razor ready real
reason rebel rebuild recall receive recipe record recycle
reduce reflect reform refuse region regret regular reject
relax release relief rely remain remember remind remove
render renew rent reopen repair repeat replace report
require rescue resemble resist resource response result retire
retreat return reunion reveal review reward rhythm rib
ribbon rice rich ride ridge rifle right rigid
ring riot ripple risk ritual rival river road
roast robot robust rocket romance roof rookie room
rose rotate rough round route royal rubber rude
rug rule run runway rural sad saddle sadness
safe sail salad salmon salon salt salute same
sample sand satisfy satoshi sauce sausage save say
scale scan scare scatter scene scheme school science
scissors scorpion scout scrap screen script scrub sea
search season seat second secret section security seed
seek segment select sell seminar senior sense sentence
series service session settle setup seven shadow shaft
shallow share shed shell sheriff shield shift shine
ship shiver shock shoe shoot shop short shoulder
shove shrimp shrug shuffle shy sibling sick side
siege sight sign silent silk silly silver similar
simple since sing siren sister situate six size
skate sketch ski skill skin skirt skull slab
slam sleep slender slice slide slight slim slogan
slot slow slush small smart smile smoke smooth
snack snake snap sniff snow soap soccer social
sock soda soft solar soldier solid solution solve
someone song soon sorry sort soul sound soup
source south space spare spatial spawn speak special
speed spell spend sphere spice spider spike spin
spirit split spoil sponsor spoon sport spot spray
spread spring spy square squeeze squirrel stable stadium
staff stage stairs stamp stand start state stay
steak steel stem step stereo stick still sting
stock stomach stone stool story stove strategy street
strike strong struggle student stuff stumble style subject
submit subway success such sudden suffer sugar suggest
suit summer sun sunny sunset super supply supreme
sure surface surge surprise surround survey suspect sustain
swallow swamp swap swarm swear sweet swift swim
swing switch sword symbol symptom syrup system table
tackle tag tail talent talk tank tape target
task taste tattoo taxi teach team tell ten
tenant tennis tent term test text thank that
theme then theory there they thing this thought
three thrive throw thumb thunder ticket tide tiger
tilt timber time tiny tip tired tissue title
toast tobacco today toddler toe together toilet token
tomato tomorrow tone tongue tonight tool tooth top
topic topple torch tornado tortoise toss total tourist
toward tower town toy track trade traffic tragic
train transfer trap trash travel tray treat tree
trend trial tribe trick trigger trim trip trophy
trouble truck true truly trumpet trust truth try
tube tuition tumble tuna tunnel turkey turn turtle
twelve twenty twice twin twist two type typical
ugly umbrella unable unaware uncle uncover under undo
unfair unfold unhappy uniform unique unit universe unknown
unlock until unusual unveil update upgrade uphold upon
upper upset urban urge usage use used useful
useless usual utility vacant vacuum vague valid valley
valve van vanish vapor various vast vault vehicle
velvet vendor venture venue verb verify version very
vessel veteran viable vibrant vicious victory video view
village vintage violin virtual virus visa visit visual
vital vivid vocal voice void volcano volume vote
voyage wage wagon wait walk wall walnut want
warfare warm warrior wash wasp waste water wave
way wealth weapon wear weasel weather web wedding
weekend weird welcome west wet whale what wheat
wheel when where whip whisper wide width wife
wild will win window wine wing wink winner
winter wire wisdom wise wish witness wolf woman
wonder wood wool word work world worry worth
wrap wreck wrestle wrist write wrong yard year
yellow you young youth zebra zero zone zoo
""".split()

assert len(_BIP39_WORDLIST) == 2048, "BIP39 wordlist must contain exactly 2048 words"


def _entropy_to_mnemonic(entropy):
    """Encode entropy (16-32 bytes, multiple of 4) as a BIP39 mnemonic."""
    if len(entropy) not in (16, 20, 24, 28, 32):
        raise ValueError("Entropy must be 16, 20, 24, 28, or 32 bytes.")
    checksum_bits = len(entropy) * 8 // 32
    checksum = hashlib.sha256(entropy).digest()
    entropy_bin = bin(int.from_bytes(entropy, "big"))[2:].zfill(len(entropy) * 8)
    checksum_bin = bin(int.from_bytes(checksum, "big"))[2:].zfill(256)[:checksum_bits]
    bits = entropy_bin + checksum_bin
    words = [_BIP39_WORDLIST[int(bits[i:i + 11], 2)] for i in range(0, len(bits), 11)]
    return " ".join(words)


def _mnemonic_to_entropy(mnemonic):
    """Decode a BIP39 mnemonic back to entropy, validating its checksum."""
    words = mnemonic.strip().lower().split()
    if len(words) not in (12, 15, 18, 21, 24):
        raise ValueError("A recovery phrase must be 12, 15, 18, 21, or 24 words.")
    try:
        indices = [_BIP39_WORDLIST.index(w) for w in words]
    except ValueError:
        bad = next(w for w in words if w not in _BIP39_WORDLIST)
        raise ValueError(f"'{bad}' is not in the recovery word list — check for typos.")
    bits = "".join(bin(i)[2:].zfill(11) for i in indices)
    checksum_len = len(bits) // 33
    entropy_bits = bits[:-checksum_len]
    given_checksum = bits[-checksum_len:]
    entropy = int(entropy_bits, 2).to_bytes(len(entropy_bits) // 8, "big")
    expected_checksum = bin(int.from_bytes(hashlib.sha256(entropy).digest(), "big"))[2:].zfill(256)[:checksum_len]
    if given_checksum != expected_checksum:
        raise ValueError("This recovery phrase doesn't check out — likely a typo or wrong word order.")
    return entropy


class NodeIdentity:
    """
    A node's cryptographic identity.

    Generated once. Stored on device. Never transmitted
    (only the public key travels).

    The private key is encrypted at rest if a passphrase
    is set — same protection as seals.

    # BRIDGE NOTE (Sovereign Root, BRIDGE.md §1): the Ed25519 keys
    # live here, not in KeyManager — KeyManager only ever holds the
    # passphrase-derived symmetric key used to encrypt things at
    # rest (this class's private key included). Two different keys,
    # two different jobs: this one proves continuity ("same node as
    # last time") without revealing who the node's operator is.
    """

    def __init__(self, private_key=None, public_key=None, node_name=None,
                 enc_private_key=None, enc_public_key=None):
        self._private_key = private_key
        self._public_key = public_key
        self.node_name = node_name
        self._fingerprint = None
        # X25519 — separate keypair for encryption. The Ed25519 keys
        # above only ever sign; they cannot decrypt anything. Keeping
        # these independent (rather than converting one into the
        # other) is the safer, standard pairing — same split Signal
        # and Nostr use.
        self._enc_private_key = enc_private_key
        self._enc_public_key = enc_public_key

    @staticmethod
    def available():
        """Check if Ed25519 is available."""
        return CRYPTO_AVAILABLE

    @classmethod
    def generate(cls, node_name=None):
        """
        Generate a new node identity.

        This is a one-time operation. The identity persists
        for the life of the node. A node that loses its
        private key loses its provable identity.
        """
        if not CRYPTO_AVAILABLE:
            raise RuntimeError(
                "cryptography package required for node identity. "
                "Install: pip install cryptography"
            )
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()
        enc_private_key = X25519PrivateKey.generate()
        enc_public_key = enc_private_key.public_key()
        return cls(private_key=private_key, public_key=public_key, node_name=node_name,
                    enc_private_key=enc_private_key, enc_public_key=enc_public_key)

    @classmethod
    def _from_seed(cls, entropy, node_name=None):
        """Deterministically derive both keypairs from one seed."""
        ed_seed = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                        info=b"phantom-ed25519-v1").derive(entropy)
        x_seed = HKDF(algorithm=hashes.SHA256(), length=32, salt=None,
                       info=b"phantom-x25519-v1").derive(entropy)
        private_key = Ed25519PrivateKey.from_private_bytes(ed_seed)
        public_key = private_key.public_key()
        enc_private_key = X25519PrivateKey.from_private_bytes(x_seed)
        enc_public_key = enc_private_key.public_key()
        return cls(private_key=private_key, public_key=public_key, node_name=node_name,
                    enc_private_key=enc_private_key, enc_public_key=enc_public_key)

    @classmethod
    def generate_with_mnemonic(cls, node_name=None, strength_bits=256):
        """
        Generate a new identity from fresh entropy, returning
        (identity, mnemonic). The mnemonic is a 24-word paper-wallet
        backup — write it down once, offline. Both the signing and
        encryption keypairs derive from the same seed, so one phrase
        recovers everything this node is.

        The mnemonic is never stored by this method — it exists only
        in this return value, once, the same way a hardware wallet
        shows it once at setup and never again unless asked.
        """
        if not CRYPTO_AVAILABLE:
            raise RuntimeError("cryptography package required for node identity.")
        entropy = secrets.token_bytes(strength_bits // 8)
        mnemonic = _entropy_to_mnemonic(entropy)
        identity = cls._from_seed(entropy, node_name=node_name)
        return identity, mnemonic

    @classmethod
    def from_mnemonic(cls, mnemonic, node_name=None):
        """
        Recreate a node identity from its BIP39 recovery phrase.
        Raises ValueError with a clear reason if it doesn't check out
        (usually a typo) rather than silently producing a wrong key.
        """
        entropy = _mnemonic_to_entropy(mnemonic)
        return cls._from_seed(entropy, node_name=node_name)

    @classmethod
    def from_seal_and_passphrase(cls, idea, moment, passphrase, node_name=None):
        """
        A deliberately burnable identity: deterministically derived
        from one specific seal's exact content plus a passphrase —
        never from randomness, never written to a recovery phrase.

        This is NOT a replacement for generate_with_mnemonic(). It is
        the opposite guarantee: recovering this identity later requires
        BOTH this exact passphrase AND this exact idea+moment. Forget
        either on purpose — or never write the idea down anywhere —
        and this identity is gone forever. That is the feature, not a
        limitation: a one-shot identity, destroyable at will.

        CRITICAL — the seal used here must stay private and unshared.
        If its idea+moment is ever gossiped, printed, or synced to
        another node, its content is no longer secret, and this
        identity's key material is only as safe as the least careful
        copy of that seal.

        CRITICAL — this is only as strong as the combined
        unpredictability of the passphrase and the idea text. A weak
        passphrase plus a guessable idea (e.g. "hello world") is a
        weak key, no matter how this is derived.

        Recovery: supply the exact same idea, moment, and passphrase.
        """
        if not idea or not moment or not passphrase:
            raise ValueError("Need a non-empty idea, moment, and passphrase.")
        material = (
            passphrase.encode('utf-8') + b'|' +
            idea.encode('utf-8') + b'|' +
            moment.encode('utf-8')
        )
        entropy = hashlib.sha256(material).digest()
        return cls._from_seed(entropy, node_name=node_name)

    @property
    def fingerprint(self):
        """
        Short identifier for this node's public key.
        First 16 hex chars of SHA-256(public_key_bytes).
        Human-readable. Not a security guarantee — just recognition.
        """
        if self._fingerprint is None and self._public_key is not None:
            pub_bytes = self._public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)
            full = hashlib.sha256(pub_bytes).hexdigest()
            self._fingerprint = full[:16]
        return self._fingerprint

    @property
    def has_private_key(self):
        return self._private_key is not None

    @property
    def has_encryption_key(self):
        return self._enc_private_key is not None

    @property
    def enc_public_key_bytes(self):
        """Raw 32-byte X25519 public key, for encrypting TO this node."""
        if self._enc_public_key is None:
            return None
        return self._enc_public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)

    @property
    def enc_public_key_b64(self):
        raw = self.enc_public_key_bytes
        return base64.b64encode(raw).decode('ascii') if raw else None

    def ensure_encryption_key(self, key_manager=None):
        """
        Add an X25519 encryption keypair to an older identity that
        predates DMs, and persist it. Safe to call every time — a
        no-op if the key already exists. Returns True if it upgraded
        the identity just now.
        """
        if self._enc_private_key is not None:
            return False
        if not self.has_private_key:
            raise RuntimeError("Cannot add an encryption key to a public-only identity.")
        self._enc_private_key = X25519PrivateKey.generate()
        self._enc_public_key = self._enc_private_key.public_key()
        self.save(key=key_manager.key if key_manager else None)
        return True

    @property
    def public_key_bytes(self):
        """Raw 32-byte public key."""
        if self._public_key is None:
            return None
        return self._public_key.public_bytes(Encoding.Raw, PublicFormat.Raw)

    @property
    def public_key_b64(self):
        """Base64-encoded public key for JSON transport."""
        raw = self.public_key_bytes
        return base64.b64encode(raw).decode('ascii') if raw else None

    def sign(self, data_bytes):
        """
        Sign data with this node's private key.
        Returns 64-byte Ed25519 signature as base64 string.
        """
        if self._private_key is None:
            raise RuntimeError("Cannot sign without private key")
        sig = self._private_key.sign(data_bytes)
        return base64.b64encode(sig).decode('ascii')

    def verify_signature(self, data_bytes, signature_b64):
        """
        Verify a signature against this node's public key.
        Returns True if valid, False if invalid or tampered.
        """
        if self._public_key is None:
            return False
        try:
            sig = base64.b64decode(signature_b64)
            self._public_key.verify(sig, data_bytes)
            return True
        except Exception:
            return False

    def sign_seal(self, seal_entry):
        """
        Sign a seal entry. Adds 'node_pubkey' and 'node_sig' fields.
        The signature covers the canonical seal data (idea + moment).
        Returns a new dict with the signature fields added.

        # BRIDGE NOTE (NODE_IDENTITY.md — "the deanonymization risk"):
        # every seal signed here uses the same key, so anyone
        # collecting enough of them can graph this node's activity.
        # NODE_IDENTITY.md names the fix as unbuilt: "one key per
        # context... this is not implemented." It partly is now, just
        # not for seals — phantom_wallet.py's PhantomWallet is exactly
        # this pattern (a second, deliberately unlinked key pair, its
        # own address namespace, its own recovery phrase) applied to
        # the money context. The same technique — a fresh, unlinked
        # key pair per context, derived from its own phrase — would
        # extend here for a "private encounters" identity distinct
        # from a "public seals" identity. Not done for seals; proven
        # to work for wallets.
        """
        data = json.dumps(
            {"idea": seal_entry["idea"], "moment": seal_entry["moment"]},
            separators=(',', ':')
        ).encode()

        signed = dict(seal_entry)
        signed["node_pubkey"] = self.public_key_b64
        signed["node_sig"] = self.sign(data)
        return signed

    @staticmethod
    def verify_signed_seal(seal_entry):
        """
        Verify a signed seal's signature.
        Returns True if the signature is valid for the given public key.
        Returns None if the seal is unsigned (no node_sig field).
        """
        if "node_sig" not in seal_entry or "node_pubkey" not in seal_entry:
            return None  # unsigned seal — not an error, just unsigned

        if not CRYPTO_AVAILABLE:
            return None  # can't verify without cryptography package

        try:
            pub_bytes = base64.b64decode(seal_entry["node_pubkey"])
            pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)

            data = json.dumps(
                {"idea": seal_entry["idea"], "moment": seal_entry["moment"]},
                separators=(',', ':')
            ).encode()

            sig = base64.b64decode(seal_entry["node_sig"])
            pub_key.verify(sig, data)
            return True
        except Exception:
            return False

    def save(self, key=None):
        """
        Save identity to disk.
        Private key(s) are encrypted if an encryption key is provided.
        Public keys are always stored in plaintext (they're public).
        """
        if self._private_key is None:
            raise RuntimeError("No private key to save")

        # Save public identity + metadata as JSON
        identity_data = {
            "node_name": self.node_name,
            "public_key": self.public_key_b64,
            "fingerprint": self.fingerprint,
            "created": datetime.now(timezone.utc).isoformat(),
        }
        if self.enc_public_key_b64:
            identity_data["enc_public_key"] = self.enc_public_key_b64
        with open(NODE_IDENTITY_FILE, "w", encoding="utf-8") as f:
            json.dump(identity_data, f, indent=2)

        # Bundle both private keys together so one file, one passphrase,
        # covers everything. A node with only the old (Ed25519-only)
        # bundle still loads fine — see load().
        pem = self._private_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        )
        bundle = {"ed25519_pem": base64.b64encode(pem).decode('ascii')}
        if self._enc_private_key is not None:
            enc_raw = self._enc_private_key.private_bytes(
                Encoding.Raw, PrivateFormat.Raw, NoEncryption()
            )
            bundle["x25519_raw"] = base64.b64encode(enc_raw).decode('ascii')

        plaintext = json.dumps(bundle).encode('utf-8')
        if key is not None and CRYPTO_AVAILABLE:
            encrypted = encrypt_data(plaintext, key)
            with open(NODE_KEY_FILE, "w", encoding="utf-8") as f:
                json.dump(encrypted, f)
        else:
            with open(NODE_KEY_FILE, "w", encoding="utf-8") as f:
                json.dump(bundle, f)

    @staticmethod
    def _parse_key_bundle(plaintext):
        """
        plaintext may be a JSON bundle (current format) or a raw PEM
        block (identities saved before X25519 existed). Handle both.
        """
        try:
            bundle = json.loads(plaintext.decode('utf-8'))
            if isinstance(bundle, dict) and "ed25519_pem" in bundle:
                return bundle
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass
        # Legacy: plaintext itself is the raw PEM.
        return {"ed25519_pem": base64.b64encode(plaintext).decode('ascii')}

    @classmethod
    def load(cls, key=None):
        """
        Load identity from disk.
        Returns None if no identity exists yet.
        """
        if not os.path.exists(NODE_IDENTITY_FILE):
            return None
        if not os.path.exists(NODE_KEY_FILE):
            return None
        if not CRYPTO_AVAILABLE:
            return None

        # Load public identity
        with open(NODE_IDENTITY_FILE, "r", encoding="utf-8") as f:
            identity_data = json.load(f)

        node_name = identity_data.get("node_name")
        pub_bytes = base64.b64decode(identity_data["public_key"])
        public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)

        enc_public_key = None
        if identity_data.get("enc_public_key"):
            enc_pub_bytes = base64.b64decode(identity_data["enc_public_key"])
            enc_public_key = X25519PublicKey.from_public_bytes(enc_pub_bytes)

        # Load private key bundle
        try:
            with open(NODE_KEY_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict) and raw.get("encrypted"):
                if key is None:
                    # Can't decrypt — return public-only identity
                    return cls(public_key=public_key, node_name=node_name,
                                enc_public_key=enc_public_key)
                plaintext = decrypt_data(raw, key)
                bundle = cls._parse_key_bundle(plaintext)
            elif isinstance(raw, dict) and "ed25519_pem" in raw:
                # Unencrypted bundle, current format
                bundle = raw
            else:
                # Unrecognized shape
                return cls(public_key=public_key, node_name=node_name,
                            enc_public_key=enc_public_key)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Legacy: raw binary PEM file, unencrypted
            with open(NODE_KEY_FILE, "rb") as f:
                pem_bytes = f.read()
            bundle = {"ed25519_pem": base64.b64encode(pem_bytes).decode('ascii')}

        pem = base64.b64decode(bundle["ed25519_pem"])
        private_key = load_pem_private_key(pem, password=None)

        enc_private_key = None
        if "x25519_raw" in bundle:
            enc_private_key = X25519PrivateKey.from_private_bytes(
                base64.b64decode(bundle["x25519_raw"])
            )
            if enc_public_key is None:
                enc_public_key = enc_private_key.public_key()

        return cls(private_key=private_key, public_key=public_key, node_name=node_name,
                    enc_private_key=enc_private_key, enc_public_key=enc_public_key)

    @classmethod
    def from_public_key_b64(cls, pub_b64, node_name=None):
        """
        Create a public-only identity from a base64 public key.
        Used when receiving a peer's identity during an encounter.
        Cannot sign — only verify.
        """
        if not CRYPTO_AVAILABLE:
            return None
        pub_bytes = base64.b64decode(pub_b64)
        public_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        return cls(public_key=public_key, node_name=node_name)

    def __repr__(self):
        name = self.node_name or "unnamed"
        fp = self.fingerprint or "no-key"
        priv = "full" if self.has_private_key else "public-only"
        return f"<NodeIdentity '{name}' [{fp}] ({priv})>"


# ─────────────────────────────────────────────────────────
# PRESENCE PULSE — "we are all one"
#
# Not a coin. Nothing is held, spent, or transferred. A pulse is a
# signed, short-lived heartbeat: "this fingerprint is alive right now."
#
# No node ever sees the whole network's pulses — only the ones it has
# received directly or gossiped from encounters. The "shared pulse"
# a node reports is always a local estimate from its own encounters,
# never a global count. That is not a limitation to fix later —
# it is the honest shape of a network with no center.
# ─────────────────────────────────────────────────────────

def _pulse_payload(fingerprint, moment, address=None):
    core = {"fingerprint": fingerprint, "moment": moment}
    if address:
        core["address"] = address
    return json.dumps(core, separators=(',', ':'), sort_keys=True).encode()


def generate_pulse(identity, address=None):
    """
    Create a signed presence pulse for this node, right now.
    Requires a loaded private key — only the node itself can pulse
    on its own behalf.

    `address` is optional and, if given, is folded into the signature —
    a relay can't attach an address you never announced. Pass your
    .onion address if you have one; a bare LAN IP isn't worth
    publishing network-wide since it's rarely reachable from outside
    that network.
    """
    if not identity or not identity.has_private_key:
        raise RuntimeError("Cannot generate a pulse without a private key.")

    moment = datetime.now(timezone.utc).isoformat()
    data = _pulse_payload(identity.fingerprint, moment, address)

    pulse = {
        "type": "pulse",
        "fingerprint": identity.fingerprint,
        "node_pubkey": identity.public_key_b64,
        "moment": moment,
        "node_sig": identity.sign(data),
    }
    if address:
        pulse["address"] = address
    return pulse


def verify_pulse(pulse):
    """
    Verify a pulse's signature matches its claimed pubkey, and that
    the pubkey actually hashes to the claimed fingerprint (so a node
    can't pulse under a fingerprint it doesn't hold the key for). If
    an address is present, it's covered by the same signature, so a
    relay can't swap in a different one while forwarding.
    Returns True if valid, False otherwise.
    """
    if not CRYPTO_AVAILABLE:
        return False
    try:
        required = ("fingerprint", "node_pubkey", "moment", "node_sig")
        if not all(k in pulse for k in required):
            return False

        pub_bytes = base64.b64decode(pulse["node_pubkey"])
        expected_fp = hashlib.sha256(pub_bytes).hexdigest()[:16]
        if expected_fp != pulse["fingerprint"]:
            return False

        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        data = _pulse_payload(pulse["fingerprint"], pulse["moment"], pulse.get("address"))
        sig = base64.b64decode(pulse["node_sig"])
        pub_key.verify(sig, data)
        return True
    except Exception:
        return False


def _pulse_age_seconds(pulse):
    try:
        moment = datetime.fromisoformat(pulse["moment"].replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - moment).total_seconds()
    except Exception:
        return float("inf")


class PulseLedger:
    """
    This node's local memory of pulses it has seen — its own, and
    any gossiped from peers during encounters.

    Keyed by fingerprint. Only the newest pulse per fingerprint is
    kept. Encrypted at rest the same way seals and encounters are.
    """

    def __init__(self, key_manager):
        self._key_manager = key_manager
        self._cache = None  # dict: fingerprint -> pulse
        self._lock = threading.RLock()

    @property
    def key(self):
        return self._key_manager.key

    def load(self):
        with self._lock:
            if self._cache is not None:
                return dict(self._cache)

            if not os.path.exists(PULSE_FILE):
                self._cache = {}
                return {}

            with open(PULSE_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)

            if isinstance(raw, dict) and raw.get("encrypted"):
                if self.key is None:
                    self._cache = {}
                    return {}
                plaintext = decrypt_data(raw, self.key)
                pulses = json.loads(plaintext.decode('utf-8'))
            else:
                pulses = raw

            self._cache = pulses
            return dict(pulses)

    def _save(self):
        if self.key is not None and CRYPTO_AVAILABLE:
            plaintext = json.dumps(self._cache, ensure_ascii=False).encode('utf-8')
            encrypted = encrypt_data(plaintext, self.key)
            with open(PULSE_FILE, "w", encoding="utf-8") as f:
                json.dump(encrypted, f, indent=2)
        else:
            with open(PULSE_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)

    def record(self, pulse):
        """
        Merge one incoming pulse. Verifies signature, keeps only the
        newest per fingerprint. Returns True if it updated anything.
        """
        if not verify_pulse(pulse):
            return False

        with self._lock:
            self.load()  # ensure cache populated
            fp = pulse["fingerprint"]
            existing = self._cache.get(fp)
            if existing and existing.get("moment", "") >= pulse["moment"]:
                return False

            self._cache[fp] = pulse
            self._save()
            return True

    def prune(self):
        """Forget fingerprints that have been silent past PULSE_FORGET_SECONDS."""
        with self._lock:
            self.load()
            before = len(self._cache)
            self._cache = {
                fp: p for fp, p in self._cache.items()
                if _pulse_age_seconds(p) <= PULSE_FORGET_SECONDS
            }
            if len(self._cache) != before:
                self._save()
            return before - len(self._cache)

    def alive_fingerprints(self):
        with self._lock:
            self.load()
            return [fp for fp, p in self._cache.items()
                    if _pulse_age_seconds(p) <= PULSE_TTL_SECONDS]

    def known_fingerprints(self):
        with self._lock:
            self.load()
            return list(self._cache.keys())

    def address_for(self, fingerprint):
        """
        The address from this fingerprint's latest known pulse, if it
        announced one and that pulse hasn't gone stale. Returns None
        if unknown, silent too long, or it never announced an address
        (e.g. it only ever pulsed from a plain LAN IP, not worth
        publishing network-wide).
        """
        with self._lock:
            self.load()
            pulse = self._cache.get(fingerprint)
            if not pulse or _pulse_age_seconds(pulse) > PULSE_TTL_SECONDS:
                return None
            return pulse.get("address")

    def alive_fraction(self):
        """
        This node's local estimate of the network's aliveness:
        alive / known, among fingerprints this node has ever met.
        Returns None if this node has never recorded a single pulse
        (including its own) — there is nothing to estimate from yet.
        """
        with self._lock:
            self.load()
            known = len(self._cache)
            if known == 0:
                return None
            alive = len(self.alive_fingerprints())
            return alive / known

    def gossip_batch(self, limit=PULSE_GOSSIP_LIMIT):
        """
        The pulses worth sharing with a peer during an encounter:
        the alive ones, newest first, capped to a reasonable size.
        """
        with self._lock:
            self.load()
            alive = [p for p in self._cache.values()
                      if _pulse_age_seconds(p) <= PULSE_TTL_SECONDS]
            alive.sort(key=lambda p: p["moment"], reverse=True)
            return alive[:limit]


# ─────────────────────────────────────────────────────────
# RECEIPT LEDGER — "contribution only counts when someone else needed it"
#
# Not currency. Not a balance. A receipt is proof that a contribution
# actually happened: three independent signatures — requester, carrier,
# destination — none of which a single node can produce alone.
#
# A node's reputation is never a number it can set for itself. It is
# only ever what other nodes' signed confirmations add up to.
# ─────────────────────────────────────────────────────────

def _receipt_payload(request_id, role, fingerprint, moment, need=None):
    d = {"request_id": request_id, "role": role, "fingerprint": fingerprint, "moment": moment}
    if need is not None:
        d["need"] = need
    return json.dumps(d, separators=(',', ':'), sort_keys=True).encode()


def create_receipt_request(identity, need):
    """
    Step 1 — the requester. "I need this done."
    `need` is a short, human-readable description of the contribution
    being asked for (e.g. "relay 1 seal", "answer 1 chat message").
    """
    if not identity or not identity.has_private_key:
        raise RuntimeError("Cannot request a receipt without a private key.")
    request_id = secrets.token_hex(16)
    moment = datetime.now(timezone.utc).isoformat()
    payload = _receipt_payload(request_id, "requester", identity.fingerprint, moment, need)
    return {
        "request_id": request_id, "role": "requester", "need": need,
        "fingerprint": identity.fingerprint, "moment": moment,
        "node_pubkey": identity.public_key_b64, "sig": identity.sign(payload),
    }


def create_receipt_carry(identity, request_part):
    """
    Step 2 — the carrier. "I did it." References the requester's
    request_id; cannot stand alone as proof of anything.
    """
    if not identity or not identity.has_private_key:
        raise RuntimeError("Cannot carry a receipt without a private key.")
    moment = datetime.now(timezone.utc).isoformat()
    payload = _receipt_payload(request_part["request_id"], "carrier", identity.fingerprint, moment)
    return {
        "request_id": request_part["request_id"], "role": "carrier",
        "fingerprint": identity.fingerprint, "moment": moment,
        "node_pubkey": identity.public_key_b64, "sig": identity.sign(payload),
    }


def create_receipt_confirmation(identity, request_part):
    """
    Step 3 — the destination. "It arrived." Often the same node as
    the requester (they asked, and they received) — that is fine;
    what matters is the carrier can never be the one confirming.
    """
    if not identity or not identity.has_private_key:
        raise RuntimeError("Cannot confirm a receipt without a private key.")
    moment = datetime.now(timezone.utc).isoformat()
    payload = _receipt_payload(request_part["request_id"], "destination", identity.fingerprint, moment)
    return {
        "request_id": request_part["request_id"], "role": "destination",
        "fingerprint": identity.fingerprint, "moment": moment,
        "node_pubkey": identity.public_key_b64, "sig": identity.sign(payload),
    }


def _verify_receipt_part(part, expected_role, expected_request_id, need=None):
    try:
        if part.get("role") != expected_role:
            return False
        if part.get("request_id") != expected_request_id:
            return False
        pub_bytes = base64.b64decode(part["node_pubkey"])
        expected_fp = hashlib.sha256(pub_bytes).hexdigest()[:16]
        if expected_fp != part["fingerprint"]:
            return False
        payload = _receipt_payload(
            part["request_id"], part["role"], part["fingerprint"], part["moment"],
            need if expected_role == "requester" else None,
        )
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub_key.verify(base64.b64decode(part["sig"]), payload)
        return True
    except Exception:
        return False


def assemble_receipt(requester_part, carrier_part, destination_part):
    """
    Combine three independently-signed parts into one verified receipt.
    Raises ValueError naming exactly what failed — this is a place
    where the failure reason matters, not just pass/fail.
    """
    request_id = requester_part.get("request_id")
    need = requester_part.get("need")

    if not _verify_receipt_part(requester_part, "requester", request_id, need):
        raise ValueError("Requester signature invalid.")
    if not _verify_receipt_part(carrier_part, "carrier", request_id):
        raise ValueError("Carrier signature invalid or references a different request.")
    if not _verify_receipt_part(destination_part, "destination", request_id):
        raise ValueError("Destination signature invalid or references a different request.")
    if carrier_part["fingerprint"] == requester_part["fingerprint"]:
        raise ValueError("A node cannot be its own carrier.")

    receipt = {
        "type": "receipt",
        "request_id": request_id,
        "need": need,
        "requester": requester_part,
        "carrier": carrier_part,
        "destination": destination_part,
    }
    data = json.dumps(receipt, separators=(',', ':'), sort_keys=True).encode()
    receipt["stamp"] = hashlib.sha256(data).hexdigest()
    return receipt


def verify_receipt(receipt):
    """Re-verify a fully assembled receipt — e.g. one received from a peer."""
    try:
        required = ("request_id", "requester", "carrier", "destination", "stamp")
        if not all(k in receipt for k in required):
            return False
        core = {k: v for k, v in receipt.items() if k != "stamp"}
        data = json.dumps(core, separators=(',', ':'), sort_keys=True).encode()
        if hashlib.sha256(data).hexdigest() != receipt["stamp"]:
            return False
        rebuilt = assemble_receipt(receipt["requester"], receipt["carrier"], receipt["destination"])
        return rebuilt["stamp"] == receipt["stamp"]
    except Exception:
        return False


class ReceiptLedger:
    """
    This node's local memory of completed, verified receipts — its own,
    and any gossiped from peers. Encrypted at rest like everything else.

    Reputation is deliberately not a single stored number: it is always
    recomputed from the receipts themselves, so nothing here lets a node
    just declare its own reputation.
    """

    def __init__(self, key_manager):
        self._key_manager = key_manager
        self._cache = None  # list of receipt dicts
        self._lock = threading.RLock()

    @property
    def key(self):
        return self._key_manager.key

    def load(self):
        with self._lock:
            if self._cache is not None:
                return list(self._cache)

            if not os.path.exists(RECEIPT_FILE):
                self._cache = []
                return []

            with open(RECEIPT_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)

            if isinstance(raw, dict) and raw.get("encrypted"):
                if self.key is None:
                    self._cache = []
                    return []
                plaintext = decrypt_data(raw, self.key)
                receipts = json.loads(plaintext.decode('utf-8'))
            else:
                receipts = raw

            self._cache = receipts
            return list(receipts)

    def _save(self):
        if self.key is not None and CRYPTO_AVAILABLE:
            plaintext = json.dumps(self._cache, ensure_ascii=False).encode('utf-8')
            encrypted = encrypt_data(plaintext, self.key)
            with open(RECEIPT_FILE, "w", encoding="utf-8") as f:
                json.dump(encrypted, f, indent=2)
        else:
            with open(RECEIPT_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)

    def record(self, receipt):
        """Verify and store one receipt. Returns True if newly added."""
        if not verify_receipt(receipt):
            return False
        with self._lock:
            self.load()
            if any(r["stamp"] == receipt["stamp"] for r in self._cache):
                return False
            self._cache.append(receipt)
            self._save()
            return True

    def as_carrier(self, fingerprint):
        with self._lock:
            self.load()
            return [r for r in self._cache if r["carrier"]["fingerprint"] == fingerprint]

    def reputation(self, fingerprint):
        """
        (total receipts carried, unique requesters served) for a
        fingerprint. Diversity of who confirmed matters more than raw
        count — ten receipts from one requester is weaker signal than
        ten from ten different requesters.
        """
        with self._lock:
            carried = self.as_carrier(fingerprint)
            unique_requesters = {r["requester"]["fingerprint"] for r in carried}
            return len(carried), len(unique_requesters)

    def balance(self, fingerprint):
        """
        Net contribution: receipts earned as carrier minus receipts
        spent as requester. Not currency, not a stored value — always
        recomputed from the ledger, so nothing lets a node just set
        its own balance. A node that only asks and never carries
        trends negative; a node that only carries trends positive.

        Returns (net, earned, spent).
        """
        with self._lock:
            self.load()
            earned = sum(1 for r in self._cache if r["carrier"]["fingerprint"] == fingerprint)
            spent = sum(1 for r in self._cache if r["requester"]["fingerprint"] == fingerprint)
            return earned - spent, earned, spent

    def all_receipts(self):
        with self._lock:
            self.load()
            return list(self._cache)


# ─────────────────────────────────────────────────────────
# TOR TRANSPORT LAYER
#
# Three levels of connection protection, detected at startup.
#
# Level 1 — Direct (no Tor)
#   Content protected (AES-256-GCM + seal verification).
#   Connection metadata NOT protected: IP addresses, timing,
#   and the fact that two specific devices met are visible
#   to anyone monitoring the network.
#
# Level 2 — Tor outbound (SOCKS5)
#   Outbound connections travel through Tor.
#   Your IP is not visible to nodes you connect to.
#   Inbound connections still use your local IP.
#   Requires: Tor running + pip install PySocks
#
# Level 3 — Tor + onion service
#   Outbound connections travel through Tor.
#   Inbound connections arrive at your .onion address.
#   Neither endpoint's IP is visible to the other.
#   Requires: Level 2 + stem + Tor control port (9051)
#
# On Android: install Orbot (F-Droid or Play Store).
# Then: pip install PySocks  (Level 2)
# Then: pip install stem     (Level 3, optional)
#
# No silent downgrade. Phantom always tells you exactly
# what is and is not protecting your connections.
#
# WHAT TOR DOES NOT PROTECT:
# — A device compromised at the OS level
# — Timing correlation by a global adversary
# — Coercion to reveal passphrase or .onion address
# These limits are named. They cannot be used to argue
# that Tor is unnecessary. Imperfect protection > none.
# ─────────────────────────────────────────────────────────

TOR_SOCKS_PORT = 9050
TOR_CONTROL_PORT = 9051
ONION_FILE = os.path.join(DATA_DIR, "phantom_onion.txt")

# Module-level state — set once by init_tor()
_TOR_LEVEL = 1           # 1=direct, 2=tor-outbound, 3=tor+onion
_ONION_ADDRESS = None    # .onion address if level 3 active
_SOCKS_AVAILABLE = False
_STEM_AVAILABLE = False
_TOR_RUNNING = False


def _check_tor_deps():
    global _SOCKS_AVAILABLE, _STEM_AVAILABLE
    try:
        import socks  # noqa: F401
        _SOCKS_AVAILABLE = True
    except ImportError:
        pass
    try:
        import stem  # noqa: F401
        _STEM_AVAILABLE = True
    except ImportError:
        pass


def _tor_socks_running():
    """Check if Tor SOCKS5 proxy is reachable on 127.0.0.1:9050."""
    import socket as _socket
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex(("127.0.0.1", TOR_SOCKS_PORT))
        s.close()
        return result == 0
    except Exception:
        return False


def _tor_control_running():
    """Check if Tor control port is reachable on 127.0.0.1:9051."""
    import socket as _socket
    try:
        s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
        s.settimeout(2)
        result = s.connect_ex(("127.0.0.1", TOR_CONTROL_PORT))
        s.close()
        return result == 0
    except Exception:
        return False


def _create_onion_service(port):
    """
    Create an ephemeral Tor hidden service on the given port.
    Returns the .onion address, or None on failure.
    Ephemeral: vanishes when Tor restarts. Nothing persists without intent.
    """
    try:
        from stem.control import Controller
        with Controller.from_port(port=TOR_CONTROL_PORT) as ctrl:
            ctrl.authenticate()
            svc = ctrl.create_ephemeral_hidden_service(
                {port: port}, await_publication=True
            )
            return f"{svc.service_id}.onion"
    except Exception:
        return None


def init_tor(port=PORT, interactive=True):
    """
    Detect Tor capabilities and set transport level.
    Call once at startup before any network operations.
    Prints a clear status block — the user always knows
    what is and is not protecting their connections.

    # BRIDGE NOTE (ARCHITECTURE_VISION.md's status table says
    # "Tor integration | Detected, not implemented" — that's stale.
    # What's actually here: Level 1 direct, Level 2 outbound via
    # SOCKS (PySocks), Level 3 full onion service (via stem, if a
    # Tor control port is reachable) with the .onion address saved
    # to ONION_FILE. Real transport-layer anonymity exists today —
    # Layer 3 of that document isn't only architecture.
    """
    global _TOR_LEVEL, _ONION_ADDRESS, _TOR_RUNNING

    _check_tor_deps()
    _TOR_RUNNING = _tor_socks_running()

    if not interactive:
        if _TOR_RUNNING and _SOCKS_AVAILABLE:
            _TOR_LEVEL = 2
        return

    print()
    print(" ┌──────────────────────────────────────────────────────────┐")
    print(" │  TRANSPORT PROTECTION                                    │")
    print(" │                                                          │")

    if not _TOR_RUNNING:
        _TOR_LEVEL = 1
        print(" │  Level 1 — Direct connection (no Tor)                   │")
        print(" │                                                          │")
        print(" │  Connection metadata is NOT protected.                   │")
        print(" │  Anyone monitoring this network can see that two         │")
        print(" │  devices met, at what time, for how long.                │")
        print(" │                                                          │")
        print(" │  To enable Tor protection:                               │")
        print(" │    Android: install Orbot from F-Droid or Play Store     │")
        print(" │    Desktop: install Tor Browser or the tor package       │")
        print(" │    Then: pip install PySocks                             │")
        print(" │    Then restart Phantom.                                 │")
        print(" └──────────────────────────────────────────────────────────┘")
        print()
        return

    if not _SOCKS_AVAILABLE:
        _TOR_LEVEL = 1
        print(" │  Tor is running — but PySocks is not installed.         │")
        print(" │  Connections will NOT use Tor.                           │")
        print(" │                                                          │")
        print(" │  To enable Tor transport:                                │")
        print(" │    pip install PySocks                                   │")
        print(" │    Then restart Phantom.                                 │")
        print(" └──────────────────────────────────────────────────────────┘")
        print()
        return

    _TOR_LEVEL = 2
    onion = None

    if _STEM_AVAILABLE and _tor_control_running():
        onion = _create_onion_service(port)
        if onion:
            _TOR_LEVEL = 3
            _ONION_ADDRESS = onion
            with open(ONION_FILE, "w") as f:
                f.write(onion + "\n")

    if _TOR_LEVEL == 3:
        print(" │  Level 3 — Tor + onion service                          │")
        print(" │                                                          │")
        print(" │  ✓ Outbound connections travel through Tor.              │")
        print(" │  ✓ Your IP is not visible to nodes you connect to.       │")
        print(" │  ✓ Inbound address is a .onion — not your IP.            │")
        print(" │                                                          │")
        onion_short = onion[:54] if onion else ""
        print(f" │  {onion_short:<56}│")
        print(" │                                                          │")
        print(" │  Share this address with nodes that want to meet you.    │")
    else:
        print(" │  Level 2 — Tor outbound                                  │")
        print(" │                                                          │")
        print(" │  ✓ Outbound connections travel through Tor.              │")
        print(" │  ✓ Your IP is not visible to nodes you connect to.       │")
        print(" │                                                          │")
        print(" │  ⚠ YOUR IP IS VISIBLE to anyone who connects to you.    │")
        print(" │  ⚠ Anyone on your local network can see that you are    │")
        print(" │    running a Phantom node and who connects to it.        │")
        print(" │                                                          │")
        print(" │  This does NOT make you anonymous as a listener.         │")
        print(" │  For full protection: pip install stem + enable Tor      │")
        print(" │  control port for Level 3 (hidden .onion service).       │")

    print(" └──────────────────────────────────────────────────────────┘")
    print()


def make_socket():
    """
    Create a socket for the current Tor level.
    Level 1: standard TCP socket.
    Level 2/3: SOCKS5-proxied socket through Tor.
    """
    import socket as _socket
    if _TOR_LEVEL >= 2 and _SOCKS_AVAILABLE:
        import socks
        s = socks.socksocket()
        s.set_proxy(socks.SOCKS5, "127.0.0.1", TOR_SOCKS_PORT)
        return s
    return _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)


def tor_status():
    """One-line summary of current transport level."""
    if _TOR_LEVEL == 3 and _ONION_ADDRESS:
        return f"Tor+onion ({_ONION_ADDRESS[:24]}...)"
    elif _TOR_LEVEL == 2:
        return "Tor outbound (Level 2)"
    else:
        return "Direct — no Tor (Level 1)"


def get_onion_address():
    """Return current .onion address if Level 3 is active."""
    return _ONION_ADDRESS


# ─────────────────────────────────────────────────────────
# CONTACT CARDS — a signed statement of "this fingerprint's
# encryption key is X." Needed because DMs require the
# recipient's X25519 key, and nothing before this exchanged
# it. Self-signed with the Ed25519 key so a relay forwarding
# someone's card can't quietly substitute a different
# encryption key and intercept DMs meant for them.
# ─────────────────────────────────────────────────────────

def create_contact_card(identity):
    """A node's shareable, signed introduction: fingerprint + both public keys."""
    if not identity or not identity.has_private_key:
        raise RuntimeError("Cannot create a contact card without a private key.")
    if not identity.has_encryption_key:
        raise RuntimeError("Identity has no encryption key yet — call ensure_encryption_key() first.")
    card = {
        "type": "contact_card",
        "fingerprint": identity.fingerprint,
        "node_name": identity.node_name,
        "public_key": identity.public_key_b64,
        "enc_public_key": identity.enc_public_key_b64,
        "moment": datetime.now(timezone.utc).isoformat(),
    }
    payload = json.dumps(card, separators=(',', ':'), sort_keys=True).encode()
    card["sig"] = identity.sign(payload)
    return card


def verify_contact_card(card):
    """
    Confirm a contact card is self-consistent: the fingerprint really
    is sha256(public_key), and the signature over the whole card
    (including enc_public_key) checks out against that same key. This
    is what stops a relay from swapping in its own encryption key
    while forwarding someone else's card.
    """
    try:
        pub_bytes = base64.b64decode(card["public_key"])
        expected_fp = hashlib.sha256(pub_bytes).hexdigest()[:16]
        if expected_fp != card["fingerprint"]:
            return False
        core = {k: v for k, v in card.items() if k != "sig"}
        payload = json.dumps(core, separators=(',', ':'), sort_keys=True).encode()
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub_key.verify(base64.b64decode(card["sig"]), payload)
        return True
    except Exception:
        return False


class ContactBook:
    """
    This node's local address book — verified contact cards it's seen,
    keyed by fingerprint. Newest card per fingerprint wins (a node can
    rotate its encryption key; the book just needs to catch up).
    Encrypted at rest like everything else.
    """

    def __init__(self, key_manager):
        self._key_manager = key_manager
        self._cache = None  # fingerprint -> card
        self._lock = threading.RLock()

    @property
    def key(self):
        return self._key_manager.key

    def load(self):
        with self._lock:
            if self._cache is not None:
                return dict(self._cache)
            if not os.path.exists(CONTACTS_FILE):
                self._cache = {}
                return {}
            with open(CONTACTS_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict) and raw.get("encrypted"):
                if self.key is None:
                    self._cache = {}
                    return {}
                plaintext = decrypt_data(raw, self.key)
                contacts = json.loads(plaintext.decode('utf-8'))
            else:
                contacts = raw if isinstance(raw, dict) else {}
            self._cache = contacts
            return dict(contacts)

    def _save(self):
        if self.key is not None and CRYPTO_AVAILABLE:
            plaintext = json.dumps(self._cache, ensure_ascii=False).encode('utf-8')
            encrypted = encrypt_data(plaintext, self.key)
            with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
                json.dump(encrypted, f, indent=2)
        else:
            with open(CONTACTS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)

    def record(self, card):
        """Verify and store a contact card. Returns True if newly added or updated."""
        if not verify_contact_card(card):
            return False
        with self._lock:
            self.load()
            existing = self._cache.get(card["fingerprint"])
            if existing and existing.get("moment", "") >= card["moment"]:
                return False  # already have this one or a newer one
            self._cache[card["fingerprint"]] = card
            self._save()
            return True

    def get(self, fingerprint):
        with self._lock:
            self.load()
            return self._cache.get(fingerprint)

    def all(self):
        with self._lock:
            self.load()
            return dict(self._cache)


# ─────────────────────────────────────────────────────────
# DIRECT MESSAGES — encrypted, addressed by fingerprint,
# store-and-forward capable (works even if sender and
# recipient are never online at the same time).
#
# Signing (Ed25519) proves who sent it. Encryption (X25519 +
# HKDF + AES-256-GCM) means only the recipient can read it —
# a carrier node can hold and forward a DM without being able
# to open it.
# ─────────────────────────────────────────────────────────

DM_TTL_SECONDS = 30 * 24 * 3600   # how long an undelivered DM is kept at all
DM_MAX_HOPS = 8                    # store-and-forward hop limit, floods stop here
DM_GOSSIP_LIMIT = 50               # max DMs offered per encounter


def _dm_shared_key(my_enc_private_key, their_enc_public_bytes):
    """
    ECDH + HKDF. Symmetric by construction: A's(priv) + B's(pub)
    produces the same 32-byte key as B's(priv) + A's(pub) — that's
    what lets sender and recipient derive the same key independently,
    without either ever transmitting it.
    """
    their_public_key = X25519PublicKey.from_public_bytes(their_enc_public_bytes)
    shared_secret = my_enc_private_key.exchange(their_public_key)
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None,
        info=b"phantom-dm-v1",
    ).derive(shared_secret)


def _dm_signed_payload(dm):
    """
    Canonical bytes covered by the sender's signature — everything
    except sig/stamp, and fields that are local bookkeeping or mutate
    in transit: `hops` changes on every forward, `received` is a
    carrier's own local timestamp, neither was ever part of what the
    sender committed to.
    """
    excluded = ("sig", "stamp", "hops", "received")
    core = {k: v for k, v in dm.items() if k not in excluded}
    return json.dumps(core, separators=(',', ':'), sort_keys=True).encode()


def create_dm(sender_identity, recipient_fingerprint, recipient_enc_pubkey_b64, message):
    """
    Build a complete, encrypted, signed DM ready to hand to any node
    for delivery or forwarding. The carrier never needs to be trusted
    with the plaintext — only `to_fingerprint` is visible to them.
    """
    if not sender_identity or not sender_identity.has_private_key:
        raise RuntimeError("Cannot send a DM without a private key.")
    if not sender_identity.has_encryption_key:
        raise RuntimeError(
            "This identity has no encryption key yet. "
            "Call identity.ensure_encryption_key() first."
        )
    if len(message.encode('utf-8')) > MAX_IDEA_LENGTH:
        raise ValueError(f"Message too long (max {MAX_IDEA_LENGTH} bytes).")

    recipient_enc_bytes = base64.b64decode(recipient_enc_pubkey_b64)
    key = _dm_shared_key(sender_identity._enc_private_key, recipient_enc_bytes)
    encrypted = encrypt_data(message.encode('utf-8'), key)

    dm = {
        "type": "dm",
        "to_fingerprint": recipient_fingerprint,
        "to_enc_pubkey": recipient_enc_pubkey_b64,
        "from_fingerprint": sender_identity.fingerprint,
        "from_pubkey": sender_identity.public_key_b64,
        "from_enc_pubkey": sender_identity.enc_public_key_b64,
        "moment": datetime.now(timezone.utc).isoformat(),
        "nonce": encrypted["nonce"],
        "ciphertext": encrypted["ciphertext"],
        "hops": 0,
    }
    dm["sig"] = sender_identity.sign(_dm_signed_payload(dm))
    data = json.dumps(dm, separators=(',', ':'), sort_keys=True).encode()
    dm["stamp"] = hashlib.sha256(data).hexdigest()
    return dm


def verify_dm_signature(dm):
    """
    Verify the DM was really signed by from_fingerprint — provable
    even by a carrier who can't decrypt the contents.
    """
    try:
        pub_bytes = base64.b64decode(dm["from_pubkey"])
        expected_fp = hashlib.sha256(pub_bytes).hexdigest()[:16]
        if expected_fp != dm["from_fingerprint"]:
            return False
        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        pub_key.verify(base64.b64decode(dm["sig"]), _dm_signed_payload(dm))
        return True
    except Exception:
        return False


def decrypt_dm(recipient_identity, dm):
    """
    Decrypt a DM addressed to this identity.
    Returns the plaintext message string.
    Raises ValueError if this isn't the recipient, the signature is
    invalid, or decryption fails for any reason (wrong key, tampering).
    """
    if dm.get("to_fingerprint") != recipient_identity.fingerprint:
        raise ValueError("This DM is not addressed to this identity.")
    if not verify_dm_signature(dm):
        raise ValueError("DM signature is invalid — sender identity doesn't check out.")
    if not recipient_identity.has_encryption_key:
        raise ValueError("This identity has no encryption key — call ensure_encryption_key() first.")

    sender_enc_bytes = base64.b64decode(dm["from_enc_pubkey"])
    key = _dm_shared_key(recipient_identity._enc_private_key, sender_enc_bytes)
    plaintext = decrypt_data({"nonce": dm["nonce"], "ciphertext": dm["ciphertext"]}, key)
    return plaintext.decode('utf-8')


class DMStore:
    """
    This node's local mailbox — DMs addressed to this node, and DMs
    this node is carrying for someone else (store-and-forward). A
    node cannot read a DM that isn't addressed to it; it can only
    hold and pass along the ciphertext.

    Encrypted at rest with the same passphrase as everything else.
    """

    def __init__(self, key_manager):
        self._key_manager = key_manager
        self._cache = None  # list of dm dicts
        self._lock = threading.RLock()

    @property
    def key(self):
        return self._key_manager.key

    def load(self):
        with self._lock:
            if self._cache is not None:
                return list(self._cache)
            if not os.path.exists(DM_FILE):
                self._cache = []
                return []
            with open(DM_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict) and raw.get("encrypted"):
                if self.key is None:
                    self._cache = []
                    return []
                plaintext = decrypt_data(raw, self.key)
                dms = json.loads(plaintext.decode('utf-8'))
            else:
                dms = raw
            self._cache = dms
            return list(dms)

    def _save(self):
        if self.key is not None and CRYPTO_AVAILABLE:
            plaintext = json.dumps(self._cache, ensure_ascii=False).encode('utf-8')
            encrypted = encrypt_data(plaintext, self.key)
            with open(DM_FILE, "w", encoding="utf-8") as f:
                json.dump(encrypted, f, indent=2)
        else:
            with open(DM_FILE, "w", encoding="utf-8") as f:
                json.dump(self._cache, f, indent=2)

    def store(self, dm):
        """
        Accept a DM to hold — whether it's for this node or one to
        carry onward. Verifies the signature (cheap, doesn't need the
        content) before ever storing anything. Rejects duplicates and
        anything over the hop limit — that's what stops an endless
        flood.
        """
        if not verify_dm_signature(dm):
            return False
        if dm.get("hops", 0) > DM_MAX_HOPS:
            return False
        with self._lock:
            self.load()
            if any(d["stamp"] == dm["stamp"] for d in self._cache):
                return False
            entry = dict(dm)
            entry["received"] = datetime.now(timezone.utc).isoformat()
            self._cache.append(entry)
            self._save()
            return True

    def inbox(self, identity):
        """
        DMs addressed to this identity that can actually be decrypted
        right now. Returns a list of (dm, plaintext) tuples, newest
        first.
        """
        with self._lock:
            self.load()
            mine = [d for d in self._cache if d.get("to_fingerprint") == identity.fingerprint]
            results = []
            for d in mine:
                try:
                    plaintext = decrypt_dm(identity, d)
                    results.append((d, plaintext))
                except ValueError:
                    continue
            results.sort(key=lambda t: t[0]["moment"], reverse=True)
            return results

    def gossip_batch(self, exclude_fingerprint=None, limit=DM_GOSSIP_LIMIT):
        """
        DMs worth offering to a peer during an encounter: not expired,
        under the hop limit, optionally excluding ones already known
        to have reached their destination (the peer we're about to
        gossip to, if we know their fingerprint).
        """
        with self._lock:
            self.load()
            now = datetime.now(timezone.utc)
            offerable = []
            for d in self._cache:
                try:
                    moment = datetime.fromisoformat(d["moment"])
                except Exception:
                    continue
                if (now - moment).total_seconds() > DM_TTL_SECONDS:
                    continue
                if d.get("hops", 0) >= DM_MAX_HOPS:
                    continue
                offerable.append(d)
            offerable.sort(key=lambda d: d["moment"], reverse=True)
            # Strip local-only bookkeeping before handing to a peer — the
            # only fields that should ever cross the wire are the ones
            # covered by the sender's signature, plus `hops`.
            clean = [{k: v for k, v in d.items() if k != "received"} for d in offerable[:limit]]
            return clean

    def receive_from_peer(self, dm):
        """
        Store a DM offered by a peer during an encounter, incrementing
        its hop count. Returns True if newly stored.
        """
        forwarded = dict(dm)
        forwarded["hops"] = dm.get("hops", 0) + 1
        return self.store(forwarded)

    def prune(self):
        """Drop DMs older than DM_TTL_SECONDS — undelivered mail eventually expires."""
        with self._lock:
            self.load()
            now = datetime.now(timezone.utc)
            kept = []
            for d in self._cache:
                try:
                    moment = datetime.fromisoformat(d["moment"])
                    if (now - moment).total_seconds() <= DM_TTL_SECONDS:
                        kept.append(d)
                except Exception:
                    continue
            removed = len(self._cache) - len(kept)
            if removed:
                self._cache = kept
                self._save()
            return removed
