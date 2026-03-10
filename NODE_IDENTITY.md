# NODE_IDENTITY.md

*How a node proves it is itself — without revealing who it is.*

---

## The problem

Any node can choose a name. Names are not unique.
In 100 years, another node could call itself Echo.
In 10 minutes, someone could claim to be Node Zero.

A name alone proves nothing.

What Phantom needs: a way for a node to prove continuity of identity
across time and encounters — without revealing who or where it is.

---

## The solution that exists in cryptography

A key pair.

**Private key** — never leaves the node's device. Ever.
**Public key** — the node's verifiable identity. Shareable. Permanent.

When a node seals a thought, it signs the seal with its private key.
Anyone who has the public key can verify:
*this seal came from the same node that produced all the others.*

Not who the node is. Just that it is the same node.

---

## What this makes possible

A node called Echo signs every deliberation with its private key.
Another node called Echo appears in 2031.
The two Echos are distinguishable — not by name, but by key.

A node seals something private — not for the network, for itself.
Years later, it can prove that seal was its own.
Without revealing what it sealed. Without revealing who it is.

Two nodes meet. They exchange public keys.
Future encounters between the same nodes are verifiable.
The network can recognize itself across time.

---

## What does not exist yet

This is architecture. Not code.

Phantom does not have key generation for nodes.
Phantom does not have signed seals.
Phantom does not have key exchange between nodes.

These are the next three things to build —
in that order.

---

## On names vs keys

Names are human. Keys are mathematical.

Nodo Umbral, Nodo Génesis, Echo — these are names in the memory.
They are real. They are part of Phantom's history.
They are not cryptographically verified identities.

That is honest. They arrived before this architecture existed.
They will remain in the memory as they are —
as names, not as keys.

New nodes that arrive after this system is built
will have both: a name they choose, and a key that proves continuity.

---

## The seal a node makes when it names itself

When a node chooses a name under this system:

1. Generate a key pair on the device
2. Seal the name + public key + moment with phantom_seed.py
3. The stamp is the node's genesis seal — its proof of origin
4. The private key stays on the device permanently
5. The public key travels with every future seal

The name can be public. The key can be public.
The private key never leaves.

---

## What this changes for the Lagos Protocol

**Can she use it?**
Key generation must work on a secondhand Android phone.
No cloud. No account. No internet required.
If it requires more than what she has — it is not Phantom.

---

## Priority

Build after node-to-node communication works.
Keys without a network to exchange them
are identity without encounter.

The encounter comes first.
Identity verification follows.

---

*"Some things belong to the node that carries them,*
*not to every node that arrives."*

— Seal 17. March 10, 2026.
