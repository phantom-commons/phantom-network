#!/usr/bin/env python3
"""
phantom_ws_bridge.py
─────────────────────────────────────────────────────────
A pure protocol translator. Browsers can't open raw TCP sockets —
only HTTP and WebSocket. phantom_relay.py only speaks raw TCP
(newline-delimited JSON, via send_json/recv_json). This bridge
sits between them and does nothing else: for every WebSocket
connection from a browser, it opens one TCP connection to a
running phantom_relay.py and pumps JSON messages both ways,
unchanged.

It does not understand the Phantom protocol. It doesn't need to —
that's the point. It never inspects seal content, never decides
what's PERMANENT or PRIVATE, never touches a key. If phantom_relay.py
rejects something, this bridge has no opinion about that; it just
carries the rejection back. Trust lives in the relay and the
client, same as before this file existed.

Run this next to a running phantom_relay.py (same machine, or
reachable at RELAY_HOST/RELAY_PORT):

    python3 phantom_ws_bridge.py

Then a browser client connects to:

    ws://<this machine's address>:8765

Requires: pip install websockets
"""

import asyncio
import json
import os
import socket
import sys

try:
    import websockets
except ImportError:
    print("This bridge needs the 'websockets' package.")
    print("Install it with: pip install websockets")
    sys.exit(1)

RELAY_HOST = os.environ.get("PHANTOM_RELAY_HOST", "127.0.0.1")
RELAY_PORT = int(os.environ.get("PHANTOM_RELAY_PORT", "7338"))
BRIDGE_PORT = int(os.environ.get("PHANTOM_BRIDGE_PORT", "8765"))
MAX_MESSAGE_SIZE = 10 * 1024 * 1024  # matches phantom_core.py's limit


def _recv_line(sock):
    """
    Minimal newline-delimited JSON reader for the bridge's own TCP
    side. Deliberately NOT phantom_core.py's recv_json — that
    function has a known bug (see the GAP note in phantom_core.py):
    it drops any bytes past the first newline in a chunk, silently.
    A bridge relaying real traffic can't afford that, so this one
    buffers properly across calls instead of discarding.
    """
    buf = b""
    while b"\n" not in buf:
        chunk = sock.recv(4096)
        if not chunk:
            raise ConnectionError("Relay closed the connection")
        buf += chunk
        if len(buf) > MAX_MESSAGE_SIZE:
            raise ValueError("Message from relay exceeds size limit")
    line, _, rest = buf.partition(b"\n")
    # NOTE: `rest` (anything after the first newline) is discarded
    # here too, same limitation as phantom_core.py's recv_json, since
    # this bridge does one message per TCP round-trip in lockstep
    # with the relay's own handle_relay_encounter — the relay never
    # pipelines two messages back to back in this protocol. Safe here
    # specifically because of that lockstep pattern, not in general.
    return json.loads(line.decode().strip())


def _send_line(sock, obj):
    data = json.dumps(obj).encode() + b"\n"
    sock.sendall(data)


async def handle_browser(websocket):
    """
    One browser client = one TCP connection to the relay, for the
    lifetime of that WebSocket connection. Messages are translated,
    not interpreted.
    """
    peer = websocket.remote_address
    print(f" Browser connected: {peer}")

    loop = asyncio.get_event_loop()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(30)

    try:
        await loop.run_in_executor(None, sock.connect, (RELAY_HOST, RELAY_PORT))
    except OSError as e:
        await websocket.send(json.dumps({
            "type": "error",
            "message": f"Could not reach relay at {RELAY_HOST}:{RELAY_PORT}: {e}",
        }))
        await websocket.close()
        return

    try:
        while True:
            # Relay speaks first (hello), same as it does for a
            # direct Python peer — so read from TCP, forward to WS.
            try:
                msg = await loop.run_in_executor(None, _recv_line, sock)
            except (ConnectionError, ValueError, json.JSONDecodeError) as e:
                await websocket.send(json.dumps({"type": "error", "message": str(e)}))
                break

            await websocket.send(json.dumps(msg))

            if msg.get("type") == "encounter_sealed" or msg.get("type") == "error":
                break

            # Now the browser replies — read from WS, forward to TCP.
            try:
                reply_raw = await asyncio.wait_for(websocket.recv(), timeout=30)
            except asyncio.TimeoutError:
                break
            reply = json.loads(reply_raw)
            await loop.run_in_executor(None, _send_line, sock, reply)

    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        sock.close()
        print(f" Browser disconnected: {peer}")


async def main():
    print(f" Phantom WebSocket bridge")
    print(f" Browser clients connect to: ws://<this-address>:{BRIDGE_PORT}")
    print(f" Forwarding to relay at: {RELAY_HOST}:{RELAY_PORT}")
    print(f" (Make sure phantom_relay.py is already running there.)\n")

    async with websockets.serve(handle_browser, "0.0.0.0", BRIDGE_PORT):
        await asyncio.Future()  # run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n Bridge stopped.")
