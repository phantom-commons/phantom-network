# phantom_node.py
#
# Node Zero to One — the first thought that travels.
# Phantom Network. March 9, 2026.
#
# WHAT THIS DOES:
# Sends a sealed thought from one Android phone to another,
# with no internet, no server, no account.
#
# HOW TO USE:
#
# Device A (sharing a thought):
#   1. Turn on mobile hotspot, name it "phantom-node"
#   2. python phantom_node.py --listen
#
# Device B (receiving):
#   1. Connect to "phantom-node" WiFi in phone settings
#   2. python phantom_node.py --connect
#
# DEPENDENCIES: Python standard library only.
# No pip install required. Works in Termux on any Android phone.
#
# ON ENCRYPTION:
# v0.1 communicates in plaintext over a local WiFi hotspot.
# This is deliberate and documented in SPEC_NODE_ZERO_TO_ONE.md.
# The seal is the integrity guarantee — tampered thoughts are
# rejected automatically. Encrypted transport comes next.
# Plaintext v0.1 is not a compromise of Phantom's principles.
# It is an honest beginning that names what it does not do yet.

import socket
import hashlib
import json
import threading
import sys
import os
from datetime import datetime, timezone

PORT = 7337
PHANTOM_VERSION = "0.1"
SEALS_FILE = "phantom_seals.json"

# ─────────────────────────────────────────────────────────
# SEAL FUNCTIONS
# Same algorithm as phantom_seed.py — never change.
# Changing separators or field order breaks all existing seals.
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
# LOCAL STORAGE
# Sealed thoughts live on your device first.
# They travel when you connect to another node.
# ─────────────────────────────────────────────────────────

def load_seals():
    if not os.path.exists(SEALS_FILE):
        return []
    with open(SEALS_FILE, "r") as f:
        return json.load(f)

def save_seal(entry):
    seals = load_seals()
    # Same stamp = same thought. No duplicates.
    if any(s["stamp"] == entry["stamp"] for s in seals):
        return False
    seals.append(entry)
    with open(SEALS_FILE, "w") as f:
        json.dump(seals, f, indent=2)
    return True

def get_latest_seal():
    seals = load_seals()
    if not seals:
        return None
    return seals[-1]

# ─────────────────────────────────────────────────────────
# NODE — LISTENING
# Device A: shares its sealed thoughts with visitors.
# ─────────────────────────────────────────────────────────

def handle_visitor(conn, addr):
    print(f"\n  Node connected: {addr[0]}")
    try:
        hello = json.dumps({
            "phantom": PHANTOM_VERSION, 
            "type": "hello"
        })
        conn.sendall((hello + "\n").encode())

        raw = conn.recv(4096).decode().strip()
        msg = json.loads(raw)

        if msg.get("type") != "request":
            print("  Unexpected message. Closing.")
            return

        thought = get_latest_seal()
        if not thought:
            response = json.dumps({
                "phantom": PHANTOM_VERSION,
                "type": "empty",
                "message": "No sealed thoughts yet."
            })
            conn.sendall((response + "\n").encode())
            print("  No sealed thoughts to share.")
            return

        payload = json.dumps({
            "phantom": PHANTOM_VERSION,
            "type": "seal",
            "idea": thought["idea"],
            "moment": thought["moment"],
            "stamp": thought["stamp"]
        })
        conn.sendall((payload + "\n").encode())
        print(f"  Sent: \"{thought['idea'][:60]}\"")

        raw = conn.recv(4096).decode().strip()
        ack = json.loads(raw)
        if ack.get("verified"):
            print("  ✓ Visitor verified the seal.")
        else:
            print("  ✗ Visitor could not verify the seal.")

    except Exception as e:
        print(f"  Error: {e}")
    finally:
        conn.close()

def listen():
    print("\n PHANTOM NODE — Listening")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    thought = get_latest_seal()
    if thought:
        print(f" Ready to share: \"{thought['idea'][:60]}\"")
    else:
        print(" No sealed thoughts yet.")
        print(" Seal something first: python phantom_node.py --seal")
        print()
        print(" (Listening anyway — seal something and a")
        print("  visitor can still connect later)")

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
                target=handle_visitor, 
                args=(conn, addr)
            )
            t.daemon = True
            t.start()
    except KeyboardInterrupt:
        print("\n Node stopping.")
    finally:
        server.close()

# ─────────────────────────────────────────────────────────
# VISITOR — CONNECTING
# Device B: finds a node and receives a sealed thought.
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
    print("\n PHANTOM VISITOR — Connecting")
    print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    if not host:
        print(" Looking for Phantom node...")
        # Try the common Android hotspot IP first
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
        print(" Make sure you are connected to the")
        print(" 'phantom-node' WiFi hotspot")
        print(" and the other phone is running:")
        print(" python phantom_node.py --listen")
        return

    print(f" Connecting to {host}:{PORT}...")
    try:
        conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        conn.settimeout(10)
        conn.connect((host, PORT))

        raw = conn.recv(4096).decode().strip()
        msg = json.loads(raw)
        if msg.get("type") != "hello":
            print(" Unexpected response. Not a Phantom node.")
            return

        print(" ✓ Phantom node found. Requesting thought...\n")

        request = json.dumps({
            "phantom": PHANTOM_VERSION, 
            "type": "request", 
            "count": 1
        })
        conn.sendall((request + "\n").encode())

        raw = conn.recv(4096).decode().strip()
        msg = json.loads(raw)

        if msg.get("type") == "empty":
            print(" Node has no sealed thoughts yet.")
            return

        if msg.get("type") != "seal":
            print(f" Unexpected message type: {msg.get('type')}")
            return

        idea = msg["idea"]
        moment = msg["moment"]
        stamp = msg["stamp"]
        verified = verify(idea, moment, stamp)

        print(" THOUGHT RECEIVED")
        print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f" Idea:   {idea}")
        print(f" Moment: {moment}")
        print(f" Stamp:  {stamp}")
        print()

        if verified:
            print(" ✓ SEAL VERIFIED — this thought is authentic.")
            saved = save_seal({
                "idea": idea, 
                "moment": moment, 
                "stamp": stamp
            })
            if saved:
                print(" ✓ Thought saved to your local seals.")
            else:
                print(" (You already have this thought.)")
        else:
            print(" ✗ SEAL INVALID — this thought may have")
            print("   been altered. Rejected.")

        print(" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")

        ack = json.dumps({
            "phantom": PHANTOM_VERSION, 
            "type": "ack", 
            "verified": verified
        })
        conn.sendall((ack + "\n").encode())

    except ConnectionRefusedError:
        print(f" Could not connect to {host}:{PORT}")
        print(" Is the other phone running:")
        print(" python phantom_node.py --listen ?")
    except Exception as e:
        print(f" Error: {e}")
    finally:
        conn.close()

# ─────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────

def main():
    print("\n PHANTOM NETWORK")
    print(" Privacy is not for hiding. It is for being free.\n")

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
        idea = input("\n Enter idea to seal:\n > ").strip()
        if idea:
            entry = seal(idea)
            save_seal(entry)
            print(f"\n PHANTOM SEAL")
            print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            print(f" Idea:   {entry['idea']}")
            print(f" Moment: {entry['moment']}")
            print(f" Stamp:  {entry['stamp']}")
            print(f" ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n")
            print(" Sealed and saved. Ready to share.\n")

    elif "--list" in args:
        seals = load_seals()
        if not seals:
            print(" No sealed thoughts yet.")
        else:
            print(f" {len(seals)} sealed thought(s):\n")
            for i, s in enumerate(seals, 1):
                print(f" [{i}] {s['idea'][:70]}")
                print(f"     {s['moment']}")
                print()

    else:
        print(" Usage:")
        print("   --listen       share your thoughts")
        print("   --connect      receive a thought")
        print("   --connect <ip> connect to specific IP")
        print("   --seal         seal a new thought")
        print("   --list         see your sealed thoughts")
        print()
        print(" First time? Start here:")
        print("   python phantom_node.py --seal")
        print()

if __name__ == "__main__":
    main()
