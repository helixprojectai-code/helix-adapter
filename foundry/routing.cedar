// Helix Foundry Routing Policy — Cedar as Decision Mesh
// Instead of: "which model?" → static dict
// Instead: Cedar evaluates context against all policies → routes to best ModelPool

// ── Policy 1: High-Stakes Logic → DeepSeek 4 Pro ──
permit(
    principal in Helix::Agent,
    action == Helix::Action::"infer",
    resource == ModelPool::"high_capability"
)
when {
    context has task_complexity &&
    context.task_complexity >= 8 &&
    context has drift_tolerance &&
    context.drift_tolerance < 0.05
};

// ── Policy 2: Adversarial / Execution → Grok 4.3 ──
permit(
    principal in Helix::Agent,
    action == Helix::Action::"infer",
    resource == ModelPool::"adversarial"
)
when {
    context has action_type &&
    context.action_type in ["bash", "execute", "api_call", "shell"]
};

// ── Policy 3: Cost-Sensitive / Batch → GPT-5.4 Nano ──
permit(
    principal in Helix::Agent,
    action == Helix::Action::"infer",
    resource == ModelPool::"cost_optimized"
)
when {
    context has priority &&
    context.priority == "batch" &&
    context has drift_tolerance &&
    context.drift_tolerance >= 0.10
};

// ── Policy 4: Multilingual / European → Mistral Large 3 ──
permit(
    principal in Helix::Agent,
    action == Helix::Action::"infer",
    resource == ModelPool::"sovereign"
)
when {
    context has locale &&
    context.locale in ["fr", "de", "es", "it", "nl", "pt"]
};

// ── Policy 5: Low-Drift Structured Output → GPT-5.4 Nano ──
permit(
    principal in Helix::Agent,
    action == Helix::Action::"infer",
    resource == ModelPool::"cost_optimized"
)
when {
    context has action_type &&
    context.action_type in ["write_file", "edit_file", "apply_patch", "summarize"]
};

// ── Default Fallback → DeepSeek 4 Pro ──
permit(
    principal in Helix::Agent,
    action == Helix::Action::"infer",
    resource == ModelPool::"high_capability"
)
when { true };
