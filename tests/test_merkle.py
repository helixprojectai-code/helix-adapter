# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0

import pytest
from helix_adapter.merkle import MerkleTree


def test_single_leaf():
    t = MerkleTree()
    root = t.append("abc")
    assert root == "abc"
    assert t.root == "abc"
    assert t.leaf_count == 1


def test_root_changes_on_append():
    t = MerkleTree()
    r1 = t.append("leaf0")
    r2 = t.append("leaf1")
    assert r1 != r2
    assert t.root == r2


def test_historical_roots():
    t = MerkleTree()
    roots = [t.append(f"leaf{i}") for i in range(4)]
    for i, r in enumerate(roots):
        assert t.root_at(i) == r
    assert t.root_at(99) is None


def test_all_roots():
    t = MerkleTree()
    for i in range(3):
        t.append(f"leaf{i}")
    entries = t.all_roots()
    assert len(entries) == 3
    assert entries[0]["turn"] == 0
    assert entries[2]["turn"] == 2


def test_proof_and_verify_single():
    t = MerkleTree()
    t.append("only")
    p = t.proof(0)
    assert p["leaf_hash"] == "only"
    assert p["proof"] == []
    assert MerkleTree.verify(p["leaf_hash"], p["proof"], p["root"])


def test_proof_and_verify_two_leaves():
    t = MerkleTree()
    t.append("left")
    t.append("right")
    for turn in range(2):
        p = t.proof(turn)
        assert MerkleTree.verify(p["leaf_hash"], p["proof"], p["root"])


def test_proof_and_verify_five_leaves():
    t = MerkleTree()
    leaves = [f"receipt-hash-{i}" for i in range(5)]
    for leaf in leaves:
        t.append(leaf)
    for turn in range(5):
        p = t.proof(turn)
        assert MerkleTree.verify(p["leaf_hash"], p["proof"], p["root"]), f"proof failed at turn {turn}"


def test_proof_out_of_range():
    t = MerkleTree()
    t.append("x")
    with pytest.raises(IndexError):
        t.proof(5)


def test_from_leaves_matches_sequential_append():
    leaves = ["a", "b", "c", "d"]
    t1 = MerkleTree()
    for l in leaves:
        t1.append(l)

    t2 = MerkleTree.from_leaves(leaves)
    assert t1.root == t2.root
    assert t1.all_roots() == t2.all_roots()


def test_tamper_detection():
    t = MerkleTree()
    for i in range(4):
        t.append(f"leaf{i}")
    p = t.proof(1)
    assert not MerkleTree.verify("tampered-hash", p["proof"], p["root"])


def test_empty_tree():
    t = MerkleTree()
    assert t.root is None
    assert t.leaf_count == 0
    assert t.root_at(0) is None
