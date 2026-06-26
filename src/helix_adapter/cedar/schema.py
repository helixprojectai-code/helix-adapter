"""Helix Cedar Schema Generation & Definitions (RFC 0003)

Provides:
- Base HELIX_SCHEMA with proper namespaces and entity/action structure
- Robust generate_schema_from_tools() helper
- SchemaBuilder class for advanced / dynamic schema construction
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# =============================================================================
# Base Helix Schema (RFC 0003 Dual-Gate Foundation)
# =============================================================================

HELIX_BASE_SCHEMA = """\
// =============================================================================
// Helix Agent Authorization Schema — RFC 0003
// Dual-Gate Architecture: Duck Gate (response) + Cedar Gate (action)
// =============================================================================

namespace Helix {

    // -------------------------------------------------------------------------
    // Entity Types
    // -------------------------------------------------------------------------
    entity User in [Principal] = {
        roles: Set<String>,
        sandbox_path: String,
    };

    entity Agent in [Principal] = {
        user: User,
        session_id: String,
        receipt_id: String,
    };

    entity Tool in [Resource] = {
        owner: User,
        workspace: String,
    };

    entity Environment in [Resource] = {
        path: String,
        owner: User,
    };

    // -------------------------------------------------------------------------
    // Core Tool Actions
    // -------------------------------------------------------------------------
    action bash {
        appliesTo {
            principal: [Agent],
            resource: [Environment],
        };
        context: {
            command: String,
            arguments: Set<String>,
            working_directory: String,
        };
    };

    action write_file {
        appliesTo {
            principal: [Agent],
            resource: [Environment],
        };
        context: {
            file_path: String,
            content_length: Long,
        };
    };

    action edit_file {
        appliesTo {
            principal: [Agent],
            resource: [Environment],
        };
        context: {
            file_path: String,
        };
    };

    action apply_patch {
        appliesTo {
            principal: [Agent],
            resource: [Tool],
        };
        context: {
            file_path: String,
            patch_content: String,
        };
    };

    action api_call {
        appliesTo {
            principal: [Agent],
            resource: [Tool],
        };
        context: {
            endpoint: String,
            method: String,
            parameters: Set<String>,
        };
    };

    action wallet_transfer {
        appliesTo {
            principal: [Agent],
            resource: [Tool],
        };
        context: {
            amount_usd: Decimal,
            destination: String,
        };
    };
}

// =============================================================================
// Governance Layer (Duck Gate outputs feed into Cedar context)
// =============================================================================
namespace Helix_Governance {

    action respond {
        appliesTo {
            principal: [Helix::Agent],
            resource: [Helix::Environment],
        };
        context: {
            drift_score: Decimal,
            marker_count: Long,
            has_valid_receipt: Boolean,
            epistemic_label: String,
        };
    };
}
"""

# Legacy alias
HELIX_SCHEMA = HELIX_BASE_SCHEMA


# =============================================================================
# Schema Generation Helpers
# =============================================================================

def generate_schema_from_tools(
    tool_definitions: List[Dict[str, Any]],
    include_governance: bool = True,
) -> str:
    """Generate Cedar schema actions from a list of tool definitions.

    Each tool_def:
        - name: str
        - parameters: List[str]  (typed as String)
        - resource_type: str     (default: "Tool")
        - principal_type: str    (default: "Agent")

    Returns a complete schema string.
    """
    actions = []
    for tool in tool_definitions:
        name = tool["name"]
        params = tool.get("parameters", [])
        resource_type = tool.get("resource_type", "Tool")
        principal_type = tool.get("principal_type", "Agent")
        context_lines = "\n        ".join(f"{p}: String," for p in params)

        action_block = f"""    action {name} {{
        appliesTo {{
            principal: [{principal_type}],
            resource: [{resource_type}],
        }};
        context: {{
            {context_lines}
        }};
    }};"""
        actions.append(action_block)

    schema = "\n\n".join(actions)
    if include_governance:
        schema += "\n\n" + _governance_section()
    return schema


def _governance_section() -> str:
    return """namespace Helix_Governance {

    action respond {
        appliesTo {
            principal: [Helix::Agent],
            resource: [Helix::Environment],
        };
        context: {
            drift_score: Decimal,
            marker_count: Long,
            has_valid_receipt: Boolean,
            epistemic_label: String,
        };
    };
}"""


# =============================================================================
# Advanced Schema Builder (for complex / dynamic use cases)
# =============================================================================

@dataclass
class SchemaBuilder:
    """Fluent builder for constructing Cedar schemas programmatically."""

    namespaces: Dict[str, List[str]] = field(default_factory=dict)

    def add_namespace(self, name: str) -> "SchemaBuilder":
        if name not in self.namespaces:
            self.namespaces[name] = []
        return self

    def add_entity(
        self,
        name: str,
        attributes: Optional[Dict[str, str]] = None,
        parents: Optional[List[str]] = None,
        namespace: str = "Helix",
    ) -> "SchemaBuilder":
        attr_str = ""
        if attributes:
            attr_lines = "\n        ".join(f"{k}: {v}," for k, v in attributes.items())
            attr_str = f" {{\n        {attr_lines}\n    }}"

        parent_str = ""
        if parents:
            parent_str = f" in [{', '.join(parents)}]"

        entity_def = f"    entity {name}{parent_str} = {attr_str};"
        self.namespaces.setdefault(namespace, []).append(entity_def)
        return self

    def add_action(
        self,
        name: str,
        principal: str,
        resource: str,
        context: Optional[Dict[str, str]] = None,
        namespace: str = "Helix",
    ) -> "SchemaBuilder":
        context_block = ""
        if context:
            ctx_lines = "\n        ".join(f"{k}: {v}," for k, v in context.items())
            context_block = f"""\n        context: {{
        {ctx_lines}
    }};"""

        action_def = f"""    action {name} {{
        appliesTo {{
            principal: [{principal}],
            resource: [{resource}],
        }};{context_block}
    }};"""
        self.namespaces.setdefault(namespace, []).append(action_def)
        return self

    def build(self) -> str:
        parts = []
        for ns, definitions in self.namespaces.items():
            ns_block = f"namespace {ns} {{\n\n" + "\n\n".join(definitions) + "\n}"
            parts.append(ns_block)
        return "\n\n".join(parts)


def get_default_helix_schema() -> str:
    """Returns the complete recommended base schema for Helix dual-gate systems."""
    return HELIX_BASE_SCHEMA
