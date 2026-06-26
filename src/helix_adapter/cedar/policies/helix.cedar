// Helix Dual-Gate Policy — Duck Gate + Cedar Gate
// RFC 0003 reference implementation
//
// UserGroup = who can request
// AgentGroup = what the agent can execute
// Action = what operation is requested
// Resource = what the operation targets

// ── Response Gate (Duck Gate): pre-model authorization ──

// Model → User: what the model can respond to
permit(
    principal in UserGroup::"readonly",
    action in Action::"read",
    resource in Resource::"data"
);

permit(
    principal in UserGroup::"standard",
    action in Action::"read" | Action::"search" | Action::"analyze",
    resource in Resource::"data" | Resource::"reports"
);

// Block users from requesting the model to generate dangerous content
forbid(
    principal in UserGroup::"standard",
    action in Action::"generate_code",
    resource in Resource::"production"
)
when {
    context has drift_score && context.drift_score >= 0.17
};

// ── Action Gate (Cedar Gate): pre-execution authorization ──

// Agent → Tools: what the agent can execute
permit(
    principal in AgentGroup::"standard",
    action in Action::"get" | Action::"list" | Action::"search",
    resource in Resource::"api" | Resource::"data"
);

// Block destructive operations by default
forbid(
    principal in AgentGroup::"standard",
    action in Action::"delete" | Action::"update" | Action::"create",
    resource in Resource::"infrastructure"
);

// Allow file operations in sandboxed workspace
permit(
    principal in AgentGroup::"standard",
    action in Action::"write" | Action::"edit" | Action::"patch",
    resource in Resource::"filesystem"
)
when {
    resource has path &&
    resource.path like "/home/agent/sandbox/*"
};

// Block shell access outside sandbox
forbid(
    principal in AgentGroup::"standard",
    action == Action::"execute",
    resource in Resource::"shell"
)
when {
    context has command &&
    !(context.command like "*sandbox*")
};

// ── Admin escalation (separate group) ──

permit(
    principal in UserGroup::"admin",
    action,
    resource
);

permit(
    principal in AgentGroup::"admin",
    action,
    resource
);
