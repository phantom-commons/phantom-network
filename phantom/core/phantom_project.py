"""
phantom_project.py

Git-style commits for versioned projects (side projects, node config as
a "distro", eventually bots/personas as forkable running instances).

Deliberately a SEPARATE module from seal() in phantom_core.py, not an
extension of it — the two have opposite designs on purpose:

    seal()            phantom_project commit
    ---------------    -----------------------
    anonymous          authored (author_fingerprint required)
    no parent          has parent(s) — forms a DAG, not a flat set
    never signed        signed with the node's Ed25519 identity key
    stamp = hash(idea+moment), NEVER touched (SEALING.md)

A commit needs authorship because reputation has to attach to *someone*
for forks/reviews to mean anything. A seal deliberately has none of
that. Building this as its own module keeps seal()'s stamp formula
exactly as untouchable as it's always been.

No consensus here, in the blockchain sense. Multiple heads (forks) are
normal and expected — this module never decides which fork is
"canonical". That's a social decision (which fork people keep syncing
to), same conclusion reached for seal forwarding/relay reputation.
"""

import hashlib
import json
import os
import shutil
from datetime import datetime, timezone

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    import base64
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


# ─────────────────────────────────────────────────────────
# COMMIT HASHING + SIGNING
# ─────────────────────────────────────────────────────────

def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode()


def compute_commit_hash(tree_hash, parents, moment, message, author_fingerprint):
    """Pure function — same shape everywhere it's needed (make_commit,
    verify_commit, and anyone re-deriving a commit_hash from parts)."""
    data = _canonical({
        "tree_hash": tree_hash,
        "parents": sorted(parents),
        "moment": moment,
        "message": message,
        "author_fingerprint": author_fingerprint,
    })
    return hashlib.sha256(data).hexdigest()


def _valid_hash_format(h):
    return isinstance(h, str) and len(h) == 64 and all(c in "0123456789abcdef" for c in h)


def make_commit(tree_hash, parents, message, author_fingerprint, identity=None):
    """
    Create a commit. Returns a dict — does NOT save it anywhere; that's
    ProjectStore's job (see below).

    identity: optional phantom_core.NodeIdentity with a private key.
    If given, the commit is signed — node_pubkey + node_sig embedded
    in the object itself, same pattern as NodeIdentity.sign_seal(), so
    anyone can attempt verification without needing the author's
    NodeIdentity loaded (they just need the embedded pubkey, which
    verify_commit() checks against author_fingerprint too — see there).

    identity=None is allowed (you may be testing, or building tooling
    before identity is wired through everywhere) but an unsigned
    commit's authorship can't be trusted by anyone who didn't already
    trust you out-of-band — it's still usable, just as anonymous as an
    unsigned seal.
    """
    if not _valid_hash_format(tree_hash):
        raise ValueError("tree_hash must be a valid hash (64 hex chars) — see hash_tree().")
    if not isinstance(parents, list):
        raise ValueError("parents must be a list (empty [] for a genesis commit).")
    for p in parents:
        if not _valid_hash_format(p):
            raise ValueError(f"Invalid parent commit hash: {p!r}")
    if not message:
        raise ValueError("Cannot commit without a message.")
    if not author_fingerprint:
        raise ValueError("author_fingerprint is required — commits are authored, unlike seals.")

    moment = datetime.now(timezone.utc).isoformat()
    commit_hash = compute_commit_hash(tree_hash, parents, moment, message, author_fingerprint)

    commit = {
        "commit_hash": commit_hash,
        "tree_hash": tree_hash,
        "parents": list(parents),
        "moment": moment,
        "message": message,
        "author_fingerprint": author_fingerprint,
    }

    if identity is not None:
        commit["node_pubkey"] = identity.public_key_b64
        commit["node_sig"] = identity.sign(commit_hash.encode())

    return commit


def verify_commit(commit):
    """
    Two independent checks, returned separately — same reasoning as
    NodeIdentity.verify_signed_seal(): integrity and authorship are
    different questions.

    Returns {"hash_valid": bool, "signature_valid": bool | None}

    hash_valid — recomputed commit_hash matches the stored one. Always
    answerable, doesn't need crypto or the author's key.

    signature_valid — True/False if node_pubkey+node_sig are present
    AND the fingerprint derived from node_pubkey matches
    author_fingerprint (catches someone signing with their own key
    while claiming a different author_fingerprint). None if the commit
    is unsigned, or if the cryptography package isn't available to
    check — both are "can't tell", not "failed".
    """
    try:
        expected_hash = compute_commit_hash(
            commit["tree_hash"], commit["parents"], commit["moment"],
            commit["message"], commit["author_fingerprint"],
        )
    except (KeyError, TypeError):
        return {"hash_valid": False, "signature_valid": None}

    hash_valid = (expected_hash == commit.get("commit_hash"))

    if "node_sig" not in commit or "node_pubkey" not in commit:
        return {"hash_valid": hash_valid, "signature_valid": None}
    if not CRYPTO_AVAILABLE:
        return {"hash_valid": hash_valid, "signature_valid": None}

    try:
        pub_bytes = base64.b64decode(commit["node_pubkey"])
        pub_fingerprint = hashlib.sha256(pub_bytes).hexdigest()[:16]
        if pub_fingerprint != commit["author_fingerprint"]:
            return {"hash_valid": hash_valid, "signature_valid": False}

        pub_key = Ed25519PublicKey.from_public_bytes(pub_bytes)
        sig = base64.b64decode(commit["node_sig"])
        pub_key.verify(sig, commit["commit_hash"].encode())
        signature_valid = True
    except Exception:
        signature_valid = False

    return {"hash_valid": hash_valid, "signature_valid": signature_valid}


# ─────────────────────────────────────────────────────────
# TREE HASHING + SNAPSHOTS
# ─────────────────────────────────────────────────────────

def hash_tree(directory):
    """
    Content-addressed hash of a directory's current state: sha256 of a
    sorted {relative_path: sha256(file_bytes)} mapping.

    Flat by design for v1 — no git-style recursive tree objects, no
    diffing/packing. Good enough to answer "did anything change"
    cheaply; not optimized for huge projects. Optimize later if needed,
    doesn't change the commit schema above at all if it does.
    """
    file_hashes = {}
    for root, _, files in sorted(os.walk(directory)):
        for fname in sorted(files):
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, directory).replace(os.sep, "/")
            with open(full_path, "rb") as f:
                file_hashes[rel_path] = hashlib.sha256(f.read()).hexdigest()
    return hashlib.sha256(_canonical(file_hashes)).hexdigest()


def snapshot_tree(directory, project_dir, tree_hash):
    """
    Copy the directory's current state into snapshots/<tree_hash>/,
    skipped if that exact tree state is already saved (same content,
    possibly reached via different commits — no point duplicating it).
    Returns the snapshot path either way.
    """
    dest = os.path.join(project_dir, "snapshots", tree_hash)
    if not os.path.exists(dest):
        shutil.copytree(directory, dest)
    return dest


# ─────────────────────────────────────────────────────────
# PROJECT STORE — one instance per project
# ─────────────────────────────────────────────────────────

class ProjectStore:
    """
    Handles commits.json + HEAD on disk for one project.

    project_dir is expected to live under something like
    .phantom_data/projects/<project_id>/ — the daemon/CLI decide the
    project_id scheme, this class doesn't care.
    """

    def __init__(self, project_dir):
        self.project_dir = project_dir
        self.commits_file = os.path.join(project_dir, "commits.json")
        self.head_file = os.path.join(project_dir, "HEAD")
        os.makedirs(project_dir, exist_ok=True)

    def load_commits(self):
        if not os.path.exists(self.commits_file):
            return []
        with open(self.commits_file) as f:
            return json.load(f)

    def _save_commits(self, commits):
        with open(self.commits_file, "w") as f:
            json.dump(commits, f, indent=2)

    def add_commit(self, commit):
        """Append a commit if its hash isn't already present. Returns
        True if it was newly added, False if it was already there
        (idempotent — safe to call again after a sync merge)."""
        commits = self.load_commits()
        if any(c["commit_hash"] == commit["commit_hash"] for c in commits):
            return False
        commits.append(commit)
        self._save_commits(commits)
        return True

    def get_commit(self, commit_hash):
        for c in self.load_commits():
            if c["commit_hash"] == commit_hash:
                return c
        return None

    def get_head(self):
        if not os.path.exists(self.head_file):
            return None
        with open(self.head_file) as f:
            content = f.read().strip()
            return content or None

    def set_head(self, commit_hash):
        if commit_hash is not None and self.get_commit(commit_hash) is None:
            raise ValueError(f"Can't set HEAD to a commit this store doesn't have: {commit_hash}")
        with open(self.head_file, "w") as f:
            f.write(commit_hash or "")

    def history(self, from_hash=None):
        """
        Walk parents[0] from from_hash (or current HEAD) back to a
        genesis commit (parents == []). "First parent" only, same
        convention git uses for a linear view — a merge commit's other
        parent(s) are still in commits.json, just not part of *this*
        particular walk. Returns newest-first.
        """
        commits_by_hash = {c["commit_hash"]: c for c in self.load_commits()}
        current = from_hash or self.get_head()
        chain = []
        seen = set()
        while current and current in commits_by_hash and current not in seen:
            seen.add(current)
            c = commits_by_hash[current]
            chain.append(c)
            current = c["parents"][0] if c["parents"] else None
        return chain

    def heads(self):
        """
        Every commit hash that isn't anyone's parent — i.e. every fork
        tip this store currently knows about, not just the one HEAD
        points to. More than one result means this store has seen a
        fork (two lines of history diverging from a common ancestor,
        or two genuinely unrelated projects sharing this store, which
        you shouldn't do — one ProjectStore per project_id).
        """
        commits = self.load_commits()
        all_hashes = {c["commit_hash"] for c in commits}
        referenced_as_parent = set()
        for c in commits:
            referenced_as_parent.update(c["parents"])
        return sorted(all_hashes - referenced_as_parent)


# ─────────────────────────────────────────────────────────
# CONVENIENCE: the "commit this folder" one-call version
# ─────────────────────────────────────────────────────────

def commit_directory(directory, project_dir, message, author_fingerprint,
                      parents=None, identity=None, move_head=True):
    """
    Hash the directory, snapshot it, build the commit, save it, and
    (by default) move this project's HEAD to it. This is what a
    "drag a folder in, hit commit" button would call — the rest of
    this module is what that button is built out of.

    parents=None means "commit on top of current HEAD" (or a genesis
    commit with parents=[] if there's no HEAD yet). Pass an explicit
    parents list to commit on top of something else on purpose —
    that's how a fork happens: parents=[some commit that isn't your
    current HEAD].
    """
    store = ProjectStore(project_dir)
    tree_hash = hash_tree(directory)
    snapshot_tree(directory, project_dir, tree_hash)

    if parents is None:
        head = store.get_head()
        parents = [head] if head else []

    commit = make_commit(tree_hash, parents, message, author_fingerprint, identity=identity)
    store.add_commit(commit)
    if move_head:
        store.set_head(commit["commit_hash"])
    return commit
