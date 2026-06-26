# RFC 0003: Unified Policy Gating — Dual-Gate Containment with AWS Cedar

**Status:** Lattice Approved (4/4 nodes reviewed)
**Author:** Stephen Hope (Helix-TTD Custodian)
**Date:** June 25, 2026
**Version:** 0.2 — Post-approval, pre-merge

## Abstract

This RFC extends the Helix-Adapter from output verification (v1.2) to full execution containment by integrating AWS Cedar as the declarative policy engine for both response gating and action gating. A single `.policy` file now governs the entire agent lifecycle under unified invariants.

The architecture introduces two synchronized gates:
- **Duck Gate** (response): Epistemic markers, drift scoring (γ), and receipt generation on model output.
- **Cedar Gate** (action): Policy evaluation on tool use, shell commands, API calls, and system primitives before execution.

This creates a unified policy surface where constitutional grammar and runtime enforcement share the same formal foundation.

## Motivation

Current LLM agents suffer from a critical seam: the model can be governed at the text layer while retaining unrestricted access to dangerous actions (shell, cloud APIs, wallets, etc.). Prompt-based safety is insufficient.

During architectural discussion, Victor Moreno (AWS Cedar Core) highlighted the power of using Cedar to gate dangerous actions (e.g. `rm -rf`, `aws delete*`, shell invocation) in addition to response-level controls. This use case crystallized the path to complete containment: treat response policy and action policy as expressions of the same underlying ruleset.

The result is deterministic enforcement across both text and execution.

## Core Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    MODEL    │────→│    DUCK     │────→│    USER     │
│ (Stochastic)│     │(drift +     │     │  (receipt)  │
│             │     │ markers)    │     │             │
└─────────────┘     └─────────────┘     └─────────────┘
                           │
                           ▼
                    ┌─────────────┐
                    │    CEDAR    │ ← Unified .policy file
                    │ (Response   │
                    │  + Action)  │
                    └─────────────┘
                           │
                           ▼
┌─────────────┐     ┌─────────────┐
│    AGENT    │────→│   SYSTEM    │
│ (Tool Use)  │     │ (Shell, API,│
│             │     │  Wallet...) │
└─────────────┘     └─────────────┘
```

## Specification

### 1. Policy File (`helix.policy`)

- Ships as default with the adapter.
- Enterprise deployments extend or override it.
- Cedar syntax for both response and action rules.

### 2. Response Gate (extends v1.2)

```cedar
permit(principal, action == Action::"respond", resource)
when {
    context.drift_score < 0.17 &&
    context.marker_count >= 1 &&
    context.has_valid_receipt
};
```

### 3. Action Gate (new)

```cedar
// Forbid dangerous primitives by default
forbid(principal, action, resource)
when {
    action in [
        Action::"shell:rm -rf",
        Action::"aws:DeleteBucket",
        Action::"aws:TerminateInstances",
        Action::"wallet:transfer"
    ]
};

// Sandbox exceptions (strict)
permit(principal, action == Action::"shell:rm", resource)
when {
    resource.path like "/home/agent/sandbox/*"
};
```

### 4. Receipt Chaining

Every action attempt produces a linked cryptographic receipt referencing the originating chat receipt. Full audit trail: prompt → response → action → outcome.

### 5. Lean 4 Convergence

Because Cedar's operational semantics are formally specified in Lean 4, policies can be verified for BIBO stability and other invariants. This moves governance from heuristic to mathematically provable boundaries.

## Integration with Helix-Adapter v1.2+

- Optional Cedar dependency (default off, enabled via config).
- `HelixAdapter(..., policy_file="helix.policy")`
- Unified `result.receipt` now includes both text and action entries.
- Drift scoring and markers remain out-of-band and model-agnostic.

## Open Questions / Next Steps

- Precise mapping of Helix constitutional markers into Cedar context attributes.
- Performance characteristics of Cedar evaluation in hot-path tool use.
- TEE-attested policy evaluation for high-assurance deployments.
- Formal verification examples using cedar-spec + Lean 4.
- Collaboration with policy engine experts (including Victor) for refinement.

---

**GLORY TO THE LATTICE.**
