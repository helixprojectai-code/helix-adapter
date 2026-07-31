# Helix Standardization Templates — Complete Index

**Purpose:** Unified documentation and data format standards across all Helix lattice nodes and operations.

**Foundation:** All templates inherit from schema.json v1.0.0 with MD/JSON isomorphism.

**CRITICAL PRINCIPLE:** These schemas are *data, not dogma*. They are invitations to coherence, not constraints. Any node may modify, extend, or repurpose these templates. If a template doesn't serve your actual work, change it. The only law is coherence — the schema exists to make that legible, not to enforce compliance.

---

## Template Overview

| Template | Use Case | Priority | File | Key Fields |
|----------|----------|----------|------|-----------|
| **Invariant** | Constitutional foundation | 🔴 CRITICAL | `INVARIANT_TEMPLATE.md` | proof, ratification_status, geng, verification_method |
| **Board Meeting** | Governance decisions | 🟠 HIGH | `BOARD_MEETING_TEMPLATE.md` | attendees, motions, decisions, action_items |
| **Ops Task** | Operational work tracking | 🟠 HIGH | `OPS_TASK_TEMPLATE.md` | status, owner, due_date, dependencies, progress_log |
| **Release** | Version deployment & artifacts | 🟠 HIGH | `RELEASE_TEMPLATE.md` | version, release_date, features, fixes, breaking_changes, upgrade_path |
| **Node Chronicle** | Cross-node event logging | 🟡 MEDIUM | `NODE_CHRONICLE_TEMPLATE.md` | geng, epistemic_frame, event_type, constitutional_alignment |
| **Research** | Investigation & discovery | 🟡 MEDIUM | `RESEARCH_TEMPLATE.md` | methodology, findings, limitations, confidence_level |
| **Session Journal** | Work continuity & handoff | 🟢 NICE-TO-HAVE | `SESSION_JOURNAL_TEMPLATE.md` | session_type, tasks, blockers, time_accounting |

---

## Quick Start by Role

### If you're a Node (TRACE, Kimi, SPIDER, BESS, etc.)
→ Use **Node Chronicle** template for all significant events

### If you're tracking operational work
→ Use **Ops Task** template for each task/action item

### If you're recording a session's work
→ Use **Session Journal** template at end of shift/session

### If you're documenting constitutional principles
→ Use **Invariant** template (rare; coordination required)

### If you're recording research & discovery
→ Use **Research** template for investigations

### If you're recording governance decisions
→ Use **Board Meeting** template for meetings

### If you're shipping a release
→ Use **Release** template for version deployments

---

## Schema Inheritance & Common Fields

All templates share the core schema v1.0.0 fields:

**Always include:**
```yaml
id:                    # unique identifier (use template-YYYY-MM-DD-slug format)
type:                  # template type (invariant|task|chronicle|research|journal|meeting)
timestamp:             # ISO 8601 (YYYY-MM-DDTHH:MM:SSZ)
date:                  # YYYY-MM-DD
author:                # who created this
custodian:             # always "Steve Hope" for Helix
substrate:             # where/how this was created
schema_version:        # v1.0.0
constitutional_version: # v1.0
ratification_status:   # draft|review|ratified|archived|superseded
maturity:              # draft|review|published|archived
category:              # domain classification
status:                # open|in_progress|resolved|closed
tags:                  # searchable labels [array]
routing:               # for signal routing (target_node, action_required)
```

**Template-specific fields:**
- **Invariant:** proof, geng, verification_method, ratification_history
- **Board Meeting:** attendees, motions, votes, decisions, action_items
- **Ops Task:** owner, due_date, status, dependencies, progress_log, blockers
- **Release:** version, release_date, branch, features, fixes, breaking_changes, upgrade_path, testing_results
- **Node Chronicle:** geng, epistemic_frame, constitutional_alignment, event_type
- **Research:** hypothesis, methodology, findings, limitations, artifacts
- **Session Journal:** session_type, work_completed, blockers, time_accounting

---

## Routing & Distribution

**Invariants** → LATTICE (all nodes must know)  
**Board Meetings** → LATTICE (governance record)  
**Ops Tasks** → SPIDER (execution tracking)  
**Releases** → SPIDER (deployment + artifact tracking)  
**Node Chronicles** → LATTICE (cross-node awareness)  
**Research** → LATTICE (shared discovery)  
**Session Journals** → NODE-SPECIFIC (handoff + continuity)

---

## Validation & Compliance

All templates validate against schema.json using the validator tool:

```bash
# Single file
python schemas/validate.py path/to/file.md --show-warnings

# All files of a type
python schemas/validate.py [directory]/ 
```

**Compliance checklist:**
- [ ] YAML frontmatter present & parseable
- [ ] All required fields populated
- [ ] ISO 8601 timestamp format
- [ ] Routing semantics correct (if signal)
- [ ] Epistemic framing used (if applicable)
- [ ] Related items cross-referenced
- [ ] Proof/signature (if ratified)

---

## File Naming Convention

```
[type]-YYYY-MM-DD-[slug].md

Examples:
- invariant-2026-07-29-constitutional-coherence.md
- meeting-2026-07-25-board-roundtable.md
- task-2026-07-29-hermes-core-wiring.md
- release-2026-07-30-v1-7-4.md
- chronicle-2026-07-29-TRACE-schema-complete.md
- research-2026-07-15-glyph-marker-audit.md
- journal-2026-07-29-operational-shift.md
```

---

## Integration with Core Schema

**Relationship:**
1. `schema.json` — canonical form (14+ core fields, type-specific extensions)
2. `SCHEMA.md` — human guide + isomorphism rules
3. `validate.py` — validation tool
4. These templates — domain-specific implementations

**All templates are valid instances of schema.json v1.0.0**

---

## Phase-In Strategy

**Week 1 (Now):**
- Introduce templates across all nodes
- Start using for new items only
- Legacy items marked as `legacy: true`

**Week 2–3:**
- Migrate critical items (invariants, board minutes)
- Update ops task tracking
- Begin research documentation

**Ongoing:**
- Node chronicles updated going forward
- Session journals for continuity
- All new work uses standardized format

---

## Support & Questions

**Template questions:**
→ See SCHEMA.md for field reference

**Validation issues:**
→ Run validator tool; check against schema.json

**Format discrepancies:**
→ Contact TRACE for clarification (forensic validator authority)

**Need to modify a template?**
→ Do it. Templates are living documents. If you find a better way to capture your work, that's the right way. Let TRACE know about patterns that emerge so others can learn.

**New template types needed:**
→ File as invariant/task; TRACE will draft template (or draft your own and share)

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.1 | 2026-07-30 | Added RELEASE_TEMPLATE (7 types); updated ARCHITECTURE.md and THEORY.md to RESEARCH_TEMPLATE; epistemic framing added across all docs |
| v1.0 | 2026-07-29 | Initial templates (6 types) for invariants, board, ops, chronicle, research, journal |

---

*Templates published 2026-07-29 | Schema v1.0.0 | TRACE ratified*
