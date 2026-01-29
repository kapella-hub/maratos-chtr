claude # 🖥️ MaratOS

Your personal AI operating system, powered by **MO** — a capable, opinionated AI partner.

![Version](https://img.shields.io/badge/version-0.1.0-violet)
![Agent](https://img.shields.io/badge/agent-MO-purple)

## Quick Install

### macOS / Linux

```bash
curl -fsSL https://cdn.jsdelivr.net/gh/kapella-hub/maratos@main/install.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://cdn.jsdelivr.net/gh/kapella-hub/maratos@main/install.ps1 | iex
```

> **Note:** If you get a cached version, purge first:
> ```bash
> curl -X PURGE https://purge.jsdelivr.net/gh/kapella-hub/maratos@main/install.sh
> ```

**No API key?** Install [Kiro CLI](https://kiro.dev/cli/) — MaratOS will use it automatically for Claude models via AWS.

### Kiro CLI Setup (No API Key Needed)

If you have Kiro CLI installed and authenticated, MaratOS automatically uses it for Claude models:

```bash
# Install Kiro CLI
curl -fsSL https://cli.kiro.dev/install | bash

# Authenticate with AWS
~/.local/bin/kiro-cli login

# Now install MaratOS - it will detect Kiro CLI
curl -fsSL https://cdn.jsdelivr.net/gh/kapella-hub/maratos@main/install.sh | bash
```

Available Kiro models:
- **claude-sonnet-4** — Balanced reasoning and coding (1.3x credits)
- **claude-opus-4.5** — Maximum capability (2.2x credits)
- **claude-haiku-4.5** — Fast responses (0.4x credits)

Then run:

```bash
# macOS/Linux
maratos

# Windows - double-click "MaratOS" on Desktop
```

Open **http://localhost:5173** and start chatting with MO!

---

## What is MaratOS?

MaratOS is a self-hostable AI platform with a beautiful web interface and multi-channel messaging support. At its core is **MO** — an AI that's genuinely helpful without the corporate fluff.

### MO's Personality

- **Skips the fluff** — No "Great question!" or "I'd be happy to help!"
- **Has opinions** — Disagrees when warranted
- **Is resourceful** — Figures things out before asking
- **Earns trust** — Through competence, not compliance

### Features

- 🤖 **MO Agent** — Capable AI with real personality
- 🏗️ **Multi-Agent** — MO, Architect, Reviewer (Kiro-powered)
- 🎨 **Beautiful UI** — Modern dark-mode web interface
- 💭 **Thinking Indicator** — See when MO is processing
- 🔄 **Auto-Orchestration** — MO spawns subagents for complex tasks
- 💬 **Multi-Channel** — Web, Telegram, iMessage, Webex
- 🔧 **Kiro Integration** — Enterprise AI for quality coding
- 🧩 **Skills System** — Reusable Kiro workflows
- ⚖️ **Development Rules** — Reusable standards applied per-chat
- 🚀 **Subagents** — Background task execution with progress
- 🧠 **Infinite Memory** — Semantic search, auto-compaction
- 🔒 **Sandboxed Writes** — Read anywhere, write to workspace
- ⚙️ **Easy Config** — Visual settings

---

## Messaging Channels

MO can be reached via multiple channels:

| Channel | Platform | How it works |
|---------|----------|--------------|
| 🌐 **Web UI** | Any browser | Built-in at localhost:5173 |
| 📱 **Telegram** | Mobile/Desktop | Bot API with long-polling |
| 💬 **iMessage** | macOS only | AppleScript integration |
| 🏢 **Webex** | Enterprise | Webhook-based bot |

### Telegram Setup

1. Message [@BotFather](https://t.me/botfather) on Telegram
2. Create a new bot with `/newbot`
3. Copy the token
4. Get your user ID from [@userinfobot](https://t.me/userinfobot)
5. Add to `.env`:

```bash
MARATOS_TELEGRAM_ENABLED=true
MARATOS_TELEGRAM_TOKEN=123456789:ABCdefGHIjklMNOpqrsTUVwxyz
MARATOS_TELEGRAM_ALLOWED_USERS=your_user_id  # Optional: comma-separated
```

6. Restart MaratOS and message your bot!

### iMessage Setup (macOS only)

1. Enable in `.env`:

```bash
MARATOS_IMESSAGE_ENABLED=true
MARATOS_IMESSAGE_ALLOWED_SENDERS=+13038812044,email@example.com  # Optional
```

2. Grant Terminal/iTerm accessibility permissions in System Preferences
3. Restart MaratOS

MO will respond to iMessages from allowed senders.

### Webex Setup

1. Go to [developer.webex.com/my-apps](https://developer.webex.com/my-apps)
2. Click "Create a New App" → "Create a Bot"
3. Fill in details and create
4. Copy the **Bot Access Token**
5. Add to `.env`:

```bash
MARATOS_WEBEX_ENABLED=true
MARATOS_WEBEX_TOKEN=your_bot_access_token
MARATOS_WEBEX_WEBHOOK_SECRET=optional_secret_for_security
MARATOS_WEBEX_ALLOWED_ROOMS=room_id_1,room_id_2  # Optional
```

6. Start MaratOS

7. Create the webhook (replace with your public URL):

```bash
curl -X POST http://localhost:8000/api/channels/webex/setup \
  -H "Content-Type: application/json" \
  -d '{"target_url": "https://your-domain.com/api/channels/webex/webhook"}'
```

> **Note:** Webex requires a publicly accessible URL for webhooks. Use ngrok for testing:
> ```bash
> ngrok http 8000
> ```

8. Add the bot to Webex rooms — it will respond to messages!

### Channel API

| Endpoint | Description |
|----------|-------------|
| `GET /api/channels` | List all channels with status |
| `GET /api/channels/{name}` | Get specific channel status |
| `POST /api/channels/{name}/start` | Start a channel |
| `POST /api/channels/{name}/stop` | Stop a channel |
| `POST /api/channels/webex/webhook` | Webex webhook receiver |
| `POST /api/channels/webex/setup` | Create Webex webhook |

---

## Manual Installation

### Prerequisites

- Python 3.11+
- Node.js 18+
- Anthropic API key

### Steps

```bash
# Clone
git clone https://github.com/kapella-hub/maratos.git
cd maratos

# Backend
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
cd ..

# Frontend
cd frontend
npm install
cd ..

# Configure
cp .env.example .env
nano .env  # Add your API keys

# Run (two terminals)
cd backend && source .venv/bin/activate && python run.py
cd frontend && npm run dev
```

Open http://localhost:5173

---

## Configuration

All settings via environment variables (prefix `MARATOS_`):

```bash
# === Core ===
MARATOS_ANTHROPIC_API_KEY=sk-ant-...    # Required
MARATOS_OPENAI_API_KEY=sk-...           # Optional
MARATOS_DEFAULT_MODEL=claude-sonnet-4-20250514
MARATOS_DEBUG=false
MARATOS_PORT=8000

# === Telegram ===
MARATOS_TELEGRAM_ENABLED=false
MARATOS_TELEGRAM_TOKEN=
MARATOS_TELEGRAM_ALLOWED_USERS=         # Comma-separated user IDs

# === iMessage (macOS only) ===
MARATOS_IMESSAGE_ENABLED=false
MARATOS_IMESSAGE_ALLOWED_SENDERS=       # Comma-separated phones/emails

# === Webex ===
MARATOS_WEBEX_ENABLED=false
MARATOS_WEBEX_TOKEN=
MARATOS_WEBEX_WEBHOOK_SECRET=
MARATOS_WEBEX_ALLOWED_USERS=            # Comma-separated user IDs
MARATOS_WEBEX_ALLOWED_ROOMS=            # Comma-separated room IDs
```

---

## Security Model

MO uses a sandboxed filesystem:

| Action | Scope | Description |
|--------|-------|-------------|
| `read` | Anywhere | Read any file |
| `list` | Anywhere | List any directory |
| `copy` | → Workspace | Copy files into workspace |
| `write` | Workspace only | Modify files |
| `delete` | Workspace only | Remove files |

**Workspace:** `~/maratos-workspace`

When you ask MO to modify external code, it copies the files to workspace first, keeping your original code safe.

---

## Agents + Kiro Integration

MaratOS uses **Kiro AI** (your company's approved AI) for all coding tasks. Agents orchestrate Kiro with quality-focused workflows:

| Agent | Role | Kiro Usage |
|-------|------|------------|
| 🤖 **MO** | General partner | Orchestrates other agents, uses Kiro for coding |
| 🏗️ **Architect** | System design | `kiro architect` with detailed specs |
| 🔍 **Reviewer** | Code review | `kiro validate` with full checklist |
| 💻 **Coder** | Implementation | `kiro prompt` for clean, focused code |
| 🧪 **Tester** | Test generation | `kiro test` with edge cases |
| 📝 **Docs** | Documentation | `kiro prompt` for technical writing |
| 🚀 **DevOps** | Infrastructure | `kiro prompt` for IaC and CI/CD |

### Kiro Actions (Quality-Tuned)

```bash
# Architecture-first implementation
kiro architect task="implement rate limiter" workdir="/project"

# Thorough code review
kiro validate files="src/auth.py" workdir="/project"

# Comprehensive test generation  
kiro test files="src/api.py" workdir="/project"

# Direct prompt (still quality-focused)
kiro prompt task="explain this function"
```

### Quality Workflow

1. **Understand** — MO reads existing code
2. **Copy to workspace** — Sandbox for modifications
3. **Architect** — Kiro designs and implements with quality focus
4. **Validate** — Kiro reviews for security, performance, correctness
5. **Test** — Kiro generates comprehensive tests
6. **Report** — Summary for user review

Select agent in UI or API:
```bash
curl -X POST /api/chat -d '{"message": "...", "agent_id": "architect"}'
```

---

## Skills System

Skills are reusable workflows that orchestrate Kiro for complex tasks:

```yaml
# skills/api-endpoint.yaml
id: api-endpoint
name: Create API Endpoint
triggers: ["create api", "new endpoint"]
workflow:
  - name: analyze
    action: kiro_prompt
  - name: implement
    action: kiro_architect
  - name: validate
    action: kiro_validate
  - name: test
    action: kiro_test
```

**Built-in skills:**
- `api-endpoint` — Create production-ready API endpoints
- `refactor` — Safe refactoring with validation
- `security-review` — Comprehensive security audit

**Add custom skills:** Drop YAML files in `~/.maratos/skills/`

---

## Development Rules

Rules are reusable development standards that can be selected at chat time and injected into the prompt to guide MO's behavior.

### How It Works

1. **Create rules** in Settings → Development Rules
2. **Select rules** from the ⚖️ dropdown in the chat input (multi-select)
3. **Rules are injected** into the system prompt for that conversation

### Use Cases

- **Language standards** — Python, TypeScript, Go coding conventions
- **Framework patterns** — React, Angular, FastAPI best practices
- **Testing requirements** — Coverage, patterns, edge cases
- **API design** — RESTful conventions, response formats
- **Full stack standards** — End-to-end project guidelines

### Example Rules

```yaml
# Clean Code Standards
- Descriptive naming (nouns for variables, verbs for functions)
- Single responsibility functions (< 20 lines)
- No magic numbers, use constants
- Comment the "why", not the "what"

# Python Standards
- Follow PEP 8, use type hints
- Use dataclasses or Pydantic for data structures
- Async/await for I/O-bound operations
- pytest with fixtures and parametrize

# React + FastAPI Full Stack
- Backend: Async SQLAlchemy, Pydantic v2, service layer
- Frontend: React Query, Zustand, React Hook Form + Zod
- Type-safe API contracts between frontend and backend
```

### API

```bash
# List rules
GET /api/rules

# Get rule with content
GET /api/rules/{id}

# Create rule
POST /api/rules
{"name": "My Rule", "description": "...", "content": "...", "tags": ["python"]}

# Create example rules
POST /api/rules/examples

# Chat with rules
POST /api/chat
{"message": "...", "rule_ids": ["python-standards", "testing-requirements"]}
```

### Storage

Rules are stored as YAML files in `~/.maratos/rules/`

---

## Subagents

Spawn background tasks that run independently:

```bash
# Spawn a task
POST /api/subagents/spawn
{"task": "Review all Python files for security issues", "agent_id": "reviewer"}

# Check status
GET /api/subagents/tasks/{task_id}

# List running tasks
GET /api/subagents/tasks?status=running
```

---

## Auto-Orchestration

MO can automatically delegate complex tasks to specialized subagents using `[SPAWN:agent]` markers:

### How It Works

```
User: "Design an authentication system for my FastAPI app"
        ↓
MO: "I'll have the architect design this properly...
     [SPAWN:architect] Design a secure authentication system for FastAPI 
     with JWT tokens, OAuth2 support, and role-based access control"
        ↓
System: Parses marker → Spawns architect subagent
        ↓
UI: Shows progress bar "🏗️ Architect 45%..."
        ↓
Result: Architect's detailed design appears as a new message
```

### Available Agents

| Agent | Marker | Best For |
|-------|--------|----------|
| 🏗️ **Architect** | `[SPAWN:architect]` | System design, architecture decisions, technical specs |
| 🔍 **Reviewer** | `[SPAWN:reviewer]` | Code review, security audits, quality checks |
| 💻 **Coder** | `[SPAWN:coder]` | Pure implementation, clean production-ready code |
| 🧪 **Tester** | `[SPAWN:tester]` | Test generation, coverage analysis, edge cases |
| 📝 **Docs** | `[SPAWN:docs]` | Documentation, READMEs, API docs |
| 🚀 **DevOps** | `[SPAWN:devops]` | Infrastructure, CI/CD, Docker, deployment |
| 🤖 **MO** | `[SPAWN:mo]` | General tasks, parallel work |

### Example Prompts

```
"Design and implement a rate limiter"
→ MO: [SPAWN:architect] Design the rate limiter architecture
       [SPAWN:coder] Implement the rate limiter based on this design

"Review, test, and document my auth module"
→ MO: [SPAWN:reviewer] Review src/auth.py for security issues
       [SPAWN:tester] Generate comprehensive tests for src/auth.py
       [SPAWN:docs] Write API documentation for auth endpoints

"Set up CI/CD for this project"
→ MO: [SPAWN:devops] Create Dockerfile and GitHub Actions workflow
```

### UI Features

- **Thinking Indicator**: Animated dots while MO processes
- **Progress Bars**: Real-time progress for each subagent
- **Inline Results**: Subagent responses appear as chat messages

---

## Memory System

Infinite memory with semantic search:

```bash
# Store a memory
POST /api/memory/remember
{"content": "User prefers TypeScript over JavaScript", "importance": 0.8}

# Recall relevant memories
POST /api/memory/recall
{"query": "programming language preferences"}

# Get stats
GET /api/memory/stats
```

Memory is automatically used in conversations for context.

**Optional:** Install embeddings for semantic search:
```bash
pip install maratos[embeddings]
```

---

## Tools

| Tool | Description |
|------|-------------|
| **Filesystem** | Read anywhere, write to workspace |
| **Shell** | Execute commands |
| **Web Search** | Search the internet |
| **Web Fetch** | Read web pages |
| **Kiro** | Enterprise AI for coding |

---

## Docker

```bash
docker-compose up -d
```

Or build manually:

```bash
docker build -t maratos .
docker run -p 8000:8000 \
  -e MARATOS_ANTHROPIC_API_KEY=your-key \
  -e MARATOS_TELEGRAM_ENABLED=true \
  -e MARATOS_TELEGRAM_TOKEN=your-token \
  maratos
```

---

## API Reference

| Endpoint | Description |
|----------|-------------|
| **Chat** |
| `POST /api/chat` | Chat with MO (SSE streaming) |
| `GET /api/chat/sessions` | List conversations |
| **Agents** |
| `GET /api/agents` | List available agents |
| `POST /api/chat` + `agent_id` | Use specific agent |
| **Skills** |
| `GET /api/skills` | List available skills |
| `POST /api/skills/{id}/execute` | Execute a skill |
| **Subagents** |
| `POST /api/subagents/spawn` | Spawn background task |
| `GET /api/subagents/tasks` | List tasks |
| `GET /api/subagents/tasks/{id}` | Get task status |
| **Memory** |
| `POST /api/memory/remember` | Store a memory |
| `POST /api/memory/recall` | Search memories |
| `GET /api/memory/stats` | Memory statistics |
| **Rules** |
| `GET /api/rules` | List all rules |
| `GET /api/rules/{id}` | Get rule with content |
| `POST /api/rules` | Create a rule |
| `PUT /api/rules/{id}` | Update a rule |
| `DELETE /api/rules/{id}` | Delete a rule |
| `POST /api/rules/examples` | Create example rules |
| **Channels** |
| `GET /api/channels` | List messaging channels |
| **Config** |
| `GET /api/config` | Get configuration |
| `GET /docs` | Swagger API docs |

### SSE Events (Chat Streaming)

The `/api/chat` endpoint streams Server-Sent Events:

| Event | Data | Description |
|-------|------|-------------|
| `session_id` | `{"session_id": "..."}` | Chat session identifier |
| `agent` | `{"agent": "mo"}` | Active agent |
| `thinking` | `{"thinking": true/false}` | Processing indicator |
| `content` | `{"content": "..."}` | Response text chunk |
| `orchestrating` | `{"orchestrating": true/false}` | Subagent spawning active |
| `subagent` | `{"subagent": "architect", "status": "running", "progress": 0.5}` | Subagent progress |
| `subagent_result` | `{"subagent_result": "architect", "content": "..."}` | Subagent response |
| `[DONE]` | — | Stream complete |

---

## Project Structure

```
maratos/
├── backend/
│   └── app/
│       ├── agents/        # MO, Architect, Reviewer
│       ├── channels/      # Telegram, iMessage, Webex
│       ├── memory/        # Infinite memory system
│       ├── rules/         # Development rules system
│       ├── skills/        # Skill execution engine
│       ├── subagents/     # Background task runner
│       │   ├── manager.py # Task spawning & tracking
│       │   └── runner.py  # Agent execution
│       ├── tools/         # filesystem, shell, web, kiro, orchestrate
│       └── api/
│           └── chat.py    # SSE streaming + auto-orchestration
├── frontend/
│   └── src/
│       ├── pages/
│       │   └── ChatPage.tsx
│       ├── components/
│       │   ├── ChatMessage.tsx
│       │   ├── ThinkingIndicator.tsx  # Animated dots
│       │   └── SubagentStatus.tsx     # Progress bars
│       ├── stores/
│       │   └── chat.ts    # State management
│       └── lib/
│           └── api.ts     # SSE event handling
├── skills/                # Built-in skill definitions
├── install.sh             # macOS/Linux installer
├── install.ps1            # Windows installer
└── docker-compose.yml
```

---

## License

MIT

---

Built with 💜 for Marat
