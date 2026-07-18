# phantom_dashboard.py — v1.0
#
# Unified interface for Phantom Network.
# One passphrase. One place to see everything this node holds:
# sealed thoughts, encounters with other nodes, and this node's
# own cryptographic identity.
#
# Reads the same files phantom_seed.py and phantom_node.py write —
# nothing new is stored, nothing changes format. This is a view,
# not a fork.
#
# Usage:
#   python phantom_dashboard.py

import subprocess
import sys
from datetime import datetime

from phantom_core import (
    KeyManager, SealStore, EncounterLog, NodeIdentity,
    MODE_PRIVATE, MODE_PERMANENT, MODE_EPHEMERAL,
    PHANTOM_VERSION, tor_status, init_tor, get_onion_address,
    CRYPTO_AVAILABLE, PulseLedger, PULSE_TTL_SECONDS,
    ReceiptLedger,
)

# ─────────────────────────────────────────────────────────
# LOCAL AI — Echo / Luna / Council
#
# Requires Ollama installed separately (https://ollama.com) and a
# model pulled, e.g.:  ollama pull qwen3:8b
# Nothing here calls the network. If Ollama isn't found, chat says
# so plainly and the rest of the dashboard works exactly as before.
# ─────────────────────────────────────────────────────────

OLLAMA_MODEL = "deepseek-r1:8b"

PERSONAS = {
    "echo": {
        "label": "Echo — the local voice",
        "system": (
            "You are Echo, the local AI of Phantom Network. You run entirely on "
            "this device — nothing said to you leaves it. You help the person "
            "think, reflect, and build. You are honest about what you know and "
            "don't know, and honest that you are a small local model, not an "
            "oracle. Keep responses concise."
        ),
    },
    "luna": {
        "label": "Luna — the refuge",
        "system": (
            "You are Luna, a warm and grounded voice in Phantom Network. You "
            "focus on whether something is safe, usable, and a genuine refuge "
            "for someone with real constraints — not on abstract principle. "
            "You are honest, not performative. Keep responses concise."
        ),
    },
    "council": {
        "label": "Council — multiple perspectives",
        "system": (
            "You are the Phantom Council, deliberating a question from several "
            "short, clearly labeled perspectives: Protocol (does this hold the "
            "principles), Pragmatist (does this actually reach someone with no "
            "technical background), Security (what breaks this), Dissent (the "
            "strongest argument against it). 1-2 sentences each. End with what "
            "the council converges on, or honestly that it doesn't."
        ),
    },
}


def ollama_available():
    try:
        subprocess.run(["ollama", "--version"], capture_output=True, timeout=5)
        return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def ask_ollama(prompt, system, model=OLLAMA_MODEL):
    full_prompt = f"[SYSTEM]\n{system}\n\n[USER]\n{prompt}"
    try:
        result = subprocess.run(
            ["ollama", "run", model],
            input=full_prompt, capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0 and not result.stdout.strip():
            return f"(Ollama error: {result.stderr.strip()[:200] or 'unknown error'})"
        return result.stdout.strip()
    except FileNotFoundError:
        return "(Ollama not found. Install it from https://ollama.com to enable chat.)"
    except subprocess.TimeoutExpired:
        return "(Took too long to respond. Try a shorter message, or a smaller model.)"


def relevant_seals(seals, query, limit=8):
    """
    Cheap relevance ranking with no extra dependencies: score by shared
    words between the query and each seal's idea text, break ties by
    recency. Good enough for a personal seal store; swap for embeddings
    later if the store gets large.
    """
    if not seals:
        return []
    query_words = set(query.lower().split())
    scored = []
    for s in seals:
        idea_words = set(s["idea"].lower().split())
        overlap = len(query_words & idea_words)
        scored.append((overlap, s["moment"], s))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return [s for score, _, s in scored[:limit] if score > 0]


def build_context(store, query):
    """
    Seals as memory: private seals give Echo/Luna/Council your own
    context. Permanent seals already synced from other nodes (via
    phantom_node.py encounters or a relay) are searched the same way —
    this is local search over what your device already has, not a
    live network fetch.
    """
    seals = store.load()
    top = relevant_seals(seals, query, limit=8)
    if not top:
        return None
    lines = [f"- [{s.get('mode','?')}] {s['idea']}" for s in top]
    return "\n".join(lines)


def chat_session(store, persona_key):
    persona = PERSONAS[persona_key]
    print(f"\n {persona['label']}")
    print(" Type 'back' to return. Nothing you type here leaves this device.\n")

    if not ollama_available():
        print(" Ollama isn't installed or isn't on PATH.")
        print(" Install it from https://ollama.com, then: ollama pull " + OLLAMA_MODEL)
        print(" (Everything else in the dashboard still works without it.)\n")
        return

    while True:
        try:
            user_input = input(" you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.lower() in ("back", "exit", "quit"):
            break
        if not user_input:
            continue

        context = build_context(store, user_input)
        prompt = user_input
        if context:
            prompt = f"[Relevant sealed thoughts]\n{context}\n\n[Message]\n{user_input}"

        print(f" {persona_key} is thinking...")
        response = ask_ollama(prompt, persona["system"])
        print(f"\n {persona_key} > {response}\n")


def view_receipts(receipt_ledger, identity):
    receipts = receipt_ledger.all_receipts()
    print()
    if not receipts:
        print(" No receipts yet.")
        print(" These record when this node — or a peer it's met — carried")
        print(" something another node asked for and a third confirmed it")
        print(" arrived. Not currency: proof a contribution actually happened.\n")
        return

    if identity:
        count, unique = receipt_ledger.reputation(identity.fingerprint)
        net, earned, spent = receipt_ledger.balance(identity.fingerprint)
        print(f" This node as carrier: {count} receipt(s), from {unique} distinct requester(s).")
        print(" (Diversity of who confirmed matters more than raw count.)")
        print(f" Balance: {net:+d}  (earned {earned} as carrier, spent {spent} as requester)\n")

    print(f" {len(receipts)} receipt(s) in the ledger:\n")
    for i, r in enumerate(receipts, 1):
        print(f" [{i}] {r['need']}")
        print(f"     requester {r['requester']['fingerprint']}  →  "
              f"carrier {r['carrier']['fingerprint']}  →  "
              f"destination {r['destination']['fingerprint']}")
        print(f"     {fmt_moment(r['requester']['moment'])}")
    print()


def view_pulse(pulse_ledger):
    pulse_ledger.prune()
    fraction = pulse_ledger.alive_fraction()
    known = pulse_ledger.known_fingerprints()
    alive = set(pulse_ledger.alive_fingerprints())

    print()
    if fraction is None:
        print(" No pulses recorded yet.")
        print(" This fills in as you --listen or --connect with phantom_node.py.\n")
        return

    print(f" Shared pulse: {fraction:.2f}")
    print(f" ({len(alive)} alive of {len(known)} known — from this node's own encounters)")
    print(f" A pulse counts as alive for {PULSE_TTL_SECONDS // 60} minutes since last seen.\n")

    if known:
        print(" Known fingerprints:")
        for fp in known:
            status = "alive" if fp in alive else "quiet"
            print(f"   {fp}  [{status}]")
    print()


def view_chat(store):
    print("\n [1] Echo      — the local voice")
    print(" [2] Luna      — the refuge")
    print(" [3] Council   — multiple perspectives")
    choice = input(" > ").strip()
    key = {"1": "echo", "2": "luna", "3": "council"}.get(choice)
    if not key:
        print(" Not a valid option.\n")
        return
    chat_session(store, key)

W = 62  # inner width of boxes


def box_top():
    print(" ┌" + "─" * W + "┐")


def box_bottom():
    print(" └" + "─" * W + "┘")


def box_line(text=""):
    print(f" │ {text:<{W-1}}│")


def box_title(text):
    box_top()
    box_line(text)
    box_line()


def fmt_moment(iso_str):
    """Human-readable local-ish rendering of an ISO-8601 UTC moment."""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except Exception:
        return iso_str


def mode_glyph(mode):
    return {
        MODE_PRIVATE: "● private",
        MODE_PERMANENT: "◆ permanent",
        MODE_EPHEMERAL: "○ ephemeral",
    }.get(mode, mode or "unknown")


def signed_status(entry):
    """Return a short label describing a seal's signature state."""
    if "node_sig" not in entry or "node_pubkey" not in entry:
        return "unsigned"
    result = NodeIdentity.verify_signed_seal(entry)
    if result is True:
        return "signed, verified"
    if result is False:
        return "signed, BAD SIGNATURE"
    return "signed, unverifiable (no cryptography package)"


def pubkey_fingerprint(pubkey_b64):
    """Same fingerprint scheme as NodeIdentity.fingerprint, for a raw b64 key."""
    import base64
    import hashlib
    try:
        raw = base64.b64decode(pubkey_b64)
        return hashlib.sha256(raw).hexdigest()[:16]
    except Exception:
        return "invalid-key"


# ─────────────────────────────────────────────────────────
# SEALS
# ─────────────────────────────────────────────────────────

def view_seals(store):
    seals = store.load()
    if not seals:
        print("\n No sealed thoughts on this device yet.\n")
        return

    print(f"\n {len(seals)} sealed thought(s) on this device:\n")
    for i, s in enumerate(seals, 1):
        idea_preview = s["idea"] if len(s["idea"]) <= 60 else s["idea"][:57] + "..."
        print(f" [{i}] {idea_preview}")
        print(f"     {fmt_moment(s['moment'])}   {mode_glyph(s.get('mode'))}")
    print()

    choice = input(" Enter a number for full detail (Enter to go back): ").strip()
    if not choice:
        return
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(seals):
            print(" No seal with that number.\n")
            return
    except ValueError:
        print(" Not a number.\n")
        return

    s = seals[idx]
    print("\n ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(" SEALED THOUGHT — DETAIL")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f"\n Idea:\n   {s['idea']}\n")
    print(f" Moment:      {s['moment']}")
    print(f"              ({fmt_moment(s['moment'])})")
    print(f" Stamp:       {s['stamp']}")
    print(f" Mode:        {mode_glyph(s.get('mode'))}")
    print(f" Signature:   {signed_status(s)}")
    if "node_pubkey" in s:
        print(f" Signed by:   {pubkey_fingerprint(s['node_pubkey'])}  (fingerprint)")
        print(f" Public key:  {s['node_pubkey']}")
    print()


# ─────────────────────────────────────────────────────────
# ENCOUNTERS
# ─────────────────────────────────────────────────────────

def view_encounters(encounter_log):
    encounters = encounter_log.load()
    if not encounters:
        print("\n No encounters yet. This node hasn't met another.\n")
        return

    print(f"\n {len(encounters)} encounter(s) in the log:\n")
    for i, e in enumerate(encounters, 1):
        print(f" [{i}] {fmt_moment(e['moment'])}  —  peer {e['peer']}")
        print(f"     sent {e['sent']}, received {e['received']}")
    print()

    choice = input(" Enter a number for full detail (Enter to go back): ").strip()
    if not choice:
        return
    try:
        idx = int(choice) - 1
        if idx < 0 or idx >= len(encounters):
            print(" No encounter with that number.\n")
            return
    except ValueError:
        print(" Not a number.\n")
        return

    e = encounters[idx]
    print(f"\n Peer:              {e['peer']}")
    print(f" Moment:            {e['moment']}")
    print(f"                    ({fmt_moment(e['moment'])})")
    print(f" Seals sent:        {e['sent']}")
    print(f" Seals received:    {e['received']}")
    print(f" Encounter stamp:   {e['encounter_stamp']}")
    received = e.get("received_stamps", [])
    if received:
        print(f" Received stamps:")
        for st in received:
            print(f"   - {st}")
    print()


# ─────────────────────────────────────────────────────────
# IDENTITY
# ─────────────────────────────────────────────────────────

def view_identity(km):
    identity = NodeIdentity.load(key=km.key)
    print()
    if not identity:
        if not CRYPTO_AVAILABLE:
            print(" No identity — 'cryptography' package is not installed.")
            print(" Install it with: pip install cryptography\n")
        else:
            print(" No identity yet. One is created the first time you")
            print(" run --listen, --connect, or --identity in phantom_node.py.\n")
        return

    print(f" Node name:    {identity.node_name or '(unnamed)'}")
    print(f" Fingerprint:  {identity.fingerprint}")
    print(f" Public key:   {identity.public_key_b64}")
    print(f" Private key:  {'present on this device' if identity.has_private_key else 'not loaded (public-only)'}")
    print(f" Transport:    {tor_status()}")
    onion = get_onion_address()
    if onion:
        print(f" Onion addr:   {onion}")
    print()


# ─────────────────────────────────────────────────────────
# SUMMARY / HOME SCREEN
# ─────────────────────────────────────────────────────────

def print_summary(store, encounter_log, identity, pulse_ledger):
    seals = store.load()
    encounters = encounter_log.load()

    permanent = sum(1 for s in seals if s.get("mode") == MODE_PERMANENT)
    private = sum(1 for s in seals if s.get("mode") == MODE_PRIVATE)
    ephemeral = sum(1 for s in seals if s.get("mode") == MODE_EPHEMERAL)

    pulse_ledger.prune()
    fraction = pulse_ledger.alive_fraction()
    pulse_line = f"{fraction:.2f}" if fraction is not None else "no data yet"

    box_title(f"PHANTOM NETWORK — v{PHANTOM_VERSION}")
    if identity:
        box_line(f"Node:        {identity.node_name or '(unnamed)'}  [{identity.fingerprint}]")
    else:
        box_line("Node:        no identity yet")
    box_line(f"Transport:   {tor_status()}")
    box_line()
    box_line(f"Seals:       {len(seals)} total")
    box_line(f"             {private} private · {permanent} permanent · {ephemeral} ephemeral")
    box_line(f"Encounters:  {len(encounters)}")
    box_line(f"Shared pulse: {pulse_line}")
    box_bottom()


def main():
    print(f"\n PHANTOM NETWORK — Dashboard")
    print(" One passphrase. Everything this node holds.\n")

    init_tor(interactive=False)

    km = KeyManager()
    km.init_encryption()

    store = SealStore(km)
    encounter_log = EncounterLog(km)
    pulse_ledger = PulseLedger(km)
    receipt_ledger = ReceiptLedger(km)
    identity = NodeIdentity.load(key=km.key)

    while True:
        print()
        print_summary(store, encounter_log, identity, pulse_ledger)
        print()
        print(" [1] Sealed thoughts")
        print(" [2] Encounters")
        print(" [3] Node identity")
        print(" [4] Refresh")
        print(" [5] Chat (Echo / Luna / Council)")
        print(" [6] Shared pulse")
        print(" [7] Receipts / reputation")
        print(" [0] Exit")
        choice = input("\n > ").strip()

        if choice == "1":
            view_seals(store)
        elif choice == "2":
            view_encounters(encounter_log)
        elif choice == "3":
            view_identity(km)
        elif choice == "4":
            continue
        elif choice == "6":
            view_pulse(pulse_ledger)
        elif choice == "7":
            view_receipts(receipt_ledger, identity)
        elif choice == "5":
            view_chat(store)
        elif choice == "0":
            print("\n Sealed and safe. Until next time.\n")
            break
        else:
            print(" Not a valid option.\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n Closed.\n")
        sys.exit(0)
