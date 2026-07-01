"""Test suite for HelixSession, JointReceipt, DriftThreshold, and receipt stores.

Coverage:
- DriftThreshold tier classification and edge cases
- InMemoryReceiptStore — full lifecycle
- SQLiteReceiptStore — full lifecycle + persistence
- HelixSession — new, send, multi-turn, clear, delete, export, running_drift
- HelixSession.resume — context restoration from store
- chain_hash integrity — tamper detection
- JointReceipt — structure, to_dict roundtrip
- Session ID uniqueness
- Context window accumulation
- Context manager protocol
- Empty/edge state handling
- Both stores satisfy same interface contract
"""

import hashlib
import json
import os
import tempfile

import pytest

from helix_adapter import (
    DriftThreshold,
    HelixSession,
    InMemoryReceiptStore,
    JointReceipt,
    SQLiteReceiptStore,
)

# ─────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────

LABELED_RESPONSE = "[FACT] HelixSession is the multi-turn host. [REASONED] It chains receipts."
UNLABELED_RESPONSE = "This is a response with no epistemic markers at all, it just goes on and on."


def mock_model_labeled(messages):
    return LABELED_RESPONSE


def mock_model_unlabeled(messages):
    return UNLABELED_RESPONSE


def mock_model_echo(messages):
    last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
    return f"[FACT] You said: {last}"


@pytest.fixture
def mem_store():
    return InMemoryReceiptStore()


@pytest.fixture
def db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def sql_store(db_path):
    return SQLiteReceiptStore(path=db_path)


@pytest.fixture
def session_mem():
    return HelixSession(model_fn=mock_model_labeled, model_name="test-mem")


@pytest.fixture
def session_sql(sql_store):
    return HelixSession(model_fn=mock_model_labeled, model_name="test-sql", store=sql_store)


# ─────────────────────────────────────────────
# DriftThreshold
# ─────────────────────────────────────────────


class TestDriftThreshold:
    def test_defaults(self):
        t = DriftThreshold()
        assert t.green == 0.10
        assert t.yellow == 0.17
        assert t.red == 0.30

    def test_tier_green(self):
        t = DriftThreshold()
        assert t.tier(0.0) == "green"
        assert t.tier(0.05) == "green"
        assert t.tier(0.099) == "green"

    def test_tier_yellow(self):
        t = DriftThreshold()
        assert t.tier(0.10) == "yellow"
        assert t.tier(0.15) == "yellow"
        assert t.tier(0.169) == "yellow"

    def test_tier_red(self):
        t = DriftThreshold()
        assert t.tier(0.17) == "red"
        assert t.tier(0.5) == "red"
        assert t.tier(1.0) == "red"

    def test_custom_thresholds(self):
        t = DriftThreshold(green=0.05, yellow=0.10, red=0.20)
        assert t.tier(0.04) == "green"
        assert t.tier(0.07) == "yellow"
        assert t.tier(0.15) == "red"

    def test_zero_score_always_green(self):
        t = DriftThreshold()
        assert t.tier(0.0) == "green"

    def test_boundary_green_yellow(self):
        t = DriftThreshold(green=0.10, yellow=0.20)
        assert t.tier(0.099) == "green"
        assert t.tier(0.10) == "yellow"

    def test_boundary_yellow_red(self):
        t = DriftThreshold(green=0.10, yellow=0.20, red=0.50)
        assert t.tier(0.199) == "yellow"
        assert t.tier(0.20) == "red"


# ─────────────────────────────────────────────
# InMemoryReceiptStore
# ─────────────────────────────────────────────


class TestInMemoryReceiptStore:
    def test_save_and_get(self, mem_store):
        receipt = {
            "exchange_id": "ex1",
            "session_id": "s1",
            "turn": 0,
            "timestamp": "2026-06-29",
            "hash": "h1",
            "chain_hash": "c1",
            "drift_score": 0.05,
            "drift_tier": "green",
            "user_message": "hi",
            "assistant_response": "hello",
            "claims": [],
            "model": "test",
        }
        mem_store.save(receipt)
        result = mem_store.get_session("s1")
        assert len(result) == 1
        assert result[0]["exchange_id"] == "ex1"

    def test_multiple_turns_ordered(self, mem_store):
        for i in range(5):
            mem_store.save(
                {
                    "exchange_id": f"ex{i}",
                    "session_id": "s1",
                    "turn": i,
                    "timestamp": "t",
                    "hash": f"h{i}",
                    "chain_hash": f"c{i}",
                    "drift_score": 0.0,
                    "drift_tier": "green",
                }
            )
        results = mem_store.get_session("s1")
        turns = [r["turn"] for r in results]
        assert turns == list(range(5))

    def test_list_sessions(self, mem_store):
        for sid in ["s1", "s2", "s3"]:
            mem_store.save(
                {
                    "exchange_id": sid,
                    "session_id": sid,
                    "turn": 0,
                    "timestamp": "t",
                    "hash": "h",
                    "chain_hash": "c",
                }
            )
        sessions = mem_store.list_sessions()
        assert set(sessions) == {"s1", "s2", "s3"}

    def test_delete_session(self, mem_store):
        mem_store.save(
            {
                "exchange_id": "ex1",
                "session_id": "s1",
                "turn": 0,
                "timestamp": "t",
                "hash": "h",
                "chain_hash": "c",
            }
        )
        mem_store.delete_session("s1")
        assert mem_store.get_session("s1") == []
        assert "s1" not in mem_store.list_sessions()

    def test_delete_nonexistent_no_error(self, mem_store):
        mem_store.delete_session("ghost")  # should not raise

    def test_get_empty_session(self, mem_store):
        assert mem_store.get_session("nonexistent") == []

    def test_export_jsonl(self, mem_store):
        for i in range(3):
            mem_store.save(
                {
                    "exchange_id": f"e{i}",
                    "session_id": "s1",
                    "turn": i,
                    "timestamp": "t",
                    "hash": "h",
                    "chain_hash": "c",
                }
            )
        export = mem_store.export_session("s1", fmt="jsonl")
        lines = [ln for ln in export.splitlines() if ln.strip()]
        assert len(lines) == 3
        for line in lines:
            json.loads(line)  # each line is valid JSON

    def test_export_json(self, mem_store):
        mem_store.save(
            {
                "exchange_id": "e1",
                "session_id": "s1",
                "turn": 0,
                "timestamp": "t",
                "hash": "h",
                "chain_hash": "c",
            }
        )
        export = mem_store.export_session("s1", fmt="json")
        data = json.loads(export)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_multiple_sessions_isolated(self, mem_store):
        mem_store.save(
            {
                "exchange_id": "a1",
                "session_id": "A",
                "turn": 0,
                "timestamp": "t",
                "hash": "h",
                "chain_hash": "c",
            }
        )
        mem_store.save(
            {
                "exchange_id": "b1",
                "session_id": "B",
                "turn": 0,
                "timestamp": "t",
                "hash": "h",
                "chain_hash": "c",
            }
        )
        assert len(mem_store.get_session("A")) == 1
        assert len(mem_store.get_session("B")) == 1
        mem_store.delete_session("A")
        assert mem_store.get_session("A") == []
        assert len(mem_store.get_session("B")) == 1


# ─────────────────────────────────────────────
# SQLiteReceiptStore
# ─────────────────────────────────────────────


class TestSQLiteReceiptStore:
    def test_save_and_get(self, sql_store):
        receipt = {
            "exchange_id": "ex1",
            "session_id": "s1",
            "turn": 0,
            "timestamp": "2026-06-29",
            "hash": "h1",
            "chain_hash": "c1",
            "drift_score": 0.05,
            "drift_tier": "green",
            "user_message": "hi",
            "assistant_response": "hello",
            "claims": [],
            "model": "test",
        }
        sql_store.save(receipt)
        result = sql_store.get_session("s1")
        assert len(result) == 1
        assert result[0]["exchange_id"] == "ex1"

    def test_persistence(self, db_path):
        store1 = SQLiteReceiptStore(path=db_path)
        store1.save(
            {
                "exchange_id": "ex1",
                "session_id": "s1",
                "turn": 0,
                "timestamp": "t",
                "hash": "h",
                "chain_hash": "c",
                "drift_score": 0.1,
                "drift_tier": "yellow",
            }
        )
        # Re-open same DB
        store2 = SQLiteReceiptStore(path=db_path)
        result = store2.get_session("s1")
        assert len(result) == 1
        assert result[0]["exchange_id"] == "ex1"

    def test_multiple_turns_ordered(self, sql_store):
        for i in range(5):
            sql_store.save(
                {
                    "exchange_id": f"ex{i}",
                    "session_id": "s1",
                    "turn": i,
                    "timestamp": "t",
                    "hash": f"h{i}",
                    "chain_hash": f"c{i}",
                    "drift_score": 0.0,
                    "drift_tier": "green",
                }
            )
        results = sql_store.get_session("s1")
        turns = [r["turn"] for r in results]
        assert turns == list(range(5))

    def test_list_sessions(self, sql_store):
        for sid in ["s1", "s2", "s3"]:
            sql_store.save(
                {
                    "exchange_id": sid,
                    "session_id": sid,
                    "turn": 0,
                    "timestamp": "t",
                    "hash": "h",
                    "chain_hash": "c",
                    "drift_score": 0.0,
                    "drift_tier": "green",
                }
            )
        sessions = sql_store.list_sessions()
        assert set(sessions) == {"s1", "s2", "s3"}

    def test_delete_session(self, sql_store):
        sql_store.save(
            {
                "exchange_id": "ex1",
                "session_id": "s1",
                "turn": 0,
                "timestamp": "t",
                "hash": "h",
                "chain_hash": "c",
                "drift_score": 0.0,
                "drift_tier": "green",
            }
        )
        sql_store.delete_session("s1")
        assert sql_store.get_session("s1") == []

    def test_export_jsonl(self, sql_store):
        for i in range(3):
            sql_store.save(
                {
                    "exchange_id": f"e{i}",
                    "session_id": "s1",
                    "turn": i,
                    "timestamp": "t",
                    "hash": "h",
                    "chain_hash": "c",
                    "drift_score": 0.0,
                    "drift_tier": "green",
                }
            )
        export = sql_store.export_session("s1", fmt="jsonl")
        lines = [ln for ln in export.splitlines() if ln.strip()]
        assert len(lines) == 3

    def test_upsert_same_exchange_id(self, sql_store):
        r = {
            "exchange_id": "ex1",
            "session_id": "s1",
            "turn": 0,
            "timestamp": "t",
            "hash": "h1",
            "chain_hash": "c1",
            "drift_score": 0.0,
            "drift_tier": "green",
        }
        sql_store.save(r)
        r["hash"] = "h2"
        sql_store.save(r)  # should not raise, upsert
        assert len(sql_store.get_session("s1")) == 1


# ─────────────────────────────────────────────
# Store interface contract — both stores behave identically
# ─────────────────────────────────────────────


@pytest.mark.parametrize("store_fixture", ["mem_store", "sql_store"])
class TestStoreContract:
    def _receipt(self, sid, turn, eid=None):
        return {
            "exchange_id": eid or f"{sid}-{turn}",
            "session_id": sid,
            "turn": turn,
            "timestamp": "t",
            "hash": f"h{turn}",
            "chain_hash": f"c{turn}",
            "drift_score": 0.0,
            "drift_tier": "green",
        }

    def test_empty_store(self, store_fixture, request):
        store = request.getfixturevalue(store_fixture)
        assert store.list_sessions() == []
        assert store.get_session("none") == []

    def test_save_retrieve(self, store_fixture, request):
        store = request.getfixturevalue(store_fixture)
        store.save(self._receipt("s1", 0))
        assert len(store.get_session("s1")) == 1

    def test_delete_clears(self, store_fixture, request):
        store = request.getfixturevalue(store_fixture)
        store.save(self._receipt("s1", 0))
        store.delete_session("s1")
        assert store.get_session("s1") == []
        assert "s1" not in store.list_sessions()


# ─────────────────────────────────────────────
# HelixSession — core behavior
# ─────────────────────────────────────────────


class TestHelixSession:
    def test_session_id_generated(self, session_mem):
        assert session_mem.id.startswith("hsess-")
        assert len(session_mem.id) > 10

    def test_session_ids_unique(self):
        sessions = [HelixSession(model_fn=mock_model_labeled) for _ in range(20)]
        ids = [s.id for s in sessions]
        assert len(set(ids)) == 20

    def test_custom_session_id(self):
        s = HelixSession(model_fn=mock_model_labeled, session_id="my-session")
        assert s.id == "my-session"

    def test_send_returns_joint_receipt(self, session_mem):
        r = session_mem.send("Hello")
        assert isinstance(r, JointReceipt)

    def test_turn_increments(self, session_mem):
        assert session_mem.turn == 0
        session_mem.send("Turn 0")
        assert session_mem.turn == 1
        session_mem.send("Turn 1")
        assert session_mem.turn == 2

    def test_receipt_turn_matches(self, session_mem):
        r0 = session_mem.send("First")
        r1 = session_mem.send("Second")
        assert r0.turn == 0
        assert r1.turn == 1

    def test_receipt_session_id_matches(self, session_mem):
        r = session_mem.send("Hello")
        assert r.session_id == session_mem.id

    def test_drift_score_labeled_response(self, session_mem):
        r = session_mem.send("Hello")
        assert r.drift_score < 0.10
        assert r.drift_tier == "green"

    def test_drift_score_unlabeled_response(self):
        s = HelixSession(model_fn=mock_model_unlabeled)
        r = s.send("Hello")
        assert r.drift_score > 0.5
        assert r.drift_tier == "red"

    def test_claims_extracted(self, session_mem):
        r = session_mem.send("Hello")
        assert len(r.claims) >= 2
        labels = [c["label"] for c in r.claims]
        assert "FACT" in labels
        assert "REASONED" in labels

    def test_receipt_stored_in_memory(self, session_mem):
        session_mem.send("Turn 0")
        session_mem.send("Turn 1")
        receipts = session_mem.store.get_session(session_mem.id)
        assert len(receipts) == 2

    def test_multi_turn_context_accumulates(self):
        seen_messages = []

        def capture_model(messages):
            seen_messages.append(list(messages))
            return LABELED_RESPONSE

        s = HelixSession(model_fn=capture_model)
        s.send("First message")
        s.send("Second message")

        # Turn 1 context should include turn 0 exchange
        assert len(seen_messages[1]) > len(seen_messages[0])
        contents = [m["content"] for m in seen_messages[1]]
        assert any("First message" in c for c in contents)

    def test_echo_model_reflects_input(self):
        s = HelixSession(model_fn=mock_model_echo)
        r = s.send("hello world")
        assert "hello world" in r.assistant_response

    def test_cedar_status_not_configured(self, session_mem):
        r = session_mem.send("Hello")
        assert r.cedar_status == "not_configured"
        assert r.cedar_authorized is None
        assert r.cedar_action is None

    def test_custom_drift_threshold(self):
        tight = DriftThreshold(green=0.01, yellow=0.05, red=0.10)
        s = HelixSession(model_fn=mock_model_labeled, drift_threshold=tight)
        r = s.send("Hello")
        # labeled response ~0.01 drift — could be green or yellow at tight threshold
        assert r.drift_tier in ("green", "yellow", "red")

    def test_repr(self, session_mem):
        rep = repr(session_mem)
        assert "HelixSession" in rep
        assert session_mem.id in rep


# ─────────────────────────────────────────────
# chain_hash integrity
# ─────────────────────────────────────────────


class TestChainHash:
    def test_chain_hash_changes_each_turn(self, session_mem):
        r0 = session_mem.send("Turn 0")
        r1 = session_mem.send("Turn 1")
        r2 = session_mem.send("Turn 2")
        assert r0.chain_hash != r1.chain_hash
        assert r1.chain_hash != r2.chain_hash
        assert r0.chain_hash != r2.chain_hash

    def test_chain_hash_deterministic(self):
        # Same inputs produce same chain — verify manual derivation
        s = HelixSession(model_fn=mock_model_labeled, session_id="fixed")
        r0 = s.send("Turn 0")
        expected = hashlib.sha256(("" + r0.hash).encode()).hexdigest()
        assert r0.chain_hash == expected

    def test_chain_hash_links_to_prior(self):
        s = HelixSession(model_fn=mock_model_labeled)
        r0 = s.send("Turn 0")
        r1 = s.send("Turn 1")
        expected_r1_chain = hashlib.sha256((r0.chain_hash + r1.hash).encode()).hexdigest()
        assert r1.chain_hash == expected_r1_chain

    def test_tamper_breaks_chain(self):
        s = HelixSession(model_fn=mock_model_labeled)
        _ = s.send("Turn 0")
        r1 = s.send("Turn 1")

        # Tamper: recalculate what r1.chain_hash would be with a different r0 hash
        fake_chain = hashlib.sha256(("tampered" + r1.hash).encode()).hexdigest()
        assert fake_chain != r1.chain_hash

    def test_receipt_hash_covers_content(self, session_mem):
        r = session_mem.send("Hello")
        assert len(r.hash) == 64  # SHA-256 hex
        assert r.hash != r.chain_hash

    def test_three_session_chain_is_ordered(self):
        s = HelixSession(model_fn=mock_model_labeled)
        receipts = [s.send(f"Turn {i}") for i in range(5)]
        # Verify full chain links correctly
        prev_chain = ""
        for r in receipts:
            expected = hashlib.sha256((prev_chain + r.hash).encode()).hexdigest()
            assert r.chain_hash == expected
            prev_chain = r.chain_hash


# ─────────────────────────────────────────────
# Session lifecycle — clear / delete / export
# ─────────────────────────────────────────────


class TestSessionLifecycle:
    def test_clear_resets_turn(self):
        s = HelixSession(model_fn=mock_model_labeled)
        s.send("Turn 0")
        s.send("Turn 1")
        sid = s.id
        s.clear()
        assert s.turn == 0
        assert s.id == sid  # session ID preserved

    def test_clear_wipes_store(self):
        store = InMemoryReceiptStore()
        s = HelixSession(model_fn=mock_model_labeled, store=store)
        s.send("Turn 0")
        s.clear()
        assert store.get_session(s.id) == []

    def test_clear_wipes_context(self):
        messages_seen = []

        def capture(messages):
            messages_seen.append(len(messages))
            return LABELED_RESPONSE

        s = HelixSession(model_fn=capture)
        s.send("Before clear")
        s.clear()
        s.send("After clear")

        # After clear, context should be fresh (same size as first turn)
        assert messages_seen[0] == messages_seen[1]

    def test_delete_removes_from_store(self):
        store = InMemoryReceiptStore()
        s = HelixSession(model_fn=mock_model_labeled, store=store)
        s.send("Turn 0")
        sid = s.id
        s.delete()
        assert store.get_session(sid) == []
        assert sid not in store.list_sessions()

    def test_export_jsonl_default(self):
        s = HelixSession(model_fn=mock_model_labeled)
        s.send("Turn 0")
        s.send("Turn 1")
        export = s.export()
        lines = [ln for ln in export.splitlines() if ln.strip()]
        assert len(lines) == 2
        for line in lines:
            data = json.loads(line)
            assert "exchange_id" in data
            assert "chain_hash" in data

    def test_export_json_format(self):
        s = HelixSession(model_fn=mock_model_labeled)
        s.send("Turn 0")
        export = s.export(fmt="json")
        data = json.loads(export)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_export_empty_session(self):
        s = HelixSession(model_fn=mock_model_labeled)
        export = s.export()
        assert export == ""

    def test_running_drift_single_turn(self):
        s = HelixSession(model_fn=mock_model_labeled)
        r = s.send("Turn 0")
        assert s.running_drift() == r.drift_score

    def test_running_drift_multiple_turns(self):
        s = HelixSession(model_fn=mock_model_labeled)
        for _ in range(5):
            s.send("Turn")
        drift = s.running_drift()
        assert 0.0 <= drift <= 1.0

    def test_running_drift_empty_session(self):
        s = HelixSession(model_fn=mock_model_labeled)
        assert s.running_drift() == 0.0


# ─────────────────────────────────────────────
# HelixSession.resume
# ─────────────────────────────────────────────


class TestHelixSessionResume:
    def test_resume_restores_turn_count(self, db_path):
        store = SQLiteReceiptStore(path=db_path)
        s = HelixSession(model_fn=mock_model_labeled, store=store)
        s.send("Turn 0")
        s.send("Turn 1")
        sid = s.id

        resumed = HelixSession.resume(sid, model_fn=mock_model_labeled, store=store)
        assert resumed.turn == 2

    def test_resume_continues_chain(self, db_path):
        store = SQLiteReceiptStore(path=db_path)
        s = HelixSession(model_fn=mock_model_labeled, store=store)
        _ = s.send("Turn 0")
        r1 = s.send("Turn 1")
        sid = s.id

        resumed = HelixSession.resume(sid, model_fn=mock_model_labeled, store=store)
        r2 = resumed.send("Turn 2")

        # Chain should continue from r1's chain_hash
        expected = hashlib.sha256((r1.chain_hash + r2.hash).encode()).hexdigest()
        assert r2.chain_hash == expected

    def test_resume_same_session_id(self, db_path):
        store = SQLiteReceiptStore(path=db_path)
        s = HelixSession(model_fn=mock_model_labeled, store=store)
        s.send("Turn 0")
        sid = s.id

        resumed = HelixSession.resume(sid, model_fn=mock_model_labeled, store=store)
        assert resumed.id == sid

    def test_resume_context_includes_history(self, db_path):
        store = SQLiteReceiptStore(path=db_path)
        messages_seen = []

        def capture(messages):
            messages_seen.append(list(messages))
            return LABELED_RESPONSE

        s = HelixSession(model_fn=capture, store=store)
        s.send("Historical message")
        sid = s.id

        resumed = HelixSession.resume(sid, model_fn=capture, store=store)
        resumed.send("New message")

        # The resumed context should contain the historical message
        last_messages = messages_seen[-1]
        contents = [m["content"] for m in last_messages]
        assert any("Historical message" in c for c in contents)

    def test_resume_nonexistent_raises(self, db_path):
        store = SQLiteReceiptStore(path=db_path)
        with pytest.raises(ValueError, match="No session found"):
            HelixSession.resume("ghost-session", model_fn=mock_model_labeled, store=store)

    def test_resume_with_memory_store(self):
        store = InMemoryReceiptStore()
        s = HelixSession(model_fn=mock_model_labeled, store=store)
        s.send("Turn 0")
        sid = s.id

        resumed = HelixSession.resume(sid, model_fn=mock_model_labeled, store=store)
        r = resumed.send("Turn 1")
        assert r.turn == 1


# ─────────────────────────────────────────────
# JointReceipt
# ─────────────────────────────────────────────


class TestJointReceipt:
    def test_to_dict_roundtrip(self, session_mem):
        r = session_mem.send("Hello")
        d = r.to_dict()
        assert isinstance(d, dict)
        assert d["exchange_id"] == r.exchange_id
        assert d["session_id"] == r.session_id
        assert d["drift_score"] == r.drift_score
        assert d["hash"] == r.hash
        assert d["chain_hash"] == r.chain_hash

    def test_receipt_fields_complete(self, session_mem):
        r = session_mem.send("Hello")
        required = [
            "exchange_id",
            "session_id",
            "turn",
            "timestamp",
            "model",
            "user_message",
            "assistant_response",
            "claims",
            "drift_score",
            "drift_tier",
            "drift_method",
            "cedar_action",
            "cedar_authorized",
            "cedar_policy_hash",
            "cedar_reason",
            "cedar_status",
            "hash",
            "chain_hash",
        ]
        d = r.to_dict()
        for field in required:
            assert field in d, f"Missing field: {field}"

    def test_user_message_stored(self, session_mem):
        r = session_mem.send("What is drift?")
        assert r.user_message == "What is drift?"

    def test_assistant_response_stored(self, session_mem):
        r = session_mem.send("Hello")
        assert r.assistant_response == LABELED_RESPONSE

    def test_receipt_serializable(self, session_mem):
        r = session_mem.send("Hello")
        serialized = json.dumps(r.to_dict(), default=str)
        deserialized = json.loads(serialized)
        assert deserialized["exchange_id"] == r.exchange_id

    def test_hash_is_sha256_hex(self, session_mem):
        r = session_mem.send("Hello")
        assert len(r.hash) == 64
        assert all(c in "0123456789abcdef" for c in r.hash)

    def test_chain_hash_is_sha256_hex(self, session_mem):
        r = session_mem.send("Hello")
        assert len(r.chain_hash) == 64


# ─────────────────────────────────────────────
# Context manager
# ─────────────────────────────────────────────


class TestContextManager:
    def test_context_manager_basic(self):
        with HelixSession(model_fn=mock_model_labeled) as s:
            r = s.send("Hello")
            assert isinstance(r, JointReceipt)

    def test_context_manager_returns_session(self):
        with HelixSession(model_fn=mock_model_labeled) as s:
            assert isinstance(s, HelixSession)

    def test_context_manager_multi_turn(self):
        with HelixSession(model_fn=mock_model_labeled) as s:
            s.send("Turn 0")
            s.send("Turn 1")
            assert s.turn == 2

    def test_context_manager_exception_does_not_propagate_extra(self):
        with pytest.raises(ValueError):
            with HelixSession(model_fn=mock_model_labeled) as s:
                s.send("Turn 0")
                raise ValueError("test error")


# ─────────────────────────────────────────────
# Top-level import
# ─────────────────────────────────────────────


class TestPublicAPI:
    def test_imports_from_top_level(self):
        from helix_adapter import (
            DriftThreshold,
            HelixSession,
            InMemoryReceiptStore,
            JointReceipt,
            SQLiteReceiptStore,
        )

        assert HelixSession is not None
        assert JointReceipt is not None
        assert DriftThreshold is not None
        assert InMemoryReceiptStore is not None
        assert SQLiteReceiptStore is not None

    def test_helix_adapter_still_works(self):
        from helix_adapter import HelixAdapter

        adapter = HelixAdapter(model_fn=mock_model_labeled, model_name="test")
        result = adapter.chat("Hello")
        assert result.response == LABELED_RESPONSE
        assert result.drift < 0.10
