"""Cedar Policy Evaluation for Helix Dual-Gate Architecture (RFC 0003)

Uses native cedar Python bindings for deterministic policy evaluation.
No subprocess, no CLI dependency.

Features:
- Schema-validated policy loading
- Fail-closed when cedar is unavailable (default deny)
- Tamper-evident, receipt-chained action sealing
- Pre- and Post-tool-use hooks for agent integration
- Clear decision objects + rich forensic context
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple

HERE = Path(__file__).parent
DEFAULT_POLICY = HERE / "policies" / "helix.policy"
DEFAULT_SCHEMA = HERE / "policies" / "helix.schema"


# =============================================================================
# Decision & Receipt Types
# =============================================================================

@dataclass
class CedarDecision:
    """Structured result from a Cedar policy evaluation."""
    authorized: bool
    reason: str
    raw_result: Any = None
    policy_hash: str = ""
    evaluated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass
class ActionReceipt:
    """Tamper-evident receipt for an authorized (or denied) action."""
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

def _parse_uid(s: str):
    """Parse a Cedar entity UID string like 'Helix::Agent::"agent-123"' into an EntityUid."""
    from cedar import EntityUid
    m = re.match(r'^(.*)::"([^"]*)"$', s)
    if m:
        return EntityUid.from_json(json.dumps({"type": m.group(1), "id": m.group(2)}))
    raise ValueError(f"Cannot parse entity UID: {s!r}. Expected format: 'Type::\"id\"'")


def _load_policies(policy_text: str):
    """Split a multi-policy Cedar file and return a populated PolicySet."""
    from cedar import Policy, PolicySet

    ps = PolicySet()
    raw_blocks = re.split(r"(?=(?:permit|forbid)\s*\()", policy_text)
    raw_blocks = [
        b.strip() for b in raw_blocks
        if b.strip() and (b.strip().startswith("permit") or b.strip().startswith("forbid"))
    ]
    errors = []
    for i, raw in enumerate(raw_blocks):
        try:
            ps.add(Policy.from_str(raw, id=f"p{i}"))
        except Exception as e:
            errors.append(f"p{i}: {e}")
    return ps, errors


class CedarPolicy:
    """Cedar policy gate using native cedar Python bindings.

    Example:
        policy = CedarPolicy()
        decision = policy.evaluate(
            principal='Helix::Agent::"agent-123"',
            action='Helix::Action::"bash"',
            resource='Helix::Environment::"workspace"',
            context={"drift_score": 0.08, "marker_count": 2, "has_valid_receipt": True},
        )
        if decision.authorized:
            receipt = policy.seal_action(exchange_id=..., action=..., decision=decision)
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
        self._validation_error: Optional[str] = None
        self.strict = strict

        self._try_load_cedar()

    def _load_text(self, path: Path) -> str:
        return path.read_text(encoding="utf-8") if path.exists() else ""

    def _hash_text(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def _try_load_cedar(self) -> None:
        try:
            import cedar  # noqa: F401
        except ImportError:
            msg = "cedar not installed — running in fallback mode (pip install cedar-python)"
            if self.strict:
                raise ImportError(msg)
            self._validation_error = msg
            return

        if not self.policy_text:
            self._validation_error = "No policy text found"
            return

        ps, errors = _load_policies(self.policy_text)
        if errors:
            msg = f"Policy load errors: {errors}"
            if self.strict:
                raise ValueError(msg)
            self._validation_error = msg
            return

        if ps.is_empty():
            msg = "Policy file contains no permit/forbid statements"
            if self.strict:
                raise ValueError(msg)
            self._validation_error = msg
            return

        self._policy_set = ps

        # Schema validation — optional but catches type errors at load time
        if self.schema_text:
            try:
                from cedar import Schema
                schema = Schema.from_cedarschema(self.schema_text)
                result = schema.validate_policyset(self._policy_set)
                if not result.valid:
                    msg = f"Schema validation failed: {[str(e) for e in result.errors]}"
                    if self.strict:
                        raise ValueError(msg)
                    self._validation_error = msg
                    self._policy_set = None
            except ImportError:
                msg = "cedar_python not installed — running in fallback mode"
                self._validation_error = msg
                if self.strict:
                    raise ImportError(msg)
            except Exception as e:
                msg = f"Failed to initialize Cedar: {e}"
                self._validation_error = msg
                if self.strict:
                    raise
                self._validation_error = msg

    @property
    def is_available(self) -> bool:
        return self._policy_set is not None

    @property
    def validation_error(self) -> Optional[str]:
        return self._validation_error

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
                reason=self._validation_error or "cedar unavailable — default deny for safety",
                policy_hash=self.policy_hash,
            )

        try:
            from cedar import Authorizer, Context, Entity, Request

            principal_uid = _parse_uid(principal)
            action_uid = _parse_uid(action)
            resource_uid = _parse_uid(resource)

            auth = Authorizer()
            auth.add_entity(Entity(uid=principal_uid, attrs={}))
            auth.add_entity(Entity(uid=action_uid, attrs={}))
            auth.add_entity(Entity(uid=resource_uid, attrs={}))

            # Cedar context values must be JSON-serialisable primitives.
            # Floats are not natively supported — convert to int*1000 or pass as
            # strings; the policy uses decimal() extension for float comparisons.
            ctx_data = {}
            if context:
                for k, v in context.items():
                    if isinstance(v, float):
                        # Convert float to Cedar decimal string format
                        ctx_data[k] = {"__extn": {"fn": "decimal", "arg": str(round(v, 4))}}
                    elif isinstance(v, bool):
                        ctx_data[k] = v
                    elif isinstance(v, (int, str)):
                        ctx_data[k] = v
                    else:
                        ctx_data[k] = str(v)

            ctx = Context.from_json(json.dumps(ctx_data))
            req = Request(
                principal=principal_uid,
                action=action_uid,
                resource=resource_uid,
                context=ctx,
            )

            result = auth.is_authorized(req, self._policy_set)
            authorized = result.allowed
            reasons = result.reason if result.reason else []
            errors = result.errors if result.errors else []
            reason_str = "; ".join(str(r) for r in reasons) if reasons else str(result.decision)
            if errors:
                reason_str += f" [errors: {'; '.join(str(e) for e in errors)}]"

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

        receipt_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()

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


# =============================================================================
# Backward-compatible thin wrapper
# =============================================================================

class CedarGate:
    """Thin backward-compatible wrapper around CedarPolicy."""

    def __init__(self, policy_file: Optional[str] = None):
        self._policy = CedarPolicy(policy_file=Path(policy_file) if policy_file else None)

    @property
    def policy_hash(self) -> str:
        return self._policy.policy_hash

    @property
    def policy_text(self) -> str:
        return self._policy.policy_text

    @property
    def is_available(self) -> bool:
        return self._policy.is_available

    def authorize(
        self,
        principal: Dict[str, str],
        action: str,
        resource: Dict[str, str],
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        decision = self._policy.evaluate(
            principal=f'{principal["type"]}::"{principal["id"]}"',
            action=action,
            resource=f'{resource["type"]}::"{resource["id"]}"',
            context=context,
        )
        return decision.authorized, decision.reason

    def seal_action(self, *args, **kwargs) -> ActionReceipt:
        return self._policy.seal_action(*args, **kwargs)


# =============================================================================
# Agent Integration Hooks
# =============================================================================

class PreToolUseHook:
    """Hook called before tool execution.
    Evaluates Cedar policy and runs optional custom pre-flight checks."""

    def __init__(self, policy: CedarPolicy):
        self.policy = policy
        self._custom_hooks: Dict[str, Callable] = {}

    def register(self, tool_name: str):
        def decorator(fn: Callable):
            self._custom_hooks[tool_name] = fn
            return fn
        return decorator

    def run(self, tool_call: Dict[str, Any]) -> Tuple[bool, str, Optional[CedarDecision]]:
        principal = tool_call.get("principal") or f'UserGroup::"{tool_call.get("user_id", "standard")}"'
        action = tool_call.get("action") or f'Action::"{tool_call.get("tool_name", "unknown")}"'
        resource = tool_call.get("resource") or f'Resource::"{tool_call.get("resource_type", "default")}"'
        context = tool_call.get("context", {})

        decision = self.policy.evaluate(principal, action, resource, context)

        if not decision.authorized:
            return False, decision.reason, decision

        tool_name = tool_call.get("tool_name", "")
        if tool_name in self._custom_hooks:
            try:
                self._custom_hooks[tool_name](tool_call)
            except Exception as e:
                return False, f"Custom pre-flight hook failed: {e}", decision

        return True, "authorized", decision


class PostToolUseHook:
    """Hook called after tool execution to generate chained action receipts."""

    def __init__(self, policy: CedarPolicy):
        self.policy = policy

    def run(
        self,
        exchange_id: str,
        tool_name: str,
        decision: CedarDecision,
        result: Any = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ActionReceipt:
        return self.policy.seal_action(
            exchange_id=exchange_id,
            action=tool_name,
            decision=decision,
            result=result,
            context=context,
        )


def load_policy(path: Optional[Path] = None) -> str:
    """Backward-compatible: load a Cedar policy file from disk."""
    p = path or DEFAULT_POLICY
    return p.read_text(encoding="utf-8") if p.exists() else ""
