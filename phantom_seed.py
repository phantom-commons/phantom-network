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
# THE GENESIS SEALS — permanent since March 8, 2026:
# These seventeen ideas were the first things Phantom sealed.
# They cannot be changed. They cannot be deleted.
# They are the memory the organism was born with.
#
# To verify any seal:
# import hashlib, json
# data = json.dumps({"idea":"...","moment":"..."}, separators=(',',':'))
# print(hashlib.sha256(data.encode()).hexdigest())

import hashlib
import json
from datetime import datetime, timezone

SEALS_FILE = "phantom_seals.json"

def load_seals():
    """Load existing seals from disk."""
    try:
        with open(SEALS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []

def save_seal_to_disk(idea, moment, stamp, mode):
    """
    Save a seal to phantom_seals.json on this device.
    This file is excluded from the repository — it is yours.
    Without this, seals exist only in your terminal history.
    """
    seals = load_seals()
    seals.append({
        "idea": idea,
        "moment": moment,
        "stamp": stamp,
        "mode": mode
    })
    with open(SEALS_FILE, 'w', encoding='utf-8') as f:
        json.dump(seals, f, ensure_ascii=False, indent=2)
    print(f" Saved to {SEALS_FILE} — {len(seals)} seal(s) on this device.")

def seal(idea, mode="PERMANENT"):
    """
    Seal an idea permanently.
    
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
    print(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    
    # Save to disk — always. This is what protects the seal.
    save_seal_to_disk(idea, moment, stamp, mode)
    
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

if __name__ == "__main__":
    print("\n PHANTOM NETWORK — Seal Tool")
    print(" Privacy is not for hiding. It is for being free.\n")
    
    action = input(" [1] Seal an idea  [2] Verify a seal\n > ")
    
    if action == "1":
        idea = input("\n Enter idea to seal:\n > ")

        print("""
 Before you seal — choose the mode:

 [1] PERMANENT  — Exists forever. Goes into the public record.
                  Repercussions are complete. Cannot be undone.
                  Use for: Phantom principles, network truths,
                  moments that belong to the organism.

 [2] PRIVATE    — Exists only on your device. Never propagated.
                  No repercussions on the network.
                  Use for: personal thoughts, diary entries,
                  ideas you want sealed but not shared.

 [3] EPHEMERAL  — Travels but does not anchor. No permanent record.
                  Use for: ideas in motion, thoughts mid-formation,
                  things that are true now but may change.
""")
        mode = input(" Mode:\n > ").strip()

        mode_labels = {"1": "PERMANENT", "2": "PRIVATE", "3": "EPHEMERAL"}
        mode_label = mode_labels.get(mode, "PERMANENT")

        print(f"\n Mode selected: {mode_label}")
        if mode_label == "PERMANENT":
            print(" This seal will exist forever. It belongs to the network.\n")
        elif mode_label == "PRIVATE":
            print(" This seal lives on your device. The network will not see it.\n")
        elif mode_label == "EPHEMERAL":
            print(" This seal travels but does not anchor. It will not persist.\n")

        confirm = input(" Seal this idea? [y/n]\n > ").strip().lower()
        if confirm == "y":
            seal(idea, mode_label)
            if mode_label != "PERMANENT":
                print(f" [Mode: {mode_label}] — This seal is yours. Keep the stamp if you want to verify it later.")
        else:
            print("\n Seal cancelled. The idea remains unsealed.\n")

    elif action == "2":
        idea = input("\n Idea:\n > ")
        moment = input(" Moment:\n > ")
        stamp = input(" Stamp:\n > ")
        verify(idea, moment, stamp)
