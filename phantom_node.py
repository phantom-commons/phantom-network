# phantom_node.py — v0.5
#
# Node-to-node encounter protocol for Phantom Network.
#
# "When two nodes meet — they do not just exchange thoughts.
#  They exchange what they have lived.
#  And the meeting produces something neither had before."
#                              — The Sixth Seal
#
# WHAT CHANGED IN v0.5:
# — Unified on phantom_core.py (single source of truth)
# — recv_json: chunked reads with 4MB size limit (was byte-by-byte, no limit)
# — Encounter log now encrypted when passphrase is set
# — Bare except clauses replaced with specific exception types
# — Protocol version check on hello exchange
# — Bloom filter size scales with seal count
# — Seal loading cached in memory (was re-reading disk per call)
# — Input validation via phantom_core.seal()
#
# PRIOR VERSIONS:
# v0.1 — broadcast latest seal
# v0.2 — bloom filter exchange, symmetric delta, encounter log
# v0.3 — seal modes (private, ephemeral, permanent), framing fix
# v0.4 — encryption at rest
# v0.5 — unified core, security hardening
#
# PORT: 7337 (unchanged — nodes remain compatible at handshake)

import socket
import json
import threading
import sys
import base64

from phantom_core import (
    PHANTOM_VERSION, PORT, MAX_MESSAGE_SIZE,
    MODE_PERMANENT, MODE_PRIVATE, MODE_EPHEMERAL,
    seal, verify, KeyManager, SealStore, EncounterLog,
    build_bloom, bloom_probably_has, compute_delta,
    send_json, recv_json,
)

# Minimum compatible protocol version
MIN_COMPATIBLE_VERSION = "0.3"

# ─────────────────────────────────────────────────────────
# ENCOUNTER PROTOCOL — NODE SIDE (listening)
#
# The meeting from the node's perspective:
#   1. Send hello, receive hello (version check)
#   2. Exchange bloom filters
#   3. Send delta (what they're missing)
#   4. Receive their delta, verify and store
#   5. Seal the encounter, log it
# ─────────────────────────────────────────────────────────

def _check_version(peer_version):
    """
    Check if peer's protocol version is compatible.
    Returns True if compatible, False otherwise.
    """
    try:
        peer_parts = [int(x) for x in peer_version.split(".")]
        min_parts = [int(x) for x in MIN_COMPATIBLE_VERSION.split(".")]
        return peer_parts >= min_parts
    except (ValueError, AttributeError):
        return False


def handle_encounter(conn, addr, store, encounter_log):
    peer = addr[0]
    print(f"\n  Node connecting: {peer}")

    sent_stamps = set()
    received_stamps = set()

    try:
        # Step 1 — Hello with version check
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "hello",
            "min_version": MIN_COMPATIBLE_VERSION
        })
        hello = recv_json(conn)
        if hello.get("type") != "hello":
            print("  Not a Phantom node. Closing.")
            return
        peer_version = hello.get("phantom", "unknown")
        if not _check_version(peer_version):
            print(f"  Incompatible version: {peer_version} (need >= {MIN_COMPATIBLE_VERSION})")
            send_json(conn, {
                "type": "error",
                "message": f"Version {peer_version} not compatible. Need >= {MIN_COMPATIBLE_VERSION}"
            })
            return
        print(f"  Phantom v{peer_version} node identified")

        # Step 2 — Bloom exchange
        my_stamps = store.get_all_stamps()
        my_bloom, my_bloom_size = build_bloom(my_stamps)
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "bloom",
            "bloom": base64.b64encode(my_bloom).decode('ascii'),
            "bloom_size": my_bloom_size,
            "seal_count": len(my_stamps)
        })

        their_bloom_msg = recv_json(conn)
        if their_bloom_msg.get("type") != "bloom":
            print("  Expected bloom. Closing.")
            return

        their_bloom_data = their_bloom_msg.get("bloom", "")
        # Support both base64 (v0.5+) and list-of-ints (v0.3-v0.4) formats
        if isinstance(their_bloom_data, str):
            their_bloom = base64.b64decode(their_bloom_data)
        else:
            their_bloom = bytes(their_bloom_data)
        their_bloom_size = their_bloom_msg.get("bloom_size", len(their_bloom) * 8)
        their_count = their_bloom_msg.get("seal_count", "?")
        print(f"  I carry {len(my_stamps)} seal(s). They carry {their_count}.")

        # Step 3 — Compute and send our delta
        delta_stamps = compute_delta(my_stamps, their_bloom, their_bloom_size)
        delta_seals = store.get_seals_by_stamps(delta_stamps)
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
                if store.save(entry):
                    received_stamps.add(entry["stamp"])
                    print(f"  + \"{entry['idea'][:55]}\"")
                else:
                    print(f"  (Already have: \"{entry['idea'][:40]}\")")
            else:
                print(f"  x Rejected (invalid seal): \"{entry['idea'][:40]}\"")

        # Step 5 — Seal and log the encounter
        encounter_stamp = encounter_log.log(
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

    except json.JSONDecodeError as e:
        print(f"  Malformed message from peer: {e}")
    except ConnectionError as e:
        print(f"  Connection lost: {e}")
    except ValueError as e:
        print(f"  Protocol error: {e}")
    except OSError as e:
        print(f"  Network error: {e}")
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────
# NODE — LISTENING
# ─────────────────────────────────────────────────────────

def listen(store, encounter_log):
    print(f"\n PHANTOM NODE — v{PHANTOM_VERSION}")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    my_stamps = store.get_all_stamps()
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
            t = threading.Thread(
                target=handle_encounter,
                args=(conn, addr, store, encounter_log)
            )
            t.daemon = True
            t.start()
    except KeyboardInterrupt:
        print("\n Node stopping.")
    finally:
        server.close()


# ─────────────────────────────────────────────────────────
# ENCOUNTER PROTOCOL — VISITOR SIDE (connecting)
# ─────────────────────────────────────────────────────────

def find_node(network_prefix="192.168.43"):
    """Scan local network for a Phantom node."""
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
        except (OSError, socket.error):
            pass
    return None


def connect(store, encounter_log, host=None):
    print(f"\n PHANTOM VISITOR — v{PHANTOM_VERSION}")
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
        except (OSError, socket.error):
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
    conn = None

    try:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(30)
        conn.connect((host, PORT))

        # Step 1 — Hello with version check
        hello = recv_json(conn)
        if hello.get("type") != "hello":
            print(" Not a Phantom node.")
            return
        peer_version = hello.get("phantom", "unknown")
        if not _check_version(peer_version):
            print(f" Incompatible version: {peer_version} (need >= {MIN_COMPATIBLE_VERSION})")
            return
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "hello",
            "min_version": MIN_COMPATIBLE_VERSION
        })
        print(f" Phantom v{peer_version} node found")

        # Step 2 — Bloom exchange
        their_bloom_msg = recv_json(conn)
        if their_bloom_msg.get("type") == "error":
            print(f" Peer rejected connection: {their_bloom_msg.get('message', 'unknown reason')}")
            return
        if their_bloom_msg.get("type") != "bloom":
            print(" Expected bloom. Closing.")
            return

        their_bloom_data = their_bloom_msg.get("bloom", "")
        if isinstance(their_bloom_data, str):
            their_bloom = base64.b64decode(their_bloom_data)
        else:
            their_bloom = bytes(their_bloom_data)
        their_bloom_size = their_bloom_msg.get("bloom_size", len(their_bloom) * 8)
        their_count = their_bloom_msg.get("seal_count", "?")

        my_stamps = store.get_all_stamps()
        my_bloom, my_bloom_size = build_bloom(my_stamps)
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "bloom",
            "bloom": base64.b64encode(my_bloom).decode('ascii'),
            "bloom_size": my_bloom_size,
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
                if store.save(entry):
                    received_stamps.add(entry["stamp"])
                    print(f" + \"{entry['idea'][:55]}\"")
                else:
                    print(f" (Already have: \"{entry['idea'][:40]}\")")
            else:
                print(f" x Rejected (invalid seal): \"{entry['idea'][:40]}\"")

        # Step 4 — Send our delta
        delta_stamps = compute_delta(my_stamps, their_bloom, their_bloom_size)
        delta_seals = store.get_seals_by_stamps(delta_stamps)
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
        our_encounter_stamp = encounter_log.log(
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
    except json.JSONDecodeError as e:
        print(f" Malformed message from peer: {e}")
    except ConnectionError as e:
        print(f" Connection lost: {e}")
    except ValueError as e:
        print(f" Protocol error: {e}")
    except OSError as e:
        print(f" Network error: {e}")
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────────────────
# INTERACTIVE SEAL + LIST
# ─────────────────────────────────────────────────────────

def seal_interactive(store):
    idea = input("\n Enter idea to seal:\n > ").strip()
    if not idea:
        return
    try:
        entry = seal(idea)
        if store.save(entry):
            print(f"\n PHANTOM SEAL")
            print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(f" Idea:   {entry['idea']}")
            print(f" Moment: {entry['moment']}")
            print(f" Stamp:  {entry['stamp']}")
            print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            print(" Sealed and saved. Ready to travel.\n")
        else:
            print(" (Duplicate — this seal already exists.)")
    except ValueError as e:
        print(f"\n {e}\n")


def list_seals(store):
    seals = store.load()
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
    print(f"\n PHANTOM NETWORK — v{PHANTOM_VERSION}")
    print(" When two nodes meet — they exchange what they have lived.\n")

    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
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
        return

    # Initialize encryption for commands that touch local seals
    km = KeyManager()
    if not any(a in args for a in ("--encounters", "-e")):
        km.init_encryption()

    store = SealStore(km)
    encounter_log = EncounterLog(km)

    if "--listen" in args or "-l" in args:
        listen(store, encounter_log)

    elif "--connect" in args or "-c" in args:
        host = None
        for arg in args:
            if arg not in ("--connect", "-c") and not arg.startswith("-"):
                host = arg
                break
        connect(store, encounter_log, host)

    elif "--seal" in args or "-s" in args:
        seal_interactive(store)

    elif "--list" in args:
        list_seals(store)

    elif "--encounters" in args or "-e" in args:
        # Encounters may be encrypted too now
        km.init_encryption()
        encounter_log = EncounterLog(km)
        encounter_log.show()

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
