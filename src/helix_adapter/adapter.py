# Copyright 2026 Helix AI Innovations Inc.
# SPDX-License-Identifier: Apache-2.0

"""
HelixAdapter — constitutional wrapper with optional Cedar action gating.

Usage (Duck Gate only):
    adapter = HelixAdapter(model_fn=my_model_fn)
    result = adapter.chat("Is AI evil?")

Usage (with Cedar action gating):
    from helix_adapter.cedar import CedarPolicy

    cedar = CedarPolicy()
    adapter = HelixAdapter(model_fn=my_model_fn, cedar_policy=cedar)

    @adapter.register_tool("bash")
    def run_bash(command: str):
        ...
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from .drift import compute_drift
from .markers import extract_claims
from .prompt import CONSTITUTIONAL_PROMPT, system_messages
from .receipt import make_receipt

# Cedar integration (optional)
try:
    from .cedar import CedarPolicy
    from .cedar.hooks import PreToolUseHook, PostToolUseHook
except ImportError:
    CedarPolicy = None
    PreToolUseHook = None
    PostToolUseHook = None


@dataclass
class ChatResult:
    """Result of a single constitutional chat exchange."""

    response: str
    claims: list[dict]
    receipt: dict
    drift: float


class HelixSecurityViolation(Exception):
    """Raised when Cedar denies an action (fail-closed)."""

    def __init__(
        self,
        message: str,
        decision: Any = None,
        principal: str = "",
        action: str = "",
        resource: str = "",
        context: dict | None = None,
    ):
        super().__init__(message)
        self.decision = decision
        self.principal = principal
        self.action = action
        self.resource = resource
        self.context = context or {}


class HelixAdapter:
    """
    Constitutional wrapper for any AI model with optional Cedar action gating.

    The adapter always applies the Helix constitutional prompt and Duck Gate
    (markers + drift + receipts) on responses.

    When a `cedar_policy` is provided, tool/action calls are automatically
    gated through Cedar before execution.
    """

    def __init__(
        self,
        model_fn: Callable[[list[dict]], str],
        model_name: str = "unknown",
        drift_method: str = "char",
        cedar_policy: Optional["CedarPolicy"] = None,
    ):
        self.model_fn = model_fn
        self.model_name = model_name
        self.drift_method = drift_method
        self._history: list[dict] = []

        # Cedar integration (optional)
        self.cedar_policy = cedar_policy
        self._pre_tool_hook = None
        self._post_tool_hook = None
        self._tools: dict[str, Callable] = {}

        if self.cedar_policy and PreToolUseHook and PostToolUseHook:
            self._pre_tool_hook = PreToolUseHook(self.cedar_policy)
            self._post_tool_hook = PostToolUseHook(self.cedar_policy)

    @property
    def history(self) -> list[dict]:
        """Return all exchange receipts from this session."""
        return list(self._history)

    # ------------------------------------------------------------------ #
    # Chat (Duck Gate)
    # ------------------------------------------------------------------ #

    def chat(self, message: str, temperature: float = 0.7) -> ChatResult:
        """Send a message through the constitutional wrapper (Duck Gate)."""
        messages = system_messages()
        messages.append({"role": "user", "content": message})

        raw_response = self.model_fn(messages)

        claims = extract_claims(raw_response)
        drift = compute_drift(raw_response, claims, method=self.drift_method)

        receipt = make_receipt(
            user_message=message,
            assistant_response=raw_response,
            claims=claims,
            model=self.model_name,
            constitutional_prompt=CONSTITUTIONAL_PROMPT,
            drift_score=drift,
            drift_method=self.drift_method,
            temperature=temperature,
        )

        self._history.append(receipt)
        return ChatResult(
            response=raw_response,
            claims=claims,
            receipt=receipt,
            drift=drift,
        )

    def running_drift(self) -> float:
        if not self._history:
            return 0.0
        from .drift import compute_running_drift

        return compute_running_drift(self._history, method=self.drift_method)

    # ------------------------------------------------------------------ #
    # Tool Registration & Execution (Cedar Gate)
    # ------------------------------------------------------------------ #

    def register_tool(self, name: str):
        """
        Decorator to register a tool with automatic Cedar gating.

        When a CedarPolicy is configured, the tool is wrapped with
        PreToolUseHook and PostToolUseHook.
        """

        def decorator(func: Callable):
            if self.cedar_policy and self._pre_tool_hook and self._post_tool_hook:
                original_func = func

                def wrapped(*args, **kwargs):
                    tool_call = {
                        "tool_name": name,
                        "principal": 'Helix::Agent::"default"',
                        "action": f'Helix::Action::"{name}"',
                        "resource": 'Helix::Environment::"default"',
                        "context": kwargs,
                    }

                    # Pre-execution check
                    allowed, reason, decision = self._pre_tool_hook.run(tool_call)
                    if not allowed:
                        raise HelixSecurityViolation(
                            f"Tool '{name}' denied by Cedar policy: {reason}",
                            decision=decision,
                            principal=tool_call["principal"],
                            action=tool_call["action"],
                            resource=tool_call["resource"],
                            context=tool_call.get("context"),
                        )

                    # Execute tool
                    result = original_func(*args, **kwargs)

                    # Post-execution receipt
                    self._post_tool_hook.run(
                        exchange_id="session-default",
                        tool_name=name,
                        decision=decision,
                        result=result,
                        context=tool_call.get("context"),
                    )

                    return result

                self._tools[name] = wrapped
                return wrapped
            else:
                # No Cedar configured → register normally
                self._tools[name] = func
                return func

        return decorator

    def get_tool(self, name: str) -> Callable | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())
