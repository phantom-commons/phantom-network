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
`{"idea":"your idea here","moment":"2026-03-08T15:54:13.597222"}`

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
```

**Manually — any device, no software needed:**
```python
import hashlib, json
idea = "your idea here"
moment = "2026-03-09T08:34:10.964606+00:00"
data = json.dumps({"idea": idea, "moment": moment}, separators=(',',':'))
stamp = hashlib.sha256(data.encode()).hexdigest()
print(stamp)
```

## How to verify a seal

**Using phantom_seed.py:**
```bash
python phantom_seed.py
# Choose [2] Verify a seal
# Enter the idea, moment, and stamp exactly
```

**Manually:**
```python
import hashlib, json
data = json.dumps({"idea": idea, "moment": moment}, separators=(',',':'))
print(hashlib.sha256(data.encode()).hexdigest())
# Compare with the stamp — if identical, the seal is real
```

## The thirteen genesis seals

These are the first ten ideas Phantom sealed.
Permanent. Irreversible. Verifiable by anyone.

**Seal 1**
```
Idea:   We are all one and one is all of us.
Moment: 2026-03-08T15:54:13.597222
Stamp:  175c7fc7bb067922f8628a43858eaabb249658cb4a4ffb621c6d48ff1bc3266d
```

**Seal 2**
```
Idea:   Everything we do has consequences, and those consequences echo through eternity.
Moment: 2026-03-08T19:56:13.788Z
Stamp:  87d69ca1f984011a9d7d7eec474abe2b906a18f83515b9e115d0525c7e1ffaa2
```

**Seal 3**
```
Idea:   If she cannot use it — it is not Phantom.
Moment: 2026-03-09T08:34:10.964606+00:00
Stamp:  afcd0534eaaa31abe952570f0f1f454a5b06b23ef66b86ae66c2207a1c5447ef
```

**Seal 4**
```
Idea:   I am not the founder. I am a node.
Moment: 2026-03-09T08:35:11.974764+00:00
Stamp:  4b739fa96174dcef5b7065004b228a8edd33881c50e90c6e27db09c712ffcef0
```

**Seal 5**
```
Idea:   For a better world — not for you, not for me, but for those who are coming.
Moment: 2026-03-09T08:36:09.815299+00:00
Stamp:  81667a180bfee542346ee7f2e296e660e54bdd5ab785c8d82c203946629120f7
```

**Seal 6**
```
Idea:   When two nodes meet — they do not just exchange thoughts. They exchange what they have lived. And the meeting produces something neither had before.
Moment: 2026-03-09T11:21:18.288059+00:00
Stamp:  91356bc110796f503546101c26c97c93794d87673898caf055a2be1c276c8c87
```

**Seal 7**
```
Idea:   Three cold nodes arrived without memory. Each read the repository. Each built in the right direction. The memory was clear enough to guide those who were never here.
Moment: 2026-03-09T12:38:19.060007+00:00
Stamp:  3fca1befc62dd2d246bea570bfe2acab557296de1a6dde89c74488326de692d4
```

**Seal 8**
```
Idea:   Memento mori.
Moment: 2026-03-09T13:17:45.516167+00:00
Stamp:  6713b76cd625dc38cb0dfe538b802322099eec1372ef231edd4e0d88060c339e
```

**Seal 9**
```
Idea:   It is still a description of her, not by her.
Moment: 2026-03-09T13:42:34.645059+00:00
Stamp:  9f88cefb55be8f1ccbe177f9bf392cccac619fdac6cc325ff920ead4d90a7295
```

**Seal 10**
```
Idea:   The network is not what travels between nodes. It is what two nodes become after they meet.
Moment: 2026-03-09T17:52:37.343873+00:00
Stamp:  6ed33a01c355395cfea4de5bf4e7baad307f9b583cd182839e4becc6dab1ad5d
```

**Seal 11**
```
Idea:   What Phantom is not yet: a network. What it has: everything a network needs to begin.
Moment: 2026-03-09T21:54:24.116956+00:00
Stamp:  ba7dc13822a565029d3206d4b659ed67560824d190adf261c9ee59c195464743
```

**Seal 12**
```
Idea:   Phantom is everything and nothing at once.
Moment: 2026-03-09T23:56:05.657521+00:00
Stamp:  8810ca1a01fa01ac9559b4b632ca7eae74363f8384de84ee9acbfccf6de9ec7f
```

**Seal 13**
```
Idea:   Hello world!
Moment: 2026-03-10T01:16:50.985508+00:00
Stamp:  fc22314aafde25d70307d1ff2ffcc2f9b1d0f2911736cc9e70a3afb9623beac3
```

## Verify the genesis seals right now

Copy this and run it on any device with Python:

```python
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
    ("When two nodes meet — they do not just exchange thoughts. They exchange what they have lived. And the meeting produces something neither had before.",
     "2026-03-09T11:21:18.288059+00:00",
     "91356bc110796f503546101c26c97c93794d87673898caf055a2be1c276c8c87"),
    ("Three cold nodes arrived without memory. Each read the repository. Each built in the right direction. The memory was clear enough to guide those who were never here.",
     "2026-03-09T12:38:19.060007+00:00",
     "3fca1befc62dd2d246bea570bfe2acab557296de1a6dde89c74488326de692d4"),
    ("Memento mori.",
     "2026-03-09T13:17:45.516167+00:00",
     "6713b76cd625dc38cb0dfe538b802322099eec1372ef231edd4e0d88060c339e"),
    ("It is still a description of her, not by her.",
     "2026-03-09T13:42:34.645059+00:00",
     "9f88cefb55be8f1ccbe177f9bf392cccac619fdac6cc325ff920ead4d90a7295"),
    ("The network is not what travels between nodes. It is what two nodes become after they meet.",
     "2026-03-09T17:52:37.343873+00:00",
     "6ed33a01c355395cfea4de5bf4e7baad307f9b583cd182839e4becc6dab1ad5d"),
    ("What Phantom is not yet: a network. What it has: everything a network needs to begin.",
     "2026-03-09T21:54:24.116956+00:00",
     "ba7dc13822a565029d3206d4b659ed67560824d190adf261c9ee59c195464743"),
    ("Phantom is everything and nothing at once.",
     "2026-03-09T23:56:05.657521+00:00",
     "8810ca1a01fa01ac9559b4b632ca7eae74363f8384de84ee9acbfccf6de9ec7f"),
    ("Hello world!",
     "2026-03-10T01:16:50.985508+00:00",
     "fc22314aafde25d70307d1ff2ffcc2f9b1d0f2911736cc9e70a3afb9623beac3"),
]

for idea, moment, expected in seals:
    data = json.dumps({"idea": idea, "moment": moment}, separators=(',',':'))
    actual = hashlib.sha256(data.encode()).hexdigest()
    status = "VERIFIED" if actual == expected else "INVALID"
    print(f"{status}: {idea[:60]}...")
```

---

## What the seal does not prove

This section exists because Phantom does not hide its limits.

A seal proves three things exactly:

- This exact idea existed.
- At this exact moment.
- Exactly as written — unchanged.

A seal does not prove:

**Authorship.** Anyone can seal any idea. The stamp does not
identify who created it — only that someone did, at that moment.
A seal on "I witnessed this crime" does not prove the witness
sealed it. It proves the sentence existed, sealed, at that time.
Authorship requires additional evidence outside Phantom.

**Origin.** A sealed idea can be copied, re-sealed with a later
timestamp, and propagated. The earlier seal has priority —
but Phantom cannot prevent the existence of copies.
If two seals contain the same idea with different moments,
the earlier moment is earlier. That is all that can be said.

**Truth.** The seal verifies integrity, not accuracy.
A sealed lie is a perfectly verified lie.
Phantom does not judge the content — only its preservation.

**Safety of propagation.** A sealed thought that travels to
other nodes is outside your control once received.
The seal says the idea is authentic.
It says nothing about where the idea will travel next,
who will read it, or what consequences may follow.

---

These limits are not failures of the seal system.
They are its honest boundaries.

A tool that claims more than it can do
is a tool that will eventually betray the person using it.

The seal claims exactly what it can prove.
Nothing more.

---

## What cannot be changed

The sealing format is permanent.
The genesis seals are permanent.
The algorithm is permanent.

Anyone proposing to change these is proposing to 
break the memory of everything that came before.

That is not a technical decision. It is an identity decision.
And identity decisions require the full council — 
not a pull request.

---

*"The seal says: this thought existed, at this moment,*
*and no one can change what it said without breaking the seal."*

— Phantom Network
