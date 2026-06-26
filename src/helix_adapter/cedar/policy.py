"""Cedar Policy Evaluation for Helix Dual-Gate Architecture (RFC 0003)

Uses native cedar bindings for deterministic policy evaluation.
No subprocess, no CLI dependency.

Features:
- Schema-validated policy loading
- Fail-closed by default (safe)
- Tamper-evident, receipt-chained action sealing
- Clear decision objects + rich forensic context
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).parent
DEFAULT_POLICY = HERE / "policies" / "helix.policy"
DEFAULT_SCHEMA = HERE / "policies" / "helix.schema"


# =============================================================================
# Decision & Receipt Types
# =============================================================================

@dataclass
class CedarDecision:
    """Result of a Cedar policy evaluation."""
    authorized: bool
    reason: str
    raw_result: Any = None
    policy_hash: str = ""
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ActionReceipt:
    """Tamper-evident receipt for an action attempt."""
    exchange_id: str
    action: str
    authorized: bool
    policy_hash: str
    receipt_hash: str
    timestamp: str
    context_hash: Optional[str] = None
    result_summary: Optional[str] = None


# =============================================================================
# Core Cedar Policy Engine
# =============================================================================

class CedarPolicy:
    """Cedar policy gate using native cedar bindings.

    Example:
        policy = CedarPolicy()
        decision = policy.evaluate(
            principal='Helix::Agent::"agent-123"',
            action='Helix::Action::"bash"',
            resource='Helix::Environment::"workspace"',
            context={"drift_score": 0.08, "marker_count": 2, "has_valid_receipt": True},
        )
    """

    def __init__(
        self,
        policy_file: Optional[Path | str] = None,
        schema_file: Optional[Path | str] = None,
        strict: bool = False,
    ):
        self.policy_path = Path(policy_file) if policy_file else DEFAULT_POLICY
        self.schema_path = Path(schema_file) if schema_file else DEFAULT_SCHEMA

        self.policy_text = self._load_text(self.policy_path)
        self.schema_text = self._load_text(self.schema_path)
        self.policy_hash = self._hash_text(self.policy_text) if self.policy_text else "no_policy"

        self._policy_set = None
        self._evaluator = None
        self._validation_error: Optional[str] = None
        self._cedar_available = False
        self.strict = strict

        self._try_load_cedar()

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _load_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _try_load_cedar(self) -> None:
        try:
            import cedar
        except ImportError:
            self._validation_error = (
                "cedar not installed — running in fail-closed mode. "
                "Install with: pip install 'helix-adapter[cedar]'"
            )
            if self.strict:
                raise ImportError(self._validation_error)
            return

        self._cedar_available = True

        if not self.policy_text.strip():
            self._validation_error = "Policy file is empty — running in fail-closed mode"
            if self.strict:
                raise ValueError(self._validation_error)
            return

        # Clean policy loading using Cedar's native loader
        try:
            from cedar import PolicySet
            self._policy_set = PolicySet.from_str(self.policy_text)
        except Exception as e:
            self._validation_error = f"Failed to parse policy file: {e}"
            if self.strict:
                raise
            return

        # Optional schema validation
        if self.schema_text:
            try:
                from cedar import Schema
                schema = Schema.from_str(self.schema_text)
                self._policy_set.validate(schema)
            except Exception as e:
                self._validation_error = f"Schema validation failed: {e}"
                if self.strict:
                    raise
                self._policy_set = None
                return

        # Create evaluator
        try:
            from cedar import Evaluator
            self._evaluator = Evaluator(self._policy_set)
        except Exception as e:
            self._validation_error = f"Failed to create evaluator: {e}"
            if self.strict:
                raise
            self._evaluator = None

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    @property
    def is_available(self) -> bool:
        return self._cedar_available and self._evaluator is not None

    @property
    def validation_error(self) -> Optional[str]:
        return self._validation_error

    @property
    def is_fail_closed(self) -> bool:
        return not self.is_available

    def evaluate(
        self,
        principal: str,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> CedarDecision:
        if not self.is_available:
            return CedarDecision(
                authorized=False,
                reason=self._validation_error or "cedar unavailable — default deny",
                policy_hash=self.policy_hash,
            )

        try:
            from cedar import Authorizer, Context, Entity, Request

            principal_uid = self._parse_uid(principal)
            action_uid = self._parse_uid(action)
            resource_uid = self._parse_uid(resource)

            auth = Authorizer()
            req = Request(
                principal=principal_uid,
                action=action_uid,
                resource=resource_uid,
                context=Context.from_json(json.dumps(context or {})),
            )

            result = auth.is_authorized(req, self._policy_set)
            authorized = result.allowed
            reason_str = "; ".join(str(r) for r in result.reason) if result.reason else str(result)

            return CedarDecision(
                authorized=authorized,
                reason=reason_str,
                raw_result=result,
                policy_hash=self.policy_hash,
            )

        except Exception as e:
            return CedarDecision(
                authorized=False,
                reason=f"Evaluation error: {e}",
                policy_hash=self.policy_hash,
            )

    def seal_action(
        self,
        exchange_id: str,
        action: str,
        decision: CedarDecision,
        result: Any = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ActionReceipt:
        context_hash = None
        if context:
            context_json = json.dumps(context, sort_keys=True, default=str)
            context_hash = hashlib.sha256(context_json.encode()).hexdigest()[:16]

        payload = {
            "exchange_id": exchange_id,
            "action": action,
            "authorized": decision.authorized,
            "policy_hash": decision.policy_hash,
            "result": str(result)[:500] if result else None,
            "context_hash": context_hash,
            "timestamp": decision.evaluated_at,
        }

        receipt_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()

        return ActionReceipt(
            exchange_id=exchange_id,
            action=action,
            authorized=decision.authorized,
            policy_hash=decision.policy_hash,
            receipt_hash=f"sha256:{receipt_hash}",
            timestamp=decision.evaluated_at,
            context_hash=context_hash,
            result_summary=str(result)[:300] if result else None,
        )

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _parse_uid(self, s: str):
        from cedar import EntityUid
        # Simple parser for 'Type::"id"' format
        if '::"' not in s:
            raise ValueError(f"Invalid Cedar UID format: {s}")
        type_part, id_part = s.split('::"', 1)
        id_part = id_part.rstrip('"')
        return EntityUid.from_json(json.dumps({"type": type_part, "id": id_part}))
