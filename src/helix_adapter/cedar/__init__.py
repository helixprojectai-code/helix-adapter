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

from .policy import CedarDecision, CedarGate, CedarPolicy, ActionReceipt, load_policy
from .hooks import PreToolUseHook, PostToolUseHook
from .schema import HELIX_SCHEMA, generate_schema_from_tools

__all__ = [
    "CedarDecision",
    "CedarGate",
    "CedarPolicy",
    "ActionReceipt",
    "PreToolUseHook",
    "PostToolUseHook",
    "load_policy",
    "HELIX_SCHEMA",
    "generate_schema_from_tools",
]
