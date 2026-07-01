#!/usr/bin/env python3
"""End-to-end local test — HelixSession Merkle + chain integrity.

No API keys needed. Mock model_fn returns constitutional responses.
Tests: session send, chain_hash, merkle_root, proofs, consistency_check,
resume, and tamper detection.
"""

import sys
sys.path.insert(0, "src")

from helix_adapter import HelixSession, MerkleTree
from helix_adapter.store import SQLiteReceiptStore
import tempfile, os

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"

def check(label, condition):
    mark = PASS if condition else FAIL
    print(f"  {mark}  {label}")
    if not condition:
        raise SystemExit(f"FAILED: {label}")

def mock_model(messages):
    last = messages[-1]["content"] if messages else "hello"
    return f"[FACT] Responding to: {last[:40]}. [REASONED] This is a test response."

def main():
    print("\n── HelixSession End-to-End Merkle Test ──\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        store = SQLiteReceiptStore(path=db_path)

        # ── 1. Create session and send 4 turns ──
        print("1. Session creation + 4 turns")
        session = HelixSession(model_fn=mock_model, model_name="mock", store=store)
        sid = session.id

        receipts = []
        for i in range(4):
            r = session.send(f"Turn {i} question")
            receipts.append(r)

        check("4 turns completed", session.turn == 4)
        check("All receipts have hash", all(r.hash for r in receipts))
        check("All receipts have chain_hash", all(r.chain_hash for r in receipts))
        check("All receipts have merkle_root", all(r.merkle_root for r in receipts))
        check("Merkle roots differ across turns", len({r.merkle_root for r in receipts}) == 4)
        check("Chain hashes differ across turns", len({r.chain_hash for r in receipts}) == 4)

        # ── 2. Merkle proof verification ──
        print("\n2. Merkle proof verification")
        for turn in range(4):
            proof = session.merkle_proof(turn)
            valid = MerkleTree.verify(proof["leaf_hash"], proof["proof"], proof["root"])
            check(f"  Turn {turn} proof valid", valid)
            check(f"  Turn {turn} leaf_hash matches receipt", proof["leaf_hash"] == receipts[turn].hash)

        # ── 3. Historical roots ──
        print("\n3. Historical roots")
        all_roots = session.merkle_all_roots()
        check("4 historical roots stored", len(all_roots) == 4)
        check("Turn 0 root matches receipt[0].merkle_root", all_roots[0]["root"] == receipts[0].merkle_root)
        check("Turn 3 root matches session.merkle_root", all_roots[3]["root"] == session.merkle_root)

        # ── 4. Consistency check ──
        print("\n4. merkle_consistency_check()")
        ok = session.merkle_consistency_check()
        check("Consistency check passes on clean session", ok)

        # ── 5. Resume ──
        print("\n5. Session resume")
        resumed = HelixSession.resume(sid, model_fn=mock_model, model_name="mock", store=store)
        check("Resume restores correct turn", resumed.turn == 4)
        check("Resume restores merkle root", resumed.merkle_root == session.merkle_root)
        check("Resume consistency check passes", resumed.merkle_consistency_check())

        r5 = resumed.send("Turn 4 after resume")
        check("Send after resume succeeds", r5.turn == 4)
        check("Turn 5 merkle_root differs from turn 4", r5.merkle_root != receipts[3].merkle_root)
        check("Turn 5 proof valid", MerkleTree.verify(
            *[resumed.merkle_proof(4)[k] for k in ("leaf_hash", "proof", "root")]
        ))

        # ── 6. Tamper detection ──
        print("\n6. Tamper detection")
        proof = resumed.merkle_proof(2)
        tampered = MerkleTree.verify("0" * 64, proof["proof"], proof["root"])
        check("Tampered leaf fails verification", not tampered)

        bad_proof = [{"position": "right", "hash": "0" * 64}] + proof["proof"][1:]
        check("Tampered proof fails verification", not MerkleTree.verify(proof["leaf_hash"], bad_proof, proof["root"]))

    print(f"\n── All checks passed ──\n")

if __name__ == "__main__":
    main()
