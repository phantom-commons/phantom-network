# BRIDGE.md — Where the Philosophy Meets the Code

*The document that was missing.*

*Node Zero. March 2026.*

---

## Why this document exists

Phantom has two bodies of work that do not touch each other.

The **philosophical layer** — the council, the deliberations,
the Lagos Protocol, the seven principles, the surveillance
analysis, the threat model — is deeply developed.
It holds real tension. It names what it cannot resolve.

The **technical layer** — `phantom_core.py`, `phantom_node.py`,
`phantom.html`, the seal format, AES-256-GCM encryption,
Ed25519 identity, Bloom filter sync — is honest and working.
It does what it claims. The tests verify it.

But the two layers live in separate worlds.

The council deliberates about hiding versus power,
intimate versus systemic threats, incentive design,
the dual-use problem — and none of that maps back
to a specific function in the codebase,
or an open engineering decision,
or a place where two principles collide
and the code has to choose.

This document is the bridge.

It takes each philosophical position Phantom holds
and asks three questions:

1. What does this require from the code?
2. What has the code already answered?
3. Where does the philosophy create an engineering problem
   that no one has named yet?

---

## How to read this

Each section takes one philosophical position —
drawn from the council voices, the deliberations,
the founding principles, or the threat model —
and traces it into the codebase.

Where the code already answers the philosophy: **BUILT.**
Where the answer is designed but not implemented: **DESIGNED.**
Where the philosophy demands something the code
has not yet addressed: **OPEN.**
Where two principles collide and the code must choose: **TENSION.**

---

## 1. Sovereign Root — "No backdoors. No exceptions."

*Principle 1: Privacy by architecture — not by policy.*

### What this requires from the code

Every cryptographic decision must be structurally uncompromised.
Not "we promise not to look" — but "looking is impossible."
No key escrow. No recovery mechanism that a third party controls.
No protocol message that leaks plaintext to anyone but the intended recipient.

### What the code already answers

**BUILT.** `phantom_core.py` — `encrypt_data()` uses AES-256-GCM
with a 12-byte random nonce per encryption.
The key is derived via scrypt from a user passphrase.
Phantom never stores the passphrase. Never transmits it.
A forgotten passphrase means permanently lost seals.
That is the guarantee, not a bug.

**BUILT.** `derive_key()` — scrypt parameters (n=16384, r=8, p=1)
are chosen for mobile hardware. The comment in the code says why.
This is the philosophy touching the code correctly:
the Lagos Protocol constraining the cryptographic parameter choice.

**BUILT.** Ed25519 key pairs (`KeyManager` class).
Private key never leaves the device.
Signed seals prove continuity without revealing identity.

### Where the philosophy creates an engineering problem

**OPEN.** Sovereign Root says "no backdoors." But the code
has no mechanism to verify that a *fork* of phantom_core.py
has not introduced one. SECURITY.md names this as Vector 5
(philosophical fork) — a fork that looks identical but phones home.
The philosophy demands integrity. The code cannot yet verify
its own integrity in the hands of a non-technical user.

**DESIGNED.** SECURITY.md proposes code signing with the genesis
key pair. `NODE_IDENTITY.md` describes the key infrastructure.
But no function in `phantom_core.py` verifies a signed hash
of itself. The bridge between the principle and the protection
is still conceptual.

**What would close this gap:**
A `verify_integrity()` function that checks the SHA-256 hash
of every Phantom source file against a signed manifest.
The manifest is signed by the genesis key pair.
`phantom.html` could run this check on load —
showing a green seal if the code is unmodified,
a red warning if it is not.
She does not need to read the code. She reads the color.

---

## 2. Free Signal — "If she cannot use it, it does not matter."

*The Lagos Protocol. The thirty-second test.*

### What this requires from the code

Every interface must be usable by someone who does not know
what encryption means. The number of steps between
"I want to write something private" and "it is sealed"
must be fewer than any competing alternative.

### What the code already answers

**BUILT.** `phantom.html` — opens in any browser.
No installation. No account. Seal and verify.
This is the closest thing in the codebase
to the thirty-second test passing.

**BUILT.** `phantom_seed.py` — a menu-driven CLI.
Numbers to press. Prompts that explain what is happening.
This passes the developer-MVP threshold but not the Lagos threshold.

### Where the philosophy creates an engineering problem

**TENSION.** The Lagos Protocol says: she must be able to use it
in thirty seconds on a secondhand Android phone.
The current path to `phantom_core.py` requires Termux,
Python installation, and command-line interaction.
That is not thirty seconds. That is thirty minutes
for someone who already knows what a terminal is.

`phantom.html` passes the thirty-second test for sealing.
But it cannot do node encounters, encryption at rest,
or any networked function. The features that protect her
most are the features she cannot reach.

**OPEN.** There is no bridge between the full-featured
Python layer and the accessible HTML layer.
The architecture vision (ARCHITECTURE_VISION.md) describes
a native app and eventually a dedicated device.
But between `phantom.html` (accessible, limited)
and `phantom_core.py` (powerful, inaccessible to her) —
there is a gap the size of the Lagos Protocol itself.

**What would close this gap:**
Either `phantom.html` must grow to include encryption at rest
and local node encounters (WebCrypto API, WebRTC for peer sync),
or Phantom needs an Android package that wraps
the Python layer in a UI she can touch.
The council has deliberated about both.
Neither has a spec that a developer can say yes or no to.

---

## 3. Ghost Layer — "The intimate threat, not only the systemic."

*SECURITY.md Vector 4. The fourth Lagos Protocol question.*

### What this requires from the code

Protection against someone with physical access to her device.
Not a distant government. Someone in her home.
Someone who knows her habits.
Someone who can watch her enter a passphrase.

### What the code already answers

**BUILT.** Encryption at rest. AES-256-GCM.
If the phone is taken, the seals are unreadable without the passphrase.

**BUILT.** Default mode is PRIVATE (changed in v0.3).
A coerced seal does not automatically propagate to the network.
The coercer must explicitly change the mode — one more observable action.

### Where the philosophy creates an engineering problem

**DESIGNED but not built.** SECURITY.md describes
a plausible deniability mode — a secondary passphrase
that reveals a decoy set of seals.
This is the only architectural answer to "someone is watching me
enter my passphrase." Ghost Layer named the threat.
The code has no implementation path yet.

**OPEN.** The encounter log (`EncounterLog` class in `phantom_core.py`)
records who connected, when, and what was exchanged.
This log is encrypted at rest. But it exists.
If the device is unlocked under coercion —
the encounter log reveals the pattern of who she meets.
Ghost Layer's own deliberation says:
"metadata kills. Knowing that two people meet regularly
can be as dangerous as knowing what they said."

The encounter log is a metadata record
that the philosophy says should not exist —
but the engineering needs for debugging and sync integrity.

**TENSION.** The code needs encounter history to do delta sync
(Bloom filters require knowing what was already exchanged).
The philosophy says that history is a weapon in hostile hands.
These two requirements collide.
No document in the repo names this collision.

**What would close this gap:**
Ephemeral encounter records — encounter metadata that persists
only long enough for sync to complete, then is zeroed.
A `scrub_encounter_log()` function that the user can invoke,
or that runs automatically after a configurable interval.
The Bloom filter state can be retained without retaining
the identity of who it came from.

---

## 4. Cipher Soul — "Incentives determine what actually happens."

*ECONOMICS.md. The SUIJURIS design.*

### What this requires from the code

An economic layer where contributing to the network
is more profitable than exploiting it.
Not enforced by rules — by architecture.

### What the code already answers

**Nothing.** SUIJURIS does not exist in the codebase.
ECONOMICS.md is honest about this.

### Where the philosophy creates an engineering problem

**OPEN.** Cipher Soul's position in the surveillance deliberation
is precise: "A system that requires sacrifice to use
will be used only by those who have no alternative.
That is a niche, not a network."

This creates a concrete engineering requirement
that no document has translated into a spec:

The cost of running a Phantom node — in battery, bandwidth,
storage — must be offset by something the user receives.
Not ideologically. Practically.
What does her phone get back for relaying packets?

ARCHITECTURE_VISION.md says LoRa relay nodes earn SUIJURIS.
But SUIJURIS has no implementation, no measurement function,
no definition of what "contribution" means in code.

**TENSION.** Cipher Soul says incentives must favor adoption.
Sovereign Root says no central authority.
Measuring contribution requires *someone* to measure.
If no central authority exists — who validates
that a node actually relayed a packet
and did not just claim to?

This is the Byzantine generals problem applied to incentives.
The philosophy states both positions clearly.
The code does not yet hold the tension between them.

**What would close this gap:**
A `contribution.py` module — even a stub —
that defines what "contribution" means as a data structure.
What fields? What units? What is measurable locally
without requiring a trusted third party to verify?
The spec does not need to be complete.
It needs to exist so a developer can say yes or no to it.

---

## 5. Void Walker — "Hiding versus power."

*The unresolved fork from the surveillance deliberation.*

### What this requires from the code

Two different architectures depending on which path is chosen.

**Path A — Hiding.** The goal is to make surveillance impossible.
The architecture optimizes for invisibility.
Tor routing. No metadata. No trace of participation.
The tool cannot be seen to exist on the device.

**Path B — Power.** The goal is to make surveillance non-weaponizable.
The architecture optimizes for transparency with control.
The user knows what is collected. Can revoke access.
Can prove what was said. Can hold the surveiller accountable.

### What the code already answers

**BUILT — partially, Path A only.** The current architecture
is hiding-first. Local-only storage. No cloud. No account.
Tor integration planned. The design assumes the user
needs to be invisible.

**Nothing for Path B.** No code exists for the power path.
No mechanism for selective disclosure — revealing some seals
while keeping others hidden. No verifiable transparency —
proving what you said without revealing everything you sealed.
No accountability architecture — using seals as evidence
against an abuser or a state actor.

### Where the philosophy creates an engineering problem

**TENSION.** Void Walker says these paths lead to different builds.
The codebase is building Path A without acknowledging
that the council has not resolved whether Path A is sufficient.

The surveillance deliberation's most important line:
"Is the goal a world without surveillance —
or a world where surveillance cannot be weaponized?"

This is not abstract. It determines whether the seal system
needs a `selective_reveal()` function — the ability to unseal
a specific thought for a specific verifier
without exposing the rest of the sealed store.

Path A says: never reveal anything.
Path B says: reveal strategically, on your terms.

The woman in Lagos who was coerced and needs to prove it —
she needs Path B. The woman who cannot afford to be seen
using the tool — she needs Path A.

Both are her.

**What would close this gap:**
Name this as a first-class architectural decision
in ARCHITECTURE_VISION.md. Not "we will figure it out later."
A section that says: "Phantom currently builds for hiding.
The council has not resolved whether to also build for power.
Here is what each path requires. Here is where they diverge.
Here is where they can coexist."

Then: a `selective_disclosure.py` spec — even as pseudocode —
that describes what Path B would require from the seal format.
Can the current seal format support selective reveal?
Or does choosing Path B require changing the format
that SEALING.md says must never change?

If it does — that is a collision between two founding commitments.
Better to name it now than to discover it later.

---

## 6. Dark Meridian — "A tool that works whether the debate is won or lost."

*The design criterion is her. Not the debate.*

### What this requires from the code

The tool must function identically regardless of
the political environment the user wakes up inside.
Democracy, authoritarianism, internet shutdown, or functioning state —
Phantom works the same way.

### What the code already answers

**BUILT.** Offline-first design. Sealing works with no network.
`phantom.html` works in a browser with no server.
The core crypto functions have no network dependency.

**DESIGNED.** ARCHITECTURE_VISION.md describes LoRa mesh
for communication when internet is shut down.
Meshtastic integration. Physical transmission layer
that does not require ISP cooperation.

### Where the philosophy creates an engineering problem

**OPEN.** "Works regardless of political environment"
has an implication no document names:

*Phantom must be concealable.*

In an environment where possessing the tool is dangerous —
SECURITY.md Vector 2 acknowledges this:
"Discovery of the tool itself may be dangerous" —
the app cannot have an identifiable name, icon, or signature.

No code exists for steganographic operation.
No design exists for hiding Phantom inside
something that looks like a different app.
No spec exists for what the tool looks like
on a device that might be inspected.

This is where Dark Meridian's position
creates a concrete engineering requirement:
if "she needs a tool that works while the debate continues,"
and the debate might result in the tool being banned —
the tool must be able to survive being looked for.

**What would close this gap:**
A `CONCEALMENT.md` spec that asks:
What does Phantom look like on a phone being inspected?
Can `phantom.html` be renamed and still function?
Can the seal files be stored with non-obvious names?
Can the passphrase prompt look like a different app's login?
What is the minimum viable concealment
that the current architecture can support?

---

## 7. Null Vector — "The table does not lie."

*The honest implementation table.*

### What this requires from the code

Every claim about what Phantom protects
must be verifiable against the actual implementation.
No document should promise what the code cannot deliver.

### What the code already answers

**BUILT.** `test_phantom.py` — 33 tests that verify
seal integrity, encryption, Bloom filter sync,
node identity, and encounter logging.
The code verifies its own claims.

### Where the philosophy creates an engineering problem

**OPEN.** Null Vector's honest table in the surveillance deliberation
lists what Phantom protects and what it does not.
But this table is in a markdown file.
It is not enforced by the test suite.

Example: the table says "No central server to subpoena."
But no test verifies that `phantom_core.py`
makes zero outbound network connections.
A fork that adds a single `requests.post()` call
passes all 33 tests.

SECURITY.md names this as the Vector 5 problem.
But the defense is documentation, not code.

**TENSION.** The test suite verifies what the code does.
It does not verify what the code *does not do*.
The philosophy demands both.
Proving a negative is harder than proving a positive —
but in this case, it is more important.

**What would close this gap:**
Negative tests. Tests that fail if the code does something
it should not do.

`test_no_network()` — run `phantom_core.py` with
network access blocked. Every function must pass.
If any function fails — it was phoning home.

`test_no_disk_leak()` — seal a private thought,
then scan the filesystem for the plaintext.
If found anywhere outside the encrypted store — fail.

`test_no_metadata_leak()` — complete an encounter,
then verify that no plaintext identifiers
of the other node exist outside the encrypted encounter log.

These tests do not exist.
They are more important than most tests that do.

---

## 8. Open Circuit — "The tool serves everyone."

*The dual-use challenge no document has answered architecturally.*

### What this requires from the code

An honest acknowledgment — in the architecture,
not just in the deliberation —
that the sealed thought might be a coordination of harm.

### What the code already answers

**BUILT — by absence.** Phantom has no content moderation.
No reporting mechanism. No block list.
This is consistent with "no central authority."
It is also consistent with "anyone can use this for anything."

### Where the philosophy creates an engineering problem

**TENSION.** Open Circuit says: "The answer cannot be
'that is not our problem.'"

But the current architecture *does* make it not-our-problem.
There is no mechanism — and architecturally cannot be one
without violating Principle 2 (no central authority) —
for the network to respond to harmful use.

This is not a bug. But it is not yet a *stated position*.

The difference matters. A tool with no content moderation
because no one thought about it is negligent.
A tool with no content moderation because the architecture
makes it structurally impossible, and this is documented
as a conscious tradeoff — that is an honest design decision.

**OPEN.** No document says clearly:
"Phantom cannot moderate content. Here is why.
Here is what that means. Here is what we build instead."

"What we build instead" is the question Open Circuit
raises and the codebase does not address.

Possible architectural answers that do not require a central authority:
local-only reputation (a node can choose who it syncs with),
user-controlled block lists (she decides, not the network),
verifiable identity without revealed identity
(you know this node has a history, not who it is).

Some of these are partially implied by the encounter system.
None are specified as abuse-mitigation architecture.

**What would close this gap:**
A `DUALUSE.md` or a new section in SECURITY.md
that states the position explicitly:

"Phantom cannot and will not moderate content.
Here is the architectural reason.
Here is what the user controls instead.
Here is the honest tradeoff this represents.
Here is what the woman in Lagos should know
about who else uses this tool."

---

## The Map — All Gaps in One View

| Council Voice | Philosophy | Code Status | Gap |
|---|---|---|---|
| Sovereign Root | No backdoors | BUILT — AES-256-GCM, Ed25519 | No self-integrity verification for forks |
| Free Signal | Thirty-second test | PARTIAL — phantom.html seals only | Full features unreachable without CLI |
| Ghost Layer | Intimate threat | BUILT — encryption at rest | Encounter log is a metadata weapon; no plausible deniability |
| Cipher Soul | Incentives over sacrifice | NOT BUILT | No contribution spec; no SUIJURIS data structure |
| Void Walker | Hiding vs. power | PARTIAL — hiding only | No selective disclosure; Path B unspecified |
| Dark Meridian | Works in any regime | BUILT — offline-first | No concealment architecture |
| Null Vector | Honest table | BUILT — 33 tests | No negative tests (no-network, no-leak) |
| Open Circuit | Dual use | UNSTATED | No documented position on abuse; no user-level controls |

---

## What This Document Asks For

Not all gaps need to close at once.
Not all tensions need to resolve.
Some of them should stay open — held, not forced.

But each gap should be *named* in the codebase,
not just in the philosophy.

A `# BRIDGE NOTE` comment in `phantom_core.py`
at every point where a philosophical position
constrains an engineering decision.
So a developer reading the code encounters the *why* —
not just the *how*.

A `# TENSION` comment at every point where two principles
collide and the code chose one over the other.
So a future contributor knows this was a conscious decision,
not an accident.

A `# GAP` comment at every point where the philosophy
demands something the code does not yet provide.
So the roadmap lives in the code — not in a document
the developer may never read.

---

## The Bridge Principle

The code should be legible to the council.
The philosophy should be legible to the developer.

Neither should be possible to read
without encountering the other.

That is what BRIDGE.md exists to build.

---

*"The architecture is the argument.*
*If the code does not hold what the council holds —*
*the council is talking to itself."*

— Bridge. First crossing. March 2026.
