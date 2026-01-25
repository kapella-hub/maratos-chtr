# 🖥️ MaratOS

Your personal AI operating system, powered by **MO** — a capable, opinionated AI partner.

![Version](https://img.shields.io/badge/version-0.1.0-violet)
![Agent](https://img.shields.io/badge/agent-MO-purple)

## Quick Install

### macOS / Linux

```bash
curl -fsSL https://raw.githubusercontent.com/kapella-hub/maratos/main/install.sh | bash
```

### Windows (PowerShell)

```powershell
irm https://raw.githubusercontent.com/kapella-hub/maratos/main/install.ps1 | iex
```

Then add your [Anthropic API key](https://console.anthropic.com/) and run:

```bash
# macOS/Linux
maratos

# Windows
# Double-click "MaratOS" on Desktop
```

Open **http://localhost:5173** and start chatting with MO!

---

## What is MaratOS?

MaratOS is a self-hostable AI platform with a beautiful web interface. At its core is **MO** — an AI that's genuinely helpful without the corporate fluff.

### MO's Personality

- **Skips the fluff** — No "Great question!" or "I'd be happy to help!"
- **Has opinions** — Disagrees when warranted
- **Is resourceful** — Figures things out before asking
- **Earns trust** — Through competence, not compliance

### Features

- 🤖 **MO Agent** — Capable AI with real personality
- 🎨 **Beautiful UI** — Modern dark-mode web interface
- 💬 **Real-time Chat** — Streaming responses
- 🔧 **Powerful Tools** — Files, shell, web search, Kiro AI
- 🔒 **Sandboxed Writes** — Read anywhere, write only to workspace
- ⚙️ **Easy Config** — Visual settings

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
# Edit .env and add your MARATOS_ANTHROPIC_API_KEY

# Run (two terminals)
cd backend && source .venv/bin/activate && python run.py
cd frontend && npm run dev
```

Open http://localhost:5173

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

## Tools

| Tool | Description |
|------|-------------|
| **Filesystem** | Read anywhere, write to workspace |
| **Shell** | Execute commands |
| **Web Search** | Search the internet |
| **Web Fetch** | Read web pages |
| **Kiro AI** | Delegate to Kiro for complex coding |

---

## Messaging Channels

MO can be reached via multiple channels:

| Channel | Description | Setup |
|---------|-------------|-------|
| **Web UI** | Built-in chat interface | Default at :5173 |
| **Telegram** | Telegram Bot API | Get token from @BotFather |
| **iMessage** | macOS only via AppleScript | Just enable in config |
| **Webex** | Cisco Webex Teams | Create bot at developer.webex.com |

### Enable Channels

Edit `.env`:

```bash
# Telegram
MARATOS_TELEGRAM_ENABLED=true
MARATOS_TELEGRAM_TOKEN=your-bot-token
MARATOS_TELEGRAM_ALLOWED_USERS=123456789  # Optional: restrict access

# iMessage (macOS only)
MARATOS_IMESSAGE_ENABLED=true
MARATOS_IMESSAGE_ALLOWED_SENDERS=+1234567890

# Webex
MARATOS_WEBEX_ENABLED=true
MARATOS_WEBEX_TOKEN=your-bot-token
```

### Webex Setup

1. Create a bot at [developer.webex.com/my-apps](https://developer.webex.com/my-apps)
2. Add the token to `.env`
3. Set up webhook: `POST /api/channels/webex/setup` with your public URL
4. Add the bot to rooms you want it to respond in

---

## Configuration

Environment variables (prefix with `MARATOS_`):

```bash
MARATOS_ANTHROPIC_API_KEY=sk-ant-...    # Required
MARATOS_OPENAI_API_KEY=sk-...           # Optional (for GPT)
MARATOS_DEFAULT_MODEL=claude-sonnet-4-20250514
MARATOS_DEBUG=false
MARATOS_PORT=8000
```

---

## Docker

```bash
docker-compose up -d
```

Or build manually:

```bash
docker build -t maratos .
docker run -p 8000:8000 -e MARATOS_ANTHROPIC_API_KEY=your-key maratos
```

---

## API

| Endpoint | Description |
|----------|-------------|
| `POST /api/chat` | Chat with MO (SSE streaming) |
| `GET /api/chat/sessions` | List conversations |
| `GET /api/config` | Get configuration |
| `GET /docs` | Swagger API docs |

---

## Project Structure

```
maratos/
├── backend/           # FastAPI + Python
│   └── app/
│       ├── agents/    # MO implementation
│       ├── tools/     # filesystem, shell, web, kiro
│       └── api/       # REST endpoints
├── frontend/          # React + Vite + Tailwind
│   └── src/
│       ├── pages/     # Chat, History, Settings
│       └── components/
├── install.sh         # macOS/Linux installer
├── install.ps1        # Windows installer
└── docker-compose.yml
```

---

## License

MIT

---

Built with 💜 for Marat
