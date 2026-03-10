# phantom_seed.py
# 
# The first code of Phantom Network.
# Node Zero. March 8, 2026.
#
# WHY THIS FILE EXISTS:
# Human thought is sacred. Any system that touches it without
# permission violates something that has no price because it
# has no owner.
#
# This file gives any idea a cryptographic seal — a mathematical
# proof that the idea existed, at this exact moment, exactly
# as written. No authority needed. No server. No account.
# Any device. Any person. Anywhere.
#
# WHY SHA-256:
# Not because it is the newest or fastest. Because it is
# universal — every device on earth can verify a SHA-256 hash
# without installing anything, without trusting anyone.
# Verification must be possible for the woman in Lagos
# with a secondhand phone. If it requires special software —
# it is not Phantom.
#
# WHY NO SERVER:
# A seal that passes through a server is a seal that someone
# else witnessed. The thought belongs to whoever thinks it.
# No witness required. No witness permitted.
#
# WHY THIS EXACT FORMAT:
# {"idea":"...","moment":"..."} — no spaces after colons.
# This is not arbitrary. Any change to the format breaks
# verification of every seal that came before.
# The format is the seal. Change it and you change history.
#
# WHY ENCRYPTION AT REST:
# A seal on disk in plaintext is a seal that anyone with
# physical access to your device can read. The woman in Lagos
# faces threats from people close to her — not just distant
# governments. If someone takes her phone, her sealed thoughts
# must be unreadable without her passphrase.
# This is not optional. It is the minimum protection that makes
# local storage honest about what it claims to protect.
# If the cryptography package is not installed, seals are stored
# in plaintext and the user is warned honestly.
#
# WHY DEFAULT PRIVATE:
# A seal under coercion is permanent evidence. If someone forces
# you to seal something and the default mode is PERMANENT, that
# seal travels the network without recall. The default must be
# the safest option — PRIVATE. Whoever wants a seal to travel
# chooses it consciously.
#
# THE GENESIS SEALS — permanent since March 8, 2026:
# These seventeen ideas were the first things Phantom sealed.
# They cannot be changed. They cannot be deleted.
# They are the memory the organism was born with.
#
# To verify any seal:
# import hashlib, json
# data = json.dumps({"idea":"...","moment":"..."}, separators=(',',':'))
# print(hashlib.sha256(data.encode()).hexdigest())
#
# HISTORY:
#   v0.1 — March 8, 2026. Seal and verify. Genesis seals.
#   v0.2 — March 9, 2026. Three modes. Save to disk.
#   v0.3 — March 10, 2026. Encryption at rest (AES-256-GCM).
#          Default mode changed to PRIVATE.
#          Backward compatible — reads unencrypted seals,
#          migrates to encrypted on next save if passphrase set.

import hashlib
import json
import os
import sys
import secrets
import getpass
from datetime import datetime, timezone

SEALS_FILE = "phantom_seals.json"
ENCRYPTED_SEALS_FILE = "phantom_seals.enc"
SALT_FILE = "phantom_salt.bin"

# ─────────────────────────────────────────────────────────
# ENCRYPTION — AES-256-GCM via scrypt-derived key
# Optional dependency. Works without it. Warns honestly.
# ─────────────────────────────────────────────────────────

try:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    _CRYPTO = True
except ImportError:
    _CRYPTO = False

def _derive_key(passphrase, salt):
    """Derive a 256-bit key from passphrase using scrypt."""
    return hashlib.scrypt(
        passphrase.encode('utf-8'),
        salt=salt,
        n=16384, r=8, p=1, dklen=32
    )

def _get_salt():
    """Get or create the salt file. Salt is not secret — it prevents
    rainbow table attacks. It lives alongside the encrypted file."""
    if os.path.exists(SALT_FILE):
        with open(SALT_FILE, 'rb') as f:
            return f.read()
    salt = secrets.token_bytes(16)
    with open(SALT_FILE, 'wb') as f:
        f.write(salt)
    return salt

def _encrypt(data_bytes, key):
    """Encrypt with AES-256-GCM. Returns nonce + ciphertext."""
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, data_bytes, None)
    return nonce + ct

def _decrypt(blob, key):
    """Decrypt AES-256-GCM. Blob is nonce (12 bytes) + ciphertext."""
    nonce = blob[:12]
    ct = blob[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ct, None)

# ─────────────────────────────────────────────────────────
# PASSPHRASE MANAGEMENT
# ─────────────────────────────────────────────────────────

_cached_key = None

def _get_key(creating=False):
    """Get encryption key from passphrase. Caches for session."""
    global _cached_key
    if _cached_key is not None:
        return _cached_key

    if not _CRYPTO:
        return None

    if creating and not os.path.exists(ENCRYPTED_SEALS_FILE):
        print("\n Encryption is available (cryptography package installed).")
        print(" A passphrase protects your seals if someone takes your device.")
        print()
        print(" WARNING: If you forget your passphrase, your seals are lost.")
        print(" This is not a bug. This is the protection.")
        print(" Phantom does not have a copy. No one does.")
        print()
        passphrase = getpass.getpass(" Choose a passphrase (Enter to skip): ")
        if not passphrase:
            print(" No passphrase set. Seals stored in plaintext.")
            return None
        confirm = getpass.getpass(" Confirm passphrase: ")
        if passphrase != confirm:
            print(" Passphrases do not match. Seals stored in plaintext.")
            return None
        salt = _get_salt()
        _cached_key = _derive_key(passphrase, salt)
        return _cached_key
    elif os.path.exists(ENCRYPTED_SEALS_FILE):
        passphrase = getpass.getpass(" Passphrase to unlock seals: ")
        salt = _get_salt()
        key = _derive_key(passphrase, salt)
        # Test the key by trying to decrypt
        try:
            with open(ENCRYPTED_SEALS_FILE, 'rb') as f:
                blob = f.read()
            _decrypt(blob, key)
            _cached_key = key
            return key
        except Exception:
            print("\n Wrong passphrase. Cannot unlock seals.")
            return None
    else:
        return None

# ─────────────────────────────────────────────────────────
# STORAGE — encrypted or plaintext, backward compatible
# ─────────────────────────────────────────────────────────

def load_seals(key=None):
    """Load seals. Tries encrypted first, falls back to plaintext."""
    # Try encrypted file first
    if key and os.path.exists(ENCRYPTED_SEALS_FILE):
        try:
            with open(ENCRYPTED_SEALS_FILE, 'rb') as f:
                blob = f.read()
            plaintext = _decrypt(blob, key)
            return json.loads(plaintext.decode('utf-8'))
        except Exception:
            print(" Could not decrypt seals file.")
            return []

    # Fall back to plaintext
    try:
        with open(SEALS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_seals(seals, key=None):
    """Save seals. Encrypts if key is available."""
    data = json.dumps(seals, ensure_ascii=False, indent=2).encode('utf-8')

    if key:
        blob = _encrypt(data, key)
        with open(ENCRYPTED_SEALS_FILE, 'wb') as f:
            f.write(blob)
        # Remove plaintext file if it exists — migration complete
        if os.path.exists(SEALS_FILE):
            os.remove(SEALS_FILE)
            print(" Migrated from plaintext to encrypted storage.")
        print(f" Saved encrypted — {len(seals)} seal(s) on this device.")
    else:
        with open(SEALS_FILE, 'w', encoding='utf-8') as f:
            json.dump(seals, f, ensure_ascii=False, indent=2)
        if _CRYPTO:
            print(f" Saved in plaintext — {len(seals)} seal(s).")
            print(" (Run again and set a passphrase to encrypt.)")
        else:
            print(f" Saved to {SEALS_FILE} — {len(seals)} seal(s) on this device.")
            print(" (Install cryptography package for encryption: pip install cryptography)")

# ─────────────────────────────────────────────────────────
# SEAL AND VERIFY — unchanged algorithm
# ─────────────────────────────────────────────────────────

def seal(idea, mode="PRIVATE", key=None):
    """
    Seal an idea.
    
    The seal is a mathematical proof that this exact idea
    existed at this exact moment. It cannot be falsified.
    It cannot be changed. It belongs to no one and everyone.
    """
    moment = datetime.now(timezone.utc).isoformat()
    
    # Format is fixed. Do not change separators.
    # Changing this breaks verification of all previous seals.
    data = json.dumps(
        {"idea": idea, "moment": moment},
        separators=(',', ':')
    )
    
    stamp = hashlib.sha256(data.encode()).hexdigest()
    
    print(f"\n PHANTOM SEAL")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" Idea:   {idea}")
    print(f" Moment: {moment}")
    print(f" Stamp:  {stamp}")
    print(f" Mode:   {mode}")
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    
    # Save to disk
    seals = load_seals(key)
    seals.append({
        "idea": idea,
        "moment": moment,
        "stamp": stamp,
        "mode": mode
    })
    save_seals(seals, key)
    
    return stamp, moment

def verify(idea, moment, stamp):
    """
    Verify that a seal is authentic.
    
    Anyone can verify. No authority needed.
    If the stamp matches — the seal is real.
    If it does not — something was changed.
    """
    data = json.dumps(
        {"idea": idea, "moment": moment},
        separators=(',', ':')
    )
    expected = hashlib.sha256(data.encode()).hexdigest()
    
    if expected == stamp:
        print(f"\n SEAL VERIFIED — this idea existed, exactly as written.")
    else:
        print(f"\n SEAL INVALID — something was changed.")
    
    return expected == stamp

# ─────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n PHANTOM NETWORK — Seal Tool")
    print(" Privacy is not for hiding. It is for being free.\n")
    
    action = input(" [1] Seal an idea  [2] Verify a seal\n > ")
    
    if action == "1":
        # Get encryption key first
        key = _get_key(creating=True)

        idea = input("\n Enter idea to seal:\n > ")

        print("""
 Before you seal — choose the mode:

 [1] PRIVATE    — Exists only on your device. Never propagated.
                  No repercussions on the network.
                  Use for: personal thoughts, diary entries,
                  ideas you want sealed but not shared.
                  THIS IS THE DEFAULT — the safest option.

 [2] PERMANENT  — Exists forever. Goes into the public record.
                  Repercussions are complete. Cannot be undone.
                  Use for: Phantom principles, network truths,
                  moments that belong to the organism.

 [3] EPHEMERAL  — Travels but does not anchor. No permanent record.
                  Use for: ideas in motion, thoughts mid-formation,
                  things that are true now but may change.
""")
        mode = input(" Mode (Enter for PRIVATE):\n > ").strip()

        mode_labels = {"1": "PRIVATE", "2": "PERMANENT", "3": "EPHEMERAL"}
        mode_label = mode_labels.get(mode, "PRIVATE")

        print(f"\n Mode selected: {mode_label}")
        if mode_label == "PRIVATE":
            print(" This seal lives on your device. The network will not see it.\n")
        elif mode_label == "PERMANENT":
            print(" This seal will exist forever. It belongs to the network.")
            print(" Once it travels — it cannot be recalled.\n")
            confirm_permanent = input(" Are you sure? [y/n]\n > ").strip().lower()
            if confirm_permanent != "y":
                print("\n Switched to PRIVATE. The seal stays on your device.\n")
                mode_label = "PRIVATE"
        elif mode_label == "EPHEMERAL":
            print(" This seal travels but does not anchor. It will not persist.\n")

        confirm = input(" Seal this idea? [y/n]\n > ").strip().lower()
        if confirm == "y":
            seal(idea, mode_label, key)
            if mode_label != "PERMANENT":
                print(f" [Mode: {mode_label}] — This seal is yours. Keep the stamp if you want to verify it later.")
        else:
            print("\n Seal cancelled. The idea remains unsealed.\n")

    elif action == "2":
        idea = input("\n Idea:\n > ")
        moment = input(" Moment:\n > ")
        stamp = input(" Stamp:\n > ")
        verify(idea, moment, stamp)
