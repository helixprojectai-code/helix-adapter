// Helix Foundry Routing Policy — Cedar as Decision Mesh
// RFC 0003 extension: Cedar evaluates request context → routes to ModelPool.
// No fallback policy here — Python handles the default (see cedar_route()).

// ── Policy 1: High-Stakes Logic → DeepSeek 4 Pro ──
permit(
    principal is Helix::Agent,
    action == Helix::Action::"infer",
    resource == Helix::ModelPool::"high_capability"
)
when {
    context has task_complexity &&
    context.task_complexity >= 8 &&
    context has drift_tolerance &&
    context.drift_tolerance.lessThan(decimal("0.05"))
};

// ── Policy 2: Adversarial / Execution → Grok 4.3 ──
permit(
    principal is Helix::Agent,
    action == Helix::Action::"infer",
    resource == Helix::ModelPool::"adversarial"
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

// ── Policy 3: Cost-Sensitive / Batch → GPT-5.4 Nano ──
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

// ── Policy 4: Multilingual / European → Mistral Large 3 ──
permit(
    principal is Helix::Agent,
    action == Helix::Action::"infer",
    resource == Helix::ModelPool::"sovereign"
)
when {
    context has locale &&
    (
        context.locale == "fr" ||
        context.locale == "de" ||
        context.locale == "es" ||
        context.locale == "it" ||
        context.locale == "nl" ||
        context.locale == "pt"
    )
};

// High-complexity tasks always go to high_capability — cost_optimized is blocked
forbid(
    principal is Helix::Agent,
    action == Helix::Action::"infer",
    resource == Helix::ModelPool::"cost_optimized"
)
when {
    context has task_complexity &&
    context.task_complexity >= 8
};

// ── Policy 5: Structured Output / Low-Cost → GPT-5.4 Nano ──
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
