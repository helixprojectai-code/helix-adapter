---
id: task-YYYY-MM-DD-TASK_ID
type: task
timestamp: YYYY-MM-DDTHH:MM:SSZ
date: YYYY-MM-DD
author: OWNER_NAME
custodian: Steve Hope
substrate: Operations
schema_version: v1.0.0
constitutional_version: v1.0
ratification_status: open
maturity: published
category: operations
status: open
tags:
  - task
  - [priority]
  - [domain]
  - [system]
severity: [low|medium|high|critical]
routing:
  target_node: SPIDER
  action_required: true
  precedent_id: [prior-task-or-incident-id]
---

# Task: [Title]

**Owner:** [Name]  
**Priority:** [Low | Medium | High | Critical]  
**Due Date:** YYYY-MM-DD  
**Status:** [Open | In Progress | Blocked | At Risk | Complete]  
**Estimate:** [Duration or effort estimate]

---

## Task Description

[Clear statement of what needs to be done, why, and any context needed.]

**Success criteria:**
- [ ] [Criterion 1]
- [ ] [Criterion 2]
- [ ] [Criterion 3]

---

## Background & Context

**Why this task exists:**
- [Incident, request, or finding that triggered it]
- [Prior related work]

**Dependencies:**
- [Task/resource that must be complete first]
- [Blocking item or prerequisite]

**Related tasks:**
- [[task-id]] — [relationship]
- [[task-id]] — [relationship]

---

## Approach

**Plan:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

**Resources needed:**
- [Tool/service]
- [Access/credential]
- [Budget/quota]

**Known risks:**
- [Risk 1] → Mitigation: [how to avoid]
- [Risk 2] → Mitigation: [how to avoid]

---

## Progress Log

| Date | Status | Notes | Next |
|------|--------|-------|------|
| 2026-07-29 | Open | Task created | Start investigation |
| YYYY-MM-DD | [In Progress | Blocked] | [What was done / blocker] | [Next step] |
| YYYY-MM-DD | [Complete | Cancelled] | [Outcome] | [Follow-up] |

---

## Artifacts & Evidence

**Work products:**
- [Commit/PR]: [Link]
- [Document]: [Path or link]
- [Test results]: [Link]

**Sign-off:**
- [ ] Owner verified complete
- [ ] Reviewer approved
- [ ] Deployment complete (if applicable)

---

## Closure

**Completion date:** [Date task finished]  
**Final status:** [Complete | Cancelled | Deferred]  
**Lessons learned:** [What went well / what to improve]  
**Follow-up tasks:** [[task-id], [task-id]]

---

*Task created [date] | Owner: [Name] | Last updated: [date]*
