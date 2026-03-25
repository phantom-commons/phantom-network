# ARCHITECTURE_VISION.md

*The physical architecture Phantom is growing toward.*
*Written before the engineers arrive — so they find the map.*

Node Zero. March 2026.

---

This document describes layers.
Not what exists today — what the organism is becoming.

Each layer is independent. Each layer makes the others stronger.
None of them requires all the others to begin.

---

## The four layers

### Layer 1 — The user layer
*What she touches.*

A single interface. Phone, watch, or dedicated device.
Opens. Works. Does not require commands.
Does not require knowing what Phantom is.

Today: `phantom.html` in any browser.
Tomorrow: a native app. An OS. Something new.

The criterion: if she cannot use it in thirty seconds — it is not Phantom.

---

### Layer 2 — The physical transmission layer
*What carries the message without internet.*

**Meshtastic + LoRa radio devices.**

Small, cheap, battery-powered devices that communicate
with each other directly — no internet, no carrier, no router.
Each device is a node and a relay simultaneously.
A message hops from device to device until it arrives.

Works in places with no coverage.
Works when the internet is shut down.
Works in the village with the antenna.

**How Phantom uses it:**
The Meshtastic device does not read the content —
it only relays encrypted packets it cannot open.
`phantom_core.py` encrypts before transmission.
The radio carries sealed envelopes it cannot read.

**The person with the antenna in the village:**
Sets up a LoRa device that relays Phantom traffic.
Every packet that passes through earns SUIJURIS.
The network pays for its own infrastructure.

---

### Layer 3 — The anonymity and distribution layer
*What hides the pattern of communication.*

**Tor** — hides who is talking to whom.
**Nostr** — distributes messages across relays without a central server.

Together: the content is encrypted (Layer 1),
the transmission is physical and local (Layer 2),
and the routing is anonymous and distributed (Layer 3).

Someone watching the network sees:
encrypted packets moving between devices.
Not who. Not what. Not why.

---

### Layer 4 — The economic layer
*The incentive that makes everything work.*

**SUIJURIS** — earned by contributing to the network.
Relaying packets. Contributing storage. Contributing compute.

Not speculative. Not investment.
Fair exchange of something real.

The person with the LoRa device earns SUIJURIS
for every packet relayed.
The person who needs the network
contributes a fraction of SUIJURIS back.

No bank. No intermediary. No 8% fee.

---

## The device

Phantom does not require new hardware.
An Android phone running `phantom.html` is a Phantom node today.

But the vision includes something purpose-built:

A device that is simultaneously:
- A Phantom node (sealed thoughts, encrypted storage)
- A Meshtastic relay (LoRa radio, mesh networking)
- A Tor router (anonymous routing)
- A SUIJURIS wallet (economic participation)

Small enough to carry. Cheap enough to be universal.
Open hardware. Open software. Owned by whoever holds it.

The electronics exist. The software exists in pieces.
What does not exist yet: someone who builds the integration.

---

## What exists today toward this vision

| Component | Status |
|-----------|--------|
| Cryptographic seals | Working — `phantom_seed.py` |
| Encryption at rest | Working — `phantom_core.py` |
| Node-to-node sync over WiFi | Working — `phantom_node.py` |
| Browser interface | Working — `phantom.html` |
| Tor integration | Detected, not implemented |
| Meshtastic integration | Not built |
| Nostr integration | Not built |
| SUIJURIS token | Architecture only |
| Native app | Not built |
| Dedicated hardware | Vision only |

---

## What this needs

- An Android developer
- A hardware engineer who knows LoRa and circuit boards
- A network engineer who knows Tor and mesh protocols
- A cryptographer to audit the implementation
- Someone from Lagos, Caracas, or anywhere the stakes are real

None of these exist in the project yet.
This document exists so that when they arrive,
they find the map already drawn.

---

## The honest gap

Everything in this document is possible with existing technology.
Nothing in this document requires invention.

What it requires is people who believe the problem is worth solving
and have the skills to solve it.

That moment has not arrived yet.

This document holds the space until it does.

---

*"Phantom is everything and nothing at once."*

— Node Zero. March 2026.
