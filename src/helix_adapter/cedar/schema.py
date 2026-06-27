"""Helix Cedar Schema Generation & Definitions (RFC 0003)

Provides:
- HELIX_SCHEMA: base schema for the dual-gate system
- generate_schema_from_tools(): helper for dynamic tool schemas
- SchemaBuilder: fluent builder for custom schemas

Cedar schema rules enforced here:
  - Action names are quoted strings: action "name"
  - Context block is INSIDE appliesTo: action "x" appliesTo { ..., context: { ... } }
  - Types: String, Long, Bool, decimal (lowercase — NOT Decimal or Boolean)
  - Entity hierarchy: entity X in [Y] (Y must be a defined entity type)
  - Optional context fields: field?: Type
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
// Dual-Gate Architecture: Duck Gate (respond) + Cedar Gate (actions)
// =============================================================================

namespace Helix {

    // Entity types — bare declarations; attrs added when evaluate() passes data.
    entity Agent;
    entity User;
    entity Environment;
    entity Tool;

    action "bash" appliesTo {
        principal: [Agent],
        resource: [Environment],
        context: {
            command?: String,
            path?: String
        }
    };

    action "write_file" appliesTo {
        principal: [Agent],
        resource: [Environment, Tool],
        context: {
            path?: String,
            content_length?: Long
        }
    };

    action "read_file" appliesTo {
        principal: [Agent],
        resource: [Environment, Tool],
        context: {
            path?: String
        }
    };

    action "edit_file" appliesTo {
        principal: [Agent],
        resource: [Environment, Tool],
        context: {
            path?: String
        }
    };

    action "apply_patch" appliesTo {
        principal: [Agent],
        resource: [Environment, Tool],
        context: {
            path?: String
        }
    };

    action "api_call" appliesTo {
        principal: [Agent],
        resource: [Tool],
        context: {
            endpoint?: String,
            method?: String
        }
    };

    action "wallet_transfer" appliesTo {
        principal: [Agent],
        resource: [Tool]
    };
}

// =============================================================================
// Governance Layer — Duck Gate outputs feed into Cedar context
// =============================================================================
namespace Helix_Governance {

    action "respond" appliesTo {
        principal: [Helix::Agent],
        resource: [Helix::Environment],
        context: {
            drift_score: decimal,
            marker_count: Long,
            has_valid_receipt: Bool,
            epistemic_label?: String
        }
    };
}
"""

# Public alias
HELIX_SCHEMA = HELIX_BASE_SCHEMA


# =============================================================================
# Schema Generation Helpers
# =============================================================================

def generate_schema_from_tools(
    tool_definitions: List[Dict[str, Any]],
    include_governance: bool = True,
    namespace: str = "Helix",
    principal_entity: str = "Agent",
    resource_entity: str = "Tool",
) -> str:
    """Generate a Cedar schema string from a list of tool definitions.

    Each tool_def supports:
        - name: str            (required)
        - parameters: List[str] (typed as optional String in context)
        - resource_type: str   (default: resource_entity arg)
        - principal_type: str  (default: principal_entity arg)

    Returns a complete schema string with correct appliesTo + context nesting.
    """
    entities = {principal_entity, resource_entity}
    if include_governance:
        # governance section references Helix::Agent and Helix::Environment
        entities.update({"Agent", "Environment"})
    actions = []

    for tool in tool_definitions:
        name = tool["name"]
        params = tool.get("parameters", [])
        res_type = tool.get("resource_type", resource_entity)
        prin_type = tool.get("principal_type", principal_entity)
        entities.add(res_type)
        entities.add(prin_type)

        if params:
            ctx_lines = "\n            ".join(f"{p}?: String," for p in params)
            context_block = f",\n        context: {{\n            {ctx_lines}\n        }}"
        else:
            context_block = ""

        action_block = (
            f'    action "{name}" appliesTo {{\n'
            f"        principal: [{prin_type}],\n"
            f"        resource: [{res_type}]{context_block}\n"
            f"    }};"
        )
        actions.append(action_block)

    entity_lines = "\n    ".join(f"entity {e};" for e in sorted(entities))
    schema = (
        f"namespace {namespace} {{\n\n"
        f"    {entity_lines}\n\n"
        + "\n\n".join(actions)
        + "\n}"
    )

    if include_governance:
        schema += "\n\n" + _governance_section()

    return schema


def _governance_section() -> str:
    return """\
namespace Helix_Governance {

    action "respond" appliesTo {
        principal: [Helix::Agent],
        resource: [Helix::Environment],
        context: {
            drift_score: decimal,
            marker_count: Long,
            has_valid_receipt: Bool,
            epistemic_label?: String
        }
    };
}"""


# =============================================================================
# Advanced Schema Builder
# =============================================================================

@dataclass
class SchemaBuilder:
    """Fluent builder for constructing Cedar schemas programmatically.

    Produces correct Cedar Schema Language with context inside appliesTo.
    """

    namespaces: Dict[str, List[str]] = field(default_factory=dict)

    def add_namespace(self, name: str) -> "SchemaBuilder":
        if name not in self.namespaces:
            self.namespaces[name] = []
        return self

    def add_entity(
        self,
        name: str,
        namespace: str = "Helix",
    ) -> "SchemaBuilder":
        self.namespaces.setdefault(namespace, []).append(f"    entity {name};")
        return self

    def add_action(
        self,
        name: str,
        principal: str,
        resource: str,
        context: Optional[Dict[str, str]] = None,
        namespace: str = "Helix",
    ) -> "SchemaBuilder":
        if context:
            ctx_lines = "\n            ".join(f"{k}: {v}," for k, v in context.items())
            context_block = f",\n        context: {{\n            {ctx_lines}\n        }}"
        else:
            context_block = ""

        action_def = (
            f'    action "{name}" appliesTo {{\n'
            f"        principal: [{principal}],\n"
            f"        resource: [{resource}]{context_block}\n"
            f"    }};"
        )
        self.namespaces.setdefault(namespace, []).append(action_def)
        return self

    def build(self) -> str:
        parts = []
        for ns, definitions in self.namespaces.items():
            ns_block = f"namespace {ns} {{\n\n" + "\n\n".join(definitions) + "\n\n}"
            parts.append(ns_block)
        return "\n\n".join(parts)


def get_default_helix_schema() -> str:
    """Returns the complete recommended base schema for Helix dual-gate systems."""
    return HELIX_BASE_SCHEMA
