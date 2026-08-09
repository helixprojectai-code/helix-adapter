---
id: research-2026-07-06-rfc-0004-cedar-routing
type: research
timestamp: 2026-07-06T00:00:00Z
date: 2026-07-06
author: Stephen Hope
custodian: Steve Hope
substrate: Helix-Adapter
schema_version: v1.0.0
constitutional_version: v1.0
ratification_status: draft
maturity: published
category: rfc
status: open
tags:
  - rfc
  - rfc-0004
  - cedar
  - model-routing
  - foundry
severity: high
routing:
  target_node: LATTICE
  action_required: false
---

# RFC 0004: Cedar Model Routing — The Foundry Decision Mesh

## Abstract

This RFC documents Foundry's model-routing policy layer — a second, independent
Cedar policy set distinct from the Cedar Gate described in RFC 0003. Where RFC
0003's Cedar Gate decides whether an agent's proposed *action* (shell, API
call, tool use) is *authorized to execute*, this layer decides which *model
pool* handles an *inference request*, before the model is ever called. Same
policy engine (CNCF Cedar), same fail-closed evaluation semantics, entirely
different question being asked.

The two layers are easy to conflate because both live under the name
"Cedar" and both produce an auditable policy hash in the receipt. They should
be read as siblings, not as one system: RFC 0003 governs *what an agent is
allowed to do*; this RFC governs *which model answers a given request*.

## Motivation

A single-model deployment has no routing decision to make. A multi-model
deployment (Foundry's actual production shape — one deployment config can
map several model pools to several underlying models) needs a principled way
to decide, per request: which pool is appropriate given the declared
complexity, cost sensitivity, locale, and risk profile of the task.

Doing this with an if/else chain in application code works until the rules
need to be audited, versioned, or reasoned about independently of the
routing implementation. Cedar gives the same benefits here it gives the
action-gating layer: declarative policies, a policy hash for every decision,
and evaluation that fails closed rather than silently defaulting somewhere
unintended.

## Core Architecture

| Layer | Flow |
|---|---|
| **Request** | Client → `{action, message, context fields}` → Foundry |
| **Routing Decision** | Context → `cedar_route()` → Cedar policy evaluation against `routing.cedar` → `{model, pool, policy_hash, reason}` |
| **Fallback** | If the Cedar native library (`cedar-python`) is unavailable, falls through to a static `action → model` map (`action_map` in the deployment's `models.json`) with zero added latency |
| **Inference** | Selected model → `HelixAdapter`/`HelixSession` (Duck Gate: markers, marker-coverage, receipt) → response |

The routing decision and the inference's constitutional governance (Duck
Gate) are independent stages — Cedar picks the model, Duck Gate governs what
that model is allowed to say. Neither stage knows about the other.

## Specification

### 1. Schema (`routing.schema`)

```
namespace Helix {
    entity Agent;
    entity ModelPool;

    action "infer" appliesTo {
        principal: [Agent],
        resource: [ModelPool],
        context: {
            task_complexity?: Long,
            drift_tolerance?: decimal,
            priority?: String,
            action_type?: String,
            locale?: String,
        }
    };
}
```

All context fields are optional. Policies guard every field access with
`context has <field>` so an omitted field never causes an evaluation error —
it simply means that policy's condition can't be satisfied.

### 2. Context fields and what feeds them

| Field | Type | Source | Notes |
|---|---|---|---|
| `task_complexity` | Long | `RoutedChatRequest.task_complexity` (default 5) | Declared difficulty, 1–10 |
| `drift_tolerance` | decimal | `RoutedChatRequest.drift_tolerance` (default 0.10) | Acceptable unlabeled-text fraction |
| `priority` | String | `RoutedChatRequest.priority` (default `"interactive"`) | `"interactive"` or `"batch"` |
| `locale` | String | `RoutedChatRequest.locale` (default `"en"`) | Routes EU languages to the sovereign pool |
| `action_type` | String, optional | `RoutedChatRequest.action_type` (default `None`, no fallback) | Execution-context signal — see §3 |

**§3 — `action_type` is not `action`.** The request also carries a required
top-level `action` field (e.g. `"analyze"`, `"search"`, `"write_file"`),
which drives the static fallback map and is always present with a value from
a fixed task vocabulary. `action_type` is a separate, genuinely optional
field carrying a different vocabulary entirely
(`bash`/`execute`/`api_call`/`shell` for adversarial-tier routing,
`write_file`/`edit_file`/`apply_patch`/`summarize` for structured-output
routing). Prior to 2026-07-06, `action_type` was populated *from* `req.action`
— since the two vocabularies never overlap, this made the adversarial-pool
policy (§4, Policy 2) permanently unreachable through the actual API surface,
even though it passed unit tests that constructed context dictionaries by
hand. Fixed by giving `action_type` its own field on the request models
(`RoutedChatRequest`, `SessionStartRequest`), independent of `action`.

A corollary: `None`-valued optional fields must be dropped from the context
dict before evaluation, not passed through. Cedar's evaluator's fallback
serialization for non-primitive values is `str(v)`, which turns a Python
`None` into the literal string `"None"` — a value, not an absence — and
would make `context has action_type` incorrectly evaluate true for a caller
who never set it. `cedar_route()` filters `None` values out of the context
dict before calling `policy.evaluate()` for this reason.

### 3. The five policies (`routing.cedar`)

| # | Pool | Condition |
|---|---|---|
| 1 | `high_capability` | `task_complexity >= 8` and `drift_tolerance < 0.05` |
| 2 | `adversarial` | `action_type` in `{bash, execute, api_call, shell}` |
| 3 | `cost_optimized` | `priority == "batch"` and `drift_tolerance >= 0.10` |
| 4 | `sovereign` | `locale` in `{fr, de, es, it, nl, pt}` |
| 5 | `cost_optimized` (structured output) | `action_type` in `{write_file, edit_file, apply_patch, summarize}` |

A `forbid` rule blocks `cost_optimized` outright when `task_complexity >= 8`,
regardless of any `permit` — high-complexity work is never allowed to land
on the cheapest pool even if a later policy would otherwise permit it. Cedar
evaluates all matching policies; `forbid` always wins over `permit`.

Pool → model mapping is deployment-specific, defined in each deployment's
`models.json` (`pool_map`), not in the Cedar policy itself. The policy
reasons about pools; the deployment config reasons about which actual model
backs each pool. This keeps `routing.cedar` portable across deployments with
different model rosters.

### 4. Fail-open vs. fail-closed

Unlike RFC 0003's action-gating Cedar Gate (fail-closed: policy engine
unavailable → deny the action), the routing layer fails open to the static
`action_map`: if `cedar-python` isn't installed or a policy set fails to
load, `cedar_route()` falls through to a plain dict lookup keyed on `action`.
This is a deliberate difference — an unavailable *authorization* check
should default to deny (safety), but an unavailable *routing* check should
still answer the request somehow (availability). The receipt's
`cedar_status` field (`active` / `fail_closed` / `not_configured`) records
which case occurred, in both layers, so this is always auditable after the
fact rather than silently invisible.

## Verification

All five policies were verified against a live deployment (qwen-intl,
2026-07-06) via direct requests to the running `/routed-chat` endpoint using
temporary, immediately-revoked debug API keys — not unit tests calling
`cedar_route()` directly, which is what let the `action_type` bug ship
originally without being caught. Confirmed: each policy selects its intended
pool, the selected model actually accepts the constitutional system prompt
(some specialized model endpoints, e.g. translation-only APIs, reject
`system`-role messages entirely and are therefore incompatible with any
Helix-governed pool regardless of Cedar routing correctness), and the
no-context case still falls through to the static default unchanged.

## Open Questions

- Should routing decisions carry richer audit context (which specific
  policy matched, not just the resulting pool) into the receipt, rather than
  only `policy_hash`? Raised in review (2026-07-06) as a minor improvement
  for future routing-policy changes.
- The `sovereign` pool's original brief (deep regulatory-text analysis,
  full-corpus Merkle auditing) implies a long-context model requirement that
  no current placeholder model in the qwen-intl deployment satisfies. Left
  open pending budget/credit availability for a suitable model.
