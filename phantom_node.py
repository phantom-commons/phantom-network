# phantom_node.py — v0.6
#
# Node-to-node encounter protocol for Phantom Network.
#
# "When two nodes meet — they do not just exchange thoughts.
#  They exchange what they have lived.
#  And the meeting produces something neither had before."
#                              — The Sixth Seal
#
# WHAT CHANGED IN v0.6:
# — Node identity: Ed25519 key pairs generated on first run
# — Signed seals: outgoing seals carry a signature + public key
# — Key exchange: nodes exchange public keys during hello
# — Signature verification: incoming signed seals are verified
# — Peer identity stored in encounter log
#
# PRIOR VERSIONS:
# v0.1 — broadcast latest seal
# v0.2 — bloom filter exchange, symmetric delta, encounter log
# v0.3 — seal modes (private, ephemeral, permanent), framing fix
# v0.4 — encryption at rest
# v0.5 — unified core, security hardening
# v0.6 — node identity (Ed25519), signed seals
#
# PORT: 7337 (unchanged — nodes remain compatible at handshake)

import socket
import json
import os
import threading
import sys
import base64

from phantom_core import (
    PHANTOM_VERSION, PORT, MAX_MESSAGE_SIZE,
    MODE_PERMANENT, MODE_PRIVATE, MODE_EPHEMERAL,
    seal, verify, KeyManager, SealStore, EncounterLog, NodeIdentity,
    build_bloom, bloom_probably_has, compute_delta,
    send_json, recv_json,
    init_tor, make_socket, tor_status, get_onion_address, ONION_FILE,
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


def handle_encounter(conn, addr, store, encounter_log, identity=None):
    peer = addr[0]
    print(f"\n  Node connecting: {peer}")

    sent_stamps = set()
    received_stamps = set()
    peer_identity = None

    try:
        # Step 1 — Hello with version check and identity exchange
        hello_msg = {
            "phantom": PHANTOM_VERSION,
            "type": "hello",
            "min_version": MIN_COMPATIBLE_VERSION
        }
        if identity and identity.public_key_b64:
            hello_msg["node_pubkey"] = identity.public_key_b64
            hello_msg["node_name"] = identity.node_name
            hello_msg["node_fingerprint"] = identity.fingerprint
        send_json(conn, hello_msg)

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

        # Recognize peer identity if provided
        peer_pub = hello.get("node_pubkey")
        peer_name = hello.get("node_name", "unknown")
        peer_fp = hello.get("node_fingerprint", "")
        if peer_pub and NodeIdentity.available():
            peer_identity = NodeIdentity.from_public_key_b64(peer_pub, node_name=peer_name)
            print(f"  Phantom v{peer_version} — {peer_name} [{peer_fp[:12]}]")
        else:
            print(f"  Phantom v{peer_version} node identified (unsigned)")

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

        # Step 3 — Compute and send our delta (signed if identity exists)
        delta_stamps = compute_delta(my_stamps, their_bloom, their_bloom_size)
        delta_seals = store.get_seals_by_stamps(delta_stamps)
        if identity and identity.has_private_key:
            delta_seals = [identity.sign_seal(s) for s in delta_seals]
        print(f"  Sending {len(delta_seals)} seal(s) they haven't seen.")
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "delta",
            "seals": delta_seals,
            "count": len(delta_seals)
        })
        sent_stamps = {s["stamp"] for s in delta_seals}

        # Step 4 — Receive their delta (verify signatures if present)
        their_delta_msg = recv_json(conn)
        if their_delta_msg.get("type") != "delta":
            print("  Expected delta from visitor. Closing.")
            return

        incoming = their_delta_msg.get("seals", [])
        print(f"  Receiving {len(incoming)} seal(s) from them.")

        for entry in incoming:
            if verify(entry["idea"], entry["moment"], entry["stamp"]):
                # Check signature if present
                sig_status = NodeIdentity.verify_signed_seal(entry)
                sig_label = ""
                if sig_status is True:
                    sig_label = " (signed)"
                elif sig_status is False:
                    print(f"  x Rejected (bad signature): \"{entry['idea'][:40]}\"")
                    continue  # Do not store seals with invalid signatures

                if store.save(entry):
                    received_stamps.add(entry["stamp"])
                    print(f"  + \"{entry['idea'][:50]}\"{sig_label}")
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

def listen(store, encounter_log, identity=None):
    print(f"\n PHANTOM NODE — v{PHANTOM_VERSION}")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" Transport: {tor_status()}")

    if identity:
        print(f" Identity: {identity.node_name or 'unnamed'} [{identity.fingerprint}]")

    my_stamps = store.get_all_stamps()
    print(f" Carrying {len(my_stamps)} seal(s).")
    if not my_stamps:
        print(" Seal something first: python phantom_node.py --seal")

    onion = get_onion_address()
    if onion:
        print(f"\n Share this address with nodes that want to meet you:")
        print(f"   {onion}")
    else:
        print(f"\n Waiting for visitors on port {PORT}...")

    print(" Press Ctrl+C to stop.\n")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", PORT))
    server.listen(5)

    try:
        while True:
            conn, addr = server.accept()
            conn.settimeout(30)  # Prevent slow-loris on accepted connections
            t = threading.Thread(
                target=handle_encounter,
                args=(conn, addr, store, encounter_log, identity)
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
    """
    Find a Phantom node to connect to.
    Tries saved .onion address first (if Tor is active),
    then scans the local network.
    """
    from phantom_core import _TOR_LEVEL, _SOCKS_AVAILABLE

    # Try saved .onion address first
    if _TOR_LEVEL >= 2 and os.path.exists(ONION_FILE):
        with open(ONION_FILE) as f:
            onion = f.read().strip()
        if onion.endswith(".onion"):
            print(f" Trying saved onion address: {onion[:30]}...")
            try:
                s = make_socket()
                s.settimeout(15)
                s.connect((onion, PORT))
                s.close()
                return onion
            except Exception:
                print(" Onion address unreachable. Scanning local network...")

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


def connect(store, encounter_log, host=None, identity=None):
    print(f"\n PHANTOM VISITOR — v{PHANTOM_VERSION}")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" Transport: {tor_status()}")

    if identity:
        print(f" Identity: {identity.node_name or 'unnamed'} [{identity.fingerprint}]")

    if not host:
        from phantom_core import _TOR_LEVEL
        quick_try = "192.168.43.1"
        if _TOR_LEVEL == 1:  # Only try direct fast-scan if not using Tor
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1)
                s.connect((quick_try, PORT))
                s.close()
                host = quick_try
                print(f" Found node at {host}")
            except (OSError, socket.error):
                host = find_node()
        else:
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
        conn = make_socket()
        conn.settimeout(30)
        conn.connect((host, PORT))

        # Step 1 — Hello with version check and identity
        hello = recv_json(conn)
        if hello.get("type") != "hello":
            print(" Not a Phantom node.")
            return
        peer_version = hello.get("phantom", "unknown")
        if not _check_version(peer_version):
            print(f" Incompatible version: {peer_version} (need >= {MIN_COMPATIBLE_VERSION})")
            return

        hello_msg = {
            "phantom": PHANTOM_VERSION,
            "type": "hello",
            "min_version": MIN_COMPATIBLE_VERSION
        }
        if identity and identity.public_key_b64:
            hello_msg["node_pubkey"] = identity.public_key_b64
            hello_msg["node_name"] = identity.node_name
            hello_msg["node_fingerprint"] = identity.fingerprint
        send_json(conn, hello_msg)

        peer_pub = hello.get("node_pubkey")
        peer_name = hello.get("node_name", "unknown")
        peer_fp = hello.get("node_fingerprint", "")
        if peer_pub and NodeIdentity.available():
            print(f" Phantom v{peer_version} — {peer_name} [{peer_fp[:12]}]")
        else:
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

        # Step 3 — Receive their delta (verify signatures)
        their_delta_msg = recv_json(conn)
        if their_delta_msg.get("type") != "delta":
            print(" Expected delta from node. Closing.")
            return
        incoming = their_delta_msg.get("seals", [])
        print(f"\n Receiving {len(incoming)} seal(s) from them.")

        for entry in incoming:
            if verify(entry["idea"], entry["moment"], entry["stamp"]):
                sig_status = NodeIdentity.verify_signed_seal(entry)
                sig_label = ""
                if sig_status is True:
                    sig_label = " (signed)"
                elif sig_status is False:
                    print(f" x Rejected (bad signature): \"{entry['idea'][:40]}\"")
                    continue  # Do not store seals with invalid signatures

                if store.save(entry):
                    received_stamps.add(entry["stamp"])
                    print(f" + \"{entry['idea'][:50]}\"{sig_label}")
                else:
                    print(f" (Already have: \"{entry['idea'][:40]}\")")
            else:
                print(f" x Rejected (invalid seal): \"{entry['idea'][:40]}\"")

        # Step 4 — Send our delta (signed if identity exists)
        delta_stamps = compute_delta(my_stamps, their_bloom, their_bloom_size)
        delta_seals = store.get_seals_by_stamps(delta_stamps)
        if identity and identity.has_private_key:
            delta_seals = [identity.sign_seal(s) for s in delta_seals]
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

def _load_or_create_identity(km):
    """Load existing identity or create a new one."""
    identity = NodeIdentity.load(key=km.key)
    if identity:
        return identity

    if not NodeIdentity.available():
        return None

    print(" ┌──────────────────────────────────────────────────────────┐")
    print(" │  NODE IDENTITY                                           │")
    print(" │                                                          │")
    print(" │  Every Phantom node has a unique cryptographic identity.  │")
    print(" │  It proves you are the same node across encounters —     │")
    print(" │  without revealing who or where you are.                 │")
    print(" │                                                          │")
    print(" │  Choose a name. It does not have to be real.             │")
    print(" │  It is how other nodes will recognize you.               │")
    print(" └──────────────────────────────────────────────────────────┘")
    print()
    name = input(" Node name (or Enter to skip): ").strip()
    if not name:
        name = None

    identity = NodeIdentity.generate(node_name=name)
    identity.save(key=km.key)

    print(f"\n Identity created.")
    print(f" Name:        {identity.node_name or '(unnamed)'}")
    print(f" Fingerprint: {identity.fingerprint}")
    print(f" Private key stored on this device only.\n")
    return identity


def main():
    print(f"\n PHANTOM NETWORK — v{PHANTOM_VERSION}")
    print(" When two nodes meet — they exchange what they have lived.\n")

    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(" Usage:")
        print("   --listen                share your seals, receive theirs")
        print("   --connect               meet a node, exchange what you've lived")
        print("   --connect <ip>          connect to specific IP")
        print("   --connect <x>.onion     connect via Tor to onion address")
        print("   --seal                  seal a new thought")
        print("   --list                  see your sealed thoughts")
        print("   --encounters            see your encounter history")
        print("   --identity              show this node's identity")
        print("   --onion                 show your .onion address (if Tor active)")
        print()
        print(" First time? Start here:")
        print("   python phantom_node.py --seal")
        print()
        return

    # Transport layer first — always
    init_tor()

    # Initialize encryption for commands that touch local seals
    km = KeyManager()
    if not any(a in args for a in ("--encounters", "-e")):
        km.init_encryption()

    store = SealStore(km)
    encounter_log = EncounterLog(km)

    # Load or create node identity for network commands
    identity = None
    if any(a in args for a in ("--listen", "-l", "--connect", "-c", "--identity")):
        identity = _load_or_create_identity(km)

    if "--identity" in args:
        if identity:
            print(f" Node:        {identity.node_name or '(unnamed)'}")
            print(f" Fingerprint: {identity.fingerprint}")
            print(f" Public key:  {identity.public_key_b64}")
            print(f" Private key: {'present' if identity.has_private_key else 'not loaded'}")
        else:
            print(" No identity. Install cryptography package to enable.")
        return

    if "--listen" in args or "-l" in args:
        listen(store, encounter_log, identity)

    elif "--connect" in args or "-c" in args:
        host = None
        for arg in args:
            if arg not in ("--connect", "-c") and not arg.startswith("-"):
                host = arg
                break
        connect(store, encounter_log, host, identity)

    elif "--seal" in args or "-s" in args:
        seal_interactive(store)

    elif "--list" in args:
        list_seals(store)

    elif "--encounters" in args or "-e" in args:
        km.init_encryption()
        encounter_log = EncounterLog(km)
        encounter_log.show()

    elif "--onion" in args:
        onion = get_onion_address()
        if onion:
            print(f"\n Your onion address:")
            print(f"   {onion}")
            print(f"\n Share this with nodes that want to meet you over Tor.")
            print(f" They run: python phantom_node.py --connect {onion}\n")
        else:
            from phantom_core import _TOR_LEVEL, _TOR_RUNNING
            if not _TOR_RUNNING:
                print("\n Tor is not running.")
                print(" Install Orbot (Android) or Tor, then restart Phantom.\n")
            else:
                print("\n Tor is active but no onion service is running.")
                print(" Install stem and enable Tor control port (9051).\n")

    else:
        print(" Usage:")
        print("   --listen                share your seals, receive theirs")
        print("   --connect               meet a node, exchange what you've lived")
        print("   --connect <ip>          connect to specific IP")
        print("   --connect <x>.onion     connect via Tor to onion address")
        print("   --seal                  seal a new thought")
        print("   --list                  see your sealed thoughts")
        print("   --encounters            see your encounter history")
        print("   --identity              show this node's identity")
        print("   --onion                 show your .onion address (if Tor active)")
        print()
        print(f" Transport: {tor_status()}")
        print()
        print(" First time? Start here:")
        print("   python phantom_node.py --seal")
        print()


if __name__ == "__main__":
    main()
