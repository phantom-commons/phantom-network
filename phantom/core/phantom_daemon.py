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
    PHANTOM_VERSION, MODE_PRIVATE, MODE_PERMANENT, MODE_EPHEMERAL, DEFAULT_MODE, CHANNELS,
    CRYPTO_AVAILABLE, PULSE_TTL_SECONDS,
    init_tor, tor_status, get_onion_address,
)
from phantom_diary import DiaryStore, make_entry, verify_entry  # [DIARY] memoria de chats con la IA local

DEFAULT_API_PORT = 7338
DEFAULT_AUTO_CONNECT_INTERVAL = 300  # 5 minutes

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))        # phantom/core/
APP_DIR = os.path.join(ROOT_DIR, '..', '..', 'app')           # Node/app/ (two levels up from phantom/core/)
PROJECT_ROOT = os.path.realpath(os.path.join(ROOT_DIR, '..', '..'))  # Node/ — raíz para el explorador de archivos

# [FILES] mismo criterio que phantom_council.py: qué se puede leer y qué no.
# Nunca exponemos datos del nodo (sellos, llaves, diary cifrado, etc.),
# solo código/documentación — es lo que un asistente necesita para ayudar
# a programar, no el contenido privado del nodo.
FILES_TEXT_EXTENSIONS = {'.md', '.py', '.txt', '.html', '.yml', '.yaml', '.toml', '.json'}
FILES_EXCLUDE_DIRS = {'.git', '__pycache__', 'node_modules', '.phantom_data'}
FILES_EXCLUDE_NAMES = {
    'phantom_seals.json', 'phantom_encounters.json', 'phantom_salt.bin',
    'phantom_key.salt', 'phantom_seals.enc', 'phantom_diary.json',
    'phantom_contacts.json', 'phantom_dms.json', 'phantom_wallet.key',
    'phantom_node.key', 'phantom_node.pub', 'phantom_pulses.json',
    '.DS_Store', 'desktop.ini',
}
FILES_MAX_READ_CHARS = 12000  # ~ lo que entra cómodo en el contexto de un modelo chico

app = Flask(__name__)
state = {}  # populated once in main(): km, store, encounter_log, pulse_ledger,
            # receipt_ledger, contact_book, dm_store, identity

# [AUTH] Global token variable - set in main()
API_TOKEN = None
# [SECURITY] Expected Host header, set in main() as "127.0.0.1:<api_port>"
EXPECTED_HOST = None


# [AUTH] Decorator to protect API endpoints
def require_token(f):
    def wrapper(*args, **kwargs):
        # [SECURITY] DNS-rebinding defense: a malicious site can get the
        # browser to re-resolve its own domain to 127.0.0.1 after the
        # page has already loaded, at which point a fetch() from that
        # page's JS looks same-origin to the browser even though it's
        # attacker code. The Host header the browser sends still
        # reflects the original domain, not 127.0.0.1 — so rejecting
        # anything that doesn't match our own bound address catches it
        # here, before the token check even runs.
        if EXPECTED_HOST and request.host != EXPECTED_HOST:
            return jsonify({
                "error": "forbidden_host",
                "message": "Request host does not match this daemon's bound address."
            }), 403

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
    # .get(), no s["channel"]/s["ref"] — sellos viejos o privados
    # simplemente no tienen estas claves, y eso es válido.
    if s.get("channel") is not None:
        out["channel"] = s["channel"]
    if s.get("ref") is not None:
        out["ref"] = s["ref"]
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
    channel = data.get("channel")  # optional, sibling of mode — see phantom_core.seal()
    ref = data.get("ref")          # optional, stamp of the seal being replied to

    if mode not in (MODE_PRIVATE, MODE_PERMANENT, MODE_EPHEMERAL):
        return jsonify({"error": "invalid_mode"}), 400
    if channel is not None and channel not in CHANNELS:
        return jsonify({"error": "invalid_channel", "message": f"channel must be one of {CHANNELS}"}), 400
    if channel is not None and mode == MODE_PRIVATE:
        return jsonify({"error": "invalid_channel", "message": "private seals don't take a channel"}), 400
    if ref is not None and (len(ref) != 64 or any(c not in "0123456789abcdef" for c in ref)):
        return jsonify({"error": "invalid_ref", "message": "ref must be a valid stamp (64 hex chars)"}), 400

    try:
        entry = core_seal(idea, mode, channel=channel, ref=ref)
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
# DIARY — memoria de las conversaciones con la IA local
# (mismo cifrado/sellado que phantom_diary.py CLI, expuesto acá
#  para que el chat del Workbench pueda guardar y recuperar)
# ─────────────────────────────────────────────────────────

def _diary_entry_to_dict(e, index=None, score=None):
    out = {
        "moment": e["moment"],
        "text": e["text"],
        "tags": e.get("tags", []),
        "mood": e.get("mood", ""),
        "stamp": e["stamp"],
        "verified": verify_entry(e),
    }
    if index is not None:
        out["index"] = index
    if score is not None:
        out["score"] = score
    return out


def _diary_multi_search(store, query, limit=5):
    """
    Búsqueda por palabra, no por frase literal. store.search() del CLI
    exige que la frase completa aparezca seguida en el texto — bien
    para el CLI donde el usuario escribe la query a mano, mal para
    contexto automático donde le pasamos texto libre de un mensaje.
    Acá partimos en palabras, contamos cuántas aparecen en cada
    entrada, y devolvemos las mejores ordenadas por ese score.
    """
    keywords = [w for w in query.lower().split() if len(w) > 2]
    if not keywords:
        return []
    entries = store.load()
    scored = []
    for e in entries:
        haystack = (e["text"] + " " + " ".join(e.get("tags", [])) + " " + e.get("mood", "")).lower()
        score = sum(1 for kw in keywords if kw in haystack)
        if score > 0:
            scored.append((score, e))
    scored.sort(key=lambda pair: pair[0], reverse=True)  # score desc; sort estable conserva orden cronológico en empates
    return scored[:limit]


@app.route("/api/diary", methods=["POST"])
@require_token
def diary_write():
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    tags = data.get("tags") or []
    mood = data.get("mood", "")
    try:
        entry = make_entry(text, tags=tags, mood=mood)
    except ValueError as e:
        return jsonify({"error": "invalid_entry", "message": str(e)}), 400
    saved = state["diary_store"].save(entry)
    return jsonify({"saved": saved, "entry": _diary_entry_to_dict(entry)}), (201 if saved else 200)


@app.route("/api/diary/recent", methods=["GET"])
@require_token
def diary_recent():
    n = request.args.get("n", default=10, type=int)
    entries = state["diary_store"].recent(n)
    return jsonify({
        "count": len(entries),
        "entries": [_diary_entry_to_dict(e) for e in entries],
    })


@app.route("/api/diary/search", methods=["GET"])
@require_token
def diary_search():
    q = request.args.get("q", default="", type=str)
    if not q.strip():
        return jsonify({"error": "empty_query"}), 400
    limit = request.args.get("limit", default=5, type=int)
    scored = _diary_multi_search(state["diary_store"], q, limit=limit)
    return jsonify({
        "count": len(scored),
        "entries": [_diary_entry_to_dict(e, score=score) for score, e in scored],
    })


# ─────────────────────────────────────────────────────────
# FILES — explorador real para el chat/council (lectura, nunca escritura)
# ─────────────────────────────────────────────────────────

def _build_file_tree(dir_path, rel=""):
    """Árbol recursivo de archivos legibles, misma lógica de exclusión
    que phantom_council.py.read_repository — código y docs sí, datos
    del nodo no."""
    nodes = []
    try:
        entries = sorted(os.listdir(dir_path))
    except OSError:
        return nodes
    for name in entries:
        if name in FILES_EXCLUDE_NAMES:
            continue
        full = os.path.join(dir_path, name)
        relpath = os.path.join(rel, name) if rel else name
        if os.path.isdir(full):
            if name in FILES_EXCLUDE_DIRS or name.startswith('.'):
                continue
            children = _build_file_tree(full, relpath)
            if children:  # no mostrar carpetas vacías (post-filtro)
                nodes.append({"type": "dir", "name": name, "path": relpath, "children": children})
        else:
            ext = os.path.splitext(name)[1].lower()
            if ext not in FILES_TEXT_EXTENSIONS:
                continue
            if name in FILES_EXCLUDE_NAMES:
                continue
            nodes.append({"type": "file", "name": name, "path": relpath})
    return nodes


def _safe_project_path(rel_path):
    """Resuelve rel_path contra PROJECT_ROOT y garantiza que no se
    escapa de ahí (nada de ../../etc/passwd). Devuelve None si es
    inválido o cae fuera de los tipos/nombres permitidos."""
    candidate = os.path.realpath(os.path.join(PROJECT_ROOT, rel_path))
    if os.path.commonpath([candidate, PROJECT_ROOT]) != PROJECT_ROOT:
        return None
    name = os.path.basename(candidate)
    if name in FILES_EXCLUDE_NAMES:
        return None
    ext = os.path.splitext(name)[1].lower()
    if ext not in FILES_TEXT_EXTENSIONS:
        return None
    for part in os.path.relpath(candidate, PROJECT_ROOT).split(os.sep):
        if part in FILES_EXCLUDE_DIRS:
            return None
    return candidate


@app.route("/api/files/tree", methods=["GET"])
@require_token
def files_tree():
    tree = _build_file_tree(PROJECT_ROOT)
    return jsonify({"root": os.path.basename(PROJECT_ROOT), "tree": tree})


@app.route("/api/files/content", methods=["GET"])
@require_token
def files_content():
    rel_path = request.args.get("path", default="", type=str)
    if not rel_path:
        return jsonify({"error": "missing_path"}), 400
    full_path = _safe_project_path(rel_path)
    if not full_path or not os.path.isfile(full_path):
        return jsonify({"error": "not_found_or_forbidden"}), 404
    try:
        with open(full_path, "r", encoding="utf-8") as f:
            content = f.read()
    except (UnicodeDecodeError, IOError) as e:
        return jsonify({"error": "unreadable", "message": str(e)}), 400
    truncated = len(content) > FILES_MAX_READ_CHARS
    if truncated:
        content = content[:FILES_MAX_READ_CHARS]
    return jsonify({
        "path": rel_path, "content": content,
        "truncated": truncated, "full_length": len(content) if not truncated else None,
    })


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
    global EXPECTED_HOST  # [SECURITY] Same deal, for the Host check

    args = sys.argv[1:]

    api_port = DEFAULT_API_PORT
    if "--api-port" in args:
        api_port = int(args[args.index("--api-port") + 1])
    EXPECTED_HOST = f"127.0.0.1:{api_port}"

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
        diary_store=DiaryStore(km),  # [DIARY] mismo km ya desbloqueado, sin passphrase extra
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