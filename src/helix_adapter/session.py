# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0

"""HelixSession — multi-turn constitutional session host.

Wraps any inference backend with:
- Multi-turn conversation context
- Per-turn JointReceipt (Cedar + Duck Gate co-sealed)
- Tamper-evident chain_hash linking all receipts
- Configurable drift thresholds
- Pluggable receipt store (in-memory or SQLite)

Usage:
    session = HelixSession(model_fn=my_fn, model_name="deepseek-4-pro")
    result = session.send("What is Cedar?")
    session.export()
    session.delete()

    # Resume a prior session
    session = HelixSession.resume("session-id", model_fn=my_fn, store=store)

    # Context manager
    with HelixSession(model_fn=my_fn) as session:
        result = session.send("Hello")
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid
import warnings
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .drift import compute_drift
from .markers import extract_claims
from .merkle import MerkleTree
from .prompt import CONSTITUTIONAL_PROMPT, system_messages
from .receipt import make_receipt
from .store import InMemoryReceiptStore, ReceiptStore

try:
    from .cedar import CedarPolicy
except ImportError:
    CedarPolicy = None


@dataclass
class DriftThreshold:
    green: float = 0.10
    yellow: float = 0.17
    red: float = 0.30

    def tier(self, score: float) -> str:
        if score < self.green:
            return "green"
        if score < self.yellow:
            return "yellow"
        return "red"


@dataclass
class JointReceipt:
    """Single tamper-evident record covering one session turn.

    Seals both Duck Gate (drift, claims) and Cedar Gate (action decision)
    in one receipt, chained to all prior turns via chain_hash.
    """
    exchange_id: str
    session_id: str
    turn: int
    timestamp: str
    model: str

    # Duck Gate
    user_message: str
    assistant_response: str
    claims: list
    drift_score: float
    drift_tier: str
    drift_method: str

    # Cedar Gate (null if no tool call this turn)
    cedar_action: Optional[str]
    cedar_authorized: Optional[bool]
    cedar_policy_hash: Optional[str]
    cedar_reason: Optional[str]
    cedar_status: str  # active | fail_closed | not_configured

    # Chain
    hash: str
    chain_hash: str

    def to_dict(self) -> dict:
        import dataclasses
        return dataclasses.asdict(self)


class HelixSession:
    """Multi-turn constitutional session host."""

    def __init__(
        self,
        model_fn: Callable[[list[dict]], str],
        model_name: str = "unknown",
        drift_threshold: Optional[DriftThreshold] = None,
        cedar_policy: Optional[Any] = None,
        store: Optional[ReceiptStore] = None,
        session_id: Optional[str] = None,
        _context: Optional[list] = None,
        _turn: int = 0,
        _last_chain_hash: str = "",
    ):
        self.model_fn = model_fn
        self.model_name = model_name
        self.threshold = drift_threshold or DriftThreshold()
        self.cedar_policy = cedar_policy
        self.store = store or InMemoryReceiptStore()
        self.session_id = session_id or f"hsess-{uuid.uuid4().hex[:12]}"
        self._context: list[dict] = _context or []
        self._turn = _turn
        self._last_chain_hash = _last_chain_hash
        self._merkle: MerkleTree = MerkleTree()

        if cedar_policy and hasattr(cedar_policy, "is_fail_closed") and cedar_policy.is_fail_closed:
            warnings.warn(
                f"Cedar policy is FAIL-CLOSED for session {self.session_id}. "
                f"Reason: {cedar_policy.validation_error}",
                RuntimeWarning,
                stacklevel=2,
            )

    # ------------------------------------------------------------------ #
    # Class methods — lifecycle
    # ------------------------------------------------------------------ #

    @classmethod
    def resume(
        cls,
        session_id: str,
        model_fn: Callable[[list[dict]], str],
        store: ReceiptStore,
        model_name: str = "unknown",
        drift_threshold: Optional[DriftThreshold] = None,
        cedar_policy: Optional[Any] = None,
    ) -> "HelixSession":
        """Reload a prior session from store, restoring context window."""
        receipts = store.get_session(session_id)
        if not receipts:
            raise ValueError(f"No session found: {session_id}")

        # Rebuild context from stored receipts
        context: list[dict] = system_messages()
        for r in receipts:
            context.append({"role": "user", "content": r["user_message"]})
            context.append({"role": "assistant", "content": r["assistant_response"]})

        last = receipts[-1]
        instance = cls(
            model_fn=model_fn,
            model_name=model_name,
            drift_threshold=drift_threshold,
            cedar_policy=cedar_policy,
            store=store,
            session_id=session_id,
            _context=context,
            _turn=last["turn"] + 1,
            _last_chain_hash=last["chain_hash"],
        )
        instance._merkle = MerkleTree.from_leaves([r["hash"] for r in receipts])
        return instance

    # ------------------------------------------------------------------ #
    # Core — send
    # ------------------------------------------------------------------ #

    def send(self, message: str) -> JointReceipt:
        """Send a message, get a JointReceipt back."""
        # Build context
        if not self._context:
            self._context = system_messages()
        self._context.append({"role": "user", "content": message})

        # Call model
        response = self.model_fn(self._context)
        self._context.append({"role": "assistant", "content": response})

        # Duck Gate
        claims = extract_claims(response)
        drift = compute_drift(response, claims)
        tier = self.threshold.tier(drift)

        # Cedar status
        cedar_status = "not_configured"
        cedar_policy_hash = None
        if self.cedar_policy:
            if hasattr(self.cedar_policy, "is_fail_closed") and self.cedar_policy.is_fail_closed:
                cedar_status = "fail_closed"
            else:
                cedar_status = "active"
                cedar_policy_hash = getattr(self.cedar_policy, "policy_hash", None)

        # Build receipt dict for hashing
        exchange_id = hashlib.sha256(
            (self.session_id + str(self._turn) + str(time.time())).encode()
        ).hexdigest()[:16]

        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        receipt_body = {
            "exchange_id": exchange_id,
            "session_id": self.session_id,
            "turn": self._turn,
            "timestamp": timestamp,
            "model": self.model_name,
            "user_message": message,
            "assistant_response": response,
            "claims": claims,
            "drift_score": round(drift, 4),
            "drift_tier": tier,
            "drift_method": "char",
            "cedar_action": None,
            "cedar_authorized": None,
            "cedar_policy_hash": cedar_policy_hash,
            "cedar_reason": None,
            "cedar_status": cedar_status,
        }

        # Self-hash
        receipt_hash = hashlib.sha256(
            json.dumps(receipt_body, sort_keys=True, default=str).encode()
        ).hexdigest()

        # Chain hash — links to all prior turns
        chain_hash = hashlib.sha256(
            (self._last_chain_hash + receipt_hash).encode()
        ).hexdigest()

        receipt = JointReceipt(
            **receipt_body,
            hash=receipt_hash,
            chain_hash=chain_hash,
        )

        merkle_root = self._merkle.append(receipt_hash)

        self.store.save({**receipt.to_dict(), "merkle_root": merkle_root})
        self._last_chain_hash = chain_hash
        self._turn += 1

        return receipt

    # ------------------------------------------------------------------ #
    # Session management
    # ------------------------------------------------------------------ #

    def clear(self) -> None:
        """Wipe conversation history and receipt chain. Session ID stays active."""
        self._context = []
        self._turn = 0
        self._last_chain_hash = ""
        self.store.delete_session(self.session_id)

    def delete(self) -> None:
        """Remove session from store entirely."""
        self.store.delete_session(self.session_id)

    def export(self, fmt: str = "jsonl") -> str:
        """Serialize the full receipt chain. fmt: 'jsonl' or 'json'."""
        return self.store.export_session(self.session_id, fmt=fmt)

    def running_drift(self) -> float:
        """Weighted running drift across all turns in this session."""
        receipts = self.store.get_session(self.session_id)
        if not receipts:
            return 0.0
        total_drift = sum(r.get("drift_score", 0.0) for r in receipts)
        return round(total_drift / len(receipts), 4)

    @property
    def merkle_root(self) -> str | None:
        return self._merkle.root

    def merkle_proof(self, turn: int) -> dict:
        return self._merkle.proof(turn)

    def merkle_all_roots(self) -> list[dict]:
        return self._merkle.all_roots()

    @property
    def turn(self) -> int:
        return self._turn

    @property
    def id(self) -> str:
        return self.session_id

    # ------------------------------------------------------------------ #
    # Context manager
    # ------------------------------------------------------------------ #

    def __enter__(self) -> "HelixSession":
        return self

    def __exit__(self, *_) -> None:
        pass

    def __repr__(self) -> str:
        return f"HelixSession(id={self.session_id!r}, turn={self._turn}, model={self.model_name!r})"
