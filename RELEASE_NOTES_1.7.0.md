# helix-adapter v1.7.0 Release Notes

**Released:** 2026-07-02
**Branch:** claude/claude-code-linux-desktop-as4dm6 → main
**PyPI:** `pip install helix-adapter==1.7.0`

---

## Overview

v1.7.0 is a **security audit release** (Fable 5 audit). It hardens the reference
API servers — `foundry/foundry.py` and `widget/api.py` — at the transport layer.
The constitutional guarantees are only as strong as the server that fronts them,
and this release closes the gaps between the two.

Nothing changes in the adapter itself. `HelixAdapter`, `HelixSession`,
`MerkleTree`, receipts, drift, and Cedar gating are all byte-for-byte the same.
If you use the library directly and front it with your own server, you are
unaffected. If you deploy the bundled Foundry or widget servers, read on.

---

## What's Fixed

### API keys are hashed at rest

The Foundry key store no longer keeps plaintext keys. `foundry_keygen.py` writes
a SHA-256 hash of each key (`foundry_db.hash_key()`); `require_key` hashes the
presented header before lookup and never returns key material. The plaintext is
shown once at creation and cannot be recovered.

```bash
python3 foundry_keygen.py --node hermes --note "Hermes inference node"
# Key created for node 'hermes':
#   hx-a1b2c3...            ← shown once; only its hash is stored
python3 foundry_keygen.py --list       # shows key-hash prefixes, never plaintext
python3 foundry_keygen.py --revoke hx-a1b2c3...
```

Read access to `foundry_keys.db` (a backup, a stray copy, a log) no longer yields
usable credentials.

### Tenant isolation on Foundry (IDOR fix)

Sessions are now owned by the node that created them. `/session/*`, `/sessions`,
and `/ledger` are scoped to the calling node via `_assert_session_access`. A
previous gap let any valid key read, export, or delete **another** node's
sessions and see every node's prompt/response history. Cross-node access now
returns `404` (not `403`, so session IDs can't be probed).

| Endpoint | Before | After |
|----------|--------|-------|
| `GET /session/{id}` | any key | owner only |
| `GET /session/{id}/export` | any key | owner only |
| `DELETE /session/{id}` | any key | owner only |
| `GET /session/{id}/merkle[/{turn}]` | any key | owner only |
| `GET /sessions` | all nodes' sessions | caller's sessions |
| `GET /ledger`, `GET /routed-chat/ledger` | all nodes' entries | caller's entries |

Legacy sessions and ledger entries with no recorded owner remain reachable for
backward compatibility; new ones always carry a `node_id`.

### Widget server is no longer an open relay

`/api/chat`, `/api/compare`, and `/v1/chat/completions` spend real (paid) model
credits. They now sit behind:

- **Optional API-key auth** — set `HELIX_WIDGET_API_KEY` to require `X-API-Key`.
- **Per-IP rate limiting** — default 20 requests / 60 s (`HELIX_RATE_LIMIT`).
- **CORS allowlist** — wildcard CORS is gone. Cross-origin access is off by
  default; add trusted origins via `HELIX_CORS_ORIGINS` (comma-separated).

Left unconfigured, the endpoints keep the open behavior for local demo use — but
`HELIX_WIDGET_API_KEY` should be set before exposing the server to any untrusted
network.

### Constitutional bypass hardened

The `/api/compare` `sp:none` bypass now:

- compares the key in **constant time** (`hmac.compare_digest`),
- is accepted via the `X-Compare-Bypass-Key` **header only** (the query-param
  path leaked the secret into access logs, browser history, and referrers), and
- drops a dead template substitution that could have shipped the secret into the
  served HTML.

### Rate limiter correctness

`X-Forwarded-For` is honored **only** when `HELIX_TRUST_PROXY=1` — otherwise the
header is attacker-controlled and would let any client forge a fresh bucket per
request. Stale IP buckets are evicted so the limiter map can't grow without
bound under IP churn.

---

## New Environment Variables

| Variable | Server | Default | Purpose |
|----------|--------|---------|---------|
| `HELIX_WIDGET_API_KEY` | widget | unset (open) | Require `X-API-Key` on model endpoints |
| `HELIX_CORS_ORIGINS` | widget | none | Comma-separated cross-origin allowlist |
| `HELIX_RATE_LIMIT` | widget | 20 | Requests per 60 s per IP |
| `HELIX_TRUST_PROXY` | both | off | Read client IP from `X-Forwarded-For` |
| `FOUNDRY_KEYS_DB` | foundry | `~/helix/keys/foundry_keys.db` | Hashed key store path |
| `HELIX_COMPARE_BYPASS_KEY` | widget | unset (disabled) | Enable `sp:none` bypass |

---

## Testing

Full suite: **111 passing, 30 skipped** (skipped tests require live API keys or
the Cedar native library). The security behavior was verified end-to-end via
smoke tests:

- key-hash round-trip — stored value is a 64-char hash, plaintext auth resolves,
  wrong key rejected;
- widget auth — unauthenticated calls to all three model endpoints return `401`,
  a valid key passes through;
- CORS — no middleware installed when no allowlist is configured;
- tenant isolation — cross-node session access returns `404`, legacy sessions
  stay reachable, `/ledger` returns only the caller's entries.

ruff + black clean on `src/ tests/ foundry/`.

---

## Breaking Changes

- **Existing Foundry keys must be re-issued.** Keys are now stored hashed, so
  plaintext keys created by earlier versions will not match the SHA-256 lookup.
  Re-run `foundry_keygen.py --node <id>` for each node after upgrading (old keys
  are unrecoverable by design — no migration path). This affects the Foundry key
  store only; library users are unaffected.
- **Widget CORS is closed by default.** Deployments that relied on wildcard CORS
  must set `HELIX_CORS_ORIGINS`.

No changes to `HelixAdapter`, `HelixSession`, `MerkleTree`, `JointReceipt`, or
any receipt/drift/Cedar behavior.

---

## Upgrade

```bash
pip install --upgrade helix-adapter==1.7.0
```

For Foundry deployments, after upgrading:

```bash
# Re-issue node keys (old plaintext keys no longer validate)
python3 foundry_keygen.py --node hermes --note "Hermes inference node"

# If behind a reverse proxy
export HELIX_TRUST_PROXY=1
```

For the widget server, before exposing it publicly:

```bash
export HELIX_WIDGET_API_KEY="$(openssl rand -hex 24)"
export HELIX_CORS_ORIGINS="https://your-frontend.example.com"
```

---

## What's Next

- Optional persistent (Redis-backed) rate limiting for multi-worker deployments
- Per-key scopes / roles on Foundry beyond node-level isolation
- Signed receipts (asymmetric key) as an upgrade path from self-hashing
