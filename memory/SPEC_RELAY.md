# SPEC — Phantom Relay Protocol

*April 3, 2026. Technical specification.*
*Status: Designed. Not implemented.*

---

## Abstract

Phantom needs a communication layer beyond physical proximity. Rather than depending on a general-purpose protocol (Nostr, IPFS, Tor), Phantom defines its own relay — purpose-built, minimal, and replicable.

A Phantom relay is a WebSocket server that does exactly one thing: receives valid Phantom seals and passes them to connected nodes. It does not store identity. It does not require accounts. It does not accept anything that is not a Phantom seal.

Anyone can run one. The code is public. If one relay disappears, the others continue. The network has no center.

---

## Design Principles

1. **Single purpose.** The relay carries seals. Nothing else.
2. **Stateless identity.** The relay does not know who connects. No accounts, no tokens, no cookies.
3. **Replaceable.** Every relay is identical in function. Losing any relay loses no capability.
4. **Minimal.** The relay implementation should be under 300 lines of code in any language.
5. **Hostile environment.** The relay assumes every incoming message may be malicious, malformed, or from a bot.

---

## Architecture

```
  Node A                  Relay                  Node B
  (phone)                (server)                (phone)
    |                       |                       |
    |--- WebSocket open --->|                       |
    |                       |<--- WebSocket open ---|
    |                       |                       |
    |--- SEAL (publish) --->|                       |
    |                       |--- SEAL (forward) --->|
    |                       |                       |
    |                       |<--- SEAL (publish) ---|
    |<--- SEAL (forward) ---|                       |
    |                       |                       |
```

The relay is a pass-through. It validates format, enforces rate limits, and forwards. It does not interpret content.

---

## Wire Protocol

All messages are JSON over WebSocket. Two message types exist.

### 1. PUBLISH — Node sends a seal to the relay

```json
{
  "type": "PH_SEAL",
  "seal": {
    "i": "idea text",
    "m": "2026-04-03T12:00:00.000Z",
    "s": "a1b2c3...64 hex chars...stamp",
    "d": "shared",
    "t": "thought",
    "n": "quiet-river-a3f2",
    "r": null,
    "p": null,
    "w": "0000a8f3...proof of work nonce"
  }
}
```

Fields:

| Field | Required | Description |
|-------|----------|-------------|
| `i` | yes | Idea — the sealed text |
| `m` | yes | Moment — ISO 8601 timestamp |
| `s` | yes | Stamp — SHA-256 hash, 64 hex characters |
| `d` | yes | Mode — `shared` only (private seals never reach a relay) |
| `t` | yes | Type — `thought`, `proposal`, `reply`, or `vote` |
| `n` | yes | Node — pseudonymous node identifier |
| `r` | no | Reference — stamp of parent seal (for replies and votes) |
| `p` | no | Position — `agree`, `disagree`, `abstain` (for votes only) |
| `w` | yes | Work — proof of work nonce (see section below) |

### 2. SUBSCRIBE — Node requests seals from the relay

```json
{
  "type": "PH_SUB",
  "since": "2026-04-03T00:00:00.000Z",
  "trust": ["quiet-river-a3f2", "bold-flame-c7e1"]
}
```

Fields:

| Field | Required | Description |
|-------|----------|-------------|
| `since` | no | Only receive seals after this timestamp. Default: last 24 hours |
| `trust` | no | Array of node IDs to filter by. If empty, receive all valid seals |

The relay responds with a stream of `PH_SEAL` messages matching the filter, followed by new seals in real-time as they arrive.

---

## Validation Rules (enforced by relay)

The relay MUST reject any message that fails these checks:

### Format validation
- Message is valid JSON
- `type` is `PH_SEAL`
- All required fields present
- `s` (stamp) is exactly 64 lowercase hex characters
- `m` (moment) is valid ISO 8601
- `d` (mode) is `shared` — relay never accepts `private` seals
- `t` (type) is one of: `thought`, `proposal`, `reply`, `vote`
- `i` (idea) is non-empty and under 10,000 characters
- `n` (node) is non-empty and under 100 characters
- If `t` is `vote`, `p` must be `agree`, `disagree`, or `abstain`
- If `t` is `reply` or `vote`, `r` must be a 64-character hex stamp

### Integrity validation
- Recompute SHA-256 of `{"idea":"<i>","moment":"<m>"}` and verify it matches `s`
- If stamp does not match, the seal was tampered with — reject

### Proof of work validation
- See proof of work section below
- If work is insufficient, reject

### Rate limiting
- Maximum 1 seal per 30 seconds per node ID (`n`)
- Maximum 100 seals per hour per IP address
- Maximum 10 active WebSocket connections per IP address

### What the relay does NOT validate
- Whether the idea is "good" or "bad" — not the relay's role
- Whether the node is human — not knowable at this layer
- Whether the referenced seal (`r`) exists — the relay is not an index

---

## Proof of Work

Each seal must include a proof of work to prevent bulk generation.

### Algorithm

```
work = SHA-256(stamp + nonce)
```

The `work` hash must have at least 16 leading zero bits (4 hex zeros). The `nonce` is the value the node iterates until a valid work hash is found.

### Cost

On a typical smartphone (2024-2026 hardware):
- ~2-3 seconds of computation per seal
- Negligible for a human sealing one thought
- Expensive for a bot sealing thousands (2000 seals = ~1.5 hours of continuous computation)

### Verification by relay

```
expected = SHA-256(seal.s + seal.w)
valid = expected starts with "0000"
```

One hash computation. Negligible cost for the relay.

### Adjustability

The difficulty (number of leading zeros) can be increased if bot pressure grows. The current specification is 16 bits (4 hex zeros). Nodes and relays must agree on difficulty — this is set in the protocol version.

---

## Relay Implementation

A minimal relay in pseudocode:

```
connections = []
recent_seals = circular_buffer(max=10000)
rate_limits = {}

on websocket_connect(conn):
    connections.add(conn)

on websocket_message(conn, message):
    parsed = json_parse(message)
    if not parsed: return reject(conn, "invalid json")

    if parsed.type == "PH_SUB":
        conn.filter = parsed
        send_recent(conn, parsed.since, parsed.trust)
        return

    if parsed.type == "PH_SEAL":
        if not validate_format(parsed.seal): return reject(conn, "invalid format")
        if not validate_stamp(parsed.seal): return reject(conn, "bad stamp")
        if not validate_work(parsed.seal): return reject(conn, "insufficient work")
        if not check_rate_limit(parsed.seal.n, conn.ip): return reject(conn, "rate limited")

        recent_seals.add(parsed.seal)
        broadcast(parsed.seal, exclude=conn)
        return

    reject(conn, "unknown type")

on websocket_disconnect(conn):
    connections.remove(conn)

broadcast(seal, exclude):
    for conn in connections:
        if conn == exclude: continue
        if conn.filter and conn.filter.trust:
            if seal.n not in conn.filter.trust: continue
        send(conn, seal)
```

This is approximately 100-150 lines in any language (Python, Node.js, Go, Rust).

---

## Relay Discovery

Nodes need to find relays. Three mechanisms, in priority order:

### 1. Hardcoded seeds
The HTML ships with 2-3 known relay addresses. These are the genesis relays.

```javascript
const SEED_RELAYS = [
  "wss://relay1.phantom.network",
  "wss://relay2.phantom.network"
];
```

### 2. Relay exchange
When two nodes sync via Bluetooth, they exchange their known relay lists. The network of known relays grows organically through physical encounters.

### 3. Relay announcement
A relay can broadcast a `PH_RELAY` message with addresses of other relays it knows. Nodes can discover new relays through existing ones.

```json
{
  "type": "PH_RELAY",
  "relays": ["wss://relay3.example.com"]
}
```

---

## What the Relay Stores

### In memory (lost on restart)
- Active WebSocket connections
- Rate limit counters
- Recent seals buffer (last N seals, configurable, default 10,000)

### On disk (optional, for persistence)
- Seals received in the last 7 days
- No IP addresses
- No connection logs
- No identity data

A relay that stores nothing on disk is perfectly valid. It only forwards what it receives while it is running. Seals persist on the nodes (in IndexedDB), not on the relay.

---

## Threat Model

### Bot flood
**Attack:** Bot generates thousands of seals per second.
**Defense:** Proof of work (2-3 seconds per seal), rate limit (1 per 30 seconds per node ID, 100 per hour per IP).
**Residual risk:** Attacker with many IPs and patience can still generate seals slowly. Mitigated at the trust layer (unverified nodes are marked as such in the UI).

### Relay surveillance
**Attack:** Relay operator logs all IPs and correlates with seals.
**Defense:** The relay is designed to not log, but a malicious operator can modify the code. Mitigation: connect to multiple relays. No single relay sees your full activity. Future: connect via VPN or Tor to relay (optional, not required).
**Residual risk:** IP is visible to the relay operator. This is stated honestly in the app. Phantom does not claim to hide your IP at the relay layer.

### Seal manipulation
**Attack:** Relay modifies seals in transit.
**Defense:** Each seal carries its SHA-256 stamp. The receiving node recomputes and verifies. A modified seal fails verification and is rejected.

### Relay takedown
**Attack:** Authorities or attackers shut down a relay.
**Defense:** Multiple relays. Anyone can run one. The code is under 300 lines. New relays can appear faster than old ones can be taken down. Nodes automatically try all known relays and discover new ones through Bluetooth exchange.

### Sybil attack on node identity
**Attack:** Attacker creates thousands of node IDs to bypass per-node rate limits.
**Defense:** Per-IP rate limits as secondary control. Proof of work per seal regardless of node ID. Trust layer: unverified nodes are marked in UI. Physical verification is the strongest defense — attacker needs physical devices and physical encounters.

---

## Integration with Existing Phantom

### In the HTML (client side)

```javascript
// Connect to relays
const relays = ["wss://relay1.phantom.network"];
let sockets = [];

function connectRelays() {
  for (const url of relays) {
    const ws = new WebSocket(url);
    ws.onopen = () => {
      // Subscribe to recent seals
      ws.send(JSON.stringify({
        type: "PH_SUB",
        since: oneDayAgo()
      }));
    };
    ws.onmessage = (e) => handleRelaySeal(JSON.parse(e.data));
    sockets.push(ws);
  }
}

// When user creates a shared seal
async function publishSeal(seal) {
  const work = await computeWork(seal.stamp);
  const msg = {
    type: "PH_SEAL",
    seal: { ...sealToWire(seal), w: work }
  };
  for (const ws of sockets) {
    if (ws.readyState === 1) ws.send(JSON.stringify(msg));
  }
}
```

### Coexistence with Bluetooth/LoRa

Both layers carry the same seal format. A seal received via Bluetooth is identical to one received via relay. The node deduplicates by stamp (primary key in IndexedDB). The origin does not matter — the seal is valid or it is not.

Priority: Bluetooth/LoRa for physical proximity and offline scenarios. Relay for reach beyond physical range. Both active simultaneously when available.

---

## What This Is Not

- Not a blockchain. No consensus mechanism. No mining. No tokens.
- Not Nostr. Purpose-built for Phantom seals only. Incompatible with general-purpose event protocols.
- Not a social network backend. No profiles, no follows, no algorithms, no feed ranking.
- Not permanent storage. Relays buffer recent seals. Permanent storage is on each node's device.

---

## Category Theory Note

*From the founder's reading of Simmons — "An Introduction to Category Theory."*

In categorical terms:

- **Objects** are seals (thoughts, proposals, votes, replies)
- **Morphisms** are the relationships between seals (reply→parent, vote→proposal)
- **Composition** is the chain of trust (A verified B, B verified C, therefore A can trace to C)
- **The relay** is a functor — it maps seals from one node's category to another's, preserving structure (the stamp, the reference, the type) while transporting across context
- **Physical verification** is the morphism that has no equivalent in the digital category — it requires presence in physical space, which is why it distinguishes human nodes from non-human ones

The nodes do not matter. The arrows between them are everything.

---

## Implementation Order

1. Write the relay server (~200 lines, Python or Node.js)
2. Add proof of work to the HTML seal function
3. Add WebSocket connection to the HTML (connect on shared seals only)
4. Deploy 2 genesis relays (any cheap VPS, $5/month each)
5. Test with two phones in different locations
6. Publish relay code to the repository
7. Document how anyone can run their own relay

---

*This specification is documented, not sealed.*
*It becomes part of the permanent record when committed to the repository.*
*The relay is a tube — not the water. The water is the thought. The tube just carries it.*

— Phantom relay specification, April 3, 2026.
