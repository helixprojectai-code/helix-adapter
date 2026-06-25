"""
Helix-Adapter Cedar Policy Integration
=======================================
Pre/post-tool-use hook for agent harnesses using CNCF Cedar
as the declarative policy engine.

Architecture:
- Duck Gate: Response-level governance (markers, drift, receipts)
- Cedar Gate: Action-level governance (tool use, shell, API, wallet)

RFC 0003: Unified Policy Gating — Dual-Gate Containment
"""

from .policy import CedarGate, load_policy
from .schema import HELIX_SCHEMA, generate_schema_from_tools

__all__ = [
    "CedarGate",
    "load_policy",
    "HELIX_SCHEMA",
    "generate_schema_from_tools",
]
