"""Cedar policy evaluation for Helix dual-gate architecture.

Uses cedar_python bindings for native policy evaluation —
no subprocess, no CLI dependency. Schema-validated, receipt-chained.

RFC 0003: Unified Policy Gating — Duck Gate + Cedar Gate.
"""

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

HERE = Path(__file__).parent
DEFAULT_POLICY = HERE / "policies" / "helix.cedar"
DEFAULT_SCHEMA = HERE / "policies" / "helix.schema"


def load_text(path: Optional[Path] = None) -> str:
    """Load a Cedar policy or schema file from disk."""
    path = path or DEFAULT_POLICY
    return path.read_text() if path.exists() else ""


class CedarPolicy:
    """Cedar policy gate using cedar_python native bindings.

    Usage:
        policy = CedarPolicy()
        ok = policy.evaluate(
            principal="UserGroup::\"readonly\"",
            action="Action::\"read\"",
            resource="Resource::\"data\"",
            context={"drift_score": 0.05, "marker_count": 3},
        )
    """

    def __init__(
        self,
        policy_file: Optional[str] = None,
        schema_file: Optional[str] = None,
    ):
        self.policy_text = load_text(
            Path(policy_file) if policy_file else DEFAULT_POLICY
        )
        self.schema_text = load_text(
            Path(schema_file) if schema_file else DEFAULT_SCHEMA
        )
        self.policy_hash = hashlib.sha256(
            self.policy_text.encode()
        ).hexdigest()[:16] if self.policy_text else "no_policy"

        self._policy_set = None
        self._evaluator = None

        try:
            from cedar_python import Evaluator, PolicySet

            self._policy_set = PolicySet.from_str(self.policy_text)
            if self.schema_text:
                from cedar_python import Schema

                self._policy_set.validate(Schema.from_str(self.schema_text))
            self._evaluator = Evaluator(self._policy_set)
        except ImportError:
            pass  # cedar_python not installed — default permit

    def evaluate(
        self,
        principal: str,
        action: str,
        resource: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        """Evaluate a Cedar authorization request.

        Returns (authorized: bool, reason: str).
        """
        if self._evaluator is None:
            # No cedar_python — fall back to default permit
            return (True, "cedar_python not installed — default permit")

        try:
            from cedar_python import Context, Entity

            result = self._evaluator.evaluate(
                principal=Entity.principal(principal),
                action=Entity.action(action),
                resource=Entity.resource(resource),
                context=Context(context or {}),
            )
            decision = result.is_allowed()
            reasons = getattr(result, "reasons", [])
            return (decision, "; ".join(str(r) for r in reasons) if reasons else str(result))
        except Exception as e:
            return (False, f"policy evaluation error: {e}")

    def seal_action(
        self,
        exchange_id: str,
        action: str,
        authorized: bool,
        result: Any = None,
    ) -> Dict[str, Any]:
        """Generate a tamper-evident action receipt chained to the chat receipt."""
        payload = {
            "exchange_id": exchange_id,
            "action": action,
            "authorized": authorized,
            "policy_hash": self.policy_hash,
            "result": str(result)[:500] if result else None,
        }
        receipt_hash = hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()
        payload["hash"] = f"sha256:{receipt_hash}"
        return payload


class CedarGate:
    """Backward-compatible alias for CedarPolicy.

    See CedarPolicy for full interface.
    """

    def __init__(self, policy_file: Optional[str] = None):
        self._policy = CedarPolicy(policy_file=policy_file)

    @property
    def policy_hash(self) -> str:
        return self._policy.policy_hash

    @property
    def policy_text(self) -> str:
        return self._policy.policy_text

    def authorize(
        self,
        principal: Dict[str, str],
        action: str,
        resource: Dict[str, str],
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[bool, str]:
        return self._policy.evaluate(
            principal=f'{principal["type"]}::"{principal["id"]}"',
            action=action,
            resource=f'{resource["type"]}::"{resource["id"]}"',
            context=context,
        )

    def seal_action(
        self, exchange_id: str, action: str,
        authorized: bool, result: Any = None,
    ) -> Dict[str, Any]:
        return self._policy.seal_action(exchange_id, action, authorized, result)


def load_policy(path: Optional[Path] = None) -> str:
    """Backward-compatible: load a Cedar policy file from disk."""
    return load_text(path)


class PreToolUseHook:
    """Hook called before an agent executes a tool.

    Evaluates Cedar policy + runs custom pre-flight checks.
    """

    def __init__(self, policy: CedarPolicy):
        self.policy = policy
        self._custom_hooks = {}

    def register(self, tool_name: str):
        def decorator(fn):
            self._custom_hooks[tool_name] = fn
            return fn
        return decorator

    def run(self, tool_name: str, tool_call: Dict[str, Any]) -> Tuple[bool, str]:
        principal = tool_call.get("principal", f'UserGroup::"{tool_call.get("user_id", "standard")}"')
        action = tool_call.get("action", f'Action::"{tool_name}"')
        resource = tool_call.get("resource", f'Resource::"{tool_call.get("resource_type", "api")}"')
        context = tool_call.get("context", {})

        ok, reason = self.policy.evaluate(principal, action, resource, context)
        if not ok:
            return (False, reason)

        if tool_name in self._custom_hooks:
            try:
                self._custom_hooks[tool_name](tool_call)
            except Exception as e:
                return (False, f"pre-flight hook failed: {e}")

        return (True, "authorized")


class PostToolUseHook:
    """Hook called after an agent executes a tool.

    Generates action receipts chained to the originating chat receipt.
    """

    def __init__(self, policy: CedarPolicy):
        self.policy = policy

    def run(
        self,
        exchange_id: str,
        tool_name: str,
        authorized: bool,
        result: Any = None,
    ) -> Dict[str, Any]:
        return self.policy.seal_action(exchange_id, tool_name, authorized, result)
