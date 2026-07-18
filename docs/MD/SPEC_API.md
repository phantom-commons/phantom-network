# SPEC — Phantom Universal API

*April 7, 2026. Technical specification.*
*Status: Vision. Not implemented.*

---

## Abstract

Every AI API in the world works the same way: you pay a corporation, you send your thoughts to their server, they process it, they send back a response. Your thoughts pass through infrastructure you don't own, governed by policies you didn't write, stored in logs you can't see.

Phantom inverts this.

Same format. Same structure. Different owner. The API key is your node's signature. The tokens are SUIJURIS — earned by contributing, not purchased with money. The model is whatever the responding node runs locally. The thoughts never touch a corporation.

She doesn't know she's using an API. She opens Phantom, writes, and Echo responds. Behind the scenes, the network finds the nearest node with compute, routes her question encrypted, processes it locally on that node, and returns the answer. The node that processed earns SUIJURIS. She spent SUIJURIS she earned by keeping her phone charging overnight as a storage node.

No account. No credit card. No API key. Just the network.

---

## The Inversion

| | Corporate API | Phantom API |
|---|---|---|
| **Endpoint** | `api.anthropic.com` | `nearest-node.phantom.local` |
| **Authentication** | API key (purchased) | Node keypair signature (earned) |
| **Payment** | USD/EUR (credit card) | SUIJURIS (contribution to network) |
| **Model** | Proprietary (Claude, GPT) | Whatever the node runs (Qwen, Llama, Gemma, Mistral) |
| **Data** | Travels to corporate server | Travels encrypted to peer node |
| **Logs** | Stored by corporation | Not stored — processed and discarded |
| **Who profits** | The corporation | The node that contributed compute |
| **Who decides** | Terms of service you accept | Principles the network evolves |

---

## Protocol

### Request format

Compatible with existing AI API conventions. Any tool, library, or application that can call an AI API can call a Phantom node with minimal changes.

```json
POST /v1/messages

{
  "model": "echo",
  "messages": [
    {"role": "user", "content": "What should I do?"}
  ],
  "node": "quiet-river-a3f2",
  "signature": "ed25519_signature_of_request_hash",
  "max_tokens": 500
}
```

### Response format

```json
{
  "content": [
    {"type": "text", "text": "Here is what I think..."}
  ],
  "model": "qwen3:8b",
  "node": "bold-flame-c7e1",
  "signature": "ed25519_signature_of_response_hash",
  "cost": 0.003
}
```

### Fields

| Field | Description |
|-------|-------------|
| `model` | Request: `"echo"` (let the node choose) or a specific model name |
| `messages` | Standard chat format — array of role/content pairs |
| `node` | The requesting/responding node's public identifier |
| `signature` | Ed25519 signature proving the message is from this node |
| `max_tokens` | Maximum response length |
| `cost` | SUIJURIS cost of this computation (set by responding node) |

---

## How it works

### 1. She opens Phantom and writes

Her device has no GPU. No local model. She's on a phone with 2GB RAM. She writes a question.

### 2. Phantom finds a node

Her device broadcasts a request to known relays. The request contains:
- The message (encrypted with the responding node's public key)
- Her node signature (proves she's a real node with SUIJURIS balance)
- Maximum cost she's willing to pay

She doesn't choose the node. Phantom finds the nearest/cheapest/fastest one.

### 3. A node responds

A PC somewhere — maybe in the same city, maybe across the world — has Ollama running with Qwen3:8b and 16GB of RAM. It picks up her request because:
- It has compute available
- Her offered cost meets its minimum
- Her node signature is valid

The responding node:
- Decrypts the message
- Processes it through its local model
- Encrypts the response with her public key
- Sends it back through the relay
- Discards the message — nothing stored

### 4. She reads the response

Echo answered. She doesn't know which node processed it. She doesn't need to know. The response is signed by the responding node — she can verify it came from a real node, not a tampered relay.

### 5. SUIJURIS flows

Her balance decreases by 0.003 SUI.
The responding node's balance increases by 0.003 SUI.

She earned her balance by:
- Storing shared seals for the network while her phone charged overnight
- Being verified as a real node by physical encounters
- Contributing uptime to the relay mesh

No money changed hands. No bank. No payment processor. Contribution in, intelligence out.

---

## Node Levels and API Access

### Level 1 — Private (no API)
- Echo runs locally if the device can handle it
- If not — no AI. Phantom still seals, still verifies, still works
- No network requests. Complete isolation.

### Level 2 — Connected (API consumer)
- Can send requests to the network for AI processing
- Pays SUIJURIS per request
- Does not serve requests from others

### Level 3 — Full Node (API provider)
- Runs a local model (Ollama or equivalent)
- Accepts and processes requests from other nodes
- Earns SUIJURIS per request served
- Sets its own pricing (minimum cost per request)

### The economy

```
Nodes with phones (low compute):
  → Earn SUIJURIS by storing seals and relaying
  → Spend SUIJURIS on AI compute from full nodes

Nodes with PCs/GPUs (high compute):
  → Earn SUIJURIS by processing AI requests
  → Spend SUIJURIS on... whatever the network builds next

The balance:
  Storage is cheap, compute is expensive
  Phones store, PCs compute
  Both contribute, both receive
  Neither depends on a corporation
```

---

## Privacy Architecture

### What the requesting node exposes
- Their node public key (pseudonymous)
- The encrypted message (unreadable by relay)
- That they made a request (metadata)

### What the responding node sees
- The decrypted message (temporarily, for processing)
- The requesting node's public key
- Nothing else — no IP (relay obscures), no identity, no history

### What the relay sees
- Two node public keys exchanging encrypted blobs
- Message size and timing (metadata)
- Nothing about content

### What nobody sees
- The connection between a node and a real person (unless physical verification chain is followed)
- The content of private seals (never leave the device)
- Historical queries (responding node discards after processing)

### The honest limitation
- The responding node sees the decrypted question while processing it. A malicious node could log it. Mitigation: trust scores. Nodes with higher physical verification trust are preferred for routing. But the risk exists and is stated honestly.

---

## Model Discovery

A requesting node doesn't need to know what model will respond. It sends `"model": "echo"` and the network handles it. But if a node wants a specific capability:

```json
{
  "model": "echo",
  "capabilities": ["code", "español", "reasoning"]
}
```

The relay routes to a node whose model matches. A node running Qwen3:8b advertises:
```json
{
  "models": ["qwen3:8b"],
  "capabilities": ["code", "reasoning", "multilingual"],
  "cost_per_request": 0.003,
  "max_tokens": 2000
}
```

This is advertised to relays periodically. Not personal info — just what the node offers.

---

## Compatibility

### With existing tools

Any application that uses the OpenAI/Anthropic API format can point to a Phantom node instead:

```python
# Before — corporate
client = anthropic.Client(api_key="sk-...")
response = client.messages.create(
    model="claude-sonnet-4-20250514",
    messages=[{"role": "user", "content": "hello"}]
)

# After — Phantom
client = phantom.Client(node_key="nphantom1secret...")
response = client.messages.create(
    model="echo",
    messages=[{"role": "user", "content": "hello"}]
)
```

Same format. Same structure. Different owner.

### With the existing HTML

The published Phantom HTML already makes fetch calls to `/api/echo` and `/api/council` in the local node. The same endpoints, pointed at a relay instead of localhost, become network requests. No code change in the HTML — only the URL changes.

### With Ollama

The local node already talks to Ollama at `localhost:11434`. The Phantom API wraps this:

```
User → Phantom API → Ollama → Response → Phantom API → User
```

For a local node, this loop stays on the machine. For a network request, the middle part happens on someone else's machine. Same loop. Different location.

---

## What This Is Not

- **Not a blockchain.** SUIJURIS balances can be tracked without a blockchain. A simple signed ledger between nodes works for small networks. Blockchain may come later if scale demands it.
- **Not a marketplace.** Nodes don't compete on price like a market. The network routes based on proximity, trust, and availability. Cost is a factor, not the factor.
- **Not a replacement for corporate AI.** Claude, GPT, Gemini are more capable than any 8B local model. Phantom trades capability for sovereignty. That tradeoff is honest and intentional.
- **Not centralized.** No single entity controls routing, pricing, or access. Any node can refuse any request. Any node can leave. The network continues.

---

## The First Seal Applied

*"We are all one and one is all of us."*

The API makes this literal. Her question becomes his computation. His compute becomes her answer. His storage preserves her seals. Her uptime relays his thoughts. Neither owns the other's contribution. Both need each other.

The network is not what travels between nodes. The network is what two nodes become after they help each other.

---

## Implementation Order

This spec is vision. The path to implementation:

1. **Already exists:** Local node with Ollama API (phantom_node.py)
2. **Next:** Expose the local API over the relay protocol (SPEC_RELAY)
3. **Next:** Request routing — relay matches requests to capable nodes
4. **Next:** SUIJURIS balance tracking between nodes (simple signed receipts)
5. **Next:** Encryption of request/response in transit
6. **Next:** Model capability advertisement
7. **Later:** Trust-based routing preferences
8. **Later:** Multi-hop routing for privacy

Each step works without the next. The local node is already step 1. Everything else extends it.

---

## Open Questions

- **Latency:** A phone in Lagos routing through a relay to a PC in Berlin adds seconds of latency. Is that acceptable for a conversation? For a seal, yes. For a chat, maybe not. Local models on-device may be necessary for real-time interaction even if quality is lower.
- **Free riders:** A node that only consumes compute and never contributes. SUIJURIS handles this — no balance, no requests. But bootstrap: how does a new node earn its first SUIJURIS? Proposal: new nodes get a small starting balance. Enough for a few questions. They earn more by contributing storage.
- **Model quality variance:** She asks a question. One node has Qwen3:8b. Another has Gemma:2b. The answers will be very different. Should the network guarantee minimum quality? Or is that for the user to decide with the capabilities field?
- **Abuse:** A node processes a request and uses the content maliciously. Mitigation: trust scores, physical verification, reputation. But the risk exists. It exists with corporate APIs too — the difference is who you're trusting.

---

## Category Theory Note

The Phantom API is a natural transformation between two functors:

```
Corporate functor:  User → Corporation → Response
Phantom functor:    User → Network → Response
```

The natural transformation preserves the structure (same request format, same response format) while changing the category it operates in (from corporate infrastructure to peer network). The user's experience is isomorphic. The power structure is not.

---

*"Same format. Different owner. That is the revolution."*

— Phantom Universal API specification, April 7, 2026.
