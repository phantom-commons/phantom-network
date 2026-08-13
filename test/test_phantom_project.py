import os
import sys
import tempfile
import shutil
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from phantom_core import NodeIdentity, CRYPTO_AVAILABLE
from phantom_project import (
    make_commit, verify_commit, compute_commit_hash,
    hash_tree, snapshot_tree, ProjectStore, commit_directory,
)


@unittest.skipUnless(CRYPTO_AVAILABLE, "cryptography package not available")
class TestCommitHashAndSignature(unittest.TestCase):
    """The commit_hash formula, and the two-question verify_commit()."""

    def setUp(self):
        self.identity = NodeIdentity.generate(node_name="test-node")
        self.fp = self.identity.fingerprint
        self.tree_hash = "a" * 64

    def test_genesis_commit_has_no_parents(self):
        c = make_commit(self.tree_hash, [], "initial", self.fp, identity=self.identity)
        self.assertEqual(c["parents"], [])
        result = verify_commit(c)
        self.assertTrue(result["hash_valid"])
        self.assertTrue(result["signature_valid"])

    def test_unsigned_commit_has_none_signature(self):
        c = make_commit(self.tree_hash, [], "no identity given", self.fp, identity=None)
        self.assertNotIn("node_sig", c)
        result = verify_commit(c)
        self.assertTrue(result["hash_valid"])
        self.assertIsNone(result["signature_valid"])

    def test_tampering_with_message_breaks_hash_valid(self):
        c = make_commit(self.tree_hash, [], "original message", self.fp, identity=self.identity)
        tampered = dict(c)
        tampered["message"] = "a different message"
        result = verify_commit(tampered)
        self.assertFalse(result["hash_valid"])

    def test_signing_with_wrong_author_fingerprint_fails_signature(self):
        """You can sign with your own key, but you can't claim to be
        someone else's fingerprint and have it verify as them."""
        other = NodeIdentity.generate(node_name="someone-else")
        lying = make_commit(self.tree_hash, [], "pretending", self.fp, identity=other)
        result = verify_commit(lying)
        self.assertTrue(result["hash_valid"])  # hash formula itself is still internally consistent
        self.assertFalse(result["signature_valid"])  # but the author claim is false

    def test_invalid_parent_hash_format_raises(self):
        with self.assertRaises(ValueError):
            make_commit(self.tree_hash, ["not-a-real-hash"], "msg", self.fp)

    def test_invalid_tree_hash_format_raises(self):
        with self.assertRaises(ValueError):
            make_commit("too-short", [], "msg", self.fp)

    def test_empty_message_raises(self):
        with self.assertRaises(ValueError):
            make_commit(self.tree_hash, [], "", self.fp)

    def test_missing_author_fingerprint_raises(self):
        with self.assertRaises(ValueError):
            make_commit(self.tree_hash, [], "msg", author_fingerprint=None)

    def test_compute_commit_hash_matches_make_commit(self):
        """The hash formula is a pure function — anyone should be able
        to recompute it independently and get the same answer."""
        c = make_commit(self.tree_hash, [], "msg", self.fp, identity=self.identity)
        recomputed = compute_commit_hash(c["tree_hash"], c["parents"], c["moment"], c["message"], c["author_fingerprint"])
        self.assertEqual(c["commit_hash"], recomputed)


class TestHashTreeAndSnapshot(unittest.TestCase):
    def setUp(self):
        self.src = tempfile.mkdtemp()
        self.project_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.src, ignore_errors=True)
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_hash_tree_is_deterministic(self):
        with open(os.path.join(self.src, "a.txt"), "w") as f:
            f.write("hello")
        h1 = hash_tree(self.src)
        h2 = hash_tree(self.src)
        self.assertEqual(h1, h2)

    def test_hash_tree_changes_when_content_changes(self):
        with open(os.path.join(self.src, "a.txt"), "w") as f:
            f.write("hello")
        h1 = hash_tree(self.src)
        with open(os.path.join(self.src, "a.txt"), "w") as f:
            f.write("hello, world")
        h2 = hash_tree(self.src)
        self.assertNotEqual(h1, h2)

    def test_snapshot_tree_copies_files(self):
        with open(os.path.join(self.src, "a.txt"), "w") as f:
            f.write("content")
        th = hash_tree(self.src)
        dest = snapshot_tree(self.src, self.project_dir, th)
        self.assertTrue(os.path.exists(os.path.join(dest, "a.txt")))

    def test_snapshot_tree_skips_if_already_saved(self):
        with open(os.path.join(self.src, "a.txt"), "w") as f:
            f.write("content")
        th = hash_tree(self.src)
        dest1 = snapshot_tree(self.src, self.project_dir, th)
        os.utime(os.path.join(dest1, "a.txt"), (0, 0))  # mark it, to prove it wasn't re-copied
        dest2 = snapshot_tree(self.src, self.project_dir, th)
        self.assertEqual(os.path.getmtime(os.path.join(dest2, "a.txt")), 0)


class TestProjectStore(unittest.TestCase):
    def setUp(self):
        self.project_dir = tempfile.mkdtemp()
        self.store = ProjectStore(self.project_dir)
        self.fp = "deadbeefdeadbeef"

    def tearDown(self):
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def _commit(self, message, parents=None):
        return make_commit("a" * 64, parents or [], message, self.fp)

    def test_add_commit_dedups_by_hash(self):
        c = self._commit("first")
        self.assertTrue(self.store.add_commit(c))
        self.assertFalse(self.store.add_commit(c))  # same hash, already there
        self.assertEqual(len(self.store.load_commits()), 1)

    def test_get_head_none_when_unset(self):
        self.assertIsNone(self.store.get_head())

    def test_set_head_requires_known_commit(self):
        with self.assertRaises(ValueError):
            self.store.set_head("f" * 64)

    def test_history_walks_first_parent_chain(self):
        c1 = self._commit("genesis")
        self.store.add_commit(c1)
        c2 = self._commit("second", parents=[c1["commit_hash"]])
        self.store.add_commit(c2)
        self.store.set_head(c2["commit_hash"])
        history = self.store.history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["commit_hash"], c2["commit_hash"])  # newest first
        self.assertEqual(history[1]["commit_hash"], c1["commit_hash"])

    def test_heads_detects_a_fork(self):
        c1 = self._commit("genesis")
        self.store.add_commit(c1)
        c2a = self._commit("branch A", parents=[c1["commit_hash"]])
        c2b = self._commit("branch B", parents=[c1["commit_hash"]])
        self.store.add_commit(c2a)
        self.store.add_commit(c2b)
        heads = self.store.heads()
        self.assertEqual(len(heads), 2)
        self.assertIn(c2a["commit_hash"], heads)
        self.assertIn(c2b["commit_hash"], heads)

    def test_heads_single_line_of_history_has_one_head(self):
        c1 = self._commit("genesis")
        self.store.add_commit(c1)
        c2 = self._commit("second", parents=[c1["commit_hash"]])
        self.store.add_commit(c2)
        self.assertEqual(self.store.heads(), [c2["commit_hash"]])


class TestCommitDirectory(unittest.TestCase):
    """The one-call convenience that ties hash_tree + snapshot + ProjectStore together."""

    def setUp(self):
        self.src = tempfile.mkdtemp()
        self.project_dir = tempfile.mkdtemp()
        self.fp = "deadbeefdeadbeef"
        with open(os.path.join(self.src, "main.py"), "w") as f:
            f.write("print('v1')")

    def tearDown(self):
        shutil.rmtree(self.src, ignore_errors=True)
        shutil.rmtree(self.project_dir, ignore_errors=True)

    def test_first_commit_is_genesis_and_moves_head(self):
        c1 = commit_directory(self.src, self.project_dir, "initial", self.fp)
        self.assertEqual(c1["parents"], [])
        store = ProjectStore(self.project_dir)
        self.assertEqual(store.get_head(), c1["commit_hash"])

    def test_second_commit_chains_onto_head_automatically(self):
        c1 = commit_directory(self.src, self.project_dir, "initial", self.fp)
        with open(os.path.join(self.src, "main.py"), "w") as f:
            f.write("print('v2')")
        c2 = commit_directory(self.src, self.project_dir, "update", self.fp)
        self.assertEqual(c2["parents"], [c1["commit_hash"]])

    def test_explicit_parents_forks_instead_of_following_head(self):
        c1 = commit_directory(self.src, self.project_dir, "initial", self.fp)
        with open(os.path.join(self.src, "main.py"), "w") as f:
            f.write("print('v2')")
        commit_directory(self.src, self.project_dir, "on top of head", self.fp)  # c2, moves HEAD
        with open(os.path.join(self.src, "main.py"), "w") as f:
            f.write("print('a fork of v1, not v2')")
        forked = commit_directory(self.src, self.project_dir, "fork", self.fp, parents=[c1["commit_hash"]])
        self.assertEqual(forked["parents"], [c1["commit_hash"]])
        store = ProjectStore(self.project_dir)
        self.assertEqual(len(store.heads()), 2)  # both tips still visible


if __name__ == "__main__":
    unittest.main()
