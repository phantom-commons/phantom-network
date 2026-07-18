# phantom_daemon.py — v1.1 (with API Token Auth)
#
# One process, three jobs, one set of in-memory stores:
#   1. Listens for incoming encounters (same as phantom_node.py --listen)
#   2. Periodically reaches out to known-alive peers on its own
#      (auto-connect, using the pulse ledger's address book)
#   3. Serves a local HTTP API on 127.0.0.1 for the dashboard, or any
#      future UI, to read/write through
#
# WHY ONE PROCESS: phantom_api.py used to be a separate process reading
# the same JSON files as phantom_node.py. Two independent processes,
# each with their own in-memory cache, both flushing whole files to
# disk — whichever saves last silently wins, dropping the other's
# writes. Merging into one process with one set of store objects
# (each now internally lock-protected, see phantom_core.py) makes that
# race structurally impossible instead of trying to avoid it by
# convention.
#
# SECURITY NOTE (v1.1): The local API is now protected by a random token
# generated at startup. The token is printed to the console. Any client
# (web UI, curl) must include X-Phantom-Token header with that token.
# This prevents other websites/tabs in your browser from accessing your
# seals without your knowledge. Keep the token secret.
#
# Usage:
#   python phantom_daemon.py
#   python phantom_daemon.py --api-port 7338 --auto-connect-interval 300
#   python phantom_daemon.py --no-api
#   python phantom_daemon.py --no-autoconnect
#   python phantom_daemon.py --no-api-auth   # Disable token auth (INSECURE, only for debugging)

import sys
import threading
import time
import base64
import hashlib
import os
import webbrowser
import secrets  # [AUTH] Added for secure token generation

from flask import Flask, request, jsonify, send_from_directory, abort

import phantom_node  # reuse listen(), connect(), identity helpers — no duplication
from phantom_core import (
    KeyManager, SealStore, EncounterLog, NodeIdentity,
    PulseLedger, ReceiptLedger, ContactBook, DMStore,
    seal as core_seal, verify as core_verify,
    create_contact_card, verify_contact_card, create_dm,
    PHANTOM_VERSION, MODE_PRIVATE, MODE_PERMANENT, MODE_EPHEMERAL, DEFAULT_MODE,
    CRYPTO_AVAILABLE, PULSE_TTL_SECONDS,
    init_tor, tor_status, get_onion_address,
)

DEFAULT_API_PORT = 7338
DEFAULT_AUTO_CONNECT_INTERVAL = 300  # 5 minutes

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))        # phantom/core/
APP_DIR = os.path.join(ROOT_DIR, '..', '..', 'app')           # Node/app/ (two levels up from phantom/core/)

app = Flask(__name__)
state = {}  # populated once in main(): km, store, encounter_log, pulse_ledger,
            # receipt_ledger, contact_book, dm_store, identity

# [AUTH] Global token variable - set in main()
API_TOKEN = None


# [AUTH] Decorator to protect API endpoints
def require_token(f):
    def wrapper(*args, **kwargs):
        # Allow skipping auth if explicitly disabled (debug only)
        if not API_TOKEN:
            return f(*args, **kwargs)
        
        # Check for token in header (X-Phantom-Token) or Bearer
        token = request.headers.get('X-Phantom-Token')
        if not token:
            auth_header = request.headers.get('Authorization', '')
            if auth_header.startswith('Bearer '):
                token = auth_header[7:]
        
        if not token or token != API_TOKEN:
            return jsonify({
                "error": "unauthorized",
                "message": "Invalid or missing API token. Check the daemon console for the token."
            }), 401
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


# ─────────────────────────────────────────────────────────
# AUTO-CONNECT LOOP
# ─────────────────────────────────────────────────────────

def auto_connect_loop(interval):
    """
    Every `interval` seconds, try to reach every fingerprint this node
    has a known, unexpired address for (from its own pulse ledger),
    skipping itself. Failures are logged and skipped, not fatal.
    """
    identity = state["identity"]
    pulse_ledger = state["pulse_ledger"]

    while True:
        time.sleep(interval)
        try:
            fingerprints = pulse_ledger.known_fingerprints()
        except Exception as e:
            print(f"[auto-connect] Could not read pulse ledger: {e}")
            continue

        for fp in fingerprints:
            if identity and fp == identity.fingerprint:
                continue
            address = pulse_ledger.address_for(fp)
            if not address:
                continue
            print(f"\n[auto-connect] Reaching out to {fp[:12]}... at {address}")
            try:
                phantom_node.connect(
                    state["store"], state["encounter_log"], address,
                    identity, pulse_ledger, state["contact_book"], state["dm_store"],
                )
            except Exception as e:
                print(f"[auto-connect] Could not reach {fp[:12]}...: {e}")


# ─────────────────────────────────────────────────────────
# LOCAL API — protected by token
# ─────────────────────────────────────────────────────────

def _seal_to_dict(s, full=True):
    out = {"stamp": s["stamp"], "moment": s["moment"], "mode": s.get("mode")}
    if full:
        out["idea"] = s["idea"]
    else:
        out["idea_preview"] = s["idea"][:70]
    return out


@app.route("/api/status", methods=["GET"])
@require_token  # [AUTH] Added decorator
def status():
    store = state["store"]
    encounter_log = state["encounter_log"]
    pulse_ledger = state["pulse_ledger"]
    identity = state["identity"]

    seals = store.load()
    counts = {
        "private": sum(1 for s in seals if s.get("mode") == MODE_PRIVATE),
        "permanent": sum(1 for s in seals if s.get("mode") == MODE_PERMANENT),
        "ephemeral": sum(1 for s in seals if s.get("mode") == MODE_EPHEMERAL),
    }
    pulse_ledger.prune()

    return jsonify({
        "phantom_version": PHANTOM_VERSION,
        "seal_count": len(seals),
        "seal_counts_by_mode": counts,
        "encounter_count": len(encounter_log.load()),
        "identity": {
            "node_name": identity.node_name,
            "fingerprint": identity.fingerprint,
        } if identity else None,
        "transport": tor_status(),
        "onion_address": get_onion_address(),
        "shared_pulse": pulse_ledger.alive_fraction(),
    })


@app.route("/api/seals", methods=["GET"])
@require_token  # [AUTH] Added decorator
def list_seals():
    seals = state["store"].load()
    return jsonify({"count": len(seals), "seals": [_seal_to_dict(s, full=False) for s in seals]})


@app.route("/api/seals/<stamp>", methods=["GET"])
@require_token  # [AUTH] Added decorator
def get_seal(stamp):
    for s in state["store"].load():
        if s["stamp"] == stamp:
            return jsonify(_seal_to_dict(s, full=True))
    return jsonify({"error": "not_found"}), 404


@app.route("/api/seals", methods=["POST"])
@require_token  # [AUTH] Added decorator
def create_seal():
    data = request.get_json(silent=True) or {}
    idea = data.get("idea", "")
    mode = data.get("mode", DEFAULT_MODE)
    if mode not in (MODE_PRIVATE, MODE_PERMANENT, MODE_EPHEMERAL):
        return jsonify({"error": "invalid_mode"}), 400
    try:
        entry = core_seal(idea, mode)
    except ValueError as e:
        return jsonify({"error": "invalid_idea", "message": str(e)}), 400
    saved = state["store"].save(entry)
    return jsonify({"saved": saved, "seal": _seal_to_dict(entry)}), (201 if saved else 200)


@app.route("/api/verify", methods=["POST"])
@require_token  # [AUTH] Added decorator
def verify_seal():
    data = request.get_json(silent=True) or {}
    valid = core_verify(data.get("idea", ""), data.get("moment", ""), data.get("stamp", ""))
    return jsonify({"valid": valid})


@app.route("/api/encounters", methods=["GET"])
@require_token  # [AUTH] Added decorator
def list_encounters():
    encounters = state["encounter_log"].load()
    return jsonify({"count": len(encounters), "encounters": encounters})


@app.route("/api/pulse", methods=["GET"])
@require_token  # [AUTH] Added decorator
def pulse_view():
    pulse_ledger = state["pulse_ledger"]
    pulse_ledger.prune()
    return jsonify({
        "shared_pulse": pulse_ledger.alive_fraction(),
        "known": pulse_ledger.known_fingerprints(),
        "alive": pulse_ledger.alive_fingerprints(),
    })


@app.route("/api/receipts", methods=["GET"])
@require_token  # [AUTH] Added decorator
def receipts_view():
    receipt_ledger = state["receipt_ledger"]
    identity = state["identity"]
    result = {"count": len(receipt_ledger.all_receipts()), "receipts": receipt_ledger.all_receipts()}
    if identity:
        net, earned, spent = receipt_ledger.balance(identity.fingerprint)
        count, unique = receipt_ledger.reputation(identity.fingerprint)
        result["this_node"] = {"balance": net, "earned": earned, "spent": spent,
                                "receipts_carried": count, "unique_requesters": unique}
    return jsonify(result)


@app.route("/api/contacts", methods=["GET"])
@require_token  # [AUTH] Added decorator
def list_contacts():
    return jsonify(state["contact_book"].all())


@app.route("/api/contacts", methods=["POST"])
@require_token  # [AUTH] Added decorator
def add_contact():
    card = request.get_json(silent=True) or {}
    if not verify_contact_card(card):
        return jsonify({"error": "invalid_card"}), 400
    added = state["contact_book"].record(card)
    return jsonify({"added": added})


@app.route("/api/card", methods=["GET"])
@require_token  # [AUTH] Added decorator
def my_card():
    identity = state["identity"]
    if not identity or not identity.has_encryption_key:
        return jsonify({"error": "no_identity"}), 400
    return jsonify(create_contact_card(identity))


@app.route("/api/dm/send", methods=["POST"])
@require_token  # [AUTH] Added decorator
def send_dm():
    data = request.get_json(silent=True) or {}
    target_fp = data.get("to", "")
    message = data.get("message", "")
    identity = state["identity"]
    if not identity or not identity.has_encryption_key:
        return jsonify({"error": "no_identity"}), 400
    contact = state["contact_book"].get(target_fp)
    if not contact:
        return jsonify({"error": "unknown_contact",
                         "message": "No contact card for that fingerprint yet."}), 404
    try:
        dm = create_dm(identity, target_fp, contact["enc_public_key"], message)
    except ValueError as e:
        return jsonify({"error": "invalid_message", "message": str(e)}), 400
    state["dm_store"].store(dm)
    return jsonify({"queued": True})


@app.route("/api/dm/inbox", methods=["GET"])
@require_token  # [AUTH] Added decorator
def dm_inbox():
    identity = state["identity"]
    if not identity or not identity.has_encryption_key:
        return jsonify({"error": "no_identity"}), 400
    dm_store = state["dm_store"]
    dm_store.prune()
    contact_book = state["contact_book"]
    inbox = dm_store.inbox(identity)
    out = []
    for dm, plaintext in inbox:
        sender_card = contact_book.get(dm["from_fingerprint"])
        out.append({
            "from_fingerprint": dm["from_fingerprint"],
            "from_name": sender_card.get("node_name") if sender_card else None,
            "moment": dm["moment"],
            "message": plaintext,
        })
    return jsonify({"count": len(out), "messages": out})


# ─────────────────────────────────────────────────────────
# STATIC APP (PWA — served from ../app/)
# Service workers require http://localhost, not file://
# ─────────────────────────────────────────────────────────

@app.route("/")
def app_index():
    if not os.path.isdir(APP_DIR):
        abort(404, description="app/ folder not found — run from the repository root layout")
    return send_from_directory(APP_DIR, "index.html")


@app.route("/manifest.json")
def app_manifest():
    return send_from_directory(APP_DIR, "manifest.json")


@app.route("/sw.js")
def app_sw():
    return send_from_directory(APP_DIR, "sw.js", mimetype="application/javascript")


@app.route("/<path:filename>")
def app_static(filename):
    if filename.startswith("api/"):
        abort(404)
    path = os.path.join(APP_DIR, filename)
    if not os.path.isfile(path):
        abort(404)
    return send_from_directory(APP_DIR, filename)


@app.route("/api/connect", methods=["POST"])
@require_token  # [AUTH] Added decorator
def api_connect():
    data = request.get_json(silent=True) or {}
    host = data.get("host") or None

    def do_connect():
        try:
            phantom_node.connect(
                state["store"], state["encounter_log"], host,
                state["identity"], state["pulse_ledger"],
                state["contact_book"], state["dm_store"],
            )
        except Exception as e:
            print(f"[api-connect] Error: {e}")

    threading.Thread(target=do_connect, daemon=True).start()
    return jsonify({"started": True, "host": host or "auto-scan"})


# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────

def main():
    global API_TOKEN  # [AUTH] We need to write to the global variable

    args = sys.argv[1:]

    api_port = DEFAULT_API_PORT
    if "--api-port" in args:
        api_port = int(args[args.index("--api-port") + 1])

    auto_connect_interval = DEFAULT_AUTO_CONNECT_INTERVAL
    if "--auto-connect-interval" in args:
        auto_connect_interval = int(args[args.index("--auto-connect-interval") + 1])

    run_api = "--no-api" not in args
    run_autoconnect = "--no-autoconnect" not in args
    open_browser = "--open-browser" in args or "--open" in args
    no_auth = "--no-api-auth" in args  # [AUTH] Debug flag to disable auth

    print(f"\n PHANTOM DAEMON — v{PHANTOM_VERSION} (with API Token Auth)")
    print(" Listener + auto-connect + local API, one process, one set of stores.\n")

    init_tor(interactive=False)

    km = KeyManager()
    km.init_encryption()

    identity = phantom_node._load_or_create_identity(km)
    identity = phantom_node._ensure_dm_ready(identity, km)

    state.update(
        km=km,
        store=SealStore(km),
        encounter_log=EncounterLog(km),
        pulse_ledger=PulseLedger(km),
        receipt_ledger=ReceiptLedger(km),
        contact_book=ContactBook(km),
        dm_store=DMStore(km),
        identity=identity,
    )

    if identity:
        print(f" Identity:  {identity.node_name or '(unnamed)'}  [{identity.fingerprint}]")
    print(f" Transport: {tor_status()}")

    listener = threading.Thread(
        target=phantom_node.listen,
        args=(state["store"], state["encounter_log"], identity,
              state["pulse_ledger"], state["contact_book"], state["dm_store"]),
        daemon=True,
    )
    listener.start()

    if run_autoconnect:
        t = threading.Thread(target=auto_connect_loop, args=(auto_connect_interval,), daemon=True)
        t.start()
        print(f" Auto-connect: every {auto_connect_interval}s, to known-alive fingerprints")
    else:
        print(" Auto-connect: off")

    if run_api:
        # [AUTH] Generate and print the API token
        if no_auth:
            API_TOKEN = None
            print("\n ⚠️  WARNING: API AUTHENTICATION IS DISABLED (--no-api-auth)")
            print("    Any website or process on localhost can access your seals.")
            print("    This is INSECURE. Use only for debugging.\n")
        else:
            API_TOKEN = secrets.token_urlsafe(32)
            print("\n ┌─────────────────────────────────────────────────────────────┐")
            print(" │  🔑  API TOKEN (Keep this secret)                          │")
            print(" │                                                             │")
            print(f" │     {API_TOKEN}  │")
            print(" │                                                             │")
            print(" │  If the browser doesn't open itself, or you open a second   │")
            print(" │  tab, paste this token there when asked.                     │")
            print(" └─────────────────────────────────────────────────────────────┘\n")

        url = f"http://127.0.0.1:{api_port}/"
        print(f" App:  {url}")
        print(f" API:  {url}api/status  (protected by token)\n")
        if open_browser:
            # The token rides along ONLY on this one automatic open, as a
            # query param — the page grabs it, stores it for the session,
            # and immediately strips it from the address bar. Any other
            # way of reaching the page (second tab, reopened bookmark)
            # falls back to the in-page paste prompt.
            auto_open_url = url + (f"?token={API_TOKEN}" if API_TOKEN else "")
            threading.Timer(1.2, lambda: webbrowser.open(auto_open_url)).start()
        app.run(host="127.0.0.1", port=api_port, threaded=True)
    else:
        print(" API: off — running listener/auto-connect only. Ctrl+C to stop.\n")
        try:
            while True:
                time.sleep(3600)
        except KeyboardInterrupt:
            print("\n Daemon stopping.\n")


if __name__ == "__main__":
    main()