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

import hashlib
import hmac
import json
import os
import sys
import secrets
import getpass
import base64
import binascii
from datetime import datetime, timezone

# ─────────────────────────────────────────────────────────
# CONSTANTS — shared across all Phantom tools
# ─────────────────────────────────────────────────────────

PHANTOM_VERSION = "0.6"
SEALS_FILE = "phantom_seals.json"
ENCOUNTER_LOG_FILE = "phantom_encounters.json"
SALT_FILE = "phantom_salt.bin"
NODE_KEY_FILE = "phantom_node.key"
NODE_IDENTITY_FILE = "phantom_node.pub"
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
    from cryptography.hazmat.primitives.asymmetric.ed25519 import (
        Ed25519PrivateKey, Ed25519PublicKey
    )
    from cryptography.hazmat.primitives.serialization import (
        Encoding, PublicFormat, PrivateFormat, NoEncryption,
        load_pem_private_key, load_pem_public_key
    )
    from cryptography.exceptions import InvalidSignature, InvalidTag
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
    except InvalidTag:
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
    return hmac.compare_digest(expected, stamp)


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
        """Seal the encounter and append to the log.

        If encryption is not available, peer address is hashed
        to prevent storing a plaintext social graph on disk.
        """
        encounters = self.load()
        moment = datetime.now(timezone.utc).isoformat()

        # Hash peer address if no encryption — never store plaintext IPs
        if self.key is None or not CRYPTO_AVAILABLE:
            stored_peer = hashlib.sha256(peer_addr.encode()).hexdigest()[:16]
        else:
            stored_peer = peer_addr

        encounter_data = {
            "peer": stored_peer,
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


def recv_json(conn, timeout=30):
    """
    Receive a newline-delimited JSON message with size limit.
    Reads in chunks for efficiency. Enforces MAX_MESSAGE_SIZE.
    Enforces timeout to prevent slow-loris attacks.
    """
    old_timeout = conn.gettimeout()
    conn.settimeout(timeout)
    data = b""
    try:
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
    finally:
        conn.settimeout(old_timeout)


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

class NodeIdentity:
    """
    A node's cryptographic identity.

    Generated once. Stored on device. Never transmitted
    (only the public key travels).

    The private key is encrypted at rest if a passphrase
    is set — same protection as seals.
    """

    def __init__(self, private_key=None, public_key=None, node_name=None):
        self._private_key = private_key
        self._public_key = public_key
        self.node_name = node_name
        self._fingerprint = None

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
        return cls(private_key=private_key, public_key=public_key, node_name=node_name)

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
        except (InvalidSignature, ValueError, binascii.Error):
            return False

    def sign_seal(self, seal_entry):
        """
        Sign a seal entry. Adds 'node_pubkey' and 'node_sig' fields.
        The signature covers the canonical seal data (idea + moment).
        Returns a new dict with the signature fields added.
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
        except (InvalidSignature, ValueError, binascii.Error):
            return False

    def save(self, key=None):
        """
        Save identity to disk.
        Private key is encrypted if an encryption key is provided.
        Public key is always stored in plaintext (it's public).
        """
        if self._private_key is None:
            raise RuntimeError("No private key to save")

        # Save public key + metadata as JSON
        identity_data = {
            "node_name": self.node_name,
            "public_key": self.public_key_b64,
            "fingerprint": self.fingerprint,
            "created": datetime.now(timezone.utc).isoformat(),
        }
        with open(NODE_IDENTITY_FILE, "w", encoding="utf-8") as f:
            json.dump(identity_data, f, indent=2)

        # Save private key — encrypted if possible
        pem = self._private_key.private_bytes(
            Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
        )
        if key is not None and CRYPTO_AVAILABLE:
            encrypted = encrypt_data(pem, key)
            with open(NODE_KEY_FILE, "w", encoding="utf-8") as f:
                json.dump(encrypted, f)
            os.chmod(NODE_KEY_FILE, 0o600)
        else:
            with open(NODE_KEY_FILE, "wb") as f:
                f.write(pem)
            os.chmod(NODE_KEY_FILE, 0o600)

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

        # Load private key
        try:
            # Try as encrypted JSON first
            with open(NODE_KEY_FILE, "r", encoding="utf-8") as f:
                raw = json.load(f)
            if isinstance(raw, dict) and raw.get("encrypted"):
                if key is None:
                    # Can't decrypt — return public-only identity
                    return cls(public_key=public_key, node_name=node_name)
                pem = decrypt_data(raw, key)
            else:
                # Unexpected format
                return cls(public_key=public_key, node_name=node_name)
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Binary PEM file (unencrypted)
            with open(NODE_KEY_FILE, "rb") as f:
                pem = f.read()

        private_key = load_pem_private_key(pem, password=None)
        return cls(private_key=private_key, public_key=public_key, node_name=node_name)

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
ONION_FILE = "phantom_onion.txt"

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
    except OSError:
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
    except OSError:
        return False


def _create_onion_service(port):
    """
    Create an ephemeral Tor hidden service on the given port.
    Returns the .onion address, or None on failure.
    Ephemeral: vanishes when Tor restarts. Nothing persists without intent.
    """
    try:
        from stem.control import Controller
        from stem import SocketError, ControllerError
        with Controller.from_port(port=TOR_CONTROL_PORT) as ctrl:
            ctrl.authenticate()
            svc = ctrl.create_ephemeral_hidden_service(
                {port: port}, await_publication=True
            )
            return f"{svc.service_id}.onion"
    except ImportError:
        return None
    except (OSError, SocketError, ControllerError):
        return None


def init_tor(port=PORT, interactive=True):
    """
    Detect Tor capabilities and set transport level.
    Call once at startup before any network operations.
    Prints a clear status block — the user always knows
    what is and is not protecting their connections.
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
