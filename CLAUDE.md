# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

MaratOS is a self-hostable AI platform with a web interface and multi-channel messaging support. The primary agent is **MO** — an opinionated AI partner that orchestrates specialized subagents for coding tasks.

## Development Commands

### Backend (Python)
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e .                    # Install dependencies
pip install -e ".[dev]"             # Include dev tools (pytest, ruff)
pip install -e ".[embeddings]"      # Optional: semantic memory search
python run.py                       # Start server on port 8000
```

### Frontend (React)
```bash
cd frontend
npm install
npm run dev      # Start dev server on port 5173
npm run build    # Production build
npm run lint     # ESLint check
```

### Running Tests
```bash
cd backend
pytest                              # Run all tests
pytest tests/test_agents.py         # Single test file
pytest -k "test_mo"                 # Run tests matching pattern
```

### Docker
```bash
docker-compose up -d                # Start all services
docker build -t maratos .           # Build image manually
```

## Architecture

### Backend Structure (`backend/app/`)

**Agents** (`agents/`): Each agent extends `base.Agent` with a system prompt and tool access.
- `mo.py` — Primary orchestrator; delegates to specialized agents via `[SPAWN:agent]` markers
- `architect.py`, `coder.py`, `reviewer.py`, `tester.py`, `docs.py`, `devops.py` — Specialized agents
- `registry.py` — Agent registration and lookup

**Auto-Orchestration**: MO emits `[SPAWN:agent_id] task description` markers in responses. The chat API (`api/chat.py`) parses these with `SPAWN_PATTERN` regex and spawns subagent tasks that run in parallel.

**Subagents** (`subagents/`):
- `manager.py` — Task spawning, tracking, and status management (`SubagentTask`, `TaskStatus`)
- `runner.py` — Executes agent tasks with memory context, reports progress via SSE

**Tools** (`tools/`):
- `filesystem.py` — Sandboxed: read anywhere, write only to `~/maratos-workspace`
- `shell.py` — Command execution
- `web.py` — Web search and fetch
- `kiro.py` — Enterprise AI integration with quality-focused prompts (architect/validate/test/prompt actions)

**Memory** (`memory/`): Infinite memory with semantic search
- `manager.py` — Context retrieval, auto-extraction from conversations
- `store.py` — SQLite persistence, optional embeddings for similarity search

**Channels** (`channels/`): Multi-channel messaging adapters
- `telegram.py`, `imessage.py`, `webex.py` — Platform integrations
- `manager.py` — Channel lifecycle management

**Skills** (`skills/`): Reusable YAML workflows in `~/.maratos/skills/`

**Autonomous** (`autonomous/`): Self-driving development team
- `models.py` — Data models: `ProjectPlan`, `ProjectTask`, `QualityGate`, `TaskIteration`
- `orchestrator.py` — Main execution engine with planning, feedback loops, quality gates
- `project_manager.py` — Registry for tracking active autonomous projects
- `git_ops.py` — Async git operations (commit, push, PR creation)
- See `docs/AUTONOMOUS.md` for full documentation

### Frontend Structure (`frontend/src/`)

- **State**: Zustand stores in `stores/` - `chat.ts` for chat, `autonomous.ts` for autonomous mode
- **SSE Handling**: `lib/api.ts` parses Server-Sent Events from `/api/chat` and `/api/autonomous/start`
- **Chat Events**: `session_id`, `thinking`, `content`, `orchestrating`, `subagent`, `subagent_result`, `[DONE]`
- **Autonomous Events**: `project_started`, `task_created`, `task_started`, `quality_gate_*`, `git_commit`, `project_completed`
- **Autonomous Components**: `AutonomousProgress`, `TaskCard`, `EventLog` in `components/autonomous/`

### API Flow

**Chat API:**
1. `POST /api/chat` with `{message, session_id?, agent_id?}`
2. Backend streams SSE: thinking indicator → content chunks → subagent spawns/progress → `[DONE]`
3. Frontend updates state per event type, displays progress bars for active subagents

**Autonomous API:**
1. `POST /api/autonomous/start` with `{name, prompt, config...}`
2. Backend streams SSE: project events → task events → quality gate events → git events → `[DONE]`
3. Control endpoints: `/pause`, `/resume`, `/cancel`, `/tasks/{id}/retry`
4. Frontend displays real-time progress, task cards, event log

## Key Patterns

### Filesystem Security Model
- READ/LIST: Allowed anywhere
- WRITE/DELETE: Only in workspace (`~/maratos-workspace`)
- COPY: Brings external files into workspace for modification

**All agents enforce mandatory copy-to-workspace workflow:**
1. Copy project to workspace first: `filesystem action=copy path=/source dest=project_name`
2. Read/analyze code in workspace
3. Make modifications only in workspace
4. Report workspace paths to user

### Agent Delegation
MO must delegate coding tasks. Format: `[SPAWN:coder] Implement X`
Valid agents: `architect`, `reviewer`, `coder`, `tester`, `docs`, `devops`, `mo`

### Kiro Integration
For coding tasks, use Kiro CLI actions:
- `kiro architect task="..." workdir="..."` — Design + implement
- `kiro validate files="..." workdir="..."` — Code review
- `kiro test files="..." workdir="..."` — Generate tests
- `kiro prompt task="..."` — Direct prompt with quality guidelines

## Configuration

Environment variables prefixed with `MARATOS_`:
- `MARATOS_ANTHROPIC_API_KEY` — Required
- `MARATOS_DEFAULT_MODEL` — Default: `claude-sonnet-4-20250514`
- `MARATOS_TELEGRAM_ENABLED/TOKEN`, `MARATOS_IMESSAGE_ENABLED`, `MARATOS_WEBEX_ENABLED/TOKEN`

## Tech Stack

- **Backend**: FastAPI, SQLAlchemy (async), SQLite, LiteLLM, Pydantic
- **Frontend**: React 18, Vite, Zustand, TailwindCSS, React Query
- **Python**: 3.11+, ruff for linting
- **Node**: 18+