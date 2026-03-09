# phantom_node.py — v0.2 (Encounter)
#
# "When two nodes meet — they do not just exchange thoughts.
#  They exchange what they have lived.
#  And the meeting produces something neither had before."
#                              — The Sixth Seal
#
# WHAT CHANGED FROM v0.1:
# v0.1 sent the latest seal. That is a broadcast — one node
# pushing one thought to whoever connects.
#
# v0.2 is a meeting. Each node announces what it carries.
# Each node receives only what it has not seen.
# The encounter log records every meeting — who, when, what moved.
#
# HOW IT WORKS:
# 1. Handshake — both nodes declare their Phantom version
# 2. Bloom exchange — each node sends a compact fingerprint
#    of every stamp it holds (the bloom filter)
# 3. Delta resolution — each node computes what the other
#    is missing and sends only those seals
# 4. Encounter sealed — the meeting itself becomes a record:
#    who connected, when, what traveled in each direction
#
# ON THE BLOOM FILTER:
# A bloom filter answers "have you seen this?" without revealing
# what you have. It is probabilistic — false positives are
# possible (sending a seal someone already has), false negatives
# are not (never withholding a seal someone needs).
# For Phantom's scale, a simple bitarray bloom is sufficient
# and keeps this file dependency-free.
#
# DEPENDENCIES: Python standard library only.
# No pip install required. Works in Termux on any Android phone.
#
# PORT: 7337 (unchanged from v0.1 — nodes are compatible at handshake)
# PROTOCOL VERSION: 0.2

import socket
import hashlib
import json
import threading
import sys
import os
from datetime import datetime, timezone

PORT = 7337
PHANTOM_VERSION = "0.2"
SEALS_FILE = "phantom_seals.json"
ENCOUNTER_LOG_FILE = "phantom_encounters.json"

# ─────────────────────────────────────────────────────────
# SEAL FUNCTIONS — unchanged from v0.1
# The seal format is the seal. It cannot change.
# ─────────────────────────────────────────────────────────

def seal(idea):
    moment = datetime.now(timezone.utc).isoformat()
    data = json.dumps(
        {"idea": idea, "moment": moment},
        separators=(',', ':')
    )
    stamp = hashlib.sha256(data.encode()).hexdigest()
    return {"idea": idea, "moment": moment, "stamp": stamp}

def verify(idea, moment, stamp):
    data = json.dumps(
        {"idea": idea, "moment": moment},
        separators=(',', ':')
    )
    expected = hashlib.sha256(data.encode()).hexdigest()
    return expected == stamp

# ─────────────────────────────────────────────────────────
# LOCAL SEAL STORAGE
# ─────────────────────────────────────────────────────────

def load_seals():
    if not os.path.exists(SEALS_FILE):
        return []
    with open(SEALS_FILE, "r") as f:
        return json.load(f)

def save_seal(entry):
    seals = load_seals()
    if any(s["stamp"] == entry["stamp"] for s in seals):
        return False
    seals.append(entry)
    with open(SEALS_FILE, "w") as f:
        json.dump(seals, f, indent=2)
    return True

def get_all_stamps():
    """Return the set of all stamp hashes this node holds."""
    return {s["stamp"] for s in load_seals()}

def get_seals_by_stamps(stamps):
    """Return full seal objects for the given stamp set."""
    return [s for s in load_seals() if s["stamp"] in stamps]

# ─────────────────────────────────────────────────────────
# BLOOM FILTER
#
# A space-efficient way to share "what I have" without
# sharing the contents. The receiver uses it to compute
# the delta — what to send.
#
# Parameters chosen for Phantom's early scale:
#   size=8192 bits (~1KB), k=5 hash functions
#   At 100 seals: ~2.5% false positive rate
#   At 500 seals: ~12% false positive rate (still safe —
#     false positives waste bandwidth, never drop seals)
# ─────────────────────────────────────────────────────────

BLOOM_SIZE = 8192  # bits
BLOOM_K = 5        # hash functions

def _bloom_positions(stamp):
    """Return k bit positions for a given stamp."""
    positions = []
    for i in range(BLOOM_K):
        h = hashlib.sha256(f"{i}:{stamp}".encode()).hexdigest()
        positions.append(int(h, 16) % BLOOM_SIZE)
    return positions

def build_bloom(stamps):
    """Build a bloom filter from a set of stamps. Returns bytes."""
    bits = bytearray(BLOOM_SIZE // 8)
    for stamp in stamps:
        for pos in _bloom_positions(stamp):
            bits[pos // 8] |= (1 << (pos % 8))
    return bytes(bits)

def bloom_probably_has(bloom_bytes, stamp):
    """Return True if the bloom filter probably contains this stamp."""
    bits = bloom_bytes
    for pos in _bloom_positions(stamp):
        if not (bits[pos // 8] & (1 << (pos % 8))):
            return False
    return True

def compute_delta(my_stamps, their_bloom_bytes):
    """
    Return the stamps I have that they probably don't.
    This is what I will send them.
    """
    delta = set()
    for stamp in my_stamps:
        if not bloom_probably_has(their_bloom_bytes, stamp):
            delta.add(stamp)
    return delta

# ─────────────────────────────────────────────────────────
# ENCOUNTER LOG
#
# Every meeting between nodes is recorded locally.
# Not for surveillance — for the organism's memory.
# The encounter log is how a node knows its own history.
# ─────────────────────────────────────────────────────────

def load_encounters():
    if not os.path.exists(ENCOUNTER_LOG_FILE):
        return []
    with open(ENCOUNTER_LOG_FILE, "r") as f:
        return json.load(f)

def log_encounter(peer_addr, sent_count, received_count, received_stamps):
    """Seal the encounter itself and append to the log."""
    encounters = load_encounters()
    moment = datetime.now(timezone.utc).isoformat()

    encounter_data = {
        "peer": peer_addr,
        "moment": moment,
        "sent": sent_count,
        "received": received_count,
        "received_stamps": list(received_stamps)
    }

    # Seal the encounter record for integrity
    raw = json.dumps(encounter_data, separators=(',', ':'), sort_keys=True)
    encounter_stamp = hashlib.sha256(raw.encode()).hexdigest()
    encounter_data["encounter_stamp"] = encounter_stamp

    encounters.append(encounter_data)
    with open(ENCOUNTER_LOG_FILE, "w") as f:
        json.dump(encounters, f, indent=2)

    return encounter_stamp

# ─────────────────────────────────────────────────────────
# SEND / RECEIVE HELPERS
# ─────────────────────────────────────────────────────────

def send_json(conn, obj):
    conn.sendall((json.dumps(obj) + "\n").encode())

def recv_json(conn, bufsize=65536):
    data = b""
    while not data.endswith(b"\n"):
        chunk = conn.recv(bufsize)
        if not chunk:
            raise ConnectionError("Connection closed mid-message")
        data += chunk
    return json.loads(data.decode().strip())

# ─────────────────────────────────────────────────────────
# ENCOUNTER PROTOCOL — NODE SIDE (listening)
#
# The meeting from the node's perspective:
#   1. Send hello
#   2. Send our bloom, receive theirs
#   3. Send delta (what they're missing)
#   4. Receive their delta, verify and store
#   5. Seal the encounter, log it
# ─────────────────────────────────────────────────────────

def handle_encounter(conn, addr):
    peer = addr[0]
    print(f"\n  Node connecting: {peer}")

    sent_stamps = set()
    received_stamps = set()

    try:
        # Step 1 — Hello
        send_json(conn, {"phantom": PHANTOM_VERSION, "type": "hello"})
        hello = recv_json(conn)
        if hello.get("type") != "hello":
            print("  Not a Phantom node. Closing.")
            return
        peer_version = hello.get("phantom", "unknown")
        print(f"  Phantom v{peer_version} node identified")

        # Step 2 — Bloom exchange
        my_stamps = get_all_stamps()
        my_bloom = build_bloom(my_stamps)
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "bloom",
            "bloom": list(my_bloom),
            "seal_count": len(my_stamps)
        })

        their_bloom_msg = recv_json(conn)
        if their_bloom_msg.get("type") != "bloom":
            print("  Expected bloom. Closing.")
            return
        their_bloom = bytes(their_bloom_msg["bloom"])
        their_count = their_bloom_msg.get("seal_count", "?")
        print(f"  I carry {len(my_stamps)} seal(s). They carry {their_count}.")

        # Step 3 — Compute and send our delta
        delta_stamps = compute_delta(my_stamps, their_bloom)
        delta_seals = get_seals_by_stamps(delta_stamps)
        print(f"  Sending {len(delta_seals)} seal(s) they haven't seen.")
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "delta",
            "seals": delta_seals,
            "count": len(delta_seals)
        })
        sent_stamps = {s["stamp"] for s in delta_seals}

        # Step 4 — Receive their delta
        their_delta_msg = recv_json(conn)
        if their_delta_msg.get("type") != "delta":
            print("  Expected delta from visitor. Closing.")
            return

        incoming = their_delta_msg.get("seals", [])
        print(f"  Receiving {len(incoming)} seal(s) from them.")

        for entry in incoming:
            if verify(entry["idea"], entry["moment"], entry["stamp"]):
                if save_seal(entry):
                    received_stamps.add(entry["stamp"])
                    print(f"  + \"{entry['idea'][:55]}\"")
                else:
                    print(f"  (Already have: \"{entry['idea'][:40]}\")")
            else:
                print(f"  x Rejected (invalid seal): \"{entry['idea'][:40]}\"")

        # Step 5 — Seal and log the encounter
        encounter_stamp = log_encounter(
            peer, len(sent_stamps), len(received_stamps), received_stamps
        )
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "encounter_sealed",
            "encounter_stamp": encounter_stamp,
            "sent": len(sent_stamps),
            "received": len(received_stamps)
        })

        print(f"\n  Meeting complete.")
        print(f"  Sent {len(sent_stamps)} | Received {len(received_stamps)}")
        print(f"  Encounter: {encounter_stamp[:24]}...")

    except Exception as e:
        print(f"  Error during encounter: {e}")
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────
# NODE — LISTENING
# ─────────────────────────────────────────────────────────

def listen():
    print("\n PHANTOM NODE — v0.2 (Encounter)")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    my_stamps = get_all_stamps()
    print(f" Carrying {len(my_stamps)} seal(s).")
    if not my_stamps:
        print(" Seal something first: python phantom_node.py --seal")

    print(f"\n Waiting for visitors on port {PORT}...")
    print(" Press Ctrl+C to stop.\n")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen(5)

    try:
        while True:
            conn, addr = server.accept()
            t = threading.Thread(target=handle_encounter, args=(conn, addr))
            t.daemon = True
            t.start()
    except KeyboardInterrupt:
        print("\n Node stopping.")
    finally:
        server.close()

# ─────────────────────────────────────────────────────────
# ENCOUNTER PROTOCOL — VISITOR SIDE (connecting)
#
# Mirror of the node's protocol. Symmetric exchange —
# both sides give and both sides receive.
# ─────────────────────────────────────────────────────────

def find_node(network_prefix="192.168.43"):
    print(f" Scanning for Phantom node...")
    for i in range(1, 255):
        ip = f"{network_prefix}.{i}"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.08)
            result = s.connect_ex((ip, PORT))
            s.close()
            if result == 0:
                return ip
        except:
            pass
    return None

def connect(host=None):
    print("\n PHANTOM VISITOR — v0.2 (Encounter)")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if not host:
        quick_try = "192.168.43.1"
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(1)
            s.connect((quick_try, PORT))
            s.close()
            host = quick_try
            print(f" Found node at {host}")
        except:
            host = find_node()

    if not host:
        print("\n No Phantom node found.")
        print(" Make sure you are connected to 'phantom-node' WiFi")
        print(" and the other phone is running:")
        print(" python phantom_node.py --listen")
        return

    print(f" Connecting to {host}:{PORT}...")

    sent_stamps = set()
    received_stamps = set()

    try:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(30)
        conn.connect((host, PORT))

        # Step 1 — Hello
        hello = recv_json(conn)
        if hello.get("type") != "hello":
            print(" Not a Phantom node.")
            return
        peer_version = hello.get("phantom", "unknown")
        send_json(conn, {"phantom": PHANTOM_VERSION, "type": "hello"})
        print(f" Phantom v{peer_version} node found")

        # Step 2 — Bloom exchange
        their_bloom_msg = recv_json(conn)
        if their_bloom_msg.get("type") != "bloom":
            print(" Expected bloom. Closing.")
            return
        their_bloom = bytes(their_bloom_msg["bloom"])
        their_count = their_bloom_msg.get("seal_count", "?")

        my_stamps = get_all_stamps()
        my_bloom = build_bloom(my_stamps)
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "bloom",
            "bloom": list(my_bloom),
            "seal_count": len(my_stamps)
        })
        print(f" I carry {len(my_stamps)} seal(s). They carry {their_count}.")

        # Step 3 — Receive their delta
        their_delta_msg = recv_json(conn)
        if their_delta_msg.get("type") != "delta":
            print(" Expected delta from node. Closing.")
            return
        incoming = their_delta_msg.get("seals", [])
        print(f"\n Receiving {len(incoming)} seal(s) from them.")

        for entry in incoming:
            if verify(entry["idea"], entry["moment"], entry["stamp"]):
                if save_seal(entry):
                    received_stamps.add(entry["stamp"])
                    print(f" + \"{entry['idea'][:55]}\"")
                else:
                    print(f" (Already have: \"{entry['idea'][:40]}\")")
            else:
                print(f" x Rejected (invalid seal): \"{entry['idea'][:40]}\"")

        # Step 4 — Send our delta
        delta_stamps = compute_delta(my_stamps, their_bloom)
        delta_seals = get_seals_by_stamps(delta_stamps)
        print(f"\n Sending {len(delta_seals)} seal(s) they haven't seen.")
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "delta",
            "seals": delta_seals,
            "count": len(delta_seals)
        })
        sent_stamps = {s["stamp"] for s in delta_seals}

        # Step 5 — Receive encounter seal, log our own
        seal_msg = recv_json(conn)
        their_encounter_stamp = seal_msg.get("encounter_stamp", "")
        our_encounter_stamp = log_encounter(
            host, len(sent_stamps), len(received_stamps), received_stamps
        )

        print(f"\n MEETING COMPLETE")
        print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f" Sent:     {len(sent_stamps)} seal(s)")
        print(f" Received: {len(received_stamps)} seal(s)")
        print(f" Their encounter: {their_encounter_stamp[:24]}...")
        print(f" Our encounter:   {our_encounter_stamp[:24]}...")
        print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    except ConnectionRefusedError:
        print(f" Could not connect to {host}:{PORT}")
        print(" Is the other phone running: python phantom_node.py --listen ?")
    except Exception as e:
        print(f" Error: {e}")
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────
# ENCOUNTER LOG DISPLAY
# ─────────────────────────────────────────────────────────

def show_encounters():
    encounters = load_encounters()
    if not encounters:
        print("\n No encounters yet. The network has not met itself.")
        return
    print(f"\n {len(encounters)} encounter(s) in the log:\n")
    for i, e in enumerate(encounters, 1):
        print(f" [{i}] {e['moment']}")
        print(f"     Peer:     {e['peer']}")
        print(f"     Sent:     {e['sent']} seal(s)")
        print(f"     Received: {e['received']} seal(s)")
        print(f"     Stamp:    {e['encounter_stamp'][:32]}...")
        print()

# ─────────────────────────────────────────────────────────
# SEAL + LIST — unchanged from v0.1
# ─────────────────────────────────────────────────────────

def seal_interactive():
    idea = input("\n Enter idea to seal:\n > ").strip()
    if not idea:
        return
    entry = seal(idea)
    save_seal(entry)
    print(f"\n PHANTOM SEAL")
    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" Idea:   {entry['idea']}")
    print(f" Moment: {entry['moment']}")
    print(f" Stamp:  {entry['stamp']}")
    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
    print(" Sealed and saved. Ready to travel.\n")

def list_seals():
    seals = load_seals()
    if not seals:
        print(" No sealed thoughts yet.")
        return
    print(f"\n {len(seals)} sealed thought(s):\n")
    for i, s in enumerate(seals, 1):
        print(f" [{i}] {s['idea'][:70]}")
        print(f"     {s['moment']}")
        print()

# ─────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────

def main():
    print("\n PHANTOM NETWORK — v0.2")
    print(" When two nodes meet — they exchange what they have lived.\n")

    args = sys.argv[1:]

    if "--listen" in args or "-l" in args:
        listen()

    elif "--connect" in args or "-c" in args:
        host = None
        for arg in args:
            if arg not in ("--connect", "-c") and not arg.startswith("-"):
                host = arg
                break
        connect(host)

    elif "--seal" in args or "-s" in args:
        seal_interactive()

    elif "--list" in args:
        list_seals()

    elif "--encounters" in args or "-e" in args:
        show_encounters()

    else:
        print(" Usage:")
        print("   --listen          share your seals, receive theirs")
        print("   --connect         meet a node, exchange what you've lived")
        print("   --connect <ip>    connect to specific IP")
        print("   --seal            seal a new thought")
        print("   --list            see your sealed thoughts")
        print("   --encounters      see your encounter history")
        print()
        print(" First time? Start here:")
        print("   python phantom_node.py --seal")
        print()

if __name__ == "__main__":
    main()
        
