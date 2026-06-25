"""Cedar schema generation for Helix agent tool definitions.

Cedar best practices (docs.cedarpolicy.com/bestpractices):
- Head constraints should carry action type and principal/resource structure
- Schema drives everything — define entity types before writing policies
- Use structured action arguments, not string matching in when clauses
"""

# Helix Cedar Schema — defines entity types and action structure
# for the dual-gate architecture per RFC 0003.

HELIX_SCHEMA = """\
// Helix Agent Authorization Schema
// Auto-generated foundation — extend for enterprise deployments

namespace Helix {
    // Entity types

    entity User in [Principal] = {
        "roles": Set<String>,
        "sandbox_path": String,
    };

    entity Agent in [Principal] = {
        "user": User,
        "session_id": String,
        "receipt_id": String,
    };

    entity Tool in [Resource] = {
        "owner": User,
        "workspace": String,
    };

    entity Environment in [Resource] = {
        "path": String,
        "owner": User,
    };

    // Actions

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

namespace Helix_Governance {
    // Governance actions

    action respond {
        appliesTo {
            principal: [Helix::Agent],
            resource: [Helix::Environment],
        };
        context: {
            drift_score: Decimal,
            marker_count: Long,
            has_valid_receipt: Boolean,
        };
    };
}
"""


def generate_schema_from_tools(tool_definitions: list) -> str:
    """Generate a Cedar schema from agent tool definitions.

    Each tool_def: {"name": "bash", "parameters": ["command"], "resource_type": "Environment"}
    Returns a Cedar schema snippet for those tools.
    """
    actions = []
    for tool in tool_definitions:
        name = tool["name"]
        params = tool.get("parameters", [])
        resource_type = tool.get("resource_type", "Tool")
        context_fields = "\n            ".join(
            f"{p}: String," for p in params
        )
        actions.append(
            f"    action {name} {{\n"
            f"        appliesTo {{\n"
            f"            principal: [Agent],\n"
            f"            resource: [{resource_type}],\n"
            f"        }};\n"
            f"        context: {{\n"
            f"            {context_fields}\n"
            f"        }};\n"
            f"    }};\n"
        )
    return "\n".join(actions)
