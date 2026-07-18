# phantom_relay.py — v0.1
#
# Multi-hop propagation for Phantom Network.
#
# "The organism evolves. The principles do not."
#
# What this does:
#   A thought sealed on Device A can travel to B, then to C,
#   then to D — without A and D ever meeting directly.
#
#   This is what makes Phantom a network.
#   phantom_node.py is two devices meeting.
#   phantom_relay.py is memory that persists beyond the meeting.
#
# How it works:
#   A relay node accepts incoming seals from any Phantom node,
#   stores them (permanent mode only, with verification),
#   and shares them in future encounters — same bloom/delta
#   protocol as phantom_node.py.
#
#   A relay is just a node that runs continuously and is
#   reachable by address (IP or .onion) rather than by
#   local WiFi scan. Anyone can run one. No permission needed.
#
# The Lagos Protocol:
#   A relay node can run on a secondhand Android phone
#   on a home WiFi network. No server. No account. No cost
#   beyond the electricity the phone was already using.
#
# Trust model:
#   Relays forward only PERMANENT seals with valid stamps.
#   A tampered seal fails verification and is dropped.
#   A relay cannot create seals. It can only carry them.
#   A relay learns the IP addresses of nodes that connect —
#   use Tor (Level 2+) to protect this.
#
# SUIJURIS integration:
#   Each hop served is recorded in the local SUIJURIS ledger.
#   The relay earns contribution weight for each seal forwarded.
#   This is how relay operators are recognized — not by promise,
#   but by the permanent record of what they carried.
#
# HISTORY:
#   v0.1 — March 12, 2026. First relay implementation.
#          Multi-hop propagation. SUIJURIS integration.
#          Tor-aware (uses make_socket from phantom_core).

import socket
import threading
import json
import sys
import os
import time
import base64
from datetime import datetime, timezone

from phantom_core import (
    PHANTOM_VERSION, PORT, MAX_MESSAGE_SIZE,
    MODE_PERMANENT,
    seal, verify, KeyManager, SealStore, EncounterLog, NodeIdentity,
    build_bloom, compute_delta,
    send_json, recv_json,
    init_tor, make_socket, tor_status, get_onion_address, ONION_FILE,
)

RELAY_VERSION = "0.1"
RELAY_PORT = 7338   # Different port so a relay and node can coexist on one machine

MIN_COMPATIBLE_VERSION = "0.3"

# ─────────────────────────────────────────────────────────
# RELAY STATISTICS
# Held in memory — reset on restart. Purposeful.
# The relay's value is in what it carries, not its uptime.
# ─────────────────────────────────────────────────────────

class RelayStats:
    def __init__(self):
        self.started = datetime.now(timezone.utc)
        self.connections = 0
        self.seals_received = 0
        self.seals_forwarded = 0
        self.lock = threading.Lock()

    def connection(self):
        with self.lock:
            self.connections += 1

    def received(self, n):
        with self.lock:
            self.seals_received += n

    def forwarded(self, n):
        with self.lock:
            self.seals_forwarded += n

    def show(self):
        uptime = datetime.now(timezone.utc) - self.started
        hours = int(uptime.total_seconds() // 3600)
        minutes = int((uptime.total_seconds() % 3600) // 60)
        print(f"\n RELAY STATISTICS")
        print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f" Uptime:     {hours}h {minutes}m")
        print(f" Connections: {self.connections}")
        print(f" Received:   {self.seals_received} seal(s)")
        print(f" Forwarded:  {self.seals_forwarded} seal(s)")
        print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")


_stats = RelayStats()


# ─────────────────────────────────────────────────────────
# RELAY ENCOUNTER HANDLER
#
# Same bloom/delta protocol as phantom_node.py.
# The relay is just a node that never originated any seals —
# it only carries what others have given it.
# ─────────────────────────────────────────────────────────

def _check_version(peer_version):
    try:
        peer_parts = [int(x) for x in peer_version.split(".")]
        min_parts = [int(x) for x in MIN_COMPATIBLE_VERSION.split(".")]
        return peer_parts >= min_parts
    except (ValueError, AttributeError):
        return False


def handle_relay_encounter(conn, addr, store, encounter_log, identity, ledger=None):
    """
    Handle one incoming connection.
    Accept seals from the visitor, share what they don't have.
    """
    peer = addr[0]
    _stats.connection()

    sent_stamps = set()
    received_stamps = set()

    try:
        # Step 1 — Hello
        hello_msg = {
            "phantom": PHANTOM_VERSION,
            "type": "hello",
            "relay": True,
            "relay_version": RELAY_VERSION,
            "min_version": MIN_COMPATIBLE_VERSION,
        }
        if identity and identity.public_key_b64:
            hello_msg["node_pubkey"] = identity.public_key_b64
            hello_msg["node_name"] = identity.node_name
            hello_msg["node_fingerprint"] = identity.fingerprint
        send_json(conn, hello_msg)

        hello = recv_json(conn)
        if hello.get("type") != "hello":
            return
        peer_version = hello.get("phantom", "unknown")
        if not _check_version(peer_version):
            send_json(conn, {
                "type": "error",
                "message": f"Version {peer_version} not compatible. Need >= {MIN_COMPATIBLE_VERSION}"
            })
            return

        peer_name = hello.get("node_name", "visitor")
        peer_fp = hello.get("node_fingerprint", "")[:12]
        print(f"  ↔ {peer_name} [{peer_fp}] — v{peer_version}")

        # Step 2 — Bloom exchange
        my_stamps = store.get_all_stamps()
        my_bloom, my_bloom_size = build_bloom(my_stamps)
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "bloom",
            "bloom": base64.b64encode(my_bloom).decode('ascii'),
            "bloom_size": my_bloom_size,
            "seal_count": len(my_stamps),
        })

        their_bloom_msg = recv_json(conn)
        if their_bloom_msg.get("type") != "bloom":
            return

        their_bloom_data = their_bloom_msg.get("bloom", "")
        if isinstance(their_bloom_data, str):
            their_bloom = base64.b64decode(their_bloom_data)
        else:
            their_bloom = bytes(their_bloom_data)
        their_bloom_size = their_bloom_msg.get("bloom_size", len(their_bloom) * 8)

        # Step 3 — Send our delta (signed if identity exists)
        delta_stamps = compute_delta(my_stamps, their_bloom, their_bloom_size)
        delta_seals = store.get_seals_by_stamps(delta_stamps)
        if identity and identity.has_private_key:
            delta_seals = [identity.sign_seal(s) for s in delta_seals]

        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "delta",
            "seals": delta_seals,
            "count": len(delta_seals),
        })
        sent_stamps = {s["stamp"] for s in delta_seals}
        _stats.forwarded(len(sent_stamps))

        # Step 4 — Receive their delta
        their_delta_msg = recv_json(conn)
        if their_delta_msg.get("type") != "delta":
            return

        incoming = their_delta_msg.get("seals", [])
        new_seals = 0

        for entry in incoming:
            # Relay policy: only accept PERMANENT seals with valid stamps
            if entry.get("mode", MODE_PERMANENT) != MODE_PERMANENT:
                continue
            if not verify(entry["idea"], entry["moment"], entry["stamp"]):
                print(f"  ✗ Rejected tampered seal: {entry.get('stamp', '?')[:20]}")
                continue
            if store.save(entry):
                received_stamps.add(entry["stamp"])
                new_seals += 1
                # Record relay contribution for each new seal forwarded in future
                if ledger:
                    try:
                        from suijuris import record_relay
                        fp = identity.fingerprint if identity else None
                        record_relay(ledger, entry["stamp"], node_fingerprint=fp)
                    except ImportError:
                        pass

        _stats.received(new_seals)
        if new_seals:
            print(f"  + {new_seals} new seal(s) accepted")

        # Step 5 — Seal the encounter
        encounter_stamp = encounter_log.log(
            peer, len(sent_stamps), len(received_stamps), received_stamps
        )
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "encounter_sealed",
            "encounter_stamp": encounter_stamp,
            "sent": len(sent_stamps),
            "received": len(received_stamps),
        })

    except json.JSONDecodeError:
        pass
    except (ConnectionError, ValueError, OSError):
        pass
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────
# RELAY SERVER
# ─────────────────────────────────────────────────────────

def run_relay(store, encounter_log, identity=None, port=RELAY_PORT, ledger=None):
    """
    Start a relay node. Listens indefinitely.
    Accepts connections from any Phantom node and participates
    in the standard bloom/delta exchange protocol.
    """
    print(f"\n PHANTOM RELAY — v{RELAY_VERSION} (Protocol: {PHANTOM_VERSION})")
    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" Transport: {tor_status()}")

    if identity:
        print(f" Identity:  {identity.node_name or 'unnamed'} [{identity.fingerprint}]")

    my_stamps = store.get_all_stamps()
    print(f" Carrying:  {len(my_stamps)} seal(s)")
    print(f" Port:      {port}")

    onion = get_onion_address()
    if onion:
        print(f"\n Share this onion address for anonymous relay access:")
        print(f"   {onion}")
        print(f" Nodes connect with:")
        print(f"   python phantom_node.py --connect {onion}")
    else:
        ip = _get_local_ip()
        if ip:
            print(f"\n Reachable at: {ip}:{port}")
            print(f" Nodes connect with:")
            print(f"   python phantom_node.py --connect {ip}")

    print(f"\n Relay running. Press Ctrl+C to stop.\n")

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", port))
    server.listen(20)

    # Status thread — prints stats every 60 seconds
    def _status_loop():
        while True:
            time.sleep(60)
            _stats.show()

    t = threading.Thread(target=_status_loop, daemon=True)
    t.start()

    try:
        while True:
            conn, addr = server.accept()
            thread = threading.Thread(
                target=handle_relay_encounter,
                args=(conn, addr, store, encounter_log, identity, ledger),
                daemon=True,
            )
            thread.start()
    except KeyboardInterrupt:
        print("\n Relay stopping.")
        _stats.show()
    finally:
        server.close()


def _get_local_ip():
    """Best-effort local IP detection."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


# ─────────────────────────────────────────────────────────
# CONNECT TO A RELAY
#
# The visitor side — connects to a specific relay address
# and exchanges seals using the standard protocol.
# ─────────────────────────────────────────────────────────

def connect_to_relay(store, encounter_log, host, identity=None, port=RELAY_PORT, ledger=None):
    """
    Connect to a relay node at a specific address.
    host can be an IP address or a .onion address.
    """
    print(f"\n PHANTOM — Connecting to relay")
    print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    print(f" Transport: {tor_status()}")
    print(f" Relay:     {host}:{port}\n")

    sent_stamps = set()
    received_stamps = set()
    conn = None

    try:
        conn = make_socket()
        conn.settimeout(30)
        conn.connect((host, port))

        # Step 1 — Hello
        hello = recv_json(conn)
        if hello.get("type") != "hello":
            print(" Not a Phantom relay.")
            return

        peer_version = hello.get("phantom", "unknown")
        if not _check_version(peer_version):
            print(f" Incompatible version: {peer_version}")
            return

        is_relay = hello.get("relay", False)
        relay_version = hello.get("relay_version", "?")
        if is_relay:
            print(f" Phantom relay v{relay_version} (protocol v{peer_version})")
        else:
            print(f" Phantom node v{peer_version}")

        hello_msg = {
            "phantom": PHANTOM_VERSION,
            "type": "hello",
            "min_version": MIN_COMPATIBLE_VERSION,
        }
        if identity and identity.public_key_b64:
            hello_msg["node_pubkey"] = identity.public_key_b64
            hello_msg["node_name"] = identity.node_name
            hello_msg["node_fingerprint"] = identity.fingerprint
        send_json(conn, hello_msg)

        # Step 2 — Bloom exchange
        their_bloom_msg = recv_json(conn)
        if their_bloom_msg.get("type") == "error":
            print(f" Relay rejected: {their_bloom_msg.get('message', 'unknown')}")
            return
        if their_bloom_msg.get("type") != "bloom":
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
            "seal_count": len(my_stamps),
        })
        print(f" I carry {len(my_stamps)} seal(s). Relay carries {their_count}.")

        # Step 3 — Receive delta from relay
        their_delta_msg = recv_json(conn)
        if their_delta_msg.get("type") != "delta":
            return

        incoming = their_delta_msg.get("seals", [])
        print(f"\n Receiving {len(incoming)} seal(s) from relay.")

        for entry in incoming:
            if verify(entry["idea"], entry["moment"], entry["stamp"]):
                sig_status = NodeIdentity.verify_signed_seal(entry)
                sig_label = " (signed)" if sig_status is True else (" (BAD SIGNATURE)" if sig_status is False else "")
                if store.save(entry):
                    received_stamps.add(entry["stamp"])
                    print(f" + \"{entry['idea'][:50]}\"{sig_label}")
                else:
                    print(f" (Already have: \"{entry['idea'][:40]}\")")
            else:
                print(f" ✗ Rejected tampered seal: \"{entry['idea'][:40]}\"")

        # Step 4 — Send our delta to relay
        delta_stamps = compute_delta(my_stamps, their_bloom, their_bloom_size)
        delta_seals = store.get_seals_by_stamps(delta_stamps)
        if identity and identity.has_private_key:
            delta_seals = [identity.sign_seal(s) for s in delta_seals]

        print(f"\n Sending {len(delta_seals)} seal(s) to relay.")
        send_json(conn, {
            "phantom": PHANTOM_VERSION,
            "type": "delta",
            "seals": delta_seals,
            "count": len(delta_seals),
        })
        sent_stamps = {s["stamp"] for s in delta_seals}

        # Step 5 — Encounter seal
        seal_msg = recv_json(conn)
        _their_encounter_stamp = seal_msg.get("encounter_stamp", "")  # noqa: not yet
        # cross-verified against anything — there's no reciprocal-proof
        # protocol between the two sides' stamps yet. Recorded here so
        # it's visible in a debugger/log, not silently dropped.
        our_encounter_stamp = encounter_log.log(
            host, len(sent_stamps), len(received_stamps), received_stamps
        )

        # Record encounter in SUIJURIS ledger
        if ledger:
            try:
                from suijuris import record_encounter
                peer_fp = hello.get("node_fingerprint", "relay")[:12]
                node_fp = identity.fingerprint if identity else None
                record_encounter(ledger, peer_fp, len(sent_stamps), len(received_stamps), node_fingerprint=node_fp)
            except ImportError:
                pass

        print(f"\n RELAY SYNC COMPLETE")
        print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f" Received: {len(received_stamps)} seal(s)")
        print(f" Sent:     {len(sent_stamps)} seal(s)")
        print(f" Stamp:    {our_encounter_stamp[:24]}...")
        print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

    except ConnectionRefusedError:
        print(f" Could not connect to relay at {host}:{port}")
        print(" Is the relay running?  python phantom_relay.py --run")
    except json.JSONDecodeError as e:
        print(f" Malformed message from relay: {e}")
    except (ConnectionError, ValueError, OSError) as e:
        print(f" Connection error: {e}")
    finally:
        if conn:
            conn.close()


# ─────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────

def _load_or_create_identity(km):
    identity = NodeIdentity.load(key=km.key)
    if identity:
        return identity
    if not NodeIdentity.available():
        return None
    name = input(" Relay name (or Enter to skip): ").strip() or None
    identity = NodeIdentity.generate(node_name=name)
    identity.save(key=km.key)
    print(f" Identity created: {identity.node_name or '(unnamed)'} [{identity.fingerprint}]\n")
    return identity


def main():
    print(f"\n PHANTOM RELAY — v{RELAY_VERSION}")
    print(" Memory that persists beyond the meeting.\n")

    args = sys.argv[1:]

    if "--help" in args or "-h" in args:
        print(" Usage:")
        print("   --run                  start this machine as a relay node")
        print("   --run --port <n>       run on a specific port (default: 7338)")
        print("   --connect <host>       sync with a relay at host[:port]")
        print("   --stats                show relay statistics")
        print()
        print(" What a relay does:")
        print("   Accepts sealed thoughts from any Phantom node,")
        print("   carries them, and shares them with future visitors.")
        print("   Thoughts travel farther than any single meeting.")
        print()
        print(" SUIJURIS:")
        print("   Every seal relayed is recorded in your contribution ledger.")
        print("   Run: python suijuris.py  to see your contribution history.")
        print()
        return

    init_tor(port=RELAY_PORT)

    km = KeyManager()
    km.init_encryption()

    store = SealStore(km)
    encounter_log = EncounterLog(km)

    # Try to load SUIJURIS ledger
    ledger = None
    try:
        from suijuris import Ledger as SuijurisLedger
        ledger = SuijurisLedger(km)
    except ImportError:
        pass

    if "--run" in args:
        identity = _load_or_create_identity(km)

        port = RELAY_PORT
        if "--port" in args:
            idx = args.index("--port")
            if idx + 1 < len(args):
                try:
                    port = int(args[idx + 1])
                except ValueError:
                    print(f" Invalid port. Using default: {RELAY_PORT}")

        run_relay(store, encounter_log, identity, port=port, ledger=ledger)

    elif "--connect" in args:
        idx = args.index("--connect")
        if idx + 1 >= len(args):
            print(" Usage: phantom_relay.py --connect <host>")
            print(" Example: phantom_relay.py --connect 192.168.1.42")
            print(" Example: phantom_relay.py --connect abc123.onion")
            return

        host_arg = args[idx + 1]
        port = RELAY_PORT

        # Allow host:port syntax
        if ":" in host_arg and not host_arg.endswith(".onion"):
            parts = host_arg.rsplit(":", 1)
            host_arg = parts[0]
            try:
                port = int(parts[1])
            except ValueError:
                pass

        identity = _load_or_create_identity(km)
        connect_to_relay(store, encounter_log, host_arg, identity, port=port, ledger=ledger)

    elif "--stats" in args:
        _stats.show()

    else:
        print(" Usage:")
        print("   --run                  start relay")
        print("   --connect <host>       sync with a relay")
        print("   --help                 full help")
        print()


if __name__ == "__main__":
    main()
