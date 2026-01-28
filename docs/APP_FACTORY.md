# App Factory v2.0 - Deterministic Project Generator

App Factory is a template-based project generator that creates complete applications with **deterministic, reproducible output**. Same inputs always produce identical files (except timestamps).

## Key Guarantees

1. **Deterministic**: Same config hash = identical file content hashes
2. **Reproducible**: Config hash tracks exact input state for verification
3. **Verifiable**: ARTIFACTS.json tracks all files with SHA-256 hashes
4. **No LLM for Boilerplate**: All scaffolding uses Jinja2 templates
5. **LLM for Customization Only**: Targeted modifications (routes, features) can use LLM

---

## Quick Start

### Structured Input (Recommended)

```python
from app.skills.generators import AppFactoryConfig, generate_project
from pathlib import Path

# Define project using structured inputs
config = AppFactoryConfig.from_dict({
    "name": "my-saas-app",
    "workspace_path": Path.home() / "projects",
    "stacks": ["fastapi", "react"],
    "features": [
        "auth-jwt",
        "database-postgres",
        "docker",
        "tests",
        "ci-github",
        "tailwind"
    ],
    "description": "My SaaS application",
    "author": "Developer Name"
})

# Generate project
manifest = await generate_project(config)

print(f"Created: {manifest.project_path}")
print(f"Files: {manifest.total_files}")
print(f"Config hash: {manifest.config_hash[:16]}...")
```

### Individual Flags (Legacy)

```python
config = AppFactoryConfig(
    name="my-api",
    workspace_path=Path("/workspace"),
    backend_stack=BackendStack.FASTAPI,
    frontend_stack=FrontendStack.NONE,
    auth_mode=AuthMode.JWT,
    database=DatabaseType.POSTGRES,
    dockerize=True,
    include_tests=True
)
```

---

## Example Invocations

### 1. Full-Stack SaaS Application

```json
{
    "name": "saas-platform",
    "workspace_path": "~/maratos-workspace",
    "stacks": ["fastapi", "react"],
    "features": [
        "auth-jwt",
        "database-postgres",
        "docker",
        "tests",
        "ci-github",
        "tailwind",
        "react-router",
        "zustand"
    ]
}
```

**Output Paths:**
```
~/maratos-workspace/saas-platform/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── auth.py
│   │   └── api/
│   │       ├── __init__.py
│   │       └── health.py
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   └── test_health.py
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── main.tsx
│   │   ├── App.tsx
│   │   ├── index.css
│   │   ├── routes.tsx
│   │   ├── stores/
│   │   │   └── index.ts
│   │   └── components/
│   │       └── Layout.tsx
│   ├── package.json
│   ├── vite.config.ts
│   ├── tailwind.config.js
│   └── Dockerfile
├── docker-compose.yaml
├── .github/workflows/ci.yaml
├── Makefile
├── README.md
├── .gitignore
├── ARTIFACTS.json          # Artifact manifest
└── VALIDATION.md           # Validation report
```

### 2. Backend-Only API

```json
{
    "name": "api-service",
    "workspace_path": "~/maratos-workspace",
    "stacks": ["fastapi"],
    "features": [
        "database-sqlite",
        "tests",
        "docker"
    ]
}
```

**Output Paths:**
```
~/maratos-workspace/api-service/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   └── api/
│       ├── __init__.py
│       └── health.py
├── tests/
│   └── ...
├── pyproject.toml
├── Dockerfile
├── docker-compose.yaml
├── README.md
├── ARTIFACTS.json
└── VALIDATION.md
```

### 3. Minimal Prototype

```json
{
    "name": "prototype",
    "workspace_path": "~/maratos-workspace",
    "stacks": ["fastapi", "react"],
    "features": []
}
```

**Output:** Bare-bones FastAPI + React with no auth, SQLite, no CI.

---

## Output Files

### ARTIFACTS.json

Complete manifest of all generated files with content hashes:

```json
{
    "project_name": "my-app",
    "project_path": "/workspace/my-app",
    "config_hash": "a1b2c3d4e5f6...",
    "created_at": "2026-01-27T12:00:00",
    "generator_version": "1.0.0",
    "generation_time_ms": 1234.56,
    "summary": {
        "total_files": 25,
        "total_size_bytes": 45678,
        "total_commands": 2,
        "validations_passed": true,
        "failed_validations": 0
    },
    "files": [
        {
            "path": "backend/app/main.py",
            "size_bytes": 1234,
            "content_hash": "sha256:abc123...",
            "template_source": "fastapi/app/main.py.j2",
            "category": "generated"
        }
    ],
    "commands": [...],
    "validations": [...]
}
```

### VALIDATION.md

Human-readable validation report:

```markdown
# Validation Report: my-app

## Generation Metadata

| Property | Value |
|----------|-------|
| **Config Hash** | `a1b2c3d4e5f6...` |
| **Generated** | 2026-01-27T12:00:00 |
| **Generator Version** | 1.0.0 |

## Validation Gates

**Result:** 5 passed, 0 failed

| Gate | Status | Message |
|------|--------|---------|
| readme_exists | PASS | README.md exists |
| backend_lint | PASS | Linting passed |
| backend_imports | PASS | Imports successful |
| frontend_build | PASS | Build successful |

## Generated Artifacts

### Generated (25 files)

| File | Size | Content Hash |
|------|------|--------------|
| `backend/app/main.py` | 1.2KB | `abc123def4...` |
...
```

---

## Available Features

| Feature | Description |
|---------|-------------|
| `auth-jwt` | JWT-based authentication |
| `auth-session` | Session-based authentication |
| `auth-oauth` | OAuth2 authentication |
| `database-sqlite` | SQLite database |
| `database-postgres` | PostgreSQL database |
| `database-mysql` | MySQL database |
| `tests` | Include test suite |
| `docs` | Include documentation |
| `docker` | Docker + docker-compose |
| `ci-github` | GitHub Actions CI |
| `ci-gitlab` | GitLab CI |
| `makefile` | Makefile with common commands |
| `pre-commit` | Pre-commit hooks |
| `tailwind` | Tailwind CSS |
| `react-router` | React Router |
| `zustand` | Zustand state management |

---

## Available Stacks

| Backend | Frontend |
|---------|----------|
| `fastapi` | `react` |
| `express` (planned) | `vue` (planned) |

---

## Reproducibility Verification

To verify deterministic output:

```python
# Generate project twice with same config
config1 = AppFactoryConfig.from_dict({...})
config2 = AppFactoryConfig.from_dict({...})  # Same inputs

manifest1 = await generate_project(config1)
manifest2 = await generate_project(config2)

# Config hashes should match
assert manifest1.config_hash == manifest2.config_hash

# File content hashes should match
files1 = {f.path: f.content_hash for f in manifest1.files}
files2 = {f.path: f.content_hash for f in manifest2.files}
assert files1 == files2
```

---

## API Endpoint

```bash
# Execute via skill API
curl -X POST http://localhost:8000/api/skills/app-factory/execute \
  -H "Content-Type: application/json" \
  -d '{
    "context": {
      "name": "my-project",
      "workspace_path": "/workspace",
      "stacks": ["fastapi", "react"],
      "features": ["auth-jwt", "docker", "tests"]
    }
  }'
```

---

## LLM Integration

App Factory uses **templates for boilerplate** and reserves **LLM for targeted modifications**:

| Task | Method |
|------|--------|
| Project scaffolding | Templates (deterministic) |
| File structure | Templates (deterministic) |
| Base configurations | Templates (deterministic) |
| Custom business routes | LLM (via Kiro) |
| Feature-specific logic | LLM (via Kiro) |
| Refactoring existing code | LLM (via Kiro) |

This ensures:
- Consistent, reproducible baselines
- Fast generation (no LLM latency for scaffolding)
- Predictable output for CI/CD pipelines
- LLM creativity where it matters (custom features)

---

## Migration from "Project X"

If you previously used a project-specific generator, App Factory generalizes that approach:

```python
# Before (project-specific)
generate_project_x(name="my-x", features=[...])

# After (generic)
config = AppFactoryConfig.from_dict({
    "name": "my-x",
    "stacks": ["fastapi", "react"],
    "features": ["auth-jwt", "database-postgres", ...]
})
await generate_project(config)
```

Project X is now just one configuration of the generic App Factory.

---

*App Factory v2.0 - Generated projects are just instances of templates.*
