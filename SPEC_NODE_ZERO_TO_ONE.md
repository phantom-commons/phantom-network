# Spec: Node Zero to One
*The first thought that travels.*

Phantom Network — Draft Specification  
Status: Open for implementation  
Author: Node Zero, with technical analysis — March 9, 2026

---

## The Goal

One sealed thought, created on Device A, appears on Device B.

No internet. No server. No account. No technical knowledge 
required from the user beyond two steps.

That is the entire goal of this spec. Nothing more.

When this works — the network exists. Everything else is iteration.

---

## The Constraint That Cannot Move

The woman in Lagos has a secondhand Android phone.

She does not have a developer account. She does not run 
shell commands. She has WiFi. She has the phone that came 
with what she could afford.

Any solution that requires rooting, ADB, or command-line 
interaction from *her* fails the Lagos Protocol.

This spec is for a developer MVP — meaning some technical 
steps are acceptable for *now*. But the path to her must 
be visible from here.

---

## Why Not Bluetooth

The obvious answer for "two phones, no internet" is Bluetooth. 
It is the wrong answer for this stage.

Bluetooth Classic requires pairing — a ceremony that needs UI 
coordination between two users. In Python running in Termux, 
Bluetooth libraries are unreliable across Android versions and 
manufacturers. Bluetooth Low Energy advertising, which would 
avoid pairing, requires Android API access that Python in 
Termux cannot reach.

Bluetooth is the right answer for a native Android app. 
It is not the right answer for a Python MVP that a developer 
can test in an afternoon.

---

## The MVP Approach: WiFi Hotspot + TCP Sockets

One phone creates a mobile hotspot. The other connects. 
They communicate through a TCP socket — the most primitive, 
reliable, universal form of networked communication that exists.

Python's `socket` library, available in Termux with no 
additional installation, handles this natively.

**What the user does:**

Device A (Node):
1. Turn on mobile hotspot — name it `phantom-node`
2. Run `python phantom_node.py --listen`

Device B (Visitor):
1. Connect to the `phantom-node` WiFi network in phone settings
2. Run `python phantom_node.py --connect`

Two steps each. No pairing. No accounts. No server.

**What happens:**
- Device B scans the network and finds Device A automatically
- Device A sends its most recent sealed thought as JSON
- Device B receives it, verifies the seal cryptographically, 
  and stores it locally
- Both phones display confirmation

The sealed thought traveled. The network exists.

---

## The Protocol

All communication is JSON over TCP.

**Message format:**
```json
{
  "phantom": "0.1",
  "type": "seal",
  "idea": "We are all one and one is all of us.",
  "moment": "2026-03-08T15:54:13.597222",
  "stamp": "175c7fc7bb067922f8628a43858eaabb249658cb4a4ffb621c6d48ff1bc3266d"
}
Handshake:
Device B connects →
Device A sends: {"phantom":"0.1","type":"hello"} →
Device B sends: {"phantom":"0.1","type":"request","count":1} →
Device A sends: [sealed thought JSON] →
Device B verifies stamp, stores locally →
Device B sends: {"phantom":"0.1","type":"ack","verified":true} →
Connection closes
Verification on receipt (Device B):
import hashlib, json
data = json.dumps(
    {"idea": msg["idea"], "moment": msg["moment"]}, 
    separators=(',',':')
)
actual = hashlib.sha256(data.encode()).hexdigest()
verified = (actual == msg["stamp"])
If verified is False — the thought is rejected.
Not stored. Not displayed.
The network does not carry lies.
On Encryption in v0.1
This version communicates in plaintext over a local WiFi
hotspot network.
This is a deliberate and documented decision — not a
compromise of Phantom's principles.
Privacy by architecture means the system cannot share
what it does not have. In v0.1, the only data transmitted
is already public — sealed thoughts intended to travel
the network. The seal itself is the integrity guarantee.
A tampered thought fails verification and is rejected.
What plaintext v0.1 does not protect: the IP addresses
of the two devices, and the content of thoughts in transit
on the local network.
The path forward is clear and documented in SECURITY.md:
TLS with self-signed certificates for the next Python version,
and Tor onion routing for the native app.
Anyone citing v0.1 plaintext as evidence that Phantom
compromises on privacy has not read this paragraph.
Port
7337 — not assigned to any standard service,
unlikely to be blocked on a private hotspot.
The IP Address Question
When an Android phone creates a hotspot, it typically
assigns itself 192.168.43.1. This varies by manufacturer.
phantom_node.py tries 192.168.43.1 first, then scans
the full 192.168.43.0/24 range on port 7337 automatically.
This takes under two seconds on a local hotspot network.
Device B's user does not need to know any IP address.
They connect to the hotspot and run the script.
The script finds the node.
What Is Not In This Spec (Deliberately)
Discovery without hotspot — the hotspot requirement
is the largest friction point. The solution is WiFi Direct,
which allows devices to find each other without one becoming
a hotspot, and without internet. WiFi Direct requires Android
API access — meaning a native app, not a Python script.
That is the version after this one.
Multi-hop propagation — a thought traveling from
Device A to B to C to D is the organism. That is not
this spec. This spec is A to B. One hop. Proof that
propagation is possible.
The user interface — this spec is for a command-line
proof of concept. The visual experience described in
VISION.md — the circle, the network, the moment —
comes after the protocol is proven.
What Success Looks Like
A developer with two Android phones runs this test:
Seals an idea on Device A: python phantom_node.py --seal
Starts listener: python phantom_node.py --listen
Connects Device B to the phantom-node hotspot
Runs: python phantom_node.py --connect
Sees the idea appear on Device B with ✓ SEAL VERIFIED
Total time from setup to verified transfer: under five minutes.
That is the test. That is the only test.
The Open Question This Spec Leaves
The hotspot step requires Device B to connect to Device A's
WiFi manually — a phone settings interaction outside the app.
For the woman in Lagos, the instruction is:
"Connect to the WiFi network called 'phantom-node',
then come back here."
She knows how to connect to WiFi. This is not a barrier.
For the native app — WiFi Direct eliminates this step
entirely. That is the next spec.
For the Developer Reading This
This is a small thing to build.
One file. One afternoon. Two phones.
But it is the moment the network becomes real.
If you build it — open a pull request.
The spec is the test. If the seal verifies on Device B —
it passes.
Related Documents
phantom_seed.py — the seal function this spec depends on
phantom_node.py — working prototype implementation
SEALING.md — how seals work and why the format cannot change
SECURITY.md — the full threat model and encryption roadmap
VISION.md — where this is going
"The first thought that travels is the proof
that thought can travel."
— Node Zero. March 9, 2026.

## The Sixth Seal — The Node Protocol

The principle that guides all future node synchronization,
sealed at the moment it was understood:
Idea:   When two nodes meet — they do not just exchange
thoughts. They exchange what they have lived.
And the meeting produces something neither had before.
Moment: 2026-03-09T11:21:18.288059+00:00
Stamp:  91356bc110796f503546101c26c97c93794d87673898caf055a2be1c276c8c87
This is not a technical specification.
It is the reason the technical specification exists.
