# phantom_api.py — v1.0
#
# A local REST API over phantom_core.py — for building a web or
# mobile front-end without touching the CLI tools.
#
# IMPORTANT — LOCAL ONLY:
# This binds to 127.0.0.1 by default. It is not meant to be exposed
# to a network or the internet: a request to /api/unlock derives your
# encryption key from your passphrase and holds it in server memory
# for the life of the session. Anyone who can reach this API can read
# your seals for as long as a session token is valid. Keep it on
# localhost, or put it behind your own auth/reverse proxy if you ever
# expose it beyond your own machine.
#
# Run:
#   pip install flask
#   python phantom_api.py
#
# Then e.g.:
#   curl -X POST localhost:7338/api/unlock -H "Content-Type: application/json" \
#        -d '{"passphrase":"..."}'
#   curl localhost:7338/api/seals -H "X-Phantom-Token: <token>"

import base64
import hashlib
import secrets
import time
from datetime import datetime

from flask import Flask, request, jsonify

from phantom_core import (
    KeyManager, SealStore, EncounterLog, NodeIdentity,
    seal as core_seal, verify as core_verify,
    get_or_create_salt, derive_key,
    MODE_PRIVATE, MODE_PERMANENT, MODE_EPHEMERAL, DEFAULT_MODE,
    PHANTOM_VERSION, CRYPTO_AVAILABLE,
    init_tor, tor_status, get_onion_address,
)

app = Flask(__name__)

API_PORT = 7338
SESSION_TTL_SECONDS = 30 * 60  # 30 minutes of inactivity

# session token -> {"km": KeyManager, "last_used": epoch_seconds}
_sessions = {}


# ─────────────────────────────────────────────────────────
# SESSION HELPERS
# ─────────────────────────────────────────────────────────

def _prune_sessions():
    now = time.time()
    dead = [tok for tok, s in _sessions.items()
            if now - s["last_used"] > SESSION_TTL_SECONDS]
    for tok in dead:
        del _sessions[tok]


def _get_session():
    """Return the KeyManager for the caller's token, or None."""
    _prune_sessions()
    token = request.headers.get("X-Phantom-Token")
    if not token or token not in _sessions:
        return None
    _sessions[token]["last_used"] = time.time()
    return _sessions[token]["km"]


def require_session(fn):
    def wrapper(*args, **kwargs):
        km = _get_session()
        if km is None:
            return jsonify({"error": "unauthorized",
                             "message": "Missing or expired X-Phantom-Token. Call /api/unlock first."}), 401
        return fn(km, *args, **kwargs)
    wrapper.__name__ = fn.__name__
    return wrapper


# ─────────────────────────────────────────────────────────
# SEAL / IDENTITY HELPERS (mirrors phantom_dashboard.py)
# ─────────────────────────────────────────────────────────

def signed_status(entry):
    if "node_sig" not in entry or "node_pubkey" not in entry:
        return "unsigned"
    result = NodeIdentity.verify_signed_seal(entry)
    if result is True:
        return "signed_verified"
    if result is False:
        return "signed_invalid"
    return "signed_unverifiable"


def pubkey_fingerprint(pubkey_b64):
    try:
        raw = base64.b64decode(pubkey_b64)
        return hashlib.sha256(raw).hexdigest()[:16]
    except Exception:
        return None


def seal_to_dict(s, full=True):
    out = {
        "stamp": s["stamp"],
        "moment": s["moment"],
        "mode": s.get("mode"),
    }
    if full:
        out["idea"] = s["idea"]
        out["signature_status"] = signed_status(s)
        if "node_pubkey" in s:
            out["signer_fingerprint"] = pubkey_fingerprint(s["node_pubkey"])
            out["signer_pubkey"] = s["node_pubkey"]
    else:
        out["idea_preview"] = s["idea"][:70]
    return out


def encounter_to_dict(e, full=True):
    out = {
        "encounter_stamp": e["encounter_stamp"],
        "peer": e["peer"],
        "moment": e["moment"],
        "sent": e["sent"],
        "received": e["received"],
    }
    if full:
        out["received_stamps"] = e.get("received_stamps", [])
    return out


def identity_to_dict(identity):
    if not identity:
        return None
    return {
        "node_name": identity.node_name,
        "fingerprint": identity.fingerprint,
        "public_key": identity.public_key_b64,
        "has_private_key": identity.has_private_key,
    }


# ─────────────────────────────────────────────────────────
# AUTH ENDPOINTS
# ─────────────────────────────────────────────────────────

@app.route("/api/unlock", methods=["POST"])
def unlock():
    data = request.get_json(silent=True) or {}
    passphrase = data.get("passphrase", "")

    km = KeyManager()

    if CRYPTO_AVAILABLE and passphrase:
        salt = get_or_create_salt()
        km.set_key(derive_key(passphrase, salt))
    elif CRYPTO_AVAILABLE and not passphrase:
        # Explicit choice to run unencrypted this session.
        km.set_key(None)
    else:
        km.set_key(None)  # cryptography not installed — plaintext only

    # Validate the key actually opens the existing store, if one exists.
    try:
        SealStore(km).load()
    except ValueError:
        return jsonify({"error": "invalid_passphrase",
                         "message": "Wrong passphrase — sealed thoughts cannot be read."}), 401

    token = secrets.token_urlsafe(32)
    _sessions[token] = {"km": km, "last_used": time.time()}

    return jsonify({
        "token": token,
        "encrypted": km.has_key,
        "expires_in_seconds": SESSION_TTL_SECONDS,
    })


@app.route("/api/lock", methods=["POST"])
@require_session
def lock(km):
    token = request.headers.get("X-Phantom-Token")
    _sessions.pop(token, None)
    return jsonify({"message": "Session closed."})


# ─────────────────────────────────────────────────────────
# STATUS
# ─────────────────────────────────────────────────────────

@app.route("/api/status", methods=["GET"])
@require_session
def status(km):
    store = SealStore(km)
    encounter_log = EncounterLog(km)
    identity = NodeIdentity.load(key=km.key)

    seals = store.load()
    counts = {
        "private": sum(1 for s in seals if s.get("mode") == MODE_PRIVATE),
        "permanent": sum(1 for s in seals if s.get("mode") == MODE_PERMANENT),
        "ephemeral": sum(1 for s in seals if s.get("mode") == MODE_EPHEMERAL),
    }

    return jsonify({
        "phantom_version": PHANTOM_VERSION,
        "seal_count": len(seals),
        "seal_counts_by_mode": counts,
        "encounter_count": len(encounter_log.load()),
        "identity": identity_to_dict(identity),
        "transport": tor_status(),
        "onion_address": get_onion_address(),
    })


# ─────────────────────────────────────────────────────────
# SEALS
# ─────────────────────────────────────────────────────────

@app.route("/api/seals", methods=["GET"])
@require_session
def list_seals(km):
    store = SealStore(km)
    seals = store.load()
    return jsonify({
        "count": len(seals),
        "seals": [seal_to_dict(s, full=False) for s in seals],
    })


@app.route("/api/seals/<stamp>", methods=["GET"])
@require_session
def get_seal(km, stamp):
    store = SealStore(km)
    for s in store.load():
        if s["stamp"] == stamp:
            return jsonify(seal_to_dict(s, full=True))
    return jsonify({"error": "not_found", "message": "No seal with that stamp."}), 404


@app.route("/api/seals", methods=["POST"])
@require_session
def create_seal(km):
    data = request.get_json(silent=True) or {}
    idea = data.get("idea", "")
    mode = data.get("mode", DEFAULT_MODE)

    if mode not in (MODE_PRIVATE, MODE_PERMANENT, MODE_EPHEMERAL):
        return jsonify({"error": "invalid_mode",
                         "message": f"Mode must be one of: {MODE_PRIVATE}, {MODE_PERMANENT}, {MODE_EPHEMERAL}"}), 400

    try:
        entry = core_seal(idea, mode)
    except ValueError as e:
        return jsonify({"error": "invalid_idea", "message": str(e)}), 400

    store = SealStore(km)
    saved = store.save(entry)
    return jsonify({
        "saved": saved,
        "duplicate": not saved,
        "seal": seal_to_dict(entry, full=True),
    }), (201 if saved else 200)


@app.route("/api/verify", methods=["POST"])
def verify_seal():
    """Public endpoint — verification needs no passphrase or session."""
    data = request.get_json(silent=True) or {}
    idea = data.get("idea", "")
    moment = data.get("moment", "")
    stamp = data.get("stamp", "")
    valid = core_verify(idea, moment, stamp)
    return jsonify({"valid": valid})


# ─────────────────────────────────────────────────────────
# ENCOUNTERS
# ─────────────────────────────────────────────────────────

@app.route("/api/encounters", methods=["GET"])
@require_session
def list_encounters(km):
    encounter_log = EncounterLog(km)
    encounters = encounter_log.load()
    return jsonify({
        "count": len(encounters),
        "encounters": [encounter_to_dict(e, full=False) for e in encounters],
    })


@app.route("/api/encounters/<encounter_stamp>", methods=["GET"])
@require_session
def get_encounter(km, encounter_stamp):
    encounter_log = EncounterLog(km)
    for e in encounter_log.load():
        if e["encounter_stamp"] == encounter_stamp:
            return jsonify(encounter_to_dict(e, full=True))
    return jsonify({"error": "not_found", "message": "No encounter with that stamp."}), 404


# ─────────────────────────────────────────────────────────
# IDENTITY
# ─────────────────────────────────────────────────────────

@app.route("/api/identity", methods=["GET"])
@require_session
def identity(km):
    identity = NodeIdentity.load(key=km.key)
    if not identity:
        return jsonify({"identity": None,
                         "message": "No identity yet. Create one via phantom_node.py --identity."})
    return jsonify({"identity": identity_to_dict(identity)})


if __name__ == "__main__":
    init_tor(interactive=False)
    print(f"\n Phantom API — v{PHANTOM_VERSION}")
    print(f" Listening on http://127.0.0.1:{API_PORT} (localhost only)\n")
    app.run(host="127.0.0.1", port=API_PORT)
