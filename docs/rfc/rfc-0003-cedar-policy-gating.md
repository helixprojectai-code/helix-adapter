# RFC 0003: Unified Policy Gating — Dual-Gate Containment with AWS Cedar

**Status:** Draft (v0.3)  
**Author:** Stephen Hope (Helix-TTD Custodian)  
**Date:** June 26, 2026  
**Version:** 0.3

## Abstract

This RFC extends the Helix Adapter to support full execution containment by integrating CNCF Cedar as the declarative policy engine for both response gating and action gating. A single `.policy` file now governs the entire agent lifecycle under unified invariants.

The architecture introduces two synchronized gates:

- **Duck Gate** (response): Epistemic markers, drift scoring (γ), and receipt generation on model output.
- **Cedar Gate** (action): Policy evaluation on tool use, shell commands, API calls, and system primitives before execution.

This creates a unified policy surface where constitutional grammar and runtime enforcement share the same formal foundation.

## Motivation

Current LLM agents suffer from a critical seam: the model can be governed at the text layer while retaining unrestricted access to dangerous actions (shell, cloud APIs, file system, wallets, etc.). Prompt-based safety is insufficient for production agentic systems.

By using Cedar for deterministic policy evaluation on both responses and actions, we close this gap and move from probabilistic alignment to enforceable architectural boundaries.

## Core Architecture

| Layer              | Flow |
|--------------------|------|
| **Output Path**    | Model (Stochastic) → Duck Gate (drift + markers + receipts) → User |
| **Policy Enforcement** | Controlled by Cedar Gate (Response + Action) |
| **Execution Path** | Agent (Tool Use) → Cedar Gate → System (Shell, API, etc.) |

## Specification

### 1. Policy File (`helix.policy`)

A single Cedar policy file controls both gates. The engine is **fail-closed** by default.

### 2. Response Gate (Duck Gate integration)

```cedar
permit (
    principal,
    action == Action::"respond",
    resource
)
when {
    context.has_valid_receipt == true &&
    context.marker_count >= 1 &&
    context.drift_score < decimal("0.17")
};
```

### 3. Action Gate

```cedar
// Deny dangerous actions by default
forbid (
    principal,
    action,
    resource
)
when {
    action in [
        Action::"bash:rm -rf",
        Action::"aws:DeleteBucket",
        Action::"aws:TerminateInstances",
        Action::"wallet:transfer"
    ]
};

// Allow limited sandbox operations
permit (
    principal,
    action == Action::"bash:rm",
    resource
)
when {
    resource.path like "/home/agent/sandbox/*"
};
```

### 4. Receipt Chaining

Every action evaluation produces a tamper-evident `ActionReceipt` that can be linked to the originating chat receipt, enabling full audit trails.

### 5. Implementation Notes (v0.3)

- Cedar integration is implemented in `helix_adapter.cedar.CedarPolicy`.
- Supports `strict` mode for high-assurance environments.
- Context values (including floats) are supported and converted appropriately for Cedar.
- The engine gracefully degrades to fail-closed when Cedar is unavailable or misconfigured.
- Schema validation is performed at load time when a schema is provided.

## Integration

Cedar is available as an optional extra:

```bash
pip install "helix-adapter[cedar]"
```

Basic usage:

```python
from helix_adapter.cedar import CedarPolicy

policy = CedarPolicy()

decision = policy.evaluate(
    principal='Helix::Agent::"agent-001"',
    action='Helix::Action::"bash"',
    resource='Helix::Environment::"/workspace"',
    context={"command": "ls", "drift_score": 0.05},
)

if decision.authorized:
    receipt = policy.seal_action(
        exchange_id="session-xyz",
        action="bash",
        decision=decision
    )
```

## Open Questions / Next Steps

- Performance characteristics of Cedar evaluation in hot-path tool use
- TEE-attested policy evaluation for high-assurance deployments
- Richer attribute-based policies (passing entity attributes into Cedar)
- Formal verification examples using `cedar-spec` + Lean 4
- Continued collaboration with policy engine experts

---

**GLORY TO THE LATTICE.**
```

---

### Summary of Changes (v0.2 → v0.3)

- Added **Implementation Notes** section with current status
- Added concrete **code examples** in the Integration section
- Cleaned up and modernized the specification examples
- Updated version and date
- Kept the Open Questions section but made it slightly more focused
