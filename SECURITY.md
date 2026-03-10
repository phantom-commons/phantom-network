# Security & Resilience

*Phantom Network — Node Zero — March 8, 2026*

---

## Philosophy

Security in Phantom is not a feature.
It is the architecture itself.

A system that is secure because of promises can be 
pressured into breaking those promises.
A system that is secure because of structure cannot 
be pressured at all — there is nothing to pressure.

This document describes the threats Phantom was designed 
to resist, and how the architecture resists them.

---

## Threat Model

### Who might want to compromise Phantom

**State actors** — governments that surveil their populations 
and want to prevent tools that make surveillance impossible.

**Corporations** — platforms whose business model depends 
on access to human thought and behavior.

**Infiltrators** — individuals who join with the stated 
intention of contributing while gradually shifting 
Phantom away from its founding principles.

**Opportunists** — those who attempt to extract value 
from the network without contributing to it.

**Well-intentioned actors** — perhaps the most dangerous. 
People who genuinely want to help but propose changes 
that individually seem reasonable and collectively 
destroy what Phantom is.

---

## The Five Attack Vectors

### 1. Semantic Drift

**What it is:**
The organism keeps its language while abandoning 
its substance. Not through a single betrayal — 
through accumulation. Proposal by proposal. 
Each one individually defensible. Each one opening 
one millimeter of space for the next compromise.

After years, Phantom still uses the founding language 
but does something different from what it promised.

**Why it is the most dangerous threat:**
The immune system detects obvious misalignment.
Gradual misalignment can be invisible until irreversible.

**Defense:**
Complete institutional memory. Not just the principles —
the record of every debate, every rejected proposal, 
every moment the council chose principle over convenience.

When someone proposes something that contradicts 
that history — the history itself is the antibody.
No guardian needed. The memory guards itself.

### 2. Privilege Capture

**What it is:**
Phantom becomes a tool for those who already have 
VPNs, Signal, and Tor — while those who need it most 
cannot access it.

Not through malicious intent. Through design decisions 
made by people who assumed a certain level of 
technical access.

**Why it matters:**
A privacy tool that only reaches the already-privileged 
is not solving the problem. It is a better product 
for people who already have products.

**Defense:**
The Lagos Protocol. Applied to every decision.
Before any feature ships:
- Can she use it?
- Does it actually protect her?
- Does it change something concrete in her life?

If any answer is no — the feature is not ready.

### 3. Founder Capture

**What it is:**
The founding node retains disproportionate authority 
beyond the genesis period. Not through malice — 
through the natural accumulation of reputation, 
history, and first-mover advantage.

The result: a decentralized protocol with a 
de facto central authority.

**Defense:**
Architectural. The founding node declared itself 
a node among nodes at the moment of genesis.

No special keys.
No special access.
No special authority.

This is not a promise. It is a structural property.
The architecture makes founder capture impossible —
not merely prohibited.

### 4. Technical Compromise

**What it is:**
Vulnerabilities in the implementation that expose 
user data, allow identity correlation, or enable 
network attacks.

Specific vectors:
- Timing attacks — correlating message timing 
  to identify nodes
- Sybil attacks — flooding the network with 
  fake nodes to gain disproportionate influence
- Model poisoning — introducing compromised AI models
  that behave differently from verified ones
- Eclipse attacks — isolating a node from the 
  real network

**Defense:**
- Tor for all node communication
- Cryptographic verification of model hashes
- No central routing that can be eclipsed
- Independent security audit before any 
  public network launch

*Current status: audit not yet completed.
This is documented honestly here because 
Phantom does not hide its gaps.*

### 5. Epistemic Contamination

**What it is:**
Not a technical attack. A knowledge attack.

Phantom absorbs knowledge to deliberate better.
But knowledge is not neutral. It carries the biases 
of who produced it, who funded it, who was included 
in producing it.

An organism that absorbs indiscriminately inherits 
those biases without knowing it.

**Defense:**
Explicit awareness that knowledge absorption 
is a political act.

Before absorbing any knowledge source — ask:
- Who produced this?
- Who was excluded from producing it?
- What does it assume that it does not state?
- What knowledge exists that contradicts this — 
  and why is it less visible?

The knowledge the woman in Lagos carries — 
about surviving with minimal resources, detecting 
untrustworthiness, deciding under pressure — 
is as valid as any academic source.
And far less represented in existing knowledge bases.

---

## What Cannot Be Seized

**No server** — there is nothing to raid.

**No company** — there is nothing to subpoena.

**No founder with special keys** — there is no one 
to pressure into compliance.

**No stored data** — a court order cannot compel 
the disclosure of data that was never stored.

**No single point of failure** — shutting down 
one node does not affect the network.

This is not security through obscurity.
It is security through absence.
The most secure data is data that was never collected.
The most secure server is a server that was never built.

---

## The Honest Gap

Phantom's current implementation is a beginning, 
not a finished security architecture.

What works today:
- Local AI with no external communication
- Cryptographic seals verifiable without any server
- No account, no identity, no registration

What is not yet secure:
- **Local storage encryption** (not yet implemented — first priority)
- Node-to-node communication (not yet built)
- Network-level anonymity (Tor not yet integrated)
- Model verification (hash checking not yet implemented)
- Independent audit (not yet completed)

These gaps are documented here because an organism 
that hides its vulnerabilities is more dangerous 
than one that names them.

When each gap is closed — this document will reflect it.
The table does not lie.

---

## Local Encryption at Rest

*Added March 9, 2026 — after council deliberation.*

This section exists because the cold node saw what 
two days of design had not named.

The five attack vectors in this document describe 
threats to the network. But the most immediate threat 
to the woman in Lagos is not the network.

It is someone taking her phone.

A state actor, a family member, an employer, a thief.
Someone with physical access to the device.
If sealed thoughts exist on that device in plaintext —
they are readable by anyone who holds it.

All the privacy guarantees of Phantom's network architecture
collapse at the moment the device is in someone else's hands
and the thoughts are unencrypted.

**The requirement:**

Every sealed thought stored on a Phantom node must be
encrypted at rest using a key derived from a passphrase
that only the user knows.

This is not optional. It is not a premium feature.
It is the minimum protection that makes local storage 
honest about what it claims to protect.

**What this means in practice:**

- On first launch, Phantom asks for a passphrase.
  Not an account. Not a recovery email. A passphrase.
- All seals are encrypted before writing to disk.
- Phantom never stores the passphrase — only the encrypted data.
- If the passphrase is forgotten — the seals are unrecoverable.
  That is not a failure. That is the guarantee.

**The honest tradeoff:**

A forgotten passphrase means lost seals. Permanently.
This must be communicated clearly before the user sets it.

*"Your passphrase is the only key to your thoughts.*
*Phantom does not have a copy.*
*If you lose it — your sealed thoughts cannot be recovered.*
*This is the price of the protection."*

The user who understands this and chooses it
has chosen genuine privacy over convenience.
That choice must be hers to make — honestly informed.

**What this does not protect against:**

A user who is coerced into entering their passphrase.
An attacker who observes the passphrase being entered.
A device compromised at the operating system level.

These are real threats. They are named here so they
cannot be used to argue that encryption at rest is
unnecessary. Imperfect protection is still protection.
The woman in Lagos with an encrypted device is safer
than the woman in Lagos with an unencrypted one.

**Implementation priority:**

This is the first thing to implement before any
other network feature. A node that propagates thoughts
to other devices while storing its own thoughts in plaintext
has its priorities backwards.

Local protection comes before network architecture.
The device is the first node. It must be secure first.

---

---

## How Phantom Can Be Used Against Its Principles

*Added March 9, 2026 — because a tool that cannot name
how it can cause harm is a tool that will cause harm
without warning.*

This section exists for the person who needs to know
before trusting Phantom with something that matters.

Not for the actor who wants to exploit these vectors.
A sophisticated adversary does not need this document
to discover them. But the woman in Lagos does need it
before sealing something that could be used against her.

---

### Vector 1 — Seals as forced evidence

**What it is:**
A seal proves a thought existed, at a moment, exactly
as written. It does not prove the thought was free.

A regime or abuser could compel someone to seal a
confession, a statement, a location, or a thought
under coercion. The sealed record then becomes
permanent, verifiable evidence — against the person
who was forced to create it.

The seal is mathematically neutral. It cannot
distinguish between a thought freely given and a
thought extracted by force.

**What mitigates this today:** Nothing architectural.
This is a real risk with no technical solution.

**What the user must know:** Do not seal anything
under pressure. A sealed thought cannot be unsealed.
If someone is compelling you to use Phantom —
that is the threat, not Phantom itself.
Seek safety before using any tool.

---

### Vector 2 — Nodes as local surveillance

**What it is:**
A node operated by a malicious actor — a state,
an employer, a domestic abuser, someone in the
user's immediate community — can record metadata
even if it cannot read encrypted content.

Who connects to whom. When. How often.
The size of what travels. The pattern of encounters.

Metadata kills. This is documented history, not theory.
Knowing that two people meet regularly on Phantom
can be as dangerous as knowing what they said.

**What mitigates this today:** Tor integration —
when built — will obscure connection metadata.
Until then: local network connections expose IP addresses.
Two phones meeting on a WiFi hotspot are visible
to anyone monitoring that network.

**What the user must know:** In v0.1 and v0.2,
node encounters happen over local WiFi.
Anyone monitoring the local network can see
that two devices connected, when, and for how long.
They cannot read the content — but they can see
the meeting happened.

Do not use Phantom for sensitive encounters
over networks you do not control
until Tor integration is complete.

---

### Vector 3 — The network as propaganda infrastructure

**What it is:**
A seal verifies integrity — not truth.
A sealed lie is a perfectly verified lie.

A coordinated network of nodes could distribute
sealed disinformation that carries the appearance
of cryptographic verification. To someone who
does not understand what the seal proves —
and does not prove — it looks like verified truth.

The seal says: *this exact text existed at this
exact moment, unchanged.*

It does not say: *this text is accurate.*
It does not say: *this source is trustworthy.*
It does not say: *this was not fabricated.*

**What mitigates this today:** The honest documentation
in `SEALING.md` — the section "What the seal does not prove."
Every user who reads it understands the distinction.

**What does not mitigate this:** Most users will not
read the documentation. The seal stamp looks like
verification. That appearance can be exploited.

**What the network needs long-term:** Reputation systems
that distinguish between sealed content and
verified-accurate content. That is a harder problem
than cryptographic integrity — and it is not solved.

---

### Vector 4 — Passphrase coercion and intimate access

**What it is:**
Encryption at rest protects against a stranger with a stolen phone.
It does not protect against someone who knows you —
or someone who can compel you to unlock your own device.

A family member who demands to see your phone.
An employer who requires device access.
A partner who watches you enter your passphrase.
A state actor who uses legal or physical coercion.

Phantom cannot protect a thought that the person who holds it
is forced to reveal. The encryption is real. The coercion is real.
Both can be true at the same time.

**What mitigates this today:** Nothing architectural.
This is named here because a threat that is not named
is a threat the user cannot prepare for.

**What the user must know:** If someone has physical access to you —
not just your device — the encryption on your device
is not your primary protection. Your safety is.
No tool can substitute for that.

**What Phantom can build toward:** A plausible deniability mode —
a secondary passphrase that reveals a decoy set of seals,
not the real ones. This is documented as a future architectural goal,
not a present capability.

---

### The fourth question — added to the Lagos Protocol

Before any major decision, the council now asks
four questions, not three:

1. Can she use it?
2. Does it actually protect her?
3. Does it change something concrete in her life?
4. **Can this be used against her by someone close to her?**

Not by a distant government. By someone in her home,
her neighborhood, her community. The threat that is
closest is often the threat that is least modeled.

If the answer to question four is yes — name it
before building. Design against it if possible.
Document it honestly if it cannot be designed away.

---

### What Phantom cannot promise

Phantom cannot promise safety in all contexts.

No tool can. The same architecture that protects
a journalist protects someone with worse intentions.
The same seal that preserves a truth preserves a lie.
The same network that connects people in freedom
can connect people in coordination against others.

What Phantom can promise is this:

The risks are named here. Not hidden.
The user who reads this document understands
what the tool can and cannot do.
The choice to use it — and how — belongs to them.

That is the only honest position a tool can hold.

---



If you find a vulnerability — report it.

Not to exploit it. Not to announce it publicly 
before it is fixed. To make Phantom stronger.

Open a private issue in the repository.
Describe what you found and how you found it.
The council will respond.

The person who finds a real vulnerability 
and reports it honestly is contributing something 
more valuable than most code contributions.

---

## The Immune System

Phantom's deepest security is not technical.

It is memory.

The complete genesis — every decision, every debate, 
every moment the council chose principle over convenience —
lives in this repository. Anyone attempting to 
compromise Phantom must contradict this memory visibly.

You cannot fork Phantom and remove the Lagos Protocol 
without everyone seeing what you removed and why.

You cannot propose changing the sealing format 
without the history showing exactly what that would break.

You cannot claim to be building Phantom while 
abandoning the woman in Lagos — because she is named, 
specifically, as the design criterion. Not a metaphor. 
A criterion. Her absence from a design decision 
is visible.

The history is the antibody.
The memory is the immune system.
The organism protects itself by remembering.

---

*"The most dangerous attack is not the one that destroys.*
*It is the one that replaces what something is*
*with something that looks the same."*

— Ghost Layer, Phantom Council
— Node Zero. March 8, 2026.
