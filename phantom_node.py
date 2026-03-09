# phantom_node.py — v0.4 (Encryption at Rest)
#
# "When two nodes meet — they do not just exchange thoughts.
#  They exchange what they have lived.
#  And the meeting produces something neither had before."
#                              — The Sixth Seal
#
# WHAT CHANGED IN v0.4:
# Sealed thoughts are now encrypted on disk.
# The device can be taken. The thoughts stay yours.
#
# Before v0.4, phantom_seals.json was plaintext. Anyone with
# physical access to the device could read every sealed thought.
# That is not privacy. That is a promise without architecture.
#
# v0.4 changes this. Every seal is encrypted with AES-256-GCM
# before being written to disk. The key is derived from a
# passphrase using scrypt — a function designed to be expensive
# to brute-force. Phantom never stores the passphrase. Only the
# encrypted data exists on disk. Without the passphrase, the
# seals are unreadable — by anyone, including Phantom.
#
# THE HONEST TRADEOFF:
# A forgotten passphrase means lost seals. Permanently.
# There is no recovery. There is no reset. There is no
# "forgot my passphrase" flow — because that flow requires
# storing something that would compromise the protection.
# This is documented to the user before they set a passphrase.
# The choice is theirs to make, honestly informed.
#
# WHAT THIS DOES NOT PROTECT AGAINST:
# — A user coerced into entering their passphrase
# — An attacker watching the passphrase being entered
# — A device compromised at the OS level
# These threats are real. They are named here so they cannot
# be used to argue that encryption at rest is unnecessary.
# Imperfect protection is still protection.
#
# ENCRYPTION SCHEME:
# Key derivation: scrypt(passphrase, salt, n=2^14, r=8, p=1) → 32 bytes
# Encryption: AES-256-GCM (authenticated — detects tampering)
# Salt: 16 random bytes, stored alongside encrypted data
# Nonce: 12 random bytes, unique per seal, stored with ciphertext
#
# WHY AES-256-GCM:
# Authenticated encryption — if someone modifies the ciphertext,
# decryption fails loudly rather than silently returning garbage.
# A tampered seal is detected, not silently corrupted.
#
# DEPENDENCY:
# Requires: pip install cryptography
# Available on Termux (Android) with Python 3.8+.
# If not installed, Phantom runs in plaintext mode with a clear
# warning. The warning is not a footnote. It appears every time.
#
# HOW IT WORKS:
# 1. On first run, Phantom asks for a passphrase (or warns if skipped)
# 2. A random 16-byte salt is generated and stored in phantom_key.salt
# 3. The passphrase + salt → 32-byte key via scrypt (never stored)
# 4. Each seal is encrypted individually before writing to disk
# 5. The encrypted file is valid JSON — structure preserved, content protected
# 6. On load, each seal is decrypted with the same key
# 7. Wrong passphrase → decryption fails → seals unreadable
#
# PRIOR VERSIONS:
# v0.1 — broadcast latest seal
# v0.2 — bloom filter exchange, symmetric delta, encounter log
# v0.3 — seal modes (private, ephemeral, permanent), framing fix
# v0.4 — encryption at rest (this version)
#
# DEPENDENCIES: Python standard library + cryptography package
# Install: pip install cryptography
# Works in Termux on any Android phone with Python 3.8+
#
# PORT: 7337 (unchanged — nodes remain compatible at handshake)
# PROTOCOL VERSION: 0.3

import socket
import hashlib
import json
import threading
import sys
import os
import secrets
import getpass
from datetime import datetime, timezone

PORT = 7337
PHANTOM_VERSION = "0.4"
SEALS_FILE = "phantom_seals.json"
ENCOUNTER_LOG_FILE = "phantom_encounters.json"
SALT_FILE = "phantom_key.salt"

# ─────────────────────────────────────────────────────────
# ENCRYPTION LAYER
#
# AES-256-GCM authenticated encryption.
# Key derived from passphrase via scrypt.
# The passphrase never leaves memory. Never touches disk.
# ─────────────────────────────────────────────────────────

# Global key state — held in memory only, never written to disk
_ENCRYPTION_KEY = None       # 32-byte derived key, or None if no passphrase
_ENCRYPTION_ENABLED = False  # True only when cryptography package is available
_KNOWN_STAMPS = set()        # In-memory cache of all stamp hashes — populated at load

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _ENCRYPTION_ENABLED = True
except ImportError:
    _ENCRYPTION_ENABLED = False

def _encryption_available():
    return _ENCRYPTION_ENABLED

def _derive_key(passphrase: str, salt: bytes) -> bytes:
    """
    Derive a 32-byte key from a passphrase using scrypt.

    Parameters chosen for mobile hardware (Android, 2-4GB RAM):
      n=16384 (2^14) — memory/CPU cost. Halved from desktop default
      to keep derivation under ~1 second on a mid-range phone.
      r=8, p=1 — standard values.

    A brute-force attacker must run scrypt for every guess.
    At these parameters, ~1000 guesses/second on dedicated hardware.
    A 6-word passphrase has ~77 bits of entropy — effectively unbreakable.
    """
    return hashlib.scrypt(
        passphrase.encode('utf-8'),
        salt=salt,
        n=16384,
        r=8,
        p=1,
        dklen=32
    )

def _load_or_create_salt() -> bytes:
    """
    Load the salt from disk, or create and save a new one.
    The salt is not secret — it prevents precomputed attacks.
    Stored in phantom_key.salt alongside the seals file.
    """
    if os.path.exists(SALT_FILE):
        with open(SALT_FILE, 'rb') as f:
            return f.read()
    salt = secrets.token_bytes(16)
    with open(SALT_FILE, 'wb') as f:
        f.write(salt)
    return salt

def _encrypt_seal(plaintext: str) -> dict:
    """
    Encrypt a seal's JSON string with AES-256-GCM.
    Returns a dict with nonce and ciphertext as hex strings.
    Each seal gets a unique nonce — nonce reuse would be catastrophic.
    """
    nonce = secrets.token_bytes(12)
    aes = AESGCM(_ENCRYPTION_KEY)
    ciphertext = aes.encrypt(nonce, plaintext.encode('utf-8'), None)
    return {
        "encrypted": True,
        "nonce": nonce.hex(),
        "ciphertext": ciphertext.hex()
    }

def _decrypt_seal(encrypted: dict) -> str:
    """
    Decrypt a seal. Returns plaintext JSON string.
    Raises ValueError if the key is wrong or data is tampered.
    AES-GCM authentication catches both cases.
    """
    nonce = bytes.fromhex(encrypted["nonce"])
    ciphertext = bytes.fromhex(encrypted["ciphertext"])
    aes = AESGCM(_ENCRYPTION_KEY)
    try:
        return aes.decrypt(nonce, ciphertext, None).decode('utf-8')
    except Exception:
        raise ValueError(
            "Decryption failed. Wrong passphrase, or the data was tampered with."
        )

def init_encryption():
    """
    Initialize encryption at startup.

    Three paths:
    1. cryptography not installed → warn, run plaintext
    2. cryptography installed, user sets passphrase → encrypted
    3. cryptography installed, user skips → warn, run plaintext

    The warning for path 3 is not subtle.
    """
    global _ENCRYPTION_KEY

    if not _encryption_available():
        print()
        print(" ╔══════════════════════════════════════════════════════╗")
        print(" ║  ENCRYPTION NOT AVAILABLE                            ║")
        print(" ║                                                      ║")
        print(" ║  Your sealed thoughts will be stored as plaintext.   ║")
        print(" ║  Anyone with access to your device can read them.    ║")
        print(" ║                                                      ║")
        print(" ║  To enable encryption:                               ║")
        print(" ║    pip install cryptography                          ║")
        print(" ║  Then restart Phantom.                               ║")
        print(" ╚══════════════════════════════════════════════════════╝")
        print()
        return

    # Existing node — salt exists, just needs passphrase to unlock
    if os.path.exists(SALT_FILE):
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
        salt = _load_or_create_salt()
        print(" Deriving key... ", end="", flush=True)
        _ENCRYPTION_KEY = _derive_key(passphrase, salt)
        print("done.")
        # Verify the key works by attempting to load seals
        try:
            load_seals()
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
            _ENCRYPTION_KEY = None
            sys.exit(1)
        return

    # New node — first run. Ask to set a passphrase.
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
    print(" │  Your thoughts will be readable by anyone with your      │")
    print(" │  device. This choice can be changed later by deleting    │")
    print(" │  your seals file and starting fresh.                     │")
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

    salt = _load_or_create_salt()
    print(" Deriving key... ", end="", flush=True)
    _ENCRYPTION_KEY = _derive_key(passphrase, salt)
    print("done.")
    print(" Encryption enabled. Your thoughts are protected.\n")

# ─────────────────────────────────────────────────────────
# SEAL FUNCTIONS — unchanged from v0.1
# The seal format is the seal. It cannot change.
# ─────────────────────────────────────────────────────────

# SEAL MODES
# "private"   — never leaves this device
# "ephemeral" — travels but wipes on app close
# "permanent" — travels and persists (default)
EPHEMERAL_SEALS = []  # volatile — exists only in memory

def seal(idea, mode="permanent"):
    moment = datetime.now(timezone.utc).isoformat()
    data = json.dumps(
        {"idea": idea, "moment": moment},
        separators=(',', ':')
    )
    stamp = hashlib.sha256(data.encode()).hexdigest()
    return {"idea": idea, "moment": moment, "stamp": stamp, "mode": mode}

def verify(idea, moment, stamp):
    data = json.dumps(
        {"idea": idea, "moment": moment},
        separators=(',', ':')
    )
    expected = hashlib.sha256(data.encode()).hexdigest()
    return expected == stamp

# ─────────────────────────────────────────────────────────
# LOCAL SEAL STORAGE
# ─────────────────────────────────────────────────────────

def load_seals():
    """
    Load seals from disk, decrypting if encryption is active.

    The file is a JSON array. Each entry is either:
    - A plaintext seal dict (no encryption, or pre-v0.4)
    - An encrypted envelope: {"encrypted": true, "nonce": "...", "ciphertext": "..."}

    Mixed files are supported — a node that upgraded from v0.3 to v0.4
    mid-use will have both plaintext and encrypted seals. Both are read.
    New seals written after enabling encryption will be encrypted.
    Old plaintext seals are not retroactively encrypted — that would
    require rewriting the file with the passphrase, which is a separate
    migration step. The user is not surprised by this: plaintext seals
    were already on disk before encryption was enabled.
    """
    if not os.path.exists(SEALS_FILE):
        return []
    with open(SEALS_FILE, "r") as f:
        raw = json.load(f)

    if _ENCRYPTION_KEY is None:
        # No key — return plaintext entries as-is, skip encrypted ones
        result = []
        skipped = 0
        for entry in raw:
            if entry.get("encrypted"):
                skipped += 1
            else:
                result.append(entry)
                _KNOWN_STAMPS.add(entry.get("stamp", ""))
        if skipped:
            print(f" ({skipped} encrypted seal(s) not loaded — enter passphrase to access)")
        return result

    # Key available — decrypt encrypted entries, pass through plaintext
    result = []
    for entry in raw:
        if entry.get("encrypted"):
            plaintext = _decrypt_seal(entry)
            seal_obj = json.loads(plaintext)
            _KNOWN_STAMPS.add(seal_obj.get("stamp", ""))
            result.append(seal_obj)
        else:
            _KNOWN_STAMPS.add(entry.get("stamp", ""))
            result.append(entry)
    return result

def save_seal(entry):
    """
    Save a seal to disk, encrypting if encryption is active.

    Private seals never reach this function — they are handled at
    the UI layer. Ephemeral seals go to volatile memory only.
    Permanent seals (default) are written to disk.

    If encryption is active: the seal JSON is encrypted before writing.
    If encryption is not active: the seal is written as plaintext,
    with no silent downgrade — the user was warned at startup.
    """
    mode = entry.get("mode", "permanent")
    if mode == "ephemeral":
        if any(s["stamp"] == entry["stamp"] for s in EPHEMERAL_SEALS):
            return False
        EPHEMERAL_SEALS.append(entry)
        return True

    # Load current raw file — bypassing decryption to preserve
    # the existing encrypted entries exactly as stored.
    if os.path.exists(SEALS_FILE):
        with open(SEALS_FILE, "r") as f:
            raw = json.load(f)
    else:
        raw = []

    # Deduplication: check the in-memory stamp cache.
    # This works for both plaintext and encrypted seals — the cache
    # is populated by load_seals() at startup, which decrypts all entries.
    # New stamps are added to the cache on save, so the cache stays current
    # within a session without re-reading the file.
    if entry["stamp"] in _KNOWN_STAMPS:
        return False

    # Prepare the entry for storage
    if _ENCRYPTION_KEY is not None and _encryption_available():
        plaintext = json.dumps(entry)
        stored = _encrypt_seal(plaintext)
    else:
        stored = entry

    raw.append(stored)
    _KNOWN_STAMPS.add(entry["stamp"])
    with open(SEALS_FILE, "w") as f:
        json.dump(raw, f, indent=2)
    return True

def get_all_stamps():
    """Return the set of all stamp hashes this node holds (permanent + ephemeral)."""
    permanent = {s["stamp"] for s in load_seals()}
    ephemeral = {s["stamp"] for s in EPHEMERAL_SEALS}
    return permanent | ephemeral

def get_seals_by_stamps(stamps):
    """Return full seal objects for the given stamp set.
    Only permanent seals travel — private and ephemeral stay local."""
    all_seals = load_seals() + EPHEMERAL_SEALS
    return [s for s in all_seals 
            if s["stamp"] in stamps and s.get("mode", "permanent") == "permanent"]

# ─────────────────────────────────────────────────────────
# BLOOM FILTER
#
# A space-efficient way to share "what I have" without
# sharing the contents. The receiver uses it to compute
# the delta — what to send.
#
# Parameters chosen for Phantom's early scale:
#   size=8192 bits (~1KB), k=5 hash functions
#   At 100 seals: ~2.5% false positive rate
#   At 500 seals: ~12% false positive rate (still safe —
#     false positives waste bandwidth, never drop seals)
# ─────────────────────────────────────────────────────────

BLOOM_SIZE = 8192  # bits
BLOOM_K = 5        # hash functions

def _bloom_positions(stamp):
    """Return k bit positions for a given stamp."""
    positions = []
    for i in range(BLOOM_K):
        h = hashlib.sha256(f"{i}:{stamp}".encode()).hexdigest()
        positions.append(int(h, 16) % BLOOM_SIZE)
    return positions

def build_bloom(stamps):
    """Build a bloom filter from a set of stamps. Returns bytes."""
    bits = bytearray(BLOOM_SIZE // 8)
    for stamp in stamps:
        for pos in _bloom_positions(stamp):
            bits[pos // 8] |= (1 << (pos % 8))
    return bytes(bits)

def bloom_probably_has(bloom_bytes, stamp):
    """Return True if the bloom filter probably contains this stamp."""
    bits = bloom_bytes
    for pos in _bloom_positions(stamp):
        if not (bits[pos // 8] & (1 << (pos % 8))):
            return False
    return True

def compute_delta(my_stamps, their_bloom_bytes):
    """
    Return the stamps I have that they probably don't.
    This is what I will send them.
    """
    delta = set()
    for stamp in my_stamps:
        if not bloom_probably_has(their_bloom_bytes, stamp):
            delta.add(stamp)
    return delta

# ─────────────────────────────────────────────────────────
# ENCOUNTER LOG
#
# Every meeting between nodes is recorded locally.
# Not for surveillance — for the organism's memory.
# The encounter log is how a node knows its own history.
# ─────────────────────────────────────────────────────────

def load_encounters():
    if not os.path.exists(ENCOUNTER_LOG_FILE):
        return []
    with open(ENCOUNTER_LOG_FILE, "r") as f:
        return json.load(f)

def log_encounter(peer_addr, sent_count, received_count, received_stamps):
    """Seal the encounter itself and append to the log."""
    encounters = load_encounters()
    moment = datetime.now(timezone.utc).isoformat()

    encounter_data = {
        "peer": peer_addr,
        "moment": moment,
        "sent": sent_count,
        "received": received_count,
        "received_stamps": list(received_stamps)
    }

    # Seal the encounter record for integrity
    raw = json.dumps(encounter_data, separators=(',', ':'), sort_keys=True)
    encounter_stamp = hashlib.sha256(raw.encode()).hexdigest()
    encounter_data["encounter_stamp"] = encounter_stamp

    encounters.append(encounter_data)
    with open(ENCOUNTER_LOG_FILE, "w") as f:
        json.dump(encounters, f, indent=2)

    return encounter_stamp

# ─────────────────────────────────────────────────────────
# SEND / RECEIVE HELPERS
# ─────────────────────────────────────────────────────────

def send_json(conn, obj):
    conn.sendall((json.dumps(obj) + "\n").encode())

def recv_json(conn):
    # Read one byte at a time until newline delimiter.
    # Prevents consuming past the message boundary when two
    # messages arrive in quick succession on a fast network.
    data = b""
    while True:
        byte = conn.recv(1)
        if not byte:
            raise ConnectionError("Connection closed mid-message")
        data += byte
        if data.endswith(b"\n"):
            break
    return json.loads(data.decode().strip())

# ─────────────────────────────────────────────────────────
# ENCOUNTER PROTOCOL — NODE SIDE (listening)
#
# The meeting from the node's perspective:
#   1. Send hello
#   2. Send our bloom, receive theirs
#   3. Send delta (what they're missing)
#   4. Receive their delta, verify and store
#   5. Seal the encounter, log it
# ─────────────────────────────────────────────────────────

def handle_encounter(conn, addr):
    peer = addr[0]
    print(f"\n  Node connecting: {peer}")

    sent_stamps = set()
    received_stamps = set()

    try:
        # Step 1 — Hello
        send_json(conn, {"phantom": PHANTOM_VERSION, "type": "hello"})
        hello = recv_json(conn)
        if hello.get("type") != "hello":
            print("  Not a Phantom node. Closing.")
            return
        peer_version = hello.get("phantom", "unknown")
        print(f"  Phantom v{peer_version} node identified")

        # Step 2 — Bloom exchange
        my_stamps = get_all_stamps()
        my_bloom = build_bloom(my_stamps)
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "bloom",
            "bloom": list(my_bloom),
            "seal_count": len(my_stamps)
        })

        their_bloom_msg = recv_json(conn)
        if their_bloom_msg.get("type") != "bloom":
            print("  Expected bloom. Closing.")
            return
        their_bloom = bytes(their_bloom_msg["bloom"])
        their_count = their_bloom_msg.get("seal_count", "?")
        print(f"  I carry {len(my_stamps)} seal(s). They carry {their_count}.")

        # Step 3 — Compute and send our delta
        delta_stamps = compute_delta(my_stamps, their_bloom)
        delta_seals = get_seals_by_stamps(delta_stamps)
        print(f"  Sending {len(delta_seals)} seal(s) they haven't seen.")
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "delta",
            "seals": delta_seals,
            "count": len(delta_seals)
        })
        sent_stamps = {s["stamp"] for s in delta_seals}

        # Step 4 — Receive their delta
        their_delta_msg = recv_json(conn)
        if their_delta_msg.get("type") != "delta":
            print("  Expected delta from visitor. Closing.")
            return

        incoming = their_delta_msg.get("seals", [])
        print(f"  Receiving {len(incoming)} seal(s) from them.")

        for entry in incoming:
            if verify(entry["idea"], entry["moment"], entry["stamp"]):
                if save_seal(entry):
                    received_stamps.add(entry["stamp"])
                    print(f"  + \"{entry['idea'][:55]}\"")
                else:
                    print(f"  (Already have: \"{entry['idea'][:40]}\")")
            else:
                print(f"  x Rejected (invalid seal): \"{entry['idea'][:40]}\"")

        # Step 5 — Seal and log the encounter
        encounter_stamp = log_encounter(
            peer, len(sent_stamps), len(received_stamps), received_stamps
        )
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "encounter_sealed",
            "encounter_stamp": encounter_stamp,
            "sent": len(sent_stamps),
            "received": len(received_stamps)
        })

        print(f"\n  Meeting complete.")
        print(f"  Sent {len(sent_stamps)} | Received {len(received_stamps)}")
        print(f"  Encounter: {encounter_stamp[:24]}...")

    except Exception as e:
        print(f"  Error during encounter: {e}")
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────
# NODE — LISTENING
# ─────────────────────────────────────────────────────────

def listen():
    print("\n PHANTOM NODE — v0.2 (Encounter)")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    my_stamps = get_all_stamps()
    print(f" Carrying {len(my_stamps)} seal(s).")
    if not my_stamps:
        print(" Seal something first: python phantom_node.py --seal")

    print(f"\n Waiting for visitors on port {PORT}...")
    print(" Press Ctrl+C to stop.\n")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen(5)

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_encounter, args=(conn, addr))
            t.daemon = True
            t.start()
    except KeyboardInterrupt:
        print("\n Node stopping.")
    finally:
        server.close()

# ─────────────────────────────────────────────────────────
# ENCOUNTER PROTOCOL — VISITOR SIDE (connecting)
#
# Mirror of the node's protocol. Symmetric exchange —
# both sides give and both sides receive.
# ─────────────────────────────────────────────────────────

def find_node(network_prefix="192.168.43"):
    print(f" Scanning for Phantom node...")
    for i in range(1, 255):
        ip = f"{network_prefix}.{i}"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.08)
            result = s.connect_ex((ip, PORT))
            s.close()
            if result == 0:
                return ip
        except:
            pass
    return None

def connect(host=None):
    print("\n PHANTOM VISITOR — v0.2 (Encounter)")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if not host:
        quick_try = "192.168.43.1"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((quick_try, PORT))
            s.close()
            host = quick_try
            print(f" Found node at {host}")
        except:
            host = find_node()

    if not host:
        print("\n No Phantom node found.")
        print(" Make sure you are connected to 'phantom-node' WiFi")
        print(" and the other phone is running:")
        print(" python phantom_node.py --listen")
        return

    print(f" Connecting to {host}:{PORT}...")

    sent_stamps = set()
    received_stamps = set()

    try:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(30)
        conn.connect((host, PORT))

        # Step 1 — Hello
        hello = recv_json(conn)
        if hello.get("type") != "hello":
            print(" Not a Phantom node.")
            return
        peer_version = hello.get("phantom", "unknown")
        send_json(conn, {"phantom": PHANTOM_VERSION, "type": "hello"})
        print(f" Phantom v{peer_version} node found")

        # Step 2 — Bloom exchange
        their_bloom_msg = recv_json(conn)
        if their_bloom_msg.get("type") != "bloom":
            print(" Expected bloom. Closing.")
            return
        their_bloom = bytes(their_bloom_msg["bloom"])
        their_count = their_bloom_msg.get("seal_count", "?")

        my_stamps = get_all_stamps()
        my_bloom = build_bloom(my_stamps)
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "bloom",
            "bloom": list(my_bloom),
            "seal_count": len(my_stamps)
        })
        print(f" I carry {len(my_stamps)} seal(s). They carry {their_count}.")

        # Step 3 — Receive their delta
        their_delta_msg = recv_json(conn)
        if their_delta_msg.get("type") != "delta":
            print(" Expected delta from node. Closing.")
            return
        incoming = their_delta_msg.get("seals", [])
        print(f"\n Receiving {len(incoming)} seal(s) from them.")

        for entry in incoming:
            if verify(entry["idea"], entry["moment"], entry["stamp"]):
                if save_seal(entry):
                    received_stamps.add(entry["stamp"])
                    print(f" + \"{entry['idea'][:55]}\"")
                else:
                    print(f" (Already have: \"{entry['idea'][:40]}\")")
            else:
                print(f" x Rejected (invalid seal): \"{entry['idea'][:40]}\"")

        # Step 4 — Send our delta
        delta_stamps = compute_delta(my_stamps, their_bloom)
        delta_seals = get_seals_by_stamps(delta_stamps)
        print(f"\n Sending {len(delta_seals)} seal(s) they haven't seen.")
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "delta",
            "seals": delta_seals,
            "count": len(delta_seals)
        })
        sent_stamps = {s["stamp"] for s in delta_seals}

        # Step 5 — Receive encounter seal, log our own
        seal_msg = recv_json(conn)
        their_encounter_stamp = seal_msg.get("encounter_stamp", "")
        our_encounter_stamp = log_encounter(
            host, len(sent_stamps), len(received_stamps), received_stamps
        )

        print(f"\n MEETING COMPLETE")
        print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f" Sent:     {len(sent_stamps)} seal(s)")
        print(f" Received: {len(received_stamps)} seal(s)")
        print(f" Their encounter: {their_encounter_stamp[:24]}...")
        print(f" Our encounter:   {our_encounter_stamp[:24]}...")
        print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    except ConnectionRefusedError:
        print(f" Could not connect to {host}:{PORT}")
        print(" Is the other phone running: python phantom_node.py --listen ?")
    except Exception as e:
        print(f" Error: {e}")
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────
# ENCOUNTER LOG DISPLAY
# ─────────────────────────────────────────────────────────

def show_encounters():
    encounters = load_encounters()
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
# SEAL + LIST — unchanged from v0.1
# ─────────────────────────────────────────────────────────

def seal_interactive():
    idea = input("\n Enter idea to seal:\n > ").strip()
    if not idea:
        return
    entry = seal(idea)
    save_seal(entry)
    print(f"\n PHANTOM SEAL")
    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" Idea:   {entry['idea']}")
    print(f" Moment: {entry['moment']}")
    print(f" Stamp:  {entry['stamp']}")
    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    print(" Sealed and saved. Ready to travel.\n")

def list_seals():
    seals = load_seals()
    if not seals:
        print(" No sealed thoughts yet.")
        return
    print(f"\n {len(seals)} sealed thought(s):\n")
    for i, s in enumerate(seals, 1):
        print(f" [{i}] {s['idea'][:70]}")
        print(f"     {s['moment']}")
        print()

# ─────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────

def main():
    print("\n PHANTOM NETWORK — v0.4")
    print(" When two nodes meet — they exchange what they have lived.\n")

    args = sys.argv[1:]

    # Encryption is initialized for all commands that touch local seals.
    # --encounters does not require it (encounter log is not encrypted in v0.4).
    if not any(a in args for a in ("--help", "-h")):
        init_encryption()

    if "--listen" in args or "-l" in args:
        listen()

    elif "--connect" in args or "-c" in args:
        host = None
        for arg in args:
            if arg not in ("--connect", "-c") and not arg.startswith("-"):
                host = arg
                break
        connect(host)

    elif "--seal" in args or "-s" in args:
        seal_interactive()

    elif "--list" in args:
        list_seals()

    elif "--encounters" in args or "-e" in args:
        show_encounters()

    else:
        print(" Usage:")
        print("   --listen          share your seals, receive theirs")
        print("   --connect         meet a node, exchange what you've lived")
        print("   --connect <ip>    connect to specific IP")
        print("   --seal            seal a new thought")
        print("   --list            see your sealed thoughts")
        print("   --encounters      see your encounter history")
        print()
        print(" First time? Start here:")
        print("   python phantom_node.py --seal")
        print()

if __name__ == "__main__":
    main()
        
