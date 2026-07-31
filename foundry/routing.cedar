// Helix Foundry Routing Policy — Cedar as Decision Mesh
// RFC 0003 extension: Cedar evaluates request context → routes to ModelPool.
// Deployment: gemma4:latest (high-capability), magnus-supernova:latest (cost-optimized)
// Fallback: Python handles unmatched policies (see cedar_route()).

// ── Policy 1: High-Complexity / Reasoning → gemma4 (high_capability) ──
permit(
    principal is Helix::Agent,
    action == Helix::Action::"infer",
    resource == Helix::ModelPool::"high_capability"
)
when {
    context has task_complexity &&
    context.task_complexity >= 8
};

// ── Policy 2: Code Execution / Bash → gemma4 (high_capability) ──
// Execution contexts require strongest reasoning for safety.
permit(
    principal is Helix::Agent,
    action == Helix::Action::"infer",
    resource == Helix::ModelPool::"high_capability"
)
when {
    context has action_type &&
    (
        context.action_type == "bash" ||
        context.action_type == "execute" ||
        context.action_type == "api_call" ||
        context.action_type == "shell"
    )
};

// ── Policy 3: Batch / Low-Drift → magnus-supernova (cost_optimized) ──
// Batch workloads with relaxed drift tolerance use cost model.
permit(
    principal is Helix::Agent,
    action == Helix::Action::"infer",
    resource == Helix::ModelPool::"cost_optimized"
)
when {
    context has priority &&
    context.priority == "batch" &&
    context has drift_tolerance &&
    context.drift_tolerance.greaterThanOrEqual(decimal("0.10"))
};

// ── Policy 4: Structured Output → magnus-supernova (cost_optimized) ──
// Write/edit/patch operations are well-bounded; cost model sufficient.
permit(
    principal is Helix::Agent,
    action == Helix::Action::"infer",
    resource == Helix::ModelPool::"cost_optimized"
)
when {
    context has action_type &&
    (
        context.action_type == "write_file" ||
        context.action_type == "edit_file" ||
        context.action_type == "apply_patch" ||
        context.action_type == "summarize"
    )
};

// ── Safety: Block cost-optimized for high-complexity ──
// Prevents downrouting high-stakes work to cheaper model.
forbid(
    principal is Helix::Agent,
    action == Helix::Action::"infer",
    resource == Helix::ModelPool::"cost_optimized"
)
when {
    context has task_complexity &&
    context.task_complexity >= 8
};
