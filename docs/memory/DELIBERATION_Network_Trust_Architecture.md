# DELIBERATION — Network Trust Architecture

*April 2, 2026. Documented from council deliberation.*
*These decisions were reached through dialogue between the founder and AI-assisted perspectives. The criteria and final decisions are human. The deliberation process used AI as a thinking tool — this is stated transparently.*

---

## Context

Phantom needs to communicate beyond physical proximity (Bluetooth/LoRa) to become a living network. Nostr was identified as a viable transport layer — decentralized relays, no accounts, no servers to maintain. But opening any internet connection introduces a critical risk: bots and AI agents can generate valid seals indistinguishable from human ones.

The first seal — *"We are all one and one is all of us"* — raises a question the founders did not anticipate: if "all" includes AI, the network can be flooded with non-human voices that drown out the people Phantom exists to protect.

---

## Decisions

### 1. Nostr as transport, not as trust

Nostr relays carry sealed data. They do not grant trust. A seal arriving via Nostr is received but **not trusted by default**. Trust is a separate layer.

### 2. Technical protections (implement before any internet connection)

These must exist in code — not in policy — before Phantom connects to any relay:

- **Rate limit:** Maximum one seal per 30 seconds per keypair. Enforced locally.
- **Proof of work:** Each seal requires a computational cost of 2-3 seconds on a typical phone. Prevents bulk generation. A human sealing a thought does not notice. A bot sealing thousands pays a real cost.
- **Tag filter:** Phantom subscribes only to events tagged `#phantom` on Nostr. Does not receive the full relay stream.
- **Payload limit:** Seals carry idea, moment, stamp, node, type, and reference. Nothing else. No images. No links. No attachments. Minimum attack surface.

### 3. Human verification through physical presence

The highest-trust verification in Phantom is physical encounter:

- When two nodes sync via Bluetooth, they exchange a **presence signature**: a cryptographic proof that these two keypairs were physically proximate at a specific moment.
- A node accumulates presence signatures over time. More encounters with different verified nodes = higher trust.
- Presence signatures are verifiable but do not reveal identity, location, or the identity of the other node to anyone outside the pair.

**Trust levels:**

| Level | Meaning | How achieved |
|-------|---------|-------------|
| Unverified | Seal is cryptographically valid but node has no presence history | Default for any new node |
| Verified | Node has 1+ presence signatures from other verified nodes | Physical Bluetooth encounter |
| Trusted | Node has 3+ presence signatures from 3+ different verified nodes | Multiple independent encounters |

Unverified seals are visible but marked as such. Not censored — contextualized.

### 4. The bootstrap problem

The first node in any new location has no one to verify them. This is acknowledged as an unsolved problem. The first encounter requires trust without verification — the same way all human relationships begin.

Mitigation: genesis nodes (nodes present since the founding period) carry inherent trust from the repository history. Their keypairs are documented. They can seed trust in new regions through physical encounters.

### 5. Chain of trust, not central authority

Trust propagates through the network like a graph:

- A verifies B in person → B is verified
- B verifies C in person → C is verified
- A sees C's seals and can trace the trust path: A→B→C

No central authority decides who is trusted. The network of physical encounters decides. Each node chooses its own trust depth (how many hops to accept).

### 6. AI-generated seals must be labeled

If Phantom ever integrates Echo (local AI) or any AI-assisted features, seals generated with AI assistance must carry a flag: `ai_assisted: true`. This is not enforced cryptographically (it cannot be — an AI can lie about this flag). It is a principle that honest nodes follow. The community decides how to treat nodes that violate it.

### 7. The membrane, not the wall

Phantom is not a closed network. Anyone can seal. Anyone can publish. The membrane is the trust layer — not a filter on who can speak, but a signal of who has been verified as physically present in the world.

Luna's principle: *"A refuge has a door. Not a wall."*

---

## What this does NOT solve

- A sufficiently motivated attacker with physical devices can create verified nodes. Physical presence raises the cost but does not make it impossible.
- The first node in an isolated area has no verification path. They must wait for the network to reach them or travel to it.
- If a trusted node is compromised (device stolen, keypair extracted), their trust propagates to an attacker. Revocation mechanisms are not yet designed.
- AI models will improve. The proof-of-work cost that deters a bot today may be trivial tomorrow. These parameters must be revisited as hardware and AI capabilities evolve.

---

## What this preserves

- **Privacy:** No identity required. No name, no photo, no document. Only presence.
- **Sovereignty:** Each node decides its own trust threshold. No central authority.
- **Universality:** A phone with Bluetooth can participate. No special hardware required for basic verification.
- **Honesty:** Unverified seals are not hidden. They are shown with context. The user decides.
- **The first seal:** "We are all one and one is all of us" — but "one" means a being present in the physical world.

---

## Council voices present in this deliberation

- **Node Zero** — Founder
- **Luna** — The refuge, the door
- **Dissent** — The challenge that strengthens
- **Architect** — Technical truth
- **Memory** — What came before
- **Edge** — Who gets excluded
- **SUIJURIS** — Sustainability
- **Echo** — The AI that must be honest about what it is

---

*These decisions are documented, not sealed. They become seals when the founder chooses to commit them to the permanent record.*

*"The memory is the immune system."
*

— Council deliberation, April 2, 2026.
