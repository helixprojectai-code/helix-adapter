# Changelog

All notable changes to `helix-adapter` are documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [1.6.0] — 2026-06-30

### Summary

Dual tamper-evidence architecture: `chain_hash` (linear sequence integrity) plus an
append-only Merkle tree (membership proofs). Every session receipt now carries a
`merkle_root` sealing the tree state at that turn. Historical roots are immutable —
old proofs remain valid after new receipts are added. Foundry gains full session
management UI with inline Merkle proof viewer. CI enforced with ruff + black.
141 tests passing.

### Added

- **`MerkleTree`** (`src/helix_adapter/merkle.py`) — append-only binary Merkle tree
  over session receipt hashes. Duplicate-last padding (Bitcoin standard). Historical
  roots stored per-turn so any prior state can be proved without rewriting the tree.
  - `append(leaf_hash)` — add receipt hash, return new root
  - `root_at(turn)` — root after exactly N receipts (immutable once written)
  - `proof(turn)` — sibling path for inclusion proof against `root_at(turn)`
  - `verify(leaf, proof, root)` — static; no tree instance required
  - `from_leaves(hashes)` — reconstruct tree from stored receipt hashes (for resume)

- **`merkle_root` on `JointReceipt`** — each receipt carries the Merkle root at
  its turn. Chain hash catches sequence tampering; Merkle root catches structural
  reordering. Receipts pre-dating 1.6.0 carry `merkle_root=None`.

- **`HelixSession` Merkle methods** — `merkle_root` property, `merkle_proof(turn)`,
  `merkle_all_roots()`. Tree initialized fresh and rebuilt from stored receipt hashes
  on `resume()`.

- **`HelixSession.merkle_consistency_check()`** — 3-layer integrity validation:
  (1) chain hash recomputed from stored receipts, (2) Merkle tree rebuilt and root
  compared, (3) each receipt's stored `merkle_root` cross-checked against the rebuilt
  tree root at that turn. Returns `True` if all layers pass.

- **Foundry session endpoints** — full session lifecycle over HTTP:
  `POST /session/start`, `POST /session/{id}/send`, `GET /session/{id}`,
  `GET /session/{id}/export`, `DELETE /session/{id}`, `GET /sessions`.
  Cedar routes on start, model locked for session lifetime.

- **Foundry `GET /session/{id}/merkle`** — current root, leaf count, all historical
  roots indexed by turn.

- **Foundry `GET /session/{id}/merkle/{turn}`** — inclusion proof for a specific
  turn with inline `valid: bool` verification result.

- **Foundry Sessions page** (`/sessions/`) — table of active receipt chains with
  running drift per session, per-receipt detail view, Merkle root display, and
  clickable proof viewer per receipt.

- **Routed Chat session mode** — toggle in UI starts a Cedar-routed session on first
  send, subsequent sends route to committed model. Badge shows session ID prefix,
  model, turn number, and chain hash prefix. "End Session" deletes and resets.

- **`/health` session stats** — `session_count` and `total_session_turns` added.

- **`e2e_merkle_test.py`** — 22-check end-to-end test: session creation, chain hash,
  merkle_root per receipt, proof verification across all turns, historical roots,
  consistency check, resume with continued sends, tamper detection on leaf and proof.
  No API keys required (mock model_fn).

- **CI: `.github/workflows/lint.yml`** — ruff + black enforced on push to
  `main`/`spider-dev`/`helix-dev` and on all PRs to `main`.

### Fixed

- **Foundry Mistral `max_tokens`** — `build_adapter()` and `build_session()` were
  sending `max_completion_tokens` to Mistral-Large-3, which returns 422. Branch now
  excludes Mistral deployments from the Azure `max_completion_tokens` path.

---

## [1.5.0] — 2026-06-29

### Summary

Multi-turn session architecture. `HelixSession` replaces per-call `HelixAdapter` usage
for conversational workloads. Receipts are now chained across turns into a tamper-evident
chain — modifying any prior receipt breaks all subsequent chain hashes. Pluggable store
layer: in-memory default or SQLite WAL-mode persistence with cross-restart session resume.
Cedar and Duck Gate co-sealed per turn in `JointReceipt`. 81 new tests. No breaking
changes to `HelixAdapter` or existing integrations.

### Added

- **`HelixSession`** (`src/helix_adapter/session.py`) — multi-turn constitutional
  session host. Manages conversation context window, per-turn receipt generation,
  and session lifecycle (`send`, `clear`, `delete`, `export`, `running_drift`).
  Context manager protocol supported.

- **`HelixSession.resume()`** — classmethod to reload a prior session from store,
  rebuilding the full conversation context window from stored receipts and restoring
  chain continuity.

- **`JointReceipt`** — dataclass co-sealing Duck Gate (drift score, claims) and Cedar
  Gate (action decision, policy hash) in a single tamper-evident record per turn.
  Fields: `exchange_id`, `session_id`, `turn`, `timestamp`, `model`, `user_message`,
  `assistant_response`, `claims`, `drift_score`, `drift_tier`, `drift_method`,
  `cedar_action`, `cedar_authorized`, `cedar_policy_hash`, `cedar_reason`,
  `cedar_status`, `hash`, `chain_hash`.

- **`chain_hash`** — tamper-evident chain linking all receipts in a session.
  Computed as `sha256(hex(prev_chain_hash) + hex(this_hash))`. Turn 0 seeds
  with empty string. Breaks on any modification to prior receipt history.

- **`MerkleTree`** (`src/helix_adapter/merkle.py`) — append-only binary Merkle
  tree over receipt hashes. Duplicate-last padding (Bitcoin standard). Provides
  `append()`, `root_at(turn)` for historical roots, `proof(turn)` for inclusion
  proofs, and static `verify()` for standalone verification without a tree instance.

- **`merkle_root` on `JointReceipt`** — each receipt now carries the Merkle root
  at its turn, enabling dual tamper evidence: chain_hash detects linear tampering,
  Merkle detects structural reordering.

- **HelixSession Merkle methods** — `session.merkle_root` property, `merkle_proof(turn)`
  for inclusion proofs, `merkle_all_roots()` for full root history. Tree is persisted
  alongside receipts and rebuilt on `resume()`.

- **`tests/test_merkle.py`** — 10-test suite covering single/multi-leaf trees,
  historical roots, inclusion proofs and verification, tamper detection, reconstruction
  from leaf list, and edge cases (empty tree, out-of-range proof).

- **`DriftThreshold`** — configurable dataclass (`green`, `yellow`, `red` float
  thresholds) with `tier(score)` method. Defaults match v1.4 thresholds. Pass
  per-deployment instances to `HelixSession` for tuned tolerance.

- **`InMemoryReceiptStore`** (`src/helix_adapter/store.py`) — default store, no
  persistence. Full `ReceiptStore` ABC contract: `save`, `get_session`,
  `list_sessions`, `delete_session`, `export_session`.

- **`SQLiteReceiptStore`** — WAL-mode persistent store. Auto-creates `~/.helix/sessions.db`
  (path configurable). Schema: `receipts` table with indexed `(session_id, turn)`.
  Survives process restarts; sessions resumable across instances.

- **`ReceiptStore` ABC** — abstract base class defining the store interface. Custom
  stores (Redis, Postgres, etc.) implement four methods.

- **`tests/test_session.py`** — 81-test suite covering `DriftThreshold` boundaries,
  both store implementations and their shared interface contract (parametrized),
  `HelixSession` core behavior, chain hash integrity and tamper detection,
  session lifecycle, `resume`, `JointReceipt` structure, context manager protocol,
  and public API regression.

- **`QUICKSTART.md`** — dedicated FastAPI quickstart. Full working API with session
  endpoints, curl examples, session resume across restarts, all lifecycle endpoints,
  API key auth, DeepSeek / Claude / Ollama backend swap examples, systemd unit,
  and receipt schema reference.

- **`assets/helix-adapter-logo.jpg`** — project logo added to repo, inserted into
  README header.

### Changed

- **`cedar_python` promoted to core dependency** — moved from `[project.optional-dependencies]`
  to `[project.dependencies]` in `pyproject.toml`. `pip install helix-adapter` now
  includes Cedar automatically.

- **`.gitignore`** — added `*.db`, `*.db-shm`, `*.db-wal`, `foundry/foundry-ledger.jsonl`

- **`__init__.py`** — exports `HelixSession`, `JointReceipt`, `DriftThreshold`,
  `InMemoryReceiptStore`, `SQLiteReceiptStore`.

- **`README.md`** — rewritten as standard project landing page: architecture flow
  diagram, install, single-turn and multi-turn usage, markers table, drift thresholds,
  CLI, receipt format, Cedar, Foundry, hardening. FastAPI section now links to
  QUICKSTART. Logo in header.

- **Drift threshold tables** (README + QUICKSTART) — boundary notation updated from
  `0.00–0.09` to `0.00–<0.10` with explicit note that boundaries are exclusive,
  matching `DriftThreshold.tier()` behaviour. Corrects potential misreading in
  regulatory contexts.

- **`chain_hash` spec** — clarified in both README receipt table and QUICKSTART
  receipt schema as hex-string concatenation (`sha256(hex(prev) + hex(this))`),
  not byte concatenation. External verifiers require this distinction.

### Fixed

- **QUICKSTART Foundry import** — `from foundry.foundry_auth import require_key`
  replaced with `sys.path.insert(0, "foundry"); from foundry_auth import require_key`.
  `foundry/` has no `__init__.py`; the original import raised `ModuleNotFoundError`.

---

## [1.4.0] — 2026-06-26

### Summary

Cedar Gate base layer cohesion pass. All Cedar integration code now runs correctly
against `cedar-python 0.1.4`. Hooks extracted to their own module. Schema and
policy files corrected throughout. Adapter Cedar wiring solidified. 49/49 tests
passing with all Cedar tests active (none skipping).

### Added

- `src/helix_adapter/cedar/hooks.py` — `PreToolUseHook` and `PostToolUseHook`
  extracted to dedicated module; `adapter.py` imports from `cedar.hooks` as intended
- `HelixSecurityViolation` exception in `adapter.py` — raised when Cedar denies
  a tool call registered via `register_tool`
- `register_tool` decorator on `HelixAdapter` — wraps tool functions with automatic
  Cedar pre/post hooks when a `cedar_policy` is configured
- `CedarGate` backward-compatible wrapper class in `policy.py`
- `ActionReceipt` dataclass exported from `cedar.__init__`
- `generate_schema_from_tools()` auto-declares `Environment` entity when
  `include_governance=True` (required by governance namespace)
- API endpoint allowlist in `helix.policy` — HTTPS-only, named hosts
  (api.github.com, pypi.org, helix.openai.azure.com, reef.helixprojectai.com)
- `/home/agent/work/*` added to file operation permit paths
- Dangerous bash command blocking via context pattern match
  (`*rm -rf*`, `*shutdown*`, `*reboot*`)
- `write_file` forbid rules for `/etc/*` and `*.env` paths
- `CHANGELOG.md` (this file)

### Fixed

**Cedar Python API (`policy.py`):**
- `PolicySet.from_str()` → `Policy.from_str(raw, id='pN') + ps.add()` loop
  (`PolicySet.from_str` does not exist in cedar-python 0.1.4)
- `Schema.from_str()` → `Schema.from_cedarschema(text)`
- `ps.validate(schema)` → `schema.validate_policyset(ps)`
- `Evaluator` class → `Authorizer` (`Evaluator` does not exist)
- `result.is_allowed()` → `result.allowed` (bool property, not method)
- Float context values now encoded as Cedar decimal extension:
  `{"__extn": {"fn": "decimal", "arg": "0.1700"}}` (raw Python floats
  cause type errors in decimal comparisons)
- `auth.add_entity()` calls added for principal, action, and resource entities
- Policy splitter regex changed from comment-stripping (`re.sub`) to
  line-start anchor (`(?m)(?=^[ \t]*(?:permit|forbid)\s*\()`) — the old
  approach destroyed `https://` URLs inside string literals

**Cedar Schema Language (`helix.schema`, `schema.py`):**
- `entity X in [Principal]` / `entity X in [Resource]` → `entity X;`
  (`Principal` and `Resource` are not defined Cedar entity types)
- `Decimal` → `decimal` (Cedar schema type names are case-sensitive)
- `Boolean` → `Bool`
- Context block moved inside `appliesTo`:
  `action "X" appliesTo { principal: [...], resource: [...], context: { ... } }`
- Action names quoted: `action "respond"` not `action respond`
- `SchemaBuilder.add_action()` now produces correct context-inside-appliesTo layout
- `_governance_section()` corrected with same fixes
- `HELIX_SCHEMA` / `HELIX_BASE_SCHEMA` rewritten throughout

**Cedar Policy Language (`helix.policy`):**
- Full namespace prefix restored on all action references:
  `Helix::Action::"bash"`, `Helix_Governance::Action::"respond"`
- `context.drift_score < decimal("0.17")` → `context.drift_score.lessThan(decimal("0.17"))`
  (Cedar `<` operator does not work on `decimal` type; use extension method)
- `action in [Action::"bash:rm -rf", ...]` → per-action `forbid` rules
  (Cedar does not support string-set membership on actions)
- `resource.path like "..."` → `context has path && context.path like "..."`
  (entity attributes are empty; path is in evaluation context)

**`cedar/__init__.py`:**
- Imports updated to pull from correct modules (`policy`, `hooks`, `schema`)
- Orphaned `_load_policy_set(self, policy_text)` function removed
  (had `self` parameter at module scope — was a no-op and a mistake)

**`adapter.py`:**
- `Action::"name"` → `Helix::Action::"name"` in `register_tool` tool_call dict
- `Resource::"default"` → `Helix::Environment::"default"`

### Changed

- `helix.schema` dual-namespace structure preserved and corrected:
  `Helix` namespace for actions, `Helix_Governance` namespace for `respond`
- Cedar tests no longer skip — all 34 Cedar tests active, 49/49 total passing
- `ARCHITECTURE.md`: Cedar Dual-Gate section updated from `v1.3 preview` to `v1.4`

---

## [1.3.0] — 2026-06-01

### Summary

Cedar Policy Gate introduced (RFC 0003). Helix Foundry added. Duck Gate + Cedar
Gate dual-gate architecture established. 34 Cedar tests added, 49 total.

### Added

- Cedar policy gate (`helix_adapter/cedar/`) — CNCF Cedar integration for
  deterministic action governance
- `CedarPolicy` class with fail-closed default, schema validation, tamper-evident
  action receipts
- `helix.policy` and `helix.schema` — base dual-gate policy and schema files
- `tests/test_cedar.py` — 34-test Cedar suite covering all gate paths
- Helix Foundry (`foundry/`) — Cedar-routed multi-model inference pool with
  `/route-chat/` and `/audit/` endpoints
- Cedar routing schema (`foundry/routing.cedar`, `foundry/routing.schema`)
- `foundry/foundry.py` — FastAPI app with rate limiting, ledger, dashboard
- RFC 0003 documentation

### Changed

- README Cedar section updated to reflect live (not preview) status
- Contributors section added

---

## [1.2.0] — 2026-05-22

### Summary

TEL v2 live delivery. First Spider→Bess inter-node transmission. Session
continuity bug fixed. Azure keys rolled.

### Added

- TEL v2 pipeline (`tests/test_v12_pipeline.py`) — 4 constitutional robustness
  tests: determinism, authority spoofing, drift blind spots, sentence label fusion
- `compute_running_drift()` helper

### Fixed

- Session receipt chaining bug
- Azure API key rotation

---

## [1.1.0] — 2026-05-20

### Summary

Initial multi-model support, drift detection methods, marker extraction hardening.

### Added

- `drift_method` parameter on `HelixAdapter` (`char`, `token`, `semantic`)
- `detect_nonstandard_markers()` for audit use cases
- `validate_response()` convenience wrapper

---

## [1.0.0] — 2026-05-01

### Summary

Initial release. Constitutional wrapper, epistemic markers, receipt generation,
drift detection.

### Added

- `HelixAdapter` — constitutional wrapper for any model function
- `CONSTITUTIONAL_PROMPT` and `MARKERS` constants
- `extract_claims()` — marker-tagged claim extraction
- `make_receipt()` — tamper-evident session receipt generation
- `compute_drift()` — response drift scoring
- `tests/test_basic.py` — baseline test suite
