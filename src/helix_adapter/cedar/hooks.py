"""Pre- and post-tool-use hooks for Cedar gate integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

if TYPE_CHECKING:
    from .policy import CedarDecision, CedarPolicy


class PreToolUseHook:
    """Evaluates Cedar policy before a tool is executed."""

    def __init__(self, policy: "CedarPolicy"):
        self._policy = policy

    def run(
        self, tool_call: Dict[str, Any]
    ) -> Tuple[bool, str, Optional["CedarDecision"]]:
        principal = tool_call.get("principal", 'Helix::Agent::"default"')
        action = tool_call.get("action", 'Helix::Action::"unknown"')
        resource = tool_call.get("resource", 'Helix::Environment::"default"')
        context = tool_call.get("context") or {}

        decision = self._policy.evaluate(
            principal=principal,
            action=action,
            resource=resource,
            context=context,
        )
        return decision.authorized, decision.reason, decision


class PostToolUseHook:
    """Seals a tamper-evident action receipt after a tool has executed."""

    def __init__(self, policy: "CedarPolicy"):
        self._policy = policy

    def run(
        self,
        exchange_id: str,
        tool_name: str,
        decision: "CedarDecision",
        result: Any = None,
        context: Optional[Dict[str, Any]] = None,
    ):
        return self._policy.seal_action(
            exchange_id=exchange_id,
            action=tool_name,
            decision=decision,
            result=result,
            context=context,
        )
