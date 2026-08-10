---
id: invariant-YYYY-MM-DD-SHORT_SLUG
type: invariant
timestamp: YYYY-MM-DDTHH:MM:SSZ
date: YYYY-MM-DD
author: CUSTODIAN_NAME
custodian: Steve Hope
substrate: Constitutional
schema_version: v1.0.0
constitutional_version: v1.0
geng: [GENG_NUMBER]
ratification_status: draft
maturity: published
category: constitutional
status: open
tags:
  - invariant
  - foundational
  - [domain-tag]
severity: critical
routing:
  target_node: LATTICE
  action_required: false
  precedent_id: [prior-invariant-id]
proof:
  hash: [invariant-proof-hash]
  derivation_method: Constitutional derivation
  timestamp: YYYY-MM-DDTHH:MM:SSZ
  verifier: TRACE
signature:
  algorithm: Ed25519
  signed_by: CUSTODIAN
  value: [signature-hex]
---

# [Invariant Title]

**Classification:** Constitutional Foundation  
**Scope:** [What domain/system this invariant governs]  
**Binding:** [All nodes | Specific node types | All actors]

## Definition

[Clear, formal statement of the invariant. This should be universally true, not context-dependent.]

**Mathematical form (if applicable):**
```
[Formal expression of the invariant]
```

**Plain language:**
[One sentence stating what must always be true]

## Rationale

**Why this matters:**
- [Primary reason this invariant is necessary]
- [Secondary implications if violated]

**Historical precedent:**
- [Prior incidents or events that necessitated this invariant]
- [Evolution of this invariant over time]

## Scope & Applicability

**Applies to:**
- [Which nodes / systems / actors]
- [Which operations / states]

**Does NOT apply to:**
- [Explicit exceptions or boundaries]

## Verification Method

**How to check if this invariant holds:**
1. [Verification step 1]
2. [Verification step 2]
3. [Test case or counterexample that would violate it]

**Automation:** [If there's a script or tool to verify, reference it]

## Violations & Recovery

**If violated:**
- [Immediate consequence]
- [Recovery procedure]
- [Who to notify]

**Historical violations:**
- [Prior incidents where this was broken, and how it was fixed]

## Related Invariants

- [[other-invariant-id]] — [relationship]
- [[another-invariant-id]] — [relationship]

---

*Invariant v1.0 | Ratified [date] | GENG [number] | No amendments yet*
