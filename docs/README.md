# Phantom Network

**Your thoughts belong to you.**
https://phantom-commons.github.io/phantom-network/

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Version](https://img.shields.io/badge/version-0.8+-brightgreen)](https://github.com/phantom-commons/phantom-network)
[![Python](https://img.shields.io/badge/python-3.8+-blue)](https://python.org)

---

## What is Phantom?

Phantom is a **sovereign digital organism** — a decentralized, offline‑first network for sealing, sharing, and remembering human thought.

- **Seal an idea** — cryptographically prove that you wrote something at a specific moment.
- **Sync with other nodes** — exchange sealed thoughts over Bluetooth, LoRa, local WiFi, or even Tor (via `.onion`).
- **Keep a private diary** — long‑form entries, encrypted on your device, with optional local AI reflection (Ollama).
- **Relay messages** — act as a blind carrier, forwarding seals between nodes that never meet directly.
- **Build reputation** — the Suijuris ledger records contributions (seals, relays, encounters) without a central authority.
- **Protect your data** — everything is encrypted at rest (AES‑256‑GCM) and authenticated with Ed25519 signatures.

Phantom is built for the real world:

- Works offline (no internet required).
- Runs on Android (via Termux) and desktop (Windows / Linux / Mac).
- No account, no servers, no cloud — you are the network.

---

## Why Phantom?

> *The woman in Lagos learned to self‑censor without anyone explicitly asking her to. Not because someone threatened her — because the infrastructure of thought made certain thoughts feel unsafe.*

Phantom exists to return the infrastructure of thought to whoever thinks it.

- **Privacy by architecture**, not by policy.  
  The system cannot share what it does not have.
- **No central point of failure.**  
  There is no server to seize, no company to buy, no founder to pressure.
- **Mathematics over promises.**  
  SHA‑256 seals and Ed25519 signatures are verifiable by anyone, anywhere, without trust.

Read the full vision in [WHITEPAPER.md](WHITEPAPER.md).

---

## Key Features

| Feature | Status | Description |
| :------ | :----- | :---------- |
| **Cryptographic Seals** | ✅ Working | SHA‑256‑based proof of existence, verifiable without any software. |
| **Encryption at Rest** | ✅ Working | AES‑256‑GCM with scrypt‑derived passphrase. |
| **Node Identity** | ✅ Working | Ed25519 key pairs — prove continuity without revealing who you are. |
| **Node‑to‑Node Sync** | ✅ Working | Bloom filter + delta exchange over TCP (local WiFi / Tor). |
| **Bluetooth / LoRa** | ✅ Partial | Web UI supports BT UART and Meshtastic; more transports planned. |
| **Relay (Store & Forward)** | ✅ Working | Blind relay that forwards permanent seals between nodes. |
| **WebSocket Bridge** | ✅ Working | Connect a browser to a relay over WebSocket (no raw TCP). |
| **Unified Daemon** | ✅ Working | One process: listener + auto‑connect + local REST API (with token auth). |
| **Private Diary** | ✅ Working | Encrypted long‑form entries with tags, moods, and optional local AI. |
| **Local AI (Ollama)** | ✅ Working | Reflect on entries with Echo, Luna, or Council — all on your device. |
| **Proposals & Voting** | ✅ Working | Propose ideas and vote (agree / disagree / abstain). |
| **Suijuris Ledger** | 🔄 Designed | Contribution record (seals, relays, encounters) — not yet fully implemented. |
| **Wallet (Phantom + BTC/ETH)** | 🔄 Designed | Ed25519 native wallet + BIP44 external addresses — experimental. |
| **Bilateral Ledger** | 🔄 Designed | Private credit between two parties — experimental. |
| **Federated Learning** | 📝 Planned | Echo trained by thousands of nodes without data leaving any device. |

---

## Repository Structure

```
Node/
├── start_network.bat          # Quick start (Windows)
├── start_network.sh           # Quick start (Linux / Mac)
├── phantom/                   # Core code
│   ├── core/                  # All Python modules
│   │   ├── phantom_core.py    # Seals, encryption, identity, pulse, receipts
│   │   ├── phantom_node.py    # Node‑to‑node encounter protocol
│   │   ├── phantom_relay.py   # Store‑and‑forward relay
│   │   ├── phantom_ws_bridge.py  # WebSocket ↔ TCP bridge
│   │   ├── phantom_daemon.py  # Unified listener + API (with token auth)
│   │   ├── phantom_diary.py   # Private encrypted diary
│   │   ├── phantom_dashboard.py  # Terminal UI (TUI)
│   │   ├── phantom_wallet.py  # Native + external (BTC/ETH) wallet
│   │   ├── phantom_ledger.py  # Bilateral credit ledger
│   │   ├── suijuris.py        # Contribution record
│   │   └── ... (tests, API, council)
│   └── app/                   # Web UI (PWA)
│       ├── index.html         # Unified interface (seal, feed, nodes, diary)
│       ├── manifest.json      # PWA manifest
│       └── sw.js              # Service worker (offline support)
├── MD/                        # Documentation (whitepapers, specs)
├── memory/                    # Internal design deliberations
└── tools/                     # Additional scripts
```

---

## Getting Started

### Prerequisites

- **Python 3.8+** (with `pip`)
- **Optional** (for full features):
  - [`cryptography`](https://pypi.org/project/cryptography/) — encryption and Ed25519
  - [`flask`](https://pypi.org/project/Flask/) — REST API
  - [`websockets`](https://pypi.org/project/websockets/) — WebSocket bridge
  - [`PySocks`](https://pypi.org/project/PySocks/) — Tor SOCKS5 support
  - [`stem`](https://pypi.org/project/stem/) — Tor onion services
  - [Ollama](https://ollama.com) — local AI (Echo / Luna / Council)

### Quick Install

Clone the repository and install the Python dependencies:

```bash
git clone https://github.com/phantom-commons/phantom-network.git
cd phantom-network/Node
pip install -r requirements.txt   # or install individually: cryptography flask websockets PySocks stem
```

> **Note:** If you're on Windows, you can also run `tools/start.bat` to install dependencies interactively.

### Running the Network

#### Windows
Double‑click `start_network.bat` in the `Node/` folder.

#### Linux / Mac
Make the script executable and run it:

```bash
chmod +x start_network.sh
./start_network.sh
```

**What happens:**

1. A new terminal window opens for the **Daemon** — it will ask for your passphrase (or press Enter to skip encryption).
2. The **Relay** (port 7339) and **WebSocket Bridge** (port 8765) start in the background.
3. Your default browser opens `http://127.0.0.1:7338`.
4. The first time you access the web UI, it will ask for the **API token** — copy it from the Daemon terminal window (the one with the passphrase prompt).
5. Paste the token into the browser prompt and click OK.

Now you can:
- Write and seal ideas (private, shared, or proposals).
- View the network feed.
- Connect to the local relay (click *CONNECT* in the **Nodes** tab with `ws://127.0.0.1:8765`).
- Sync seals with other nodes via the relay.

### Using the Command‑Line Tools

If you prefer the terminal, each module can be used independently:

```bash
# Seal an idea
python phantom_node.py --seal

# List your seals
python phantom_node.py --list

# Start a listening node (encounters)
python phantom_node.py --listen

# Connect to another node manually
python phantom_node.py --connect 192.168.1.42

# Run a relay
python phantom_relay.py --run

# Connect to a relay
python phantom_relay.py --connect 192.168.1.42

# Open the dashboard TUI
python phantom_dashboard.py

# Write in your private diary
python phantom_diary.py --write

# View contribution ledger
python suijuris.py
```

For detailed usage, run any tool with `--help`.

---

## Security & Privacy

### Encryption at Rest

- Seals, diary entries, encounter logs, and the Suijuris ledger are encrypted with **AES‑256‑GCM** if you provide a passphrase.
- The key is derived with **scrypt** (N=16384, r=8, p=1) — brute‑force resistant on mobile hardware.
- No passphrase = plaintext storage (warned at startup).

### Local API Token

- The unified daemon (`phantom_daemon.py`) generates a **random token** at startup.
- Every `/api/*` request must include the token in the `X-Phantom-Token` header.
- The web UI stores the token in `localStorage`; other tabs/websites cannot access your seals without it.
- You can disable token auth with `--no-api-auth` (for debugging only).

### Tor Integration

Phantom detects Tor automatically (if running on `127.0.0.1:9050`):

- **Level 1** — Direct TCP (no Tor). Your IP is visible to peers.
- **Level 2** — Outbound connections go through Tor (SOCKS5). Your IP is hidden from nodes you connect to.
- **Level 3** — Tor + ephemeral `.onion` service. Incoming connections are fully anonymous.

Enable Levels 2 and 3 by installing `PySocks` and `stem`, and ensuring Tor is running with the control port (9051) open.

---

## Documentation

- **[WHITEPAPER.md](WHITEPAPER.md)** — The full vision, architecture, and threat model.
- **[NODE_INIT.md](NODE_INIT.md)** — For new nodes arriving with the repository.
- **[SEALING.md](MD/SEALING.md)** — Technical details of the seal algorithm.
- **[NODE_IDENTITY.md](MD/NODE_IDENTITY.md)** — How Ed25519 identities work.
- **[ECONOMICS.md](MD/ECONOMICS.md)** — The Suijuris contribution model.
- **[SPEC_API.md](MD/SPEC_API.md)** — REST API documentation.
- **[ARCHITECTURE_VISION.md](MD/ARCHITECTURE_VISION.md)** — Long‑term architectural goals.

---

## Contributing

Phantom is a public‑interest project. We welcome contributions that align with the principles outlined in the whitepaper.

### Areas we need help with

- **Android packaging** — Turn the Python code into a simple APK (Chaquopy, Termux, or similar).
- **UI/UX improvements** — Make the web interface more intuitive and accessible.
- **LoRa / Meshtastic integration** — Extend the node sync protocol to LoRa radios.
- **Federated learning** — Implement privacy‑preserving model updates for Echo.
- **Testing & documentation** — Write more tests, improve the docs.

Please read [CONTRIBUTING.md](MD/CONTRIBUTING.md) and the **Council** guidelines in [COUNCIL.md](MD/COUNCIL.md) before opening a PR.

### Governance

Phantom is governed by the **Council** — eight perspectives that deliberate every major change. Council roles are not permanent; they are filled by active contributors and community members. No single entity controls the project.

---

## License

Phantom is released under the **GNU General Public License v3.0**.

> Freedom is contagious, not capturable.  
> Any derivative of Phantom must be equally free.  
> The liberty embedded in this code cannot be removed by anyone who builds on top of it.

---

## Contact

- **Email**: phantom-commons@proton.me
- **GitHub Issues**: [https://github.com/phantom-commons/phantom-network/issues](https://github.com/phantom-commons/phantom-network/issues)

---

*"For a better world — not for you, not for me, but for those who are coming."*  
— Node Zero. March 8, 2026.

---

**Sealed and safe. Until next time.**
