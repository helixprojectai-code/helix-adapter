# helix-adapter v1.6.0 Release Notes

**Released:** 2026-06-30
**Branch:** spider-dev → main
**PyPI:** `pip install helix-adapter==1.6.0`

---

## What's New

### Append-Only Merkle Tree — Dual Tamper Evidence

The headline feature of v1.6. Every session now carries two independent integrity
structures over its receipt chain:

| Structure | What it catches | Cost |
|-----------|----------------|------|
| `chain_hash` | Sequence tampering — reorder, insert, or delete a receipt | O(1) per turn |
| Merkle tree | Membership claims — prove any specific receipt is in the session | O(log n) per proof |

They are complementary. `chain_hash` tells you the history hasn't been rewritten.
A Merkle proof tells you a specific receipt belongs to a specific session state —
without revealing the rest of the chain.

```python
from helix_adapter import HelixSession, MerkleTree, SQLiteReceiptStore

session = HelixSession(model_fn=call_model, store=SQLiteReceiptStore())

r0 = session.send("What is Cedar policy?")
r1 = session.send("How does it relate to ZTC?")

# Root after turn 1
print(session.merkle_root)          # sha256 of the full tree

# Prove turn 0 is in the session
proof = session.merkle_proof(0)
valid = MerkleTree.verify(proof["leaf_hash"], proof["proof"], proof["root"])
print(valid)                        # True

# Historical root — turn 0's root, permanently sealed
print(session.merkle_root)         # different from turn 0's root
print(proof["root"])               # turn 0's root — unchanged by later turns
```

Historical roots are immutable. A proof generated against `root_at(3)` remains
valid regardless of how many turns are added afterward. This is the append-only
guarantee.

---

### MerkleTree — Public API

`MerkleTree` is now a first-class export from `helix_adapter`:

```python
from helix_adapter import MerkleTree

tree = MerkleTree()
tree.append("receipt-hash-0")
tree.append("receipt-hash-1")
tree.append("receipt-hash-2")

proof = tree.proof(1)
MerkleTree.verify(proof["leaf_hash"], proof["proof"], proof["root"])  # True

# Reconstruct from stored hashes (e.g. after loading from DB)
tree2 = MerkleTree.from_leaves(["receipt-hash-0", "receipt-hash-1", "receipt-hash-2"])
assert tree.root == tree2.root
```

Duplicate-last leaf padding — the Bitcoin standard. Trees with any number of leaves
produce valid proofs, including single-leaf and odd-count trees.

---

### merkle_root on JointReceipt

Every `JointReceipt` now carries `merkle_root` — the tree root at the moment that
receipt was sealed:

```python
receipt = session.send("Turn 3")

print(receipt.hash)          # this receipt's hash (leaf)
print(receipt.chain_hash)    # linear chain linking to all prior turns
print(receipt.merkle_root)   # Merkle root of leaves 0..3
```

The three fields together give you the complete tamper-evidence picture: content
integrity (`hash`), sequence integrity (`chain_hash`), and membership integrity
(`merkle_root`).

---

### merkle_consistency_check() — 3-Layer Validation

`HelixSession.merkle_consistency_check()` runs all three integrity layers in one call:

1. **Chain integrity** — recomputes `chain_hash` from stored receipts and compares
2. **Merkle integrity** — rebuilds tree from receipt hashes and compares root
3. **Cross-check** — verifies each receipt's stored `merkle_root` matches the
   rebuilt tree root at its turn

Returns `True` if all three pass. Logs warnings on any mismatch. Use after `resume()`
on untrusted storage, or as a periodic health check on long-running sessions.

```python
session = HelixSession.resume(session_id, model_fn=fn, store=store)
if not session.merkle_consistency_check():
    raise RuntimeError("Session integrity failure — do not continue")
```

---

### Foundry: Session Management Layer

`HelixSession` is now fully integrated into Helix Foundry. Cedar routes the context
on session start, the model is locked for the session lifetime, and every turn is
receipt-sealed with the full dual tamper-evidence stack.

**New endpoints:**

| Endpoint | Method | What it does |
|----------|--------|--------------|
| `/session/start` | POST | Cedar-route context, commit model, create session |
| `/session/{id}/send` | POST | Send turn, get `JointReceipt` fields back |
| `/session/{id}` | GET | Metadata + full receipt chain + `merkle_root` |
| `/session/{id}/export` | GET | Full chain as JSON or JSONL |
| `/session/{id}/merkle` | GET | Current root, leaf count, all historical roots |
| `/session/{id}/merkle/{turn}` | GET | Inclusion proof + inline `valid: bool` |
| `/session/{id}` | DELETE | Remove session and receipt chain |
| `/sessions` | GET | All sessions with stats |

---

### Foundry: Sessions UI

New `/sessions/` page — table of active receipt chains with running drift per session,
per-receipt detail view, and a Merkle proof viewer. Click any session to expand the
receipt chain; click any receipt to see its inclusion proof verified inline.

**Routed Chat session mode** — checkbox in the existing UI. First send starts a
Cedar-routed session; subsequent sends go to the committed model. Badge shows session
ID, model, turn number, and chain hash prefix. "End Session" deletes and resets.

---

## Testing

11 new tests in `tests/test_merkle.py`. 22-check end-to-end script
(`e2e_merkle_test.py`) covering the full stack without API keys. Full suite: 141
tests passing, reviewed against live Foundry by the Hermes node.

Coverage: single/multi-leaf trees, historical roots, proofs across all turn counts,
tamper detection on leaf and proof path, reconstruction from stored hashes, session
resume with continued sends, consistency check on clean and resumed sessions.

---

## CI

**ruff + black** enforced via `.github/workflows/lint.yml` — runs on push to
`main`, `spider-dev`, `helix-dev`, and on all PRs to `main`. Configuration in
`pyproject.toml` under `[tool.ruff]` and `[tool.black]`.

---

## Breaking Changes

None. `HelixAdapter`, `HelixSession`, and all existing integrations are unchanged.
`JointReceipt` gains one new optional field: `merkle_root: Optional[str] = None`.
Receipts generated before v1.6.0 deserialize cleanly with `merkle_root=None`.

---

## What's Next

- Qwen Cloud deployment — full Foundry stack on Alibaba Cloud Model Studio
  (140+ model catalogue, Cedar routing across sovereign CN infrastructure)
- Session context window management (truncation strategy for long conversations)
- PyPI release under Helix AI Innovations org
