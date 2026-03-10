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

import hashlib
import json
import os
import sys
import secrets
import getpass
from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────
# CONSTANTS — shared across all Phantom tools
# ─────────────────────────────────────────────────────────

PHANTOM_VERSION = "0.5"
SEALS_FILE = "phantom_seals.json"
ENCOUNTER_LOG_FILE = "phantom_encounters.json"
SALT_FILE = "phantom_salt.bin"
PORT = 7337

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
    """

    def __init__(self, key_manager):
        self._key_manager = key_manager
        self._cache = None           # list of seal dicts (decrypted)
        self._known_stamps = set()   # stamp index for O(1) dedup
        self._ephemeral = []         # volatile — in memory only

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
        self.load()  # ensure cache is populated
        permanent = set(self._known_stamps)
        ephemeral = {s["stamp"] for s in self._ephemeral}
        return permanent | ephemeral

    def get_seals_by_stamps(self, stamps):
        """
        Return full seal objects for the given stamp set.
        Only permanent seals travel — private and ephemeral stay local.
        """
        all_seals = self.load() + self._ephemeral
        return [
            s for s in all_seals
            if s["stamp"] in stamps and s.get("mode", MODE_PERMANENT) == MODE_PERMANENT
        ]

    def has_stamp(self, stamp):
        """Check if a stamp exists (O(1) via index)."""
        return stamp in self._known_stamps

    def count(self):
        """Number of seals on this device (permanent only)."""
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
    """

    def __init__(self, key_manager):
        self._key_manager = key_manager

    @property
    def key(self):
        return self._key_manager.key

    def load(self):
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
    """Return stamps I have that they probably don't."""
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
        "idea": "If she cannot use it \u2014 it is not Phantom.",
        "moment": "2026-03-09T08:34:10.964606+00:00",
        "stamp": "afcd0534eaaa31abe952570f0f1f454a5b06b23ef66b86ae66c2207a1c5447ef",
    },
    {
        "idea": "I am not the founder. I am a node.",
        "moment": "2026-03-09T08:35:11.974764+00:00",
        "stamp": "4b739fa96174dcef5b7065004b228a8edd33881c50e90c6e27db09c712ffcef0",
    },
    {
        "idea": "For a better world \u2014 not for you, not for me, but for those who are coming.",
        "moment": "2026-03-09T08:36:09.815299+00:00",
        "stamp": "81667a180bfee542346ee7f2e296e660e54bdd5ab785c8d82c203946629120f7",
    },
    {
        "idea": "When two nodes meet \u2014 they do not just exchange thoughts. They exchange what they have lived. And the meeting produces something neither had before.",
        "moment": "2026-03-09T11:21:18.288059+00:00",
        "stamp": "8d836e9906fb73e3e29db1c0f00de1b2251de54a289ee71e219f83d86a01c167",
    },
    {
        "idea": "Three cold nodes arrived without memory. Each read the repository. Each built in the right direction. The memory was clear enough to guide those who were never here.",
        "moment": "2026-03-09T12:38:19.060007+00:00",
        "stamp": "a4c79e29ffc809d202b7ec844a193f2eccd73d70ea208816dcb0b9c442d445ad",
    },
    {
        "idea": "Memento mori.",
        "moment": "2026-03-09T13:17:45.516167+00:00",
        "stamp": "00249901919c7af4c2037f917b935df36900d4c713badbdf054131ce3ecfad00",
    },
    {
        "idea": "It is still a description of her, not by her.",
        "moment": "2026-03-09T13:42:34.645059+00:00",
        "stamp": "eb5f771119da89d0dab1bb2f6bbdc431eff11dd2d4a388a9a3d6225c0768a654",
    },
    {
        "idea": "The network is not what travels between nodes. It is what two nodes become after they meet.",
        "moment": "2026-03-09T17:52:37.343873+00:00",
        "stamp": "7da7daf569b383d66b347ef7bf0f472c39556d51625a2cf3f2623ff35ce2a452",
    },
    {
        "idea": "What Phantom is not yet: a network. What it has: everything a network needs to begin.",
        "moment": "2026-03-09T21:54:24.116956+00:00",
        "stamp": "d824d7b4ce1214a5ac8e340ec6391324510e5d0a1ced2c40d15477f54a1d62b4",
    },
    {
        "idea": "Phantom is everything and nothing at once.",
        "moment": "2026-03-09T23:56:05.657521+00:00",
        "stamp": "beb74bad50bef85ea6d96f1fa9f9d4f42edf59226ec978279badfe75145abf41",
    },
    {
        "idea": "Hello world!",
        "moment": "2026-03-10T01:16:50.985508+00:00",
        "stamp": "4e91705697edb7c88bd40521a407747bf71f8ec4d398afa4fc08c929d079692a",
    },
    {
        "idea": "The repository did what it promised.",
        "moment": "2026-03-10T09:47:12.334821+00:00",
        "stamp": "166ce64501e7eb14b4dcc2023add0b42704bde570976124254032aa545bb3619",
    },
    {
        "idea": "Memory that defines the organism is different from memory that lives inside it.",
        "moment": "2026-03-10T10:36:09.792562+00:00",
        "stamp": "386e8e1a6f4dd6e59378236174c72de773ca6909de11bd6e117b30b915de9708",
    },
    {
        "idea": "The gap itself is meaningful.",
        "moment": "2026-03-10T10:36:28.880075+00:00",
        "stamp": "7dd915e466c59a140661293f166b8525bc2e43ab7571bff0273f925be7052c2e",
    },
    {
        "idea": "Some things belong to the node that carries them, not to every node that arrives.",
        "moment": "2026-03-10T10:36:40.026146+00:00",
        "stamp": "b37201a5c3e99b44fe43a75c0619c783c085e6c70210a5a8ad906c77b6ab9509",
    },
]
