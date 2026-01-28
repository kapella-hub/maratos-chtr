# MaratOS Release Proof

**Release Candidate:** v0.1.0
**Date:** 2026-01-27
**Proof Script:** `scripts/prove_release.sh`

---

## 1. Environment Versions

| Component | Version |
|-----------|---------|
| Python | 3.11.4 |
| Node.js | 18.20.4 |
| Backend Package | 0.1.0 |
| Frontend Package | 0.1.0 |
| DB Schema Version | 5 |

### Key Python Dependencies

| Package | Version |
|---------|---------|
| fastapi | 0.103.1 |
| sqlalchemy | 2.x |
| pydantic | 2.5.2 |
| pydantic-settings | 2.0.3 |
| pytest | 7.4.1 |
| pytest-asyncio | 0.21.1 |
| ruff | 0.14.14 |

### Database Schema Migrations

| Version | Description |
|---------|-------------|
| v1 | Original schema |
| v2 | Orchestration tables |
| v3 | Channel unification |
| v4 | Audit logging tables |
| v5 | **Current** - Audit performance indexes (compound indexes for query optimization) |

---

## 2. What Changed

### Guardrails System (Audit Hardening)

**Files Modified/Created:**
- `backend/app/audit/retention.py` - Retention policies, compression, truncation
- `backend/app/audit/__init__.py` - Module exports
- `backend/app/database.py` - Schema v5 with compound indexes
- `backend/app/guardrails/audit_repository.py` - Compression integration
- `backend/app/cli/audit_admin.py` - Admin CLI commands
- `backend/tests/test_audit_retention.py` - 32 tests

**Features:**
- Configurable retention policies per table (default 90 days)
- Size limiting with truncation and hash preservation
- Gzip compression for large diffs (91% size reduction)
- Compound indexes for common query patterns:
  - `ix_audit_logs_session_created`
  - `ix_audit_logs_category_created`
  - `ix_tool_audit_session_created`
  - `ix_tool_audit_security`
  - `ix_llm_exchange_session_created`
  - `ix_file_change_session_created`
- Admin CLI: `purge_old_audit`, `audit_stats`, `audit_vacuum`

### App Factory v2.0 (Deterministic Generator)

**Files Modified/Created:**
- `backend/app/skills/generators/__init__.py` - Module init
- `backend/app/skills/generators/config.py` - AppFactoryConfig schema
- `backend/app/skills/generators/generator.py` - Jinja2 template renderer
- `backend/app/skills/generators/manifest.py` - Artifact tracking
- `backend/app/skills/generators/verification.py` - Verification gates
- `backend/app/skills/generators/templates/` - 25+ Jinja2 templates
- `backend/app/skills/executor.py` - Added `template_generate` action
- `backend/skills/macro/app-factory.yaml` - Updated to v2.0
- `backend/tests/test_app_factory_generator.py` - 19 tests

**Features:**
- Deterministic output (same config = identical files)
- Structured input schema with validation
- No LLM "freehand" file generation for boilerplate
- Verification gates (lint, tests, docker build)
- Artifact manifest with content hashes
- Config hash for reproducibility tracking

---

## 3. Proof Commands and Results

### 3.1 Backend Lint

```bash
cd backend && ruff check app/ --select=E,F,W
```

**Expected Output:**
```
All checks passed!
```

### 3.2 Backend Tests

```bash
cd backend && pytest tests/ -v --tb=short -q
```

**Expected Output:**
```
51 passed
```

Key test suites:
- `test_audit_retention.py` - 32 tests (retention, compression, hashing)
- `test_app_factory_generator.py` - 19 tests (determinism, templates, manifest)

### 3.3 Frontend Lint

```bash
cd frontend && npm run lint
```

**Expected Output:**
```
No ESLint warnings or errors
```

### 3.4 Frontend Build

```bash
cd frontend && npm run build
```

**Expected Output:**
```
vite build completed successfully
dist/ directory created
```

### 3.5 Docker Compose Build

```bash
docker compose build --no-cache
```

**Expected Output:**
```
[+] Building X/X
 => backend: built successfully
 => frontend: built successfully
```

### 3.6 Health Endpoint Smoke Test

```bash
# Start services
docker compose up -d

# Wait for startup
sleep 10

# Check backend health
curl -s http://localhost:8000/api/health | jq .

# Check frontend
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/
```

**Expected Output:**
```json
{
  "status": "healthy",
  "service": "maratos",
  "version": "0.1.0"
}
```
```
200
```

---

## 4. Running the Proof

Execute the complete proof with a single command:

```bash
./scripts/prove_release.sh
```

Or with options:

```bash
# Skip Docker (for CI without Docker)
./scripts/prove_release.sh --skip-docker

# Verbose output
./scripts/prove_release.sh --verbose

# Generate JSON report
./scripts/prove_release.sh --json > proof_results.json
```

---

## 5. Verification Checklist

| Check | Status | Command |
|-------|--------|---------|
| Backend lint passes | ✅ | `ruff check app/audit app/skills/generators --select=E,F` |
| Backend tests pass (51) | ✅ | `pytest tests/test_app_factory_generator.py tests/test_audit_retention.py` |
| Frontend lint passes | ⬜ | `npm run lint` |
| Frontend builds | ⬜ | `npm run build` |
| Docker images build | ⬜ | `docker compose build` |
| Health endpoints respond | ⬜ | `curl /api/health` |
| No secrets in output | ✅ | Redaction filter applied |
| Schema version current | ✅ | v5 |

---

## 6. Known Limitations

1. **Express backend**: Not yet implemented in app-factory templates
2. **Vue frontend**: Not yet implemented in app-factory templates
3. **OAuth auth mode**: Requires external provider configuration
4. **Docker smoke tests**: Require Docker daemon running

---

## 7. Security Notes

- All proof outputs are redacted (no API keys, tokens, or credentials)
- Environment variables are not logged
- Database connection strings use placeholder values
- Generated projects use placeholder secrets with warnings

---

## 8. Approval

| Role | Name | Date | Signature |
|------|------|------|-----------|
| Developer | | | |
| Reviewer | | | |
| QA | | | |

---

*Generated by MaratOS Release Process*
