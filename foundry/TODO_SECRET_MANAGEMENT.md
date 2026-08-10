# TODO: Foundry Secret Management

**Current State (2026-07-15):**
- API keys stored in SQLite at `/root/.helix/foundry_keys.db`
- Database path set via `FOUNDRY_KEYS_DB` environment variable in Dockerfile
- Database mounted as volume from host: `/mnt/workdisk/foundry:/root/.helix`

**Issues with Current Approach:**
1. API key database is on-disk in plaintext (local SQLite)
2. Mounted volume requires proper file permissions management
3. No encryption of database at rest
4. No audit logging of key access/usage
5. Key rotation requires manual database manipulation

**Recommended Solutions (Priority Order):**

### Short-term (Local/Dev)
- [ ] Wrap `foundry_keys.db` access with proper permissions (mode 0600)
- [ ] Add audit logging to `foundry_auth.py` for key validation attempts
- [ ] Document key generation procedure in runbook

### Medium-term (Infrastructure)
- [ ] Integrate with HashiCorp Vault for secret storage
- [ ] Implement key rotation workflow
- [ ] Add encryption at rest for database

### Long-term (Constitutional)
- [ ] Tie API key lifecycle to node identity (U(B) ∈ SU(8))
- [ ] Implement time-bound key tokens with drift detection
- [ ] Audit trail that feeds into constitutional compliance checks

**References:**
- `foundry_auth.py` — API key validation logic
- `foundry_keygen.py` — Key generation CLI
- `foundry_db.py` — Database path configuration (lines 16-18)
- Docker volume mount: `deploy/core-node/docker-compose.yml`

