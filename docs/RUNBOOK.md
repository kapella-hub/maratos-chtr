# MaratOS Operational Runbook

**Version:** 1.0
**Last Updated:** 2026-01-27

This runbook provides step-by-step procedures for operating MaratOS. An operator unfamiliar with the codebase should be able to install, configure, run, and troubleshoot the system using this guide.

---

## Table of Contents

1. [Quick Reference](#1-quick-reference)
2. [Installation](#2-installation)
3. [Configuration](#3-configuration)
4. [Start/Stop Procedures](#4-startstop-procedures)
5. [Upgrade Procedure](#5-upgrade-procedure)
6. [Backup and Restore](#6-backup-and-restore)
7. [Incident Triage](#7-incident-triage)
8. [Diff Approval Workflow](#8-diff-approval-workflow)
9. [Corp Mode (Air-Gapped/Restricted Networks)](#9-corp-mode-air-gappedrestricted-networks)
10. [Maintenance Tasks](#10-maintenance-tasks)

---

## 1. Quick Reference

### Key Paths

| Item | Path |
|------|------|
| Database | `./data/maratos.db` |
| Settings | `./data/settings.json` |
| Workspace | `~/maratos-workspace` |
| Backend logs | `/tmp/maratos-backend.log` |
| Frontend logs | `/tmp/maratos-frontend.log` |
| Skills directory | `~/.maratos/skills` |
| Config file | `.env` (project root) |

### Key Ports

| Service | Port |
|---------|------|
| Backend API | 8000 |
| Frontend | 5173 |

### Key Commands

```bash
# Start (development)
./restart.sh

# Start (Docker)
docker compose up -d

# Stop
pkill -f "uvicorn app.main:app"
pkill -f "vite"

# Check health
curl http://localhost:8000/api/health

# View logs
tail -f /tmp/maratos-backend.log
```

---

## 2. Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- kiro-cli (LLM provider)
- Git

### Step 1: Clone Repository

```bash
git clone <repository-url> maratos
cd maratos
```

### Step 2: Install Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -e .

# For development (includes pytest, ruff)
pip install -e ".[dev]"
```

### Step 3: Install Frontend

```bash
cd frontend
npm install
```

### Step 4: Verify kiro-cli

```bash
# kiro-cli must be installed and authenticated
kiro-cli --version
kiro-cli models  # Should list available models
```

### Step 5: Create Configuration

```bash
# Copy example configuration
cp .env.example .env

# Edit with your settings
vi .env
```

### Step 6: Initialize Database

```bash
cd backend
python -c "import asyncio; from app.database import init_db; asyncio.run(init_db())"
```

### Step 7: Verify Installation

```bash
# Start backend
cd backend && python run.py &

# Check health
curl http://localhost:8000/api/health
# Expected: {"status":"healthy","service":"maratos","version":"0.1.0"}
```

---

## 3. Configuration

### Environment Variables

Create a `.env` file in the project root:

```bash
# === REQUIRED ===
# (None - kiro-cli handles LLM authentication)

# === SERVER ===
MARATOS_HOST=0.0.0.0
MARATOS_PORT=8000
MARATOS_DEBUG=false

# === MODEL ===
MARATOS_DEFAULT_MODEL=claude-sonnet-4
MARATOS_THINKING_LEVEL=medium

# === PATHS ===
MARATOS_DATABASE_URL=sqlite+aiosqlite:///./data/maratos.db
MARATOS_DATA_DIR=./data
MARATOS_WORKSPACE_DIR=~/maratos-workspace
MARATOS_SKILLS_DIR=~/.maratos/skills

# === SECURITY (see Corp Mode section) ===
MARATOS_GUARDRAILS_STRICT_MODE=false
MARATOS_GUARDRAILS_SANDBOX_MODE=false
MARATOS_GUARDRAILS_READONLY_MODE=false

# === RATE LIMITING ===
MARATOS_RATE_LIMIT_ENABLED=true
MARATOS_RATE_LIMIT_CHAT=20/minute
MARATOS_RATE_LIMIT_DEFAULT=100/minute

# === TIMEOUTS ===
MARATOS_LLM_TIMEOUT=120
MARATOS_TOOL_TIMEOUT=60
MARATOS_HTTP_TIMEOUT=30
```

### Configuration Validation

```bash
# Check current configuration
curl http://localhost:8000/api/config

# Check guardrails configuration
curl http://localhost:8000/api/guardrails/config
```

### Persistence

Settings are persisted to `./data/settings.json`. This file is auto-created and updated when settings change via the API.

---

## 4. Start/Stop Procedures

### Development Mode

**Start:**
```bash
# Recommended: use restart script
./restart.sh

# Manual start (backend only)
cd backend
source .venv/bin/activate
python run.py

# Manual start (frontend)
cd frontend
npm run dev
```

**Stop:**
```bash
# Stop all processes
pkill -f "uvicorn app.main:app"
pkill -f "vite"

# Or use process IDs from log files
cat /tmp/maratos-backend.pid | xargs kill
```

### Docker Mode

**Start:**
```bash
docker compose up -d
```

**Stop:**
```bash
docker compose down
```

**Restart:**
```bash
docker compose restart
```

**View logs:**
```bash
docker compose logs -f
```

### Health Checks

```bash
# Backend health
curl -s http://localhost:8000/api/health | jq .

# Expected response:
{
  "status": "healthy",
  "service": "maratos",
  "version": "0.1.0"
}

# Frontend (should return HTML)
curl -s -o /dev/null -w "%{http_code}" http://localhost:5173/
# Expected: 200
```

### Graceful Shutdown

On shutdown, MaratOS:
1. Cancels running subagent tasks
2. Stops messaging channels (Telegram, Webex, etc.)
3. Flushes audit logs
4. Closes database connections

Allow 10-15 seconds for graceful shutdown before force-killing.

---

## 5. Upgrade Procedure

### Pre-Upgrade Checklist

- [ ] Backup database (see Section 6)
- [ ] Backup workspace directory
- [ ] Note current version: `curl http://localhost:8000/api/health`
- [ ] Review changelog for breaking changes
- [ ] Schedule maintenance window

### Upgrade Steps

```bash
# 1. Stop services
docker compose down
# or
pkill -f "uvicorn app.main:app"

# 2. Backup (critical!)
./scripts/backup.sh  # or manual backup

# 3. Pull new version
git fetch origin
git checkout v<new-version>
# or
git pull origin main

# 4. Update dependencies
cd backend
source .venv/bin/activate
pip install -e .

cd ../frontend
npm install

# 5. Run database migrations (automatic)
# Migrations run automatically on startup via init_db()
# Schema version is tracked in schema_version table

# 6. Start services
./restart.sh
# or
docker compose up -d

# 7. Verify
curl http://localhost:8000/api/health

# 8. Run smoke tests
curl http://localhost:8000/api/sessions
```

### Rollback Procedure

```bash
# 1. Stop services
docker compose down

# 2. Restore previous version
git checkout v<previous-version>

# 3. Restore database backup
cp ./data/maratos.db.backup ./data/maratos.db

# 4. Reinstall dependencies
cd backend && pip install -e .
cd ../frontend && npm install

# 5. Start services
./restart.sh
```

### Database Schema Versions

| Version | Description |
|---------|-------------|
| v1 | Original schema |
| v2 | Orchestration tables |
| v3 | Channel unification |
| v4 | Audit logging tables |
| v5 | Audit performance indexes (current) |

---

## 6. Backup and Restore

### What to Backup

| Item | Path | Priority |
|------|------|----------|
| Database | `./data/maratos.db` | CRITICAL |
| Settings | `./data/settings.json` | HIGH |
| Workspace | `~/maratos-workspace` | HIGH |
| User skills | `~/.maratos/skills` | MEDIUM |
| Environment | `.env` | MEDIUM |

### Manual Backup

```bash
# Create backup directory
BACKUP_DIR="./backups/$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_DIR"

# Backup database (while service is running - SQLite supports this)
cp ./data/maratos.db "$BACKUP_DIR/maratos.db"

# Backup settings
cp ./data/settings.json "$BACKUP_DIR/settings.json"

# Backup workspace (can be large)
tar -czf "$BACKUP_DIR/workspace.tar.gz" -C ~ maratos-workspace

# Backup user skills
tar -czf "$BACKUP_DIR/skills.tar.gz" -C ~ .maratos/skills

# Backup environment
cp .env "$BACKUP_DIR/.env"

# Create manifest
echo "Backup created: $(date)" > "$BACKUP_DIR/MANIFEST.txt"
echo "Database size: $(du -h ./data/maratos.db)" >> "$BACKUP_DIR/MANIFEST.txt"
```

### Automated Backup Script

Create `scripts/backup.sh`:

```bash
#!/bin/bash
set -e

BACKUP_ROOT="${BACKUP_ROOT:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_DIR="$BACKUP_ROOT/$TIMESTAMP"

echo "Creating backup in $BACKUP_DIR..."
mkdir -p "$BACKUP_DIR"

# Database
echo "Backing up database..."
cp ./data/maratos.db "$BACKUP_DIR/maratos.db"

# Settings
[ -f ./data/settings.json ] && cp ./data/settings.json "$BACKUP_DIR/"

# Workspace (optional, can be large)
if [ "${BACKUP_WORKSPACE:-true}" = "true" ]; then
    echo "Backing up workspace..."
    tar -czf "$BACKUP_DIR/workspace.tar.gz" -C ~ maratos-workspace 2>/dev/null || true
fi

# Cleanup old backups (keep last 7)
ls -dt "$BACKUP_ROOT"/*/ | tail -n +8 | xargs rm -rf 2>/dev/null || true

echo "Backup complete: $BACKUP_DIR"
```

### Restore Procedure

```bash
# 1. Stop services
docker compose down

# 2. Identify backup to restore
ls -la ./backups/

# 3. Restore database
cp ./backups/YYYYMMDD_HHMMSS/maratos.db ./data/maratos.db

# 4. Restore settings
cp ./backups/YYYYMMDD_HHMMSS/settings.json ./data/settings.json

# 5. Restore workspace (if needed)
tar -xzf ./backups/YYYYMMDD_HHMMSS/workspace.tar.gz -C ~

# 6. Start services
./restart.sh

# 7. Verify
curl http://localhost:8000/api/health
```

### Backup Schedule Recommendation

| Environment | Frequency | Retention |
|-------------|-----------|-----------|
| Production | Daily | 30 days |
| Staging | Weekly | 7 days |
| Development | On-demand | 3 days |

Crontab example:
```bash
# Daily backup at 2 AM
0 2 * * * cd /path/to/maratos && ./scripts/backup.sh >> /var/log/maratos-backup.log 2>&1
```

---

## 7. Incident Triage

### Log Locations

| Log | Location | Contents |
|-----|----------|----------|
| Backend | `/tmp/maratos-backend.log` | API requests, errors, agent activity |
| Frontend | `/tmp/maratos-frontend.log` | Build errors, dev server |
| Docker | `docker compose logs` | Combined container output |

### Log Formats

**Development Mode (colored console):**
```
2026-01-27 10:15:32 [INFO] app.api.chat: POST /api/chat 200 1523ms session=abc123
```

**Production Mode (JSON):**
```json
{"timestamp":"2026-01-27T10:15:32.123Z","level":"INFO","logger":"app.api.chat","message":"Request completed","method":"POST","path":"/api/chat","status_code":200,"duration_ms":1523,"session_id":"abc123"}
```

### Finding Audit Entries

Audit logs are stored in the database. Query them using SQLite:

```bash
# Connect to database
sqlite3 ./data/maratos.db

# Recent audit events
SELECT datetime(created_at), category, action, metadata
FROM audit_logs
ORDER BY created_at DESC
LIMIT 20;

# Tool executions in last hour
SELECT datetime(created_at), tool_name, result_status, duration_ms
FROM tool_audit_logs
WHERE created_at > datetime('now', '-1 hour')
ORDER BY created_at DESC;

# Security-relevant operations
SELECT datetime(created_at), tool_name, agent_id, metadata
FROM tool_audit_logs
WHERE security_relevant = 1
ORDER BY created_at DESC
LIMIT 50;

# Failed operations
SELECT datetime(created_at), tool_name, error_message
FROM tool_audit_logs
WHERE result_status = 'error'
ORDER BY created_at DESC;

# File changes by session
SELECT datetime(created_at), operation, file_path, content_hash
FROM file_change_logs
WHERE session_id = 'YOUR_SESSION_ID'
ORDER BY created_at;

# LLM token usage
SELECT datetime(created_at), model, input_tokens, output_tokens
FROM llm_exchange_logs
ORDER BY created_at DESC
LIMIT 20;
```

### Common Issues

#### Issue: Service won't start

**Symptoms:** Backend fails to start, port already in use

**Diagnosis:**
```bash
# Check if port is in use
lsof -i :8000

# Check for zombie processes
ps aux | grep uvicorn
ps aux | grep maratos
```

**Resolution:**
```bash
# Kill existing processes
pkill -f "uvicorn app.main:app"
pkill -9 -f "uvicorn"  # Force kill if needed

# Restart
./restart.sh
```

#### Issue: Database locked

**Symptoms:** `sqlite3.OperationalError: database is locked`

**Diagnosis:**
```bash
# Check for processes holding the database
fuser ./data/maratos.db
lsof ./data/maratos.db
```

**Resolution:**
```bash
# Stop all MaratOS processes
pkill -f "uvicorn app.main:app"

# Wait a few seconds
sleep 5

# Restart
./restart.sh
```

#### Issue: kiro-cli not responding

**Symptoms:** LLM requests timeout, chat not working

**Diagnosis:**
```bash
# Test kiro-cli directly
kiro-cli models
kiro-cli chat "Hello"
```

**Resolution:**
```bash
# Re-authenticate kiro-cli
kiro-cli auth login

# Restart services
./restart.sh
```

#### Issue: High memory usage

**Symptoms:** System slow, OOM errors

**Diagnosis:**
```bash
# Check memory usage
ps aux --sort=-%mem | head -10

# Check audit log size
sqlite3 ./data/maratos.db "SELECT name, SUM(pgsize) FROM dbstat GROUP BY name ORDER BY SUM(pgsize) DESC;"
```

**Resolution:**
```bash
# Purge old audit logs
python scripts/purge_audit.py --days 30

# Restart to free memory
./restart.sh
```

### Escalation Contacts

| Level | Contact | When |
|-------|---------|------|
| L1 | On-call operator | Service down, alerts firing |
| L2 | Platform team | Database issues, performance |
| L3 | Development team | Code bugs, security incidents |

---

## 8. Diff Approval Workflow

When `MARATOS_GUARDRAILS_DIFF_FIRST_ENABLED=true`, file modifications require explicit approval.

### How It Works

1. Agent proposes a file modification
2. System generates a unified diff
3. Operator reviews diff in UI or API response
4. Operator approves or rejects
5. If approved, modification is applied
6. If rejected or timeout (default 5 minutes), operation blocked

### Enabling Diff-First Mode

```bash
# In .env
MARATOS_GUARDRAILS_DIFF_FIRST_ENABLED=true
MARATOS_GUARDRAILS_DIFF_FIRST_REQUIRE_WRITES=true
MARATOS_GUARDRAILS_DIFF_FIRST_REQUIRE_DELETES=true
MARATOS_GUARDRAILS_DIFF_FIRST_REQUIRE_SHELL=true
MARATOS_GUARDRAILS_DIFF_FIRST_TIMEOUT_SECONDS=300
MARATOS_GUARDRAILS_DIFF_FIRST_PROTECTED_PATTERNS=*.py,*.js,*.ts,*.yaml,*.yml,*.json
```

### Reviewing Diffs Safely

1. **Check the file path** - Is this a file you expect to be modified?
2. **Review the diff context** - Do the surrounding lines look correct?
3. **Verify the change intent** - Does the change match what was requested?
4. **Check for sensitive data** - No credentials, secrets, or PII being written?
5. **Confirm workspace boundary** - Is the path within allowed directories?

### Approval API

```bash
# Pending approvals (if implemented)
curl http://localhost:8000/api/approvals/pending

# Approve a change
curl -X POST http://localhost:8000/api/approvals/{id}/approve

# Reject a change
curl -X POST http://localhost:8000/api/approvals/{id}/reject \
  -H "Content-Type: application/json" \
  -d '{"reason": "Unexpected file modification"}'
```

### Readonly Mode (Maximum Safety)

For code review or audit scenarios:

```bash
MARATOS_GUARDRAILS_READONLY_MODE=true
```

This automatically:
- Enables diff-first for ALL operations
- Requires approval for any write, delete, or shell command
- Protects ALL files (pattern: `*`)

---

## 9. Corp Mode (Air-Gapped/Restricted Networks)

### Overview

Corp Mode is for deployments where:
- No direct internet access
- Traffic must go through corporate proxies
- Only approved tools/operations are allowed
- Audit requirements are strict

### No Internet Configuration

If the deployment has no internet access:

```bash
# Disable external features
MARATOS_RATE_LIMIT_ENABLED=true  # Prevent runaway requests

# Ensure kiro-cli is configured for internal endpoints
# (kiro-cli configuration is separate - consult kiro-cli docs)
```

### Proxy Settings

MaratOS uses httpx for HTTP requests, which respects standard proxy environment variables:

```bash
# In .env or system environment
HTTP_PROXY=http://proxy.corp.example.com:8080
HTTPS_PROXY=http://proxy.corp.example.com:8080
NO_PROXY=localhost,127.0.0.1,.corp.example.com
```

For kiro-cli proxy configuration, refer to kiro-cli documentation.

### Tool Allowlists

Control which tools each agent can use:

```bash
# Restrict coder to filesystem only (no shell)
MARATOS_GUARDRAILS_CODER_ALLOWED_TOOLS=filesystem,kiro

# Restrict all agents in sandbox mode (no shell anywhere)
MARATOS_GUARDRAILS_SANDBOX_MODE=true

# Custom allowlists per agent
MARATOS_GUARDRAILS_ARCHITECT_ALLOWED_TOOLS=filesystem,kiro
MARATOS_GUARDRAILS_REVIEWER_ALLOWED_TOOLS=filesystem,kiro
MARATOS_GUARDRAILS_TESTER_ALLOWED_TOOLS=filesystem,kiro
MARATOS_GUARDRAILS_DOCS_ALLOWED_TOOLS=filesystem,kiro
MARATOS_GUARDRAILS_DEVOPS_ALLOWED_TOOLS=filesystem,kiro
MARATOS_GUARDRAILS_MO_ALLOWED_TOOLS=routing,filesystem,kiro,sessions
```

### Available Tools

| Tool | Description | Default Agents |
|------|-------------|----------------|
| `routing` | Agent delegation | MO only |
| `filesystem` | File read/write | All |
| `shell` | Command execution | All (disable in sandbox) |
| `web_search` | Web search | MO only |
| `web_fetch` | URL fetching | MO only |
| `kiro` | Kiro-cli integration | All |
| `sessions` | Session management | MO only |
| `canvas` | Diagram generation | MO only |

### Where to Change Allowlists

1. **Environment variables** (recommended for deployment):
   ```bash
   # In .env
   MARATOS_GUARDRAILS_CODER_ALLOWED_TOOLS=filesystem,kiro
   ```

2. **Guardrails config file** (for complex policies):
   ```python
   # backend/app/guardrails/config.py
   # Modify AGENT_POLICIES dictionary
   ```

3. **API endpoint** (runtime, if implemented):
   ```bash
   curl -X PUT http://localhost:8000/api/guardrails/agent/coder/tools \
     -H "Content-Type: application/json" \
     -d '["filesystem", "kiro"]'
   ```

### Recommended Corp Mode Configuration

```bash
# === SECURITY ===
MARATOS_GUARDRAILS_STRICT_MODE=true
MARATOS_GUARDRAILS_SANDBOX_MODE=true
MARATOS_GUARDRAILS_DIFF_FIRST_ENABLED=true
MARATOS_GUARDRAILS_DIFF_FIRST_REQUIRE_SHELL=true

# === BUDGET LIMITS ===
MARATOS_GUARDRAILS_MAX_TOOL_LOOPS_PER_MESSAGE=3
MARATOS_GUARDRAILS_MAX_TOOL_CALLS_PER_SESSION=50
MARATOS_GUARDRAILS_MAX_SHELL_TIME_SECONDS=30
MARATOS_GUARDRAILS_MAX_SPAWNED_TASKS_PER_RUN=3

# === AUDIT ===
MARATOS_GUARDRAILS_AUDIT_RETENTION_DAYS=365
MARATOS_GUARDRAILS_AUDIT_COMPRESS_DIFFS=true

# === TOOL RESTRICTIONS ===
MARATOS_GUARDRAILS_CODER_ALLOWED_TOOLS=filesystem,kiro
MARATOS_GUARDRAILS_ARCHITECT_ALLOWED_TOOLS=filesystem,kiro
MARATOS_GUARDRAILS_REVIEWER_ALLOWED_TOOLS=filesystem,kiro
MARATOS_GUARDRAILS_TESTER_ALLOWED_TOOLS=filesystem,kiro

# === NETWORK ===
HTTP_PROXY=http://proxy.corp.example.com:8080
HTTPS_PROXY=http://proxy.corp.example.com:8080
NO_PROXY=localhost,127.0.0.1
```

### Verifying Corp Mode

```bash
# Check guardrails configuration
curl http://localhost:8000/api/guardrails/config | jq .

# Expected output for corp mode:
{
  "modes": {
    "strict_mode": true,
    "readonly_mode": false,
    "sandbox_mode": true,
    "diff_first_enabled": true
  },
  "budget_limits": {
    "max_tool_loops_per_message": 3,
    "max_tool_calls_per_session": 50,
    "max_shell_time_seconds": 30
  },
  ...
}
```

---

## 10. Maintenance Tasks

### Daily

- [ ] Check health endpoint
- [ ] Review error logs
- [ ] Verify backup completed

### Weekly

- [ ] Review audit logs for anomalies
- [ ] Check disk space
- [ ] Review security-relevant operations

### Monthly

- [ ] Purge old audit logs
- [ ] Review and rotate credentials
- [ ] Test backup restoration
- [ ] Review guardrails configuration

### Audit Log Purge

```bash
# Dry run - see what would be deleted
python scripts/purge_audit.py --dry-run --days 90

# Actual purge
python scripts/purge_audit.py --days 90

# Cron-friendly (quiet, exit code only)
python scripts/purge_audit.py --cron --days 90

# Check stats
python scripts/purge_audit.py --stats
```

### Database Maintenance

```bash
# Check database size
du -h ./data/maratos.db

# Vacuum database (reclaim space)
sqlite3 ./data/maratos.db "VACUUM;"

# Analyze for query optimization
sqlite3 ./data/maratos.db "ANALYZE;"

# Check integrity
sqlite3 ./data/maratos.db "PRAGMA integrity_check;"
```

### Monitoring Queries

```bash
# Active sessions in last 24h
sqlite3 ./data/maratos.db "SELECT COUNT(*) FROM sessions WHERE updated_at > datetime('now', '-1 day');"

# Messages today
sqlite3 ./data/maratos.db "SELECT COUNT(*) FROM messages WHERE created_at > datetime('now', '-1 day');"

# Tool calls by type
sqlite3 ./data/maratos.db "SELECT tool_name, COUNT(*) FROM tool_audit_logs GROUP BY tool_name ORDER BY COUNT(*) DESC;"

# Error rate
sqlite3 ./data/maratos.db "SELECT
  ROUND(100.0 * SUM(CASE WHEN result_status = 'error' THEN 1 ELSE 0 END) / COUNT(*), 2) as error_pct
FROM tool_audit_logs
WHERE created_at > datetime('now', '-1 day');"
```

---

## Appendix A: Environment Variable Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `MARATOS_HOST` | 0.0.0.0 | Server bind address |
| `MARATOS_PORT` | 8000 | Server port |
| `MARATOS_DEBUG` | false | Debug mode |
| `MARATOS_DEFAULT_MODEL` | claude-sonnet-4 | Default LLM model |
| `MARATOS_THINKING_LEVEL` | medium | Thinking depth |
| `MARATOS_DATABASE_URL` | sqlite+aiosqlite:///./data/maratos.db | Database URL |
| `MARATOS_WORKSPACE_DIR` | ~/maratos-workspace | Workspace path |
| `MARATOS_LLM_TIMEOUT` | 120 | LLM request timeout (seconds) |
| `MARATOS_TOOL_TIMEOUT` | 60 | Tool execution timeout |
| `MARATOS_GUARDRAILS_STRICT_MODE` | false | Enable strict limits |
| `MARATOS_GUARDRAILS_SANDBOX_MODE` | false | Disable shell access |
| `MARATOS_GUARDRAILS_READONLY_MODE` | false | Require approval for everything |
| `MARATOS_GUARDRAILS_DIFF_FIRST_ENABLED` | false | Require diff approval |
| `HTTP_PROXY` | (none) | HTTP proxy URL |
| `HTTPS_PROXY` | (none) | HTTPS proxy URL |

---

## Appendix B: API Quick Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/health` | GET | Health check |
| `/api/config` | GET | Current configuration |
| `/api/guardrails/config` | GET | Security configuration |
| `/api/sessions` | GET | List sessions |
| `/api/chat` | POST | Send chat message |
| `/api/skills` | GET | List available skills |

---

*Last updated: 2026-01-27*
