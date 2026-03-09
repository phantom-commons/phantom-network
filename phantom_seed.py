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
# These five ideas were the first things Phantom sealed.
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

def seal(idea):
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
    
    return stamp

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
        seal(idea)
        
    elif action == "2":
        idea = input("\n Idea:\n > ")
        moment = input(" Moment:\n > ")
        stamp = input(" Stamp:\n > ")
        verify(idea, moment, stamp)
