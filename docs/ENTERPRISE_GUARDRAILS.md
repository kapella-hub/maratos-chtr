# Enterprise Guardrails Configuration

This document describes the security guardrails available for enterprise deployments of MaratOS. All guardrails are designed with **safe defaults** - missing configuration results in secure, restrictive behavior.

## Quick Start

1. Copy `.env.example` to `.env`
2. Configure settings with `MARATOS_GUARDRAILS_` prefix
3. Restart MaratOS - invalid values fail fast with clear error messages

**Minimal secure configuration:**
```bash
# Enable strict mode for production
MARATOS_GUARDRAILS_STRICT_MODE=true
```

---

## Table of Contents

1. [Enterprise Mode Flags](#1-enterprise-mode-flags)
2. [Budget Limits](#2-budget-limits)
3. [Diff-First Mode](#3-diff-first-mode)
4. [Audit Retention](#4-audit-retention)
5. [Agent Tool Allowlists](#5-agent-tool-allowlists)
6. [Configuration Validation](#6-configuration-validation)
7. [Recommended Configurations](#7-recommended-configurations)
8. [Programmatic Access](#8-programmatic-access)

---

## 1. Enterprise Mode Flags

High-level security modes that override individual settings for maximum protection.

| Setting | Default | Description |
|---------|---------|-------------|
| `STRICT_MODE` | `false` | Minimum limits, no shell, workspace-only writes |
| `READONLY_MODE` | `false` | No writes or deletes allowed (approval required for everything) |
| `SANDBOX_MODE` | `false` | All agents write only to workspace |

### Strict Mode

When `MARATOS_GUARDRAILS_STRICT_MODE=true`:
- Tool loops limited to 3 per message
- Shell time limited to 30 seconds per command
- Total shell time limited to 2 minutes per session
- Spawn tasks limited to 3 per run
- Output size limited to 100KB
- All writes restricted to workspace directory

**Recommended for:** Production environments, untrusted user input

### Readonly Mode

When `MARATOS_GUARDRAILS_READONLY_MODE=true`:
- Diff-first mode automatically enabled
- All file modifications require explicit approval
- All shell commands require explicit approval
- Agents can only read and analyze code

**Recommended for:** Code review, security audits, demo environments

### Sandbox Mode

When `MARATOS_GUARDRAILS_SANDBOX_MODE=true`:
- All agents restricted to workspace-only writes
- Shell access removed from tool allowlists
- External paths require copy-to-workspace workflow

**Recommended for:** Multi-tenant environments, external contractors

---

## 2. Budget Limits

Prevent runaway agent loops and resource exhaustion.

### Tool Loop Limits

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `MAX_TOOL_LOOPS_PER_MESSAGE` | 6 | 1-20 | Iterations in tool loop per message |
| `MAX_TOOL_CALLS_PER_MESSAGE` | 20 | 1-100 | Total tool calls per message |
| `MAX_TOOL_CALLS_PER_SESSION` | 100 | 1-1000 | Total tool calls per session |

**Why this matters:** Without limits, an agent could enter an infinite loop calling tools repeatedly. The default of 6 loops allows complex multi-step tasks while preventing runaway behavior.

### Spawn Limits

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `MAX_SPAWNED_TASKS_PER_RUN` | 10 | 0-50 | Subagent spawns per orchestrator run |
| `MAX_NESTED_SPAWN_DEPTH` | 3 | 1-10 | Maximum depth of nested agent spawns |

**Why this matters:** The MO orchestrator can spawn subagents (coder, tester, etc.). Without limits, this could create an exponential explosion of parallel tasks.

### Shell Execution Limits

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `MAX_SHELL_TIME_SECONDS` | 120 | 1-600 | Max time per shell command |
| `MAX_SHELL_CALLS_PER_MESSAGE` | 10 | 0-50 | Max shell invocations per message |
| `MAX_TOTAL_SHELL_TIME_PER_SESSION` | 600 | 60-3600 | Total shell time per session (10 min) |

**Why this matters:** Shell commands are the most privileged operation. Limits prevent long-running commands or excessive shell usage from impacting system resources.

### Output Limits

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `MAX_OUTPUT_SIZE_BYTES` | 1MB | 10KB-10MB | Max output per tool call |

**Why this matters:** Large outputs can exhaust memory and slow down LLM context processing.

---

## 3. Diff-First Mode

Require explicit approval before executing high-impact actions.

### Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `DIFF_FIRST_ENABLED` | `false` | Enable diff-first mode globally |
| `DIFF_FIRST_REQUIRE_WRITES` | `true` | Show diff for file writes |
| `DIFF_FIRST_REQUIRE_DELETES` | `true` | Show diff for file deletes |
| `DIFF_FIRST_REQUIRE_SHELL` | `false` | Show command for shell execution |
| `DIFF_FIRST_TIMEOUT_SECONDS` | 300 | Timeout for approval (5 min) |
| `DIFF_FIRST_PROTECTED_PATTERNS` | `*.py,*.js,...` | File patterns requiring approval |

### Default Protected Patterns

```
*.py,*.js,*.ts,*.yaml,*.yml,*.json,Dockerfile*,*.sql
```

### How It Works

1. Agent proposes a file modification
2. System shows unified diff to user
3. User approves/rejects within timeout
4. If approved, modification is applied
5. If rejected or timeout, operation is blocked

### Example: Production Diff-First

```bash
MARATOS_GUARDRAILS_DIFF_FIRST_ENABLED=true
MARATOS_GUARDRAILS_DIFF_FIRST_REQUIRE_WRITES=true
MARATOS_GUARDRAILS_DIFF_FIRST_REQUIRE_DELETES=true
MARATOS_GUARDRAILS_DIFF_FIRST_REQUIRE_SHELL=true
MARATOS_GUARDRAILS_DIFF_FIRST_TIMEOUT_SECONDS=120
MARATOS_GUARDRAILS_DIFF_FIRST_PROTECTED_PATTERNS=*
```

---

## 4. Audit Retention

Control how long audit logs are stored and how large payloads are handled.

### Retention Periods

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `AUDIT_RETENTION_DAYS` | 90 | 1-365 | General audit logs |
| `AUDIT_TOOL_RETENTION_DAYS` | 60 | 1-365 | Tool execution logs |
| `AUDIT_LLM_RETENTION_DAYS` | 30 | 1-365 | LLM exchange logs (largest) |
| `AUDIT_FILE_RETENTION_DAYS` | 90 | 1-365 | File change logs |
| `AUDIT_BUDGET_RETENTION_DAYS` | 30 | 1-365 | Budget/usage logs |

**Storage considerations:** LLM exchange logs are typically the largest due to full prompt/response content. The shorter default (30 days) helps manage storage.

### Size Limits

| Setting | Default | Range | Description |
|---------|---------|-------|-------------|
| `AUDIT_MAX_DIFF_SIZE` | 50KB | 1KB-1MB | Max diff size before truncation |
| `AUDIT_MAX_ERROR_SIZE` | 10KB | 500B-100KB | Max error message size |
| `AUDIT_MAX_CONTENT_SIZE` | 5KB | 500B-100KB | Max redacted content size |
| `AUDIT_MAX_PARAMS_SIZE` | 10KB | 500B-100KB | Max params JSON size |

### Compression & Hashing

| Setting | Default | Description |
|---------|---------|-------------|
| `AUDIT_COMPRESS_DIFFS` | `true` | Enable gzip for large diffs |
| `AUDIT_COMPRESSION_THRESHOLD` | 1KB | Compress diffs larger than this |
| `AUDIT_HASH_ALGORITHM` | `sha256` | Hash algorithm (`sha256` or `sha512`) |
| `AUDIT_PRESERVE_HASH_ON_TRUNCATE` | `true` | Always preserve original hash |

**How compression works:**
1. Diffs larger than threshold are gzip compressed
2. Compressed content is base64 encoded with `GZIP:` prefix
3. Original hash is preserved for verification
4. Typical compression ratio: 91% size reduction

### Example: Compliance-Focused Retention

```bash
# Keep everything for 1 year
MARATOS_GUARDRAILS_AUDIT_RETENTION_DAYS=365
MARATOS_GUARDRAILS_AUDIT_TOOL_RETENTION_DAYS=365
MARATOS_GUARDRAILS_AUDIT_LLM_RETENTION_DAYS=365
MARATOS_GUARDRAILS_AUDIT_FILE_RETENTION_DAYS=365
MARATOS_GUARDRAILS_AUDIT_BUDGET_RETENTION_DAYS=365

# Larger size limits for complete audit trails
MARATOS_GUARDRAILS_AUDIT_MAX_DIFF_SIZE=1000000
MARATOS_GUARDRAILS_AUDIT_COMPRESS_DIFFS=true
```

---

## 5. Agent Tool Allowlists

Override default tool access for specific agents.

### Available Tools

| Tool | Description |
|------|-------------|
| `routing` | Agent routing and delegation |
| `filesystem` | File read/write/list operations |
| `shell` | Command execution |
| `web_search` | Web search queries |
| `web_fetch` | URL content fetching |
| `kiro` | Kiro-cli integration |
| `sessions` | Session management |
| `canvas` | Canvas/diagram generation |

### Default Allowlists

| Agent | Default Tools |
|-------|---------------|
| `mo` | `routing,filesystem,shell,web_search,web_fetch,kiro,sessions,canvas` |
| `architect` | `filesystem,shell,kiro` |
| `coder` | `filesystem,shell,kiro` |
| `reviewer` | `filesystem,shell,kiro` (read-only filesystem) |
| `tester` | `filesystem,shell,kiro` |
| `docs` | `filesystem,shell,kiro` |
| `devops` | `filesystem,shell,kiro` |

### Overriding Allowlists

```bash
# Restrict coder to filesystem only (no shell)
MARATOS_GUARDRAILS_CODER_ALLOWED_TOOLS=filesystem,kiro

# Give reviewer web access for documentation lookup
MARATOS_GUARDRAILS_REVIEWER_ALLOWED_TOOLS=filesystem,shell,kiro,web_search,web_fetch
```

**Note:** Empty value uses the default allowlist from `AGENT_POLICIES`.

---

## 6. Configuration Validation

All configuration values are validated at startup. Invalid values cause a fast failure with clear error messages.

### Validation Rules

1. **Range validation:** Numeric values must be within specified ranges
2. **Format validation:** Patterns must be valid (no empty patterns)
3. **Algorithm validation:** Hash algorithm must be `sha256` or `sha512`
4. **Consistency checks:** Compression threshold must not exceed max diff size

### Example Error Messages

```
ValidationError: audit_max_diff_size must be between 1000 and 1000000
ValidationError: audit_hash_algorithm must be one of: sha256, sha512
Warning: audit_compression_threshold (60000) > audit_max_diff_size (50000)
```

### Programmatic Validation

```python
from app.guardrails.config import validate_guardrails_config

errors = validate_guardrails_config()
if errors:
    for error in errors:
        print(f"Config error: {error}")
```

---

## 7. Recommended Configurations

### Development (Permissive)

```bash
# No special configuration needed - defaults are suitable for development
# All limits are generous, diff-first is disabled
```

### Staging (Moderate Security)

```bash
MARATOS_GUARDRAILS_DIFF_FIRST_ENABLED=true
MARATOS_GUARDRAILS_DIFF_FIRST_REQUIRE_SHELL=false
MARATOS_GUARDRAILS_MAX_SPAWNED_TASKS_PER_RUN=5
MARATOS_GUARDRAILS_SANDBOX_MODE=true
```

### Production (High Security)

```bash
MARATOS_GUARDRAILS_STRICT_MODE=true
MARATOS_GUARDRAILS_DIFF_FIRST_ENABLED=true
MARATOS_GUARDRAILS_DIFF_FIRST_REQUIRE_SHELL=true
MARATOS_GUARDRAILS_AUDIT_RETENTION_DAYS=365
MARATOS_GUARDRAILS_AUDIT_COMPRESS_DIFFS=true
```

### Code Review / Audit

```bash
MARATOS_GUARDRAILS_READONLY_MODE=true
MARATOS_GUARDRAILS_AUDIT_RETENTION_DAYS=365
```

### Multi-Tenant / External Contractors

```bash
MARATOS_GUARDRAILS_SANDBOX_MODE=true
MARATOS_GUARDRAILS_STRICT_MODE=true
MARATOS_GUARDRAILS_DIFF_FIRST_ENABLED=true
MARATOS_GUARDRAILS_MAX_SPAWNED_TASKS_PER_RUN=3
MARATOS_GUARDRAILS_MAX_SHELL_TIME_SECONDS=30
```

---

## 8. Programmatic Access

### Getting Current Configuration

```python
from app.guardrails.config import (
    get_guardrails_settings,
    get_budget_limits,
    get_diff_approval_config,
    get_audit_retention_config,
    get_agent_tool_allowlist,
    get_config_summary,
)

# Full settings object
settings = get_guardrails_settings()
print(f"Strict mode: {settings.strict_mode}")

# Computed budget limits (respects strict mode)
limits = get_budget_limits()
print(f"Max tool loops: {limits.max_tool_loops_per_message}")

# Diff approval config (respects readonly mode)
diff_config = get_diff_approval_config()
print(f"Diff-first enabled: {diff_config.enabled}")

# Audit retention config
audit_config = get_audit_retention_config()
print(f"Audit retention: {audit_config.default_retention_days} days")

# Agent tool allowlist (None = use default)
tools = get_agent_tool_allowlist("coder")
print(f"Coder tools: {tools}")

# Full summary for diagnostics
summary = get_config_summary()
print(f"Active modes: {summary['modes']}")
print(f"Validation errors: {summary['validation_errors']}")
```

### Resetting Configuration (Testing)

```python
from app.guardrails.config import reset_guardrails_settings

# Reset to reload from environment
reset_guardrails_settings()
```

### API Endpoint

```bash
# Get current guardrails configuration
curl http://localhost:8000/api/guardrails/config

# Response:
{
  "modes": {
    "strict_mode": false,
    "readonly_mode": false,
    "sandbox_mode": false,
    "diff_first_enabled": false
  },
  "budget_limits": {
    "max_tool_loops_per_message": 6,
    "max_tool_calls_per_session": 100,
    "max_spawned_tasks_per_run": 10,
    "max_shell_time_seconds": 120.0
  },
  "audit_retention": {
    "default_days": 90,
    "llm_days": 30,
    "max_diff_size": 50000,
    "compress_diffs": true
  },
  "validation_errors": []
}
```

---

## Security Notes

1. **No config = safe defaults.** If you don't configure guardrails, the system uses secure, restrictive defaults.

2. **Validation fails fast.** Invalid configuration values cause startup failure with clear error messages.

3. **Mode precedence:** `readonly_mode` > `strict_mode` > `sandbox_mode`. If multiple modes conflict, the more restrictive setting wins.

4. **Environment variables only.** Guardrails cannot be modified at runtime through the API - only through environment configuration.

5. **Audit hash preservation.** When content is truncated, the original hash is always preserved for forensic verification.

---

## Migration Guide

### From Pre-Guardrails Versions

1. Existing deployments continue to work with defaults
2. Copy `.env.example` to see all available options
3. Enable `STRICT_MODE` for immediate security hardening
4. Gradually tune individual settings as needed

### Configuration File Location

Primary: `.env` file in project root
Fallback: Environment variables (e.g., from Docker, Kubernetes)

---

*Last updated: 2026-01-27*
