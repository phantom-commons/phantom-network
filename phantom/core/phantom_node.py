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
import re
import threading
import sys
import base64
import getpass
from datetime import datetime, timezone

from phantom_core import (
    PHANTOM_VERSION, PORT, MAX_MESSAGE_SIZE,
    MODE_PERMANENT, MODE_PRIVATE, MODE_EPHEMERAL,
    seal, verify, KeyManager, SealStore, EncounterLog, NodeIdentity,
    build_bloom, bloom_probably_has, compute_delta,
    send_json, recv_json,
    init_tor, make_socket, tor_status, get_onion_address, ONION_FILE,
    PulseLedger, generate_pulse, verify_pulse,
    ContactBook, DMStore, create_contact_card, verify_contact_card,
    create_dm, decrypt_dm,
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


def handle_encounter(conn, addr, store, encounter_log, identity=None, pulse_ledger=None,
                      contact_book=None, dm_store=None):
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
        claimed_fp = hello.get("node_fingerprint", "")
        if peer_pub and NodeIdentity.available():
            peer_identity = NodeIdentity.from_public_key_b64(peer_pub, node_name=peer_name)
            # Never trust a self-reported fingerprint string — a peer's
            # public key is the only thing that's cryptographically
            # theirs. Recompute the fingerprint from it, and only show
            # what they claimed if it doesn't match (worth a warning).
            real_fp = peer_identity.fingerprint
            if claimed_fp and claimed_fp != real_fp:
                print(f"  WARNING: peer claimed fingerprint {claimed_fp[:12]} "
                      f"but their key's real fingerprint is {real_fp[:12]}")
            print(f"  Phantom v{peer_version} — {peer_name} [{real_fp[:12]}]")
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
                    sig_label = " (BAD SIGNATURE)"

                if store.save(entry):
                    received_stamps.add(entry["stamp"])
                    print(f"  + \"{entry['idea'][:50]}\"{sig_label}")
                else:
                    print(f"  (Already have: \"{entry['idea'][:40]}\")")
            else:
                print(f"  x Rejected (invalid seal): \"{entry['idea'][:40]}\"")

        # Step 4.5 — Pulse exchange (presence, not seals — "we are all one")
        pulses_received = 0
        if pulse_ledger is not None and identity and identity.has_private_key:
            try:
                my_pulse = generate_pulse(identity, address=get_onion_address())
                pulse_ledger.record(my_pulse)
                outgoing_pulses = pulse_ledger.gossip_batch()
                send_json(conn, {
                    "phantom": PHANTOM_VERSION,
                    "type": "pulse_batch",
                    "pulses": outgoing_pulses,
                })
                their_pulse_msg = recv_json(conn)
                if their_pulse_msg.get("type") == "pulse_batch":
                    for p in their_pulse_msg.get("pulses", []):
                        if pulse_ledger.record(p):
                            pulses_received += 1
                    if pulses_received:
                        print(f"  ~ {pulses_received} presence pulse(s) received.")
            except RuntimeError:
                pass  # no private key available for pulsing this session

        # Step 4.6 — Contact card + DM exchange (encrypted, store-and-forward)
        dms_received = 0
        if (contact_book is not None and dm_store is not None
                and identity and identity.has_private_key and identity.has_encryption_key):
            try:
                my_card = create_contact_card(identity)
                outgoing_dms = dm_store.gossip_batch()
                send_json(conn, {
                    "phantom": PHANTOM_VERSION,
                    "type": "contact_dm_batch",
                    "card": my_card,
                    "dms": outgoing_dms,
                })
                their_batch = recv_json(conn)
                if their_batch.get("type") == "contact_dm_batch":
                    peer_card = their_batch.get("card")
                    if peer_card and contact_book.record(peer_card):
                        print(f"  Contact card recorded: {peer_card.get('node_name') or peer_card['fingerprint']}")
                    for d in their_batch.get("dms", []):
                        if dm_store.receive_from_peer(d):
                            dms_received += 1
                    if dms_received:
                        print(f"  ~ {dms_received} message(s) received (relayed or delivered).")
            except RuntimeError:
                pass  # identity not ready for DMs this session

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

def listen(store, encounter_log, identity=None, pulse_ledger=None, contact_book=None, dm_store=None):
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
            t = threading.Thread(
                target=handle_encounter,
                args=(conn, addr, store, encounter_log, identity, pulse_ledger, contact_book, dm_store)
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


def connect(store, encounter_log, host=None, identity=None, pulse_ledger=None,
            contact_book=None, dm_store=None):
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
        claimed_fp = hello.get("node_fingerprint", "")
        if peer_pub and NodeIdentity.available():
            peer_identity = NodeIdentity.from_public_key_b64(peer_pub, node_name=peer_name)
            real_fp = peer_identity.fingerprint
            if claimed_fp and claimed_fp != real_fp:
                print(f" WARNING: peer claimed fingerprint {claimed_fp[:12]} "
                      f"but their key's real fingerprint is {real_fp[:12]}")
            print(f" Phantom v{peer_version} — {peer_name} [{real_fp[:12]}]")
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
                    sig_label = " (BAD SIGNATURE)"

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

        # Step 4.5 — Pulse exchange (presence, not seals — "we are all one")
        pulses_received = 0
        if pulse_ledger is not None and identity and identity.has_private_key:
            try:
                their_pulse_msg = recv_json(conn)
                if their_pulse_msg.get("type") == "pulse_batch":
                    for p in their_pulse_msg.get("pulses", []):
                        if pulse_ledger.record(p):
                            pulses_received += 1
                    if pulses_received:
                        print(f" ~ {pulses_received} presence pulse(s) received.")

                my_pulse = generate_pulse(identity, address=get_onion_address())
                pulse_ledger.record(my_pulse)
                outgoing_pulses = pulse_ledger.gossip_batch()
                send_json(conn, {
                    "phantom": PHANTOM_VERSION,
                    "type": "pulse_batch",
                    "pulses": outgoing_pulses,
                })
            except RuntimeError:
                pass

        # Step 4.6 — Contact card + DM exchange (encrypted, store-and-forward)
        dms_received = 0
        if (contact_book is not None and dm_store is not None
                and identity and identity.has_private_key and identity.has_encryption_key):
            try:
                their_batch = recv_json(conn)
                if their_batch.get("type") == "contact_dm_batch":
                    peer_card = their_batch.get("card")
                    if peer_card and contact_book.record(peer_card):
                        print(f" Contact card recorded: {peer_card.get('node_name') or peer_card['fingerprint']}")
                    for d in their_batch.get("dms", []):
                        if dm_store.receive_from_peer(d):
                            dms_received += 1
                    if dms_received:
                        print(f" ~ {dms_received} message(s) received (relayed or delivered).")

                my_card = create_contact_card(identity)
                outgoing_dms = dm_store.gossip_batch()
                send_json(conn, {
                    "phantom": PHANTOM_VERSION,
                    "type": "contact_dm_batch",
                    "card": my_card,
                    "dms": outgoing_dms,
                })
            except RuntimeError:
                pass

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

def _looks_like_fingerprint(s):
    """A fingerprint is exactly 16 lowercase hex chars — distinct from
    an IPv4 address, a hostname, or an .onion address."""
    return bool(re.fullmatch(r"[0-9a-f]{16}", s or ""))


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

    choice = input(" Restore from an existing 24-word paper backup? (y/N): ").strip().lower()
    if choice == "y":
        return _restore_identity_interactive(km)

    name = input(" Node name (or Enter to skip): ").strip()
    if not name:
        name = None

    identity, mnemonic = NodeIdentity.generate_with_mnemonic(node_name=name)

    print("\n ┌──────────────────────────────────────────────────────────┐")
    print(" │  YOUR PAPER BACKUP — WRITE THIS DOWN NOW                 │")
    print(" │                                                          │")
    print(" │  These 24 words are the only way to recover this        │")
    print(" │  identity if this device is lost, wiped, or broken.      │")
    print(" │  Phantom shows them once, right now, and never again.    │")
    print(" │  Write them on paper. Do not save them in a file, a      │")
    print(" │  photo, or a note app on this device.                    │")
    print(" └──────────────────────────────────────────────────────────┘\n")
    words = mnemonic.split()
    for i in range(0, 24, 4):
        row = "   ".join(f"{i+j+1:>2}. {words[i+j]}" for j in range(4))
        print(f" {row}")
    print()
    input(" Press Enter once you've written all 24 words down: ")

    identity.save(key=km.key)

    print(f"\n Identity created.")
    print(f" Name:        {identity.node_name or '(unnamed)'}")
    print(f" Fingerprint: {identity.fingerprint}")
    print(f" Private key stored on this device only.\n")
    return identity


def _restore_identity_interactive(km):
    """Restore an identity from a 24-word paper backup, typed in now."""
    if NodeIdentity.load(key=km.key):
        print(" An identity already exists on this device — refusing to")
        print(" overwrite it. Move or delete the existing phantom_node.key")
        print(" / phantom_node.pub first if you really mean to replace it.\n")
        return None

    print("\n Enter your 24-word recovery phrase, separated by spaces.")
    phrase = input(" > ").strip()
    name = input(" Node name (or Enter to skip): ").strip() or None

    try:
        identity = NodeIdentity.from_mnemonic(phrase, node_name=name)
    except ValueError as e:
        print(f"\n Could not restore: {e}\n")
        return None

    identity.save(key=km.key)
    print(f"\n Identity restored.")
    print(f" Name:        {identity.node_name or '(unnamed)'}")
    print(f" Fingerprint: {identity.fingerprint}")
    print(f" If this fingerprint matches what you had before, it worked.\n")
    return identity


def _one_shot_identity_interactive():
    """
    A deliberately burnable identity: derived live from one specific
    idea + moment + passphrase, never from randomness, never given a
    recovery phrase. Deliberately independent of KeyManager/passphrase
    encryption — this identity's whole point is that nothing about it
    is required to persist anywhere.
    """
    print("\n ┌──────────────────────────────────────────────────────────┐")
    print(" │  ONE-SHOT IDENTITY — deliberately burnable                │")
    print(" │                                                          │")
    print(" │  This identity is derived from three things you supply  │")
    print(" │  right now: an idea, a moment, and a passphrase. The     │")
    print(" │  same three things always produce the exact same        │")
    print(" │  identity — forget any one of them on purpose, and it   │")
    print(" │  is gone forever. That is the feature.                  │")
    print(" │                                                          │")
    print(" │  Do not use an idea you have ever sealed as permanent    │")
    print(" │  or shared. If it's ever left this device, it's no       │")
    print(" │  longer secret, and neither is this identity.            │")
    print(" └──────────────────────────────────────────────────────────┘\n")

    idea = input(" Idea (never shared, never marked permanent): ").strip()
    if not idea:
        print(" No idea entered — nothing to derive from.\n")
        return None

    choice = input(" Is this a (n)ew one-shot identity or are you (r)ecovering one? [n/r]: ").strip().lower()
    if choice == "r":
        moment = input(" Exact moment you were given at creation: ").strip()
        if not moment:
            print(" No moment entered — cannot recover without it.\n")
            return None
    else:
        moment = datetime.now(timezone.utc).isoformat()
        print(f" Moment (write this down exactly, you'll need it to recover):")
        print(f"   {moment}")

    passphrase = getpass.getpass(" Passphrase for this identity: ")
    if not passphrase:
        print(" No passphrase entered — refusing to derive an unprotected identity.\n")
        return None

    name = input(" Node name (or Enter to skip): ").strip() or None

    identity = NodeIdentity.from_seal_and_passphrase(idea, moment, passphrase, node_name=name)

    print(f"\n Identity derived.")
    print(f" Name:        {identity.node_name or '(unnamed)'}")
    print(f" Fingerprint: {identity.fingerprint}")
    print(f"\n Nothing has been saved to disk. To get this exact identity")
    print(f" back later, you will need this exact idea, this exact")
    print(f" moment, and this exact passphrase — all three, unchanged.")
    print(f" Losing or discarding any one of them is permanent.\n")
    return identity


def _ensure_dm_ready(identity, km):
    """Upgrade an identity created before DMs existed, in place."""
    if identity and identity.has_private_key and not identity.has_encryption_key:
        identity.ensure_encryption_key(km)
        print(" (Identity upgraded with an encryption key for DMs.)")
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
        print("   --connect <fingerprint> connect using a fingerprint (needs a recent pulse)")
        print("   --seal                  seal a new thought")
        print("   --list                  see your sealed thoughts")
        print("   --encounters            see your encounter history")
        print("   --identity              show this node's identity")
        print("   --onion                 show your .onion address (if Tor active)")
        print("   --pulse                 show the shared aliveness pulse")
        print("   --restore-identity      restore an identity from its 24-word paper backup")
        print("   --one-shot-identity     derive a deliberately burnable identity (advanced)")
        print("   --card                  print your contact card (share it to be DM'd)")
        print("   --add-contact <json>    import a contact card (paste JSON or a file path)")
        print("   --contacts              list known contacts")
        print("   --send <fingerprint> <message...>   send a DM (delivered directly or relayed)")
        print("   --inbox                 read DMs addressed to you")
        print()
        print(" First time? Start here:")
        print("   python phantom_node.py --seal")
        print()
        return

    # Transport layer first — always
    init_tor()

    # Initialize encryption for commands that touch local seals
    km = KeyManager()
    if not any(a in args for a in ("--encounters", "-e", "--one-shot-identity")):
        km.init_encryption()

    store = SealStore(km)
    encounter_log = EncounterLog(km)
    pulse_ledger = PulseLedger(km)
    contact_book = ContactBook(km)
    dm_store = DMStore(km)

    # Load or create node identity for network commands
    identity = None
    if any(a in args for a in ("--listen", "-l", "--connect", "-c", "--identity", "--pulse",
                                "--card", "--send", "--inbox")):
        identity = _load_or_create_identity(km)
        identity = _ensure_dm_ready(identity, km)

    if "--restore-identity" in args:
        _restore_identity_interactive(km)
        return

    if "--one-shot-identity" in args:
        _one_shot_identity_interactive()
        return

    if "--identity" in args:
        if identity:
            print(f" Node:        {identity.node_name or '(unnamed)'}")
            print(f" Fingerprint: {identity.fingerprint}")
            print(f" Public key:  {identity.public_key_b64}")
            print(f" Private key: {'present' if identity.has_private_key else 'not loaded'}")
        else:
            print(" No identity. Install cryptography package to enable.")
        return

    if "--pulse" in args:
        pulse_ledger.prune()
        fraction = pulse_ledger.alive_fraction()
        known = len(pulse_ledger.known_fingerprints())
        alive = len(pulse_ledger.alive_fingerprints())
        print()
        if fraction is None:
            print(" No pulses recorded yet — meet a node with --listen or --connect.")
        else:
            print(f" Shared pulse: {fraction:.2f}")
            print(f" ({alive} alive of {known} known — from this node's own encounters)")
        print()
        return

    if "--listen" in args or "-l" in args:
        listen(store, encounter_log, identity, pulse_ledger, contact_book, dm_store)

    elif "--connect" in args or "-c" in args:
        host = None
        for arg in args:
            if arg not in ("--connect", "-c") and not arg.startswith("-"):
                host = arg
                break

        if host and _looks_like_fingerprint(host):
            target_fp = host
            resolved = pulse_ledger.address_for(target_fp)
            if not resolved:
                print(f"\n No known address for fingerprint {target_fp}.")
                print(" This node has never seen a pulse announcing where that")
                print(" fingerprint is reachable — meet a node that has, or ask")
                print(" them for their .onion address directly.\n")
                return
            print(f"\n Resolved {target_fp} → {resolved}")
            host = resolved

        connect(store, encounter_log, host, identity, pulse_ledger, contact_book, dm_store)

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

    elif "--card" in args:
        if not identity or not identity.has_encryption_key:
            print(" No identity with an encryption key yet.")
            return
        card = create_contact_card(identity)
        print("\n Your contact card — share it any way you like (message, QR, file).")
        print(" Someone who has this can send you a DM, even if you two never meet")
        print(" directly, as long as some chain of encounters connects you.\n")
        print(json.dumps(card, indent=2))
        print()

    elif "--add-contact" in args:
        idx = args.index("--add-contact")
        if idx + 1 >= len(args):
            print(" Usage: --add-contact <json-string-or-file-path>")
            return
        raw = args[idx + 1]
        if os.path.exists(raw):
            with open(raw, "r", encoding="utf-8") as f:
                raw = f.read()
        try:
            card = json.loads(raw)
        except json.JSONDecodeError:
            print(" Could not parse that as JSON.")
            return
        if not verify_contact_card(card):
            print(" Contact card failed verification — not adding it.")
            return
        if contact_book.record(card):
            print(f" Contact added: {card.get('node_name') or card['fingerprint']} [{card['fingerprint']}]")
        else:
            print(" Already have this contact (or a newer version of it).")

    elif "--contacts" in args:
        contacts = contact_book.all()
        if not contacts:
            print("\n No contacts yet. Share --card with someone, or --add-contact theirs.\n")
        else:
            print(f"\n {len(contacts)} contact(s):\n")
            for fp, card in contacts.items():
                print(f" {card.get('node_name') or '(unnamed)'}  [{fp}]")
            print()

    elif "--send" in args:
        idx = args.index("--send")
        if idx + 2 >= len(args):
            print(" Usage: --send <fingerprint> <message...>")
            return
        target_fp = args[idx + 1]
        message = " ".join(args[idx + 2:])
        if not identity or not identity.has_encryption_key:
            print(" No identity with an encryption key yet.")
            return
        contact = contact_book.get(target_fp)
        if not contact:
            print(f" No contact known with fingerprint {target_fp}.")
            print(" Use --add-contact first, or meet them once with --listen/--connect.")
            return
        try:
            dm = create_dm(identity, target_fp, contact["enc_public_key"], message)
        except ValueError as e:
            print(f" {e}")
            return
        dm_store.store(dm)
        print(f"\n Message sealed for {contact.get('node_name') or target_fp}.")
        print(" It will deliver next time you --listen or --connect with any node")
        print(" that eventually reaches them — even if that's not directly.\n")

    elif "--inbox" in args:
        if not identity or not identity.has_encryption_key:
            print(" No identity with an encryption key yet.")
            return
        dm_store.prune()
        inbox = dm_store.inbox(identity)
        if not inbox:
            print("\n No messages yet.\n")
        else:
            print(f"\n {len(inbox)} message(s):\n")
            for dm, plaintext in inbox:
                sender_card = contact_book.get(dm["from_fingerprint"])
                sender_name = sender_card.get("node_name") if sender_card else None
                print(f" from {sender_name or dm['from_fingerprint']}  ({dm['moment']})")
                print(f"   {plaintext}\n")

    else:
        print(" Usage:")
        print("   --listen                share your seals, receive theirs")
        print("   --connect               meet a node, exchange what you've lived")
        print("   --connect <ip>          connect to specific IP")
        print("   --connect <x>.onion     connect via Tor to onion address")
        print("   --connect <fingerprint> connect using a fingerprint (needs a recent pulse)")
        print("   --seal                  seal a new thought")
        print("   --list                  see your sealed thoughts")
        print("   --encounters            see your encounter history")
        print("   --identity              show this node's identity")
        print("   --onion                 show your .onion address (if Tor active)")
        print("   --pulse                 show the shared aliveness pulse")
        print("   --restore-identity      restore an identity from its 24-word paper backup")
        print("   --one-shot-identity     derive a deliberately burnable identity (advanced)")
        print("   --card                  print your contact card")
        print("   --add-contact <json>    import a contact card")
        print("   --contacts              list known contacts")
        print("   --send <fp> <message>   send a DM")
        print("   --inbox                 read DMs addressed to you")
        print()
        print(f" Transport: {tor_status()}")
        print()
        print(" First time? Start here:")
        print("   python phantom_node.py --seal")
        print()


if __name__ == "__main__":
    main()
