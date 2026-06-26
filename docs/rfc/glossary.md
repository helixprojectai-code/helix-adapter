# Cedar Integration Glossary

This glossary defines key terms used in the Helix Adapter's Cedar Policy Gating implementation and related documentation.

## Core Concepts

**Duck Gate**  
The response-level governance layer. Responsible for enforcing epistemic markers (`[FACT]`, `[REASONED]`, etc.), calculating drift score (γ), validating receipts, and ensuring output integrity before a response is returned to the user.

**Cedar Gate**  
The action-level governance layer powered by CNCF Cedar. Evaluates whether an agent is allowed to perform a specific action (tool use, shell command, API call, etc.) based on declarative policies.

**Dual-Gate Architecture**  
The combined system of Duck Gate (response governance) + Cedar Gate (action governance). Together they provide layered containment for LLM agents.

**Fail-Closed**  
The default security posture: if Cedar cannot evaluate a request (missing policy, error, or unavailable), the action is denied. This is the opposite of fail-open behavior.

**Drift Score (γ)**  
A real-time metric produced by the Duck Gate that quantifies how much the model's output has drifted from expected behavior or grounding. Passed into Cedar context for policy decisions.

**Epistemic Markers**  
Structured labels such as `[FACT]`, `[HYPOTHESIS]`, `[ASSUMPTION]`, and `[SUBVERSION_RISK]` that the Duck Gate requires models to use. These help both humans and downstream systems understand the confidence level of statements.

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
The formal specification for Unified Policy Gating using Cedar in the Helix system.

**Foundry**  
Helix's multi-model routing and orchestration layer. Can be combined with Cedar for policy-aware model selection.
