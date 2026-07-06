# Cedar Integration Glossary

This glossary defines key terms used in the Helix Adapter's Cedar Policy Gating implementation and related documentation.

## Core Concepts

**Duck Gate**  
The response-level governance layer. Responsible for enforcing epistemic markers (`[FACT]`, `[REASONED]`, etc.), calculating marker coverage (the `drift_score` field), validating receipts, and ensuring output integrity before a response is returned to the user.

**Cedar Gate**  
The action-level governance layer powered by CNCF Cedar. Evaluates whether an agent is allowed to perform a specific action (tool use, shell command, API call, etc.) based on declarative policies.

**Dual-Gate Architecture**  
The combined system of Duck Gate (response governance) + Cedar Gate (action governance). Together they provide layered containment for LLM agents.

**Fail-Closed**  
The default security posture: if Cedar cannot evaluate a request (missing policy, error, or unavailable), the action is denied. This is the opposite of fail-open behavior.

**Marker Coverage (`drift_score` field)**  
A real-time metric produced by the Duck Gate: the fraction of a response's text that lacks a proper epistemic marker (`0.0` = fully labeled, `1.0` = no markers at all). Passed into Cedar context as `drift_score` for policy decisions. The field is still named `drift_score`/`drift_tier` in code and receipts for API stability, but "drift" here is a narrow, text-labeling-completeness signal — it is **not** the same measure as the constitutional convergence tolerance (γ = 0.17, Policy 007) used elsewhere in Helix's mesh governance, nor the same as RFC 0002's proposed attention-entropy metric. All three happened to share the name and a similar threshold value; they are unrelated calculations over unrelated inputs. See RFC 0002 §2 for the disambiguation.

**Epistemic Markers**  
Structured labels such as `[FACT]`, `[HYPOTHESIS]`, `[ASSUMPTION]`, and `[SUBVERSION_RISK]` that the Duck Gate requires models to use. These help both humans and downstream systems understand the confidence level of statements. Since v1.7.2, each of the five implemented markers (`FACT`/`REASONED`/`HYPOTHESIS`/`UNCERTAIN`/`CONCLUSION`) also carries a fixed glyph (✅ 🔗 🧪 ❓ 🏁) as a language-independent audit cue — required paired with the bracketed label for non-English claims, optional for English.

**Receipt Chaining**  
The practice of linking Response Receipts (from the Duck Gate) with Action Receipts (from the Cedar Gate) to create a full, tamper-evident audit trail from prompt to final action outcome.

## Cedar-Specific Terms

**PARC Model**  
Cedar's core authorization model consisting of:
- **Principal**: Who is making the request (e.g. an agent or user)
- **Action**: What operation is being requested
- **Resource**: What is being acted upon
- **Context**: Additional data used to make the decision

**Policy Set**  
A collection of `permit` and `forbid` statements loaded into Cedar. Can be defined in one or more `.cedar` files.

**Schema**  
A formal definition of entity types, attributes, and actions. Used to validate policies at load time and catch structural errors early.

**Context**  
Additional structured data passed to Cedar during evaluation (e.g. `drift_score`, `has_valid_receipt`, `command`). Must be JSON-serializable.

**decimal()**  
Cedar's extension function used to represent floating-point numbers (since Cedar does not have a native float type). Used heavily for `drift_score`.

## Implementation Terms

**CedarPolicy**  
The main class in `helix_adapter.cedar` that wraps the Cedar engine. Handles policy loading, schema validation, evaluation, and receipt generation.

**CedarDecision**  
The structured result returned by `CedarPolicy.evaluate()`. Contains `authorized`, `reason`, `policy_hash`, and other forensic data.

**ActionReceipt**  
A tamper-evident record generated after an action is evaluated. Used for audit logging and chaining with conversation receipts.

**HelixSecurityViolation**  
Exception raised when Cedar denies an action. Used to enforce fail-closed behavior in a clear, catchable way.

**PreToolUseHook / PostToolUseHook**  
Optional hooks that run before and after tool execution. Can perform additional checks or side effects beyond Cedar policy evaluation.

**strict mode**  
When enabled on `CedarPolicy`, any error during initialization or evaluation causes an exception instead of graceful degradation to fail-closed mode. Useful for high-assurance environments.

## Related Concepts

**RFC 0003**  
The formal specification for Unified Policy Gating using Cedar in the Helix system — the Cedar Gate that authorizes (or denies) an agent's proposed tool/action calls before execution.

**RFC 0004**  
The formal specification for Foundry's Cedar model-routing layer (`routing.cedar`) — a separate Cedar policy set from RFC 0003's Cedar Gate. This one decides which model pool handles an inference request; RFC 0003 decides whether an action is allowed to execute. Same policy engine, different question.

**Foundry**  
Helix's multi-model routing and orchestration layer. Uses Cedar for policy-aware model selection per RFC 0004.
