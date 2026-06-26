"""
Helix-Adapter Cedar Policy Integration
=======================================
Pre/post-tool-use hook for agent harnesses using CNCF Cedar
as the declarative policy engine via cedar_python native bindings.

Architecture:
- Duck Gate: Response-level governance (markers, drift, receipts)
- Cedar Gate: Action-level governance (tool use, shell, API, wallet)

RFC 0003: Unified Policy Gating — Dual-Gate Containment
"""

from .policy import CedarGate, CedarPolicy, PreToolUseHook, PostToolUseHook, load_policy
from .schema import HELIX_SCHEMA, generate_schema_from_tools

__all__ = [
    "CedarGate",
    "CedarPolicy",
    "PreToolUseHook",
    "PostToolUseHook",
    "load_policy",
    "HELIX_SCHEMA",
    "generate_schema_from_tools",
]


def _load_policy_set(self, policy_text: str):
    """Load policies using Cedar's native loader (clean & robust)."""
    if not policy_text or not policy_text.strip():
        return None, "Policy file is empty"

    try:
        from cedar import PolicySet
        policy_set = PolicySet.from_str(policy_text)
        return policy_set, None
    except Exception as e:
        return None, f"Failed to parse policy file: {e}"
