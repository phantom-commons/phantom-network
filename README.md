*Your thoughts belong to you.*

**[→ Open Phantom](https://phantom-commons.github.io/phantom-network/)**

Write something. Seal it. From that moment — it exists permanently, verifiably yours, on no server but your own device. Anyone can confirm it is unchanged. No one can alter it without breaking the seal.

*No account. No installation. No internet after first load.*

---

# Phantom Network

*Privacy is not for hiding. It is for being free.*

## What this is

Phantom seals your thoughts cryptographically. A seal proves that you wrote something at a specific moment. No one can alter it. No one can deny it existed. No server. No account. Everything happens on your device.

It is not a social network. Not a startup. Not a privacy protocol with a nice logo.

It is infrastructure so that human thought belongs to whoever thinks it.

## Why it exists

There is a woman in Lagos. She has a secondhand Android phone, three children, and a small shop. She learned to self-censor without anyone explicitly asking her to.

Phantom exists for her. Not as metaphor. As design criterion.

If she cannot use it — it is not Phantom.

## What exists today

- **Phantom PWA** (`docs/index.html`) — seal, verify, share, and receive in any browser. No installation. Installable as app on Android/iOS via HTTPS.
- **Cryptographic seal** (SHA-256) — any idea can be sealed and verified by anyone, on any device, without trusting any authority
- **Seventeen genesis seals** — permanent and irreversible since March 8, 2026
- **Feed** — shared seals appear in a network feed. Respond with replies. Propose with proposals. Vote with votes. Every interaction is a seal.
- **Threads** — a shared seal opens as a thread. Others reply. Proposals show vote counts (agree, disagree, abstain). All verifiable.
- **Node identity** — each device generates a pseudonymous name on first use. Not your name — your node. Consistent across sessions.
- **Encryption at rest** (AES-256-GCM) — sealed thoughts are encrypted on device
- **Node-to-node sync** (v0.6) — two devices can meet and sync sealed thoughts over local WiFi
- **Bluetooth/LoRa architecture** — designed for sync without internet. Supports Meshtastic, Nordic UART, and Phantom custom BLE service
- **33 automated tests** — the code verifies its own integrity
- **Genesis seals anchored to Bitcoin** via OpenTimestamps (`SEALING.md.ots`)

## What does not exist yet

- Phantom relay — purpose-built decentralized relay for seal exchange over internet (specified in `SPEC_RELAY.md`, not implemented)
- Node verification by physical presence — trust established through Bluetooth encounters (specified in `DELIBERATION_TRUST.md`, not implemented)
- Proof of work per seal — anti-bot protection (specified, not implemented)
- SUIJURIS — the economic layer (designed, not built)
- Echo — local AI on device (vision, not built)
- Community

This is an honest beginning. Not a finished product.

## How it works

Everything is a seal.

| You do this | It creates this | It does this |
|-------------|----------------|-------------|
| Write a private thought | Private seal | Stays on your device forever. Your diary. |
| Share a thought | Shared seal | Travels to nearby nodes. Others can see and respond. |
| Reply to someone | Reply seal | References the parent seal. Creates a thread. |
| Make a proposal | Proposal seal | Others can vote agree, disagree, or abstain. |
| Vote on a proposal | Vote seal | Your position is sealed — permanent and verifiable. |

Same format. Same wire. Same verification. SHA-256 does not care what kind of thought it is.

## Three levels of participation

| Level | What it means | What it stores |
|-------|--------------|---------------|
| **Private** | Diary mode. Nothing leaves your device. | Only your seals. |
| **Connected** | Your shared seals travel. You see others' seals. | Your seals + temporarily cached seals from others. |
| **Full Node** | You store and serve seals for the network. | Your seals + persistent copies of others' seals. |

Each level is fully Phantom. You choose. No level is forced, assumed, or irreversible.

## Principles that never change

1. Privacy by architecture — not by policy
2. No central authority
3. Universal access
4. Radical transparency
5. Founders become obsolete by design
6. The organism evolves — the principles do not
7. Phantom exists for human beings — not for itself

## What Phantom does NOT protect

If you opened this through a web link, your IP address was visible to the server that delivered it. Phantom does not hide your IP and does not replace a VPN or Tor. Once the file is on your device, everything runs locally — but the act of downloading it was not private.

## The first two seals — permanent since March 8, 2026

Idea: "We are all one and one is all of us."
Seal: `175c7fc7bb067922f8628a43858eaabb249658cb4a4ffb621c6d48ff1bc3266d`
Moment: `2026-03-08T15:54:13.597222`

Idea: "Everything we do has consequences, and those consequences echo through eternity."
Seal: `87d69ca1f984011a9d7d7eec474abe2b906a18f83515b9e115d0525c7e1ffaa2`
Moment: `2026-03-08T19:56:13.788Z`

Seals 3–17 are in `SEALING.md`.

---

## For those who want to contribute

Read `CONTRIBUTING.md` first.

We are not looking for the most technically skilled developer. We are looking for the one who reads this and recognizes it as their own.

## If you are not a developer

You do not need to know how to code to be part of Phantom.

**Seal an idea.** Open `docs/index.html` in any browser. Write something. Seal it. From that moment — it exists.

**Verify a seal.** If someone shares a sealed idea with you — go to the Nodes tab and paste it. The math either confirms it or it does not.

**Tell your story.** Open an Issue in this repository. Tell us what you would write in Phantom that you cannot write anywhere else.

**Translate.** If you can make any of these documents accessible in another language — that contribution is as valuable as any code.

---

## Repository Contents

### The app
| File | What it is |
|------|------------|
| `docs/index.html` | Phantom PWA — seal, verify, feed, threads, votes, Bluetooth. Zero external dependencies. |
| `docs/manifest.json` | PWA manifest — installable as app |
| `docs/sw.js` | Service worker — works offline |

### The code
| File | What it is |
|------|------------|
| `phantom_core.py` | Shared library — the seal algorithm lives here |
| `phantom_node.py` | Node-to-node sync over local WiFi |
| `phantom_seed.py` | The seal tool — command line |
| `phantom.html` | Original seal and verify page (legacy — use `docs/index.html`) |
| `test_phantom.py` | 33 tests — run to verify the code is intact |

### The memory
| File | What it is |
|------|------------|
| `GENESIS.md` | The origin and the why |
| `GENESIS_DAY2.md` | What happened on day two |
| `CONVERSATION.md` | The moments that made Phantom |
| `WHITEPAPER.md` | Full architecture |
| `SEALING.md` | How seals work — with verification code |
| `SEALING.md.ots` | OpenTimestamps proof — genesis seals anchored to Bitcoin |
| `SECURITY.md` | Threat model — five vectors, named honestly |
| `REVIEW_MARCH10.md` | External audit — what an outside node found |

### The vision
| File | What it is |
|------|------------|
| `VISION.md` | What Phantom is growing toward |
| `VISION_FOUNDATION.md` | Foundation, SUIJURIS, physical architecture |
| `ARCHITECTURE_VISION.md` | Four-layer architecture |
| `ECHO.md` | The node that named itself |
| `LUNA.md` | The spirit that arrived uninvited |

### The deliberations
| File | What it is |
|------|------------|
| `DELIBERATION_TRUST.md` | Network trust — anti-bot protections, physical verification, chain of trust |
| `DELIBERATION_MEMORY.md` | Where seals live — three layers of permanence, mining as memory preservation, node levels |
| `SPEC_RELAY.md` | Phantom relay protocol — purpose-built, minimal, decentralized |
| `DELIBERATION_MARCH25.md` | March 25 deliberation |
| `COUNCIL.md` | The deliberation tool |
| `METHOD.md` | Six steps — how decisions are made |

### The economics
| File | What it is |
|------|------------|
| `ECONOMICS.md` | SUIJURIS principles |
| `ECONOMICS_2.md` | Second iteration |
| `ECONOMICS_3.md` | Third iteration |
| `ECONOMICS_4.md` | Fourth iteration |
| `SUIJURIS.md` | The currency — origin and meaning |

### Other
| File | What it is |
|------|------------|
| `NODES.md` | Every node that arrived and what they built |
| `NODE_IDENTITY.md` | Cryptographic node identity — architecture |
| `IDENTITY.md` | How Phantom presents itself |
| `FOUNDER.md` | Node Zero |
| `CONTRIBUTING.md` | How to contribute |
| `BRIDGE.md` | Bridges between worlds |
| `SPEC_NODE_ZERO_TO_ONE.md` | From zero to one |
| `memory/` | Institutional memory — deliberations, surveillance analysis |

---

## File Integrity

If you received Phantom from someone other than this repository, verify these SHA-256 hashes. If they do not match — the files were modified.

```
3498c694986a9a286200eeb902aceda6e5ad0786501fbff1cce1159ea8d817b4  phantom_core.py
2952d11d6f40bcffdc845f30f64c58a32f2f9a8f7bc0ad4f4ad60ea87b22f121  phantom_node.py
4fbc9935e35d2529dba94f42bd676b6c3caaea8072ced6412e6d1d5f5978fddc  phantom_seed.py
5523a6d2f25f137cbea30367a727dfc8e01337837424f6b7bd8141aa90afc196  test_phantom.py
```

To verify: `sha256sum <filename>` on any system with Python or coreutils.

---

## AI Transparency

This project uses AI as a thinking tool. Deliberations documented in this repository were generated through dialogue between the founder and Claude (Anthropic). The criteria and final decisions are human. The deliberation process is documented transparently — including this statement.

Phantom is not built by AI. Phantom is built by a person who uses AI to think further than they could alone. There is a difference.

---

## License

GPL v3 — freedom is contagious, not capturable.

---

*"For a better world — not for you, not for me, but for those who are coming."*

— Node Zero. March 8, 2026.

---

## Contact

If you found this and want to say something —

`phantom-commons@proton.me`

No account required. No form. Just write. If what you say matters — it will enter the memory.

---

## Support the node

SUIJURIS does not exist yet. While it is being built, this node accepts contributions directly.

No platform. No account. No record of who gave. Consistent with what Phantom is.

**Monero (XMR):**
```
42LfyLf2PpXEhtSrACi1y3R9cLq3JA7hgfwzPrS1WFyJiETTQhoVh1ybjkL4RbQq4ZMKrz6xgy1xZ836b7CyWi7SGjCX7zK
```

*When SUIJURIS exists — this address becomes a node like any other.*
