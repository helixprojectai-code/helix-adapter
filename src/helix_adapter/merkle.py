# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0

"""Append-only Merkle tree for HelixSession receipt chains.

Leaves are receipt hashes. Duplicate-last padding (Bitcoin standard).
Historical roots are stored so any prior turn can be proved without
rewriting the tree.
"""

from __future__ import annotations

import hashlib


def _sha(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


def _next_pow2(n: int) -> int:
    if n <= 1:
        return 1
    p = 1
    while p < n:
        p <<= 1
    return p


def _compute_root(leaves: list[str]) -> str:
    if not leaves:
        return _sha("")
    if len(leaves) == 1:
        return leaves[0]
    size = _next_pow2(len(leaves))
    layer = leaves + [leaves[-1]] * (size - len(leaves))
    while len(layer) > 1:
        layer = [_sha(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]
    return layer[0]


class MerkleTree:
    """Append-only binary Merkle tree.

    Each append stores the resulting root so historical roots are
    available without re-traversal. Proofs are generated against the
    root at the time the leaf was added (root_at(turn)).
    """

    def __init__(self) -> None:
        self._leaves: list[str] = []
        self._roots: list[str] = []

    # ------------------------------------------------------------------ #
    # Mutation
    # ------------------------------------------------------------------ #

    def append(self, leaf_hash: str) -> str:
        """Add a leaf, return the new root."""
        self._leaves.append(leaf_hash)
        root = _compute_root(self._leaves)
        self._roots.append(root)
        return root

    # ------------------------------------------------------------------ #
    # Accessors
    # ------------------------------------------------------------------ #

    @property
    def root(self) -> str | None:
        return self._roots[-1] if self._roots else None

    @property
    def leaf_count(self) -> int:
        return len(self._leaves)

    def root_at(self, turn: int) -> str | None:
        if 0 <= turn < len(self._roots):
            return self._roots[turn]
        return None

    def all_roots(self) -> list[dict]:
        return [{"turn": i, "root": r} for i, r in enumerate(self._roots)]

    # ------------------------------------------------------------------ #
    # Proof
    # ------------------------------------------------------------------ #

    def proof(self, turn: int) -> dict:
        """Merkle inclusion proof for the leaf at `turn`.

        Proves that leaf is in root_at(turn) — the root at the moment
        that receipt was sealed. Sibling path walks from leaf to root.
        Position 'right' means the sibling is to the right of the
        current node; 'left' means it's to the left.
        """
        if turn < 0 or turn >= len(self._leaves):
            raise IndexError(f"turn {turn} out of range (0..{len(self._leaves) - 1})")

        n = turn + 1
        leaves = self._leaves[:n]
        size = _next_pow2(n)
        layer = leaves + [leaves[-1]] * (size - len(leaves))

        siblings: list[dict] = []
        idx = turn
        while len(layer) > 1:
            if idx % 2 == 0:
                sib_idx = idx + 1
                siblings.append({"position": "right", "hash": layer[sib_idx]})
            else:
                sib_idx = idx - 1
                siblings.append({"position": "left", "hash": layer[sib_idx]})
            idx //= 2
            layer = [_sha(layer[i] + layer[i + 1]) for i in range(0, len(layer), 2)]

        return {
            "turn": turn,
            "leaf_hash": self._leaves[turn],
            "proof": siblings,
            "root": self._roots[turn],
            "leaf_count": n,
        }

    # ------------------------------------------------------------------ #
    # Verification (standalone — no tree instance needed)
    # ------------------------------------------------------------------ #

    @staticmethod
    def verify(leaf_hash: str, proof: list[dict], root: str) -> bool:
        """Verify a proof path against a known root."""
        current = leaf_hash
        for step in proof:
            if step["position"] == "right":
                current = _sha(current + step["hash"])
            else:
                current = _sha(step["hash"] + current)
        return current == root

    # ------------------------------------------------------------------ #
    # Reconstruction
    # ------------------------------------------------------------------ #

    @classmethod
    def from_leaves(cls, leaf_hashes: list[str]) -> "MerkleTree":
        """Rebuild tree from an ordered list of leaf hashes."""
        tree = cls()
        for h in leaf_hashes:
            tree.append(h)
        return tree

    def __repr__(self) -> str:
        return f"MerkleTree(leaves={self.leaf_count}, root={self.root!r})"
