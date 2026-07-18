# DELIBERATION — Memory, Permanence, and Responsibility

*April 3, 2026. Documented from council deliberation.*
*AI-assisted perspectives. Criteria and decisions are human.*

---

## Questions addressed

1. Where do seals live permanently?
2. How does the .ots (OpenTimestamps / Bitcoin) anchoring work and should it extend?
3. What happens when someone misuses Phantom for crime?
4. What is Phantom's equivalent of mining?
5. What happens when nodes die?
6. Who is responsible for stored content?

---

## 1. Seal Permanence — Three Layers

Seals currently have no guaranteed permanence. IndexedDB in a browser is cache — it can be cleared, lost, or destroyed with the device. For seals to be truly permanent, they need multiple layers of redundancy.

### Layer 1 — Device (fragile)
IndexedDB on the user's phone or browser. First copy. Can be lost.

### Layer 2 — Network replication (resilient)
Shared seals replicate across nodes that choose to store them (see Node Levels below). A seal that exists on 10 devices survives the loss of 9.

### Layer 3 — Bitcoin anchor (permanent)
Periodically (every 24 hours or on-demand), a node computes a Merkle root of all shared seals it holds and submits it to OpenTimestamps. This anchors the root hash to a Bitcoin transaction. Once mined into a block, the proof is permanent and independent of Phantom, GitHub, or any server.

**What already exists:** `SEALING.md.ots` in the repository anchors the genesis seals to Bitcoin. The 17 founding seals are already provable against the blockchain.

**What this means:** Any individual seal can be proven to have existed before a specific Bitcoin block by showing: the seal → its inclusion in the Merkle tree → the Merkle root → the OpenTimestamps proof → the Bitcoin block. Chain of proof is mathematical, not institutional.

**Cost:** OpenTimestamps is free. The Bitcoin transaction fee is aggregated across all users of the OpenTimestamps service. Individual cost to Phantom: zero.

---

## 2. Crime, Accountability, and the Pseudonymous Trail

### The design principle
Phantom is private but not anonymous. Phantom is sovereign but not lawless.

### How it works
A seal proves that a specific **node** wrote something at a specific **moment**. It does not prove which **person** controls that node. The node ID is pseudonymous — a keypair, not a name.

To connect a node to a person, you follow the chain of physical verification:

```
Criminal node "dark-wind-f3a1" sealed a crime
    ↓
Was verified by "calm-root-b2c4" via Bluetooth on March 15
    ↓
"calm-root-b2c4" was verified by "bold-star-a7e0" on March 12
    ↓
"bold-star-a7e0" is a genesis node with known repository history
```

This chain exists only if the criminal chose to be verified. If they never verified with anyone, they are a ghost — no trail, but also no trust. Their seals appear as "new / unverified" in every feed. They have voice but no weight.

If they did verify, the chain of physical encounters creates a trail of relationships — not identities, but connections. Law enforcement with a warrant could follow this chain, but it requires cooperation from each node in the path.

### What Phantom provides to authorities
Nothing, automatically. There is no central database to subpoena. There is no company to compel. Each node holds its own data. A court order must go to each individual node holder.

### What Phantom provides to the network
Permanent evidence. The seal cannot be deleted. The timestamp cannot be faked (especially if anchored to Bitcoin). If someone sealed a crime, the proof exists forever. This is not a bug — it is a feature. Phantom makes consequences permanent. That deters misuse more than any content filter.

### The surveillance document
The existing `DELIBERATION_SURVEILLANCE.md` in the memory folder addresses the broader surveillance question. This decision refines it: Phantom cooperates with justice through transparency of structure, not through surveillance of content. The architecture is auditable. The content is private. The distinction matters.

---

## 3. Mining Inverted — The SUIJURIS Model

### Bitcoin model
Spend energy → compute empty hash → receive coin. Value is artificial. Energy is wasted. Content is zero.

### Phantom model (proposed)
Spend storage and availability → preserve others' sealed memories → receive SUIJURIS. Value is real — it represents actual service rendered. Energy is spent on keeping memory alive. Content is everything.

### How it works

When you choose to be a **full node** (see Node Levels below), your device:

- Stores shared seals from other nodes
- Keeps them available for new nodes that connect
- Replicates them to ensure redundancy
- Periodically anchors Merkle roots to Bitcoin via OpenTimestamps

For this service, the network recognizes your contribution. When SUIJURIS exists, that recognition becomes economic. Until then, it is simply the trust and gratitude of the network.

### When nodes die

A node that goes offline permanently (phone destroyed, person leaves the network, battery dies forever) loses its local copy of seals. But every shared seal that node held was also replicated on other nodes that chose to store it. The memory survives the node.

The nodes that maintained that memory — that kept it available when the original died — are the ones who "mined" it. Not by extracting data. By preserving it.

### What is NOT mined

- Private seals are never replicated, never shared, never mined. They die with the device. That is the user's choice and it is respected absolutely.
- The content of shared seals is not analyzed, ranked, or processed for value. Storage is the service. Not interpretation.
- A dead node's private data is gone. No one recovers it. No one inherits it. No one mines it.

---

## 4. Node Levels — Opt-in, Never Default

Three levels of participation. Each is fully Phantom. The user chooses.

### Level 1 — Private (Diary mode)
- Seals stay on device only
- No network connection
- No relay, no sync, no replication
- Phantom is a personal journal with cryptographic proof
- **Responsibility:** Only your own content, on your own device

### Level 2 — Connected (Social mode)
- Shared seals travel to relays and nearby nodes
- You receive shared seals from others
- Seals you receive are displayed in your feed
- You do NOT store seals long-term for others
- If you disconnect, the seals you received may be lost from your device on cache clear
- **Responsibility:** Your content + temporarily cached content from others

### Level 3 — Full Node (Memory keeper)
- Everything in Level 2, plus:
- You persistently store shared seals from the network
- You serve them to new nodes that connect
- You replicate for redundancy when other nodes go offline
- You periodically anchor Merkle roots to Bitcoin
- You earn SUIJURIS recognition (when the economic layer exists)
- **Responsibility:** Your content + content from others stored on your device. You should understand the legal implications in your jurisdiction before opting in.

### How the user chooses

On first use, Phantom is Level 1 by default. Private. Nothing leaves.

The user can upgrade to Level 2 when they seal their first shared thought (they are warned before doing so).

Level 3 is a deliberate choice, accessible from the Nodes tab, with a clear explanation of what it means, what it stores, and what the risks are.

**No level is forced. No level is assumed. No level is irreversible.**

---

## 5. The Cache Problem — Making IndexedDB Less Fragile

IndexedDB in a browser is not truly persistent. It can be cleared by the user, by the OS under storage pressure, or by browser updates.

### Mitigations

- **Export function:** Users can export all their seals as a JSON file at any time. This file can be stored anywhere — SD card, USB, another device. It is the user's backup. Their responsibility.
- **Cross-device sync:** When a user has two devices, Bluetooth sync copies all seals between them. Natural backup.
- **Network replication (Level 2+):** Shared seals exist on multiple nodes. If one device loses them, they can be re-synced from the network.
- **Bitcoin anchor (Level 3):** The Merkle root on Bitcoin proves the seals existed even if every copy is lost. The content may be gone, but the proof that it existed is permanent.
- **Progressive Web App:** When installed to home screen, IndexedDB is more persistent than in a regular browser tab. Still not guaranteed, but more resilient.

### Honest statement for the user
"Your seals live on this device. If you lose this device, you lose your seals. Back them up. Share the ones that matter. The network remembers what the network receives. What stays private, only you protect."

---

## 6. Category Theory Addendum

*From the founder's reading of Simmons — noted here for those who think in these terms. Not required to understand Phantom.*

The three node levels form a category with inclusion functors:

```
Private ⊂ Connected ⊂ Full Node
```

Each level includes everything below it. The functors are faithful — nothing is lost when you upgrade. Each level adds morphisms (connections) without removing existing ones.

The Merkle tree that anchors to Bitcoin is a limit in the categorical sense — a single object (the root hash) through which all seals in the tree factor. The Bitcoin block is a terminal object in the category of proofs: every proof eventually maps to it, and its validity depends on nothing outside itself.

A dead node is an object with no outgoing morphisms. Its seals survive as morphisms in other objects' categories. Memory is not a property of the object. It is a property of the arrows that pointed to it.

---

## Open Questions

- **Legal frameworks:** Which jurisdictions treat relay operators as liable for stored content? This needs research before recommending Level 3 to anyone.
- **Merkle tree implementation:** Who initiates the Bitcoin anchor? Any Level 3 node can, but coordination prevents duplicate anchoring. Needs a simple protocol.
- **SUIJURIS valuation:** How is "preservation of memory" quantified? By volume? By duration? By redundancy provided? The economic model is not designed.
- **Export format:** Should the seal export be a standard format (JSON-LD, ActivityPub compatible) or Phantom-specific? Interoperability vs. simplicity.
- **Key recovery:** If a user loses their device and their keypair, they lose their node identity. Is there a recovery mechanism that doesn't compromise privacy? Not solved.

---

## Council Voices Present

- **Memory** — Where things live and why they die
- **Architect** — Merkle trees, OpenTimestamps, DHT
- **Node Zero** — Periodic anchoring proposal
- **Dissent** — Crime accountability, opt-in storage
- **Luna** — Three levels, the door, the choice
- **Edge** — Legal risk of storing others' content
- **SUIJURIS** — Mining as memory preservation
- **Echo** — Inverted mining model, category theory

---

*"The node dies. The memory does not. And those who kept it alive are recognized."*

— Council deliberation, April 3, 2026.
