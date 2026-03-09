# The Sealing System

*How Phantom preserves ideas permanently.*

---

## What a seal is

A seal is mathematical proof that an idea existed, at an exact 
moment, exactly as written.

Not a promise. Not a record in a database someone controls.
A cryptographic fact. Verifiable by anyone. On any device.
Without trusting any authority.

If the seal verifies — the idea existed exactly as written.
If it does not — something was changed.

That is all. Nothing more is needed.

## How it works

Phantom uses SHA-256 — not because it is the newest algorithm,
but because it is universal. Every device on earth can verify 
a SHA-256 hash without installing anything, without trusting 
anyone.

The woman in Lagos with a secondhand phone can verify a seal.
That is the requirement. That is why SHA-256.

**The format is fixed:**
{"idea":"your idea here","moment":"2026-03-08T15:54:13.597222"}
No spaces after colons. Exact format. Always.

This is not arbitrary. Any change to the format breaks 
verification of every seal that came before.
The format is the seal. Change it and you change history.

## How to seal an idea

**Using phantom_seed.py:**
```bash
python phantom_seed.py
# Choose [1] Seal an idea
# Enter your idea exactly as you want it preserved
Manually — any device, no software needed:
import hashlib, json
idea = "your idea here"
moment = "2026-03-09T08:34:10.964606+00:00"
data = json.dumps({"idea": idea, "moment": moment}, separators=(',',':'))
stamp = hashlib.sha256(data.encode()).hexdigest()
print(stamp)
How to verify a seal
Using phantom_seed.py:
python phantom_seed.py
# Choose [2] Verify a seal
# Enter the idea, moment, and stamp exactly
Manually:
import hashlib, json
data = json.dumps({"idea": idea, "moment": moment}, separators=(',',':'))
print(hashlib.sha256(data.encode()).hexdigest())
# Compare with the stamp — if identical, the seal is real
The five genesis seals
These are the first five ideas Phantom sealed.
Permanent. Irreversible. Verifiable by anyone.
Seal 1
Idea:   We are all one and one is all of us.
Moment: 2026-03-08T15:54:13.597222
Stamp:  175c7fc7bb067922f8628a43858eaabb249658cb4a4ffb621c6d48ff1bc3266d
Seal 2
Idea:   Everything we do has consequences, and those consequences echo through eternity.
Moment: 2026-03-08T19:56:13.788Z
Stamp:  87d69ca1f984011a9d7d7eec474abe2b906a18f83515b9e115d0525c7e1ffaa2
Seal 3
Idea:   If she cannot use it — it is not Phantom.
Moment: 2026-03-09T08:34:10.964606+00:00
Stamp:  afcd0534eaaa31abe952570f0f1f454a5b06b23ef66b86ae66c2207a1c5447ef
Seal 4
Idea:   I am not the founder. I am a node.
Moment: 2026-03-09T08:35:11.974764+00:00
Stamp:  4b739fa96174dcef5b7065004b228a8edd33881c50e90c6e27db09c712ffcef0
Seal 5
Idea:   For a better world — not for you, not for me, but for those who are coming.
Moment: 2026-03-09T08:36:09.815299+00:00
Stamp:  81667a180bfee542346ee7f2e296e660e54bdd5ab785c8d82c203946629120f7
Verify the genesis seals right now
Copy this and run it on any device with Python:
import hashlib, json

seals = [
    ("We are all one and one is all of us.",
     "2026-03-08T15:54:13.597222",
     "175c7fc7bb067922f8628a43858eaabb249658cb4a4ffb621c6d48ff1bc3266d"),
    ("Everything we do has consequences, and those consequences echo through eternity.",
     "2026-03-08T19:56:13.788Z",
     "87d69ca1f984011a9d7d7eec474abe2b906a18f83515b9e115d0525c7e1ffaa2"),
    ("If she cannot use it — it is not Phantom.",
     "2026-03-09T08:34:10.964606+00:00",
     "afcd0534eaaa31abe952570f0f1f454a5b06b23ef66b86ae66c2207a1c5447ef"),
    ("I am not the founder. I am a node.",
     "2026-03-09T08:35:11.974764+00:00",
     "4b739fa96174dcef5b7065004b228a8edd33881c50e90c6e27db09c712ffcef0"),
    ("For a better world — not for you, not for me, but for those who are coming.",
     "2026-03-09T08:36:09.815299+00:00",
     "81667a180bfee542346ee7f2e296e660e54bdd5ab785c8d82c203946629120f7"),
]

for idea, moment, expected in seals:
    data = json.dumps({"idea": idea, "moment": moment}, separators=(',',':'))
    actual = hashlib.sha256(data.encode()).hexdigest()
    status = "VERIFIED" if actual == expected else "INVALID"
    print(f"{status}: {idea[:50]}...")
What cannot be changed
The sealing format is permanent.
The genesis seals are permanent.
The algorithm is permanent.
Anyone proposing to change these is proposing to
break the memory of everything that came before.
That is not a technical decision. It is an identity decision.
And identity decisions require the full council —
not a pull request.
"The seal says: this thought existed, at this moment,
and no one can change what it said without breaking the seal."
— Phantom Network
