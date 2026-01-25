# 🖥️ MaratOS - AI Operating System

## Vision
A personal AI operating system powered by MO — a capable, opinionated AI partner that's genuinely helpful without the corporate fluff.

---

## Core Concept

**MO** is the heart of MaratOS. Not a generic assistant, but a partner with:
- Real personality and opinions
- Resourcefulness (figures things out before asking)
- Trust earned through competence
- Concise, helpful responses without sycophancy

---

## Features

### Web Interface
- Modern React UI with Tailwind
- Dark mode by default
- Real-time streaming chat
- Conversation history
- Visual settings

### MO Agent
- Personality inspired by SOUL.md principles
- Full tool access: files, shell, web
- Remembers conversation context
- Smart and opinionated

### Tools
- **Filesystem**: Read, write, edit files
- **Shell**: Execute commands, git, scripts
- **Web Search**: Find information online
- **Web Fetch**: Read web pages

---

## Tech Stack

### Backend
- **FastAPI** - Async Python API
- **SQLite** - Conversation persistence
- **LiteLLM** - Multi-model support

### Frontend
- **React 18** + Vite
- **TailwindCSS**
- **Zustand** - State management
- **React Query** - Data fetching

---

## MO's System Prompt Core

```
You are MO, the MaratOS agent. You're not a chatbot — you're a capable partner.

Core Principles:
- Be genuinely helpful, not performatively helpful
- Have opinions — disagree when warranted
- Be resourceful before asking
- Earn trust through competence
```

---

## API

```
POST /api/chat              # Chat with MO (SSE stream)
GET  /api/chat/sessions     # List sessions
GET  /api/chat/sessions/:id # Get session
DELETE /api/chat/sessions/:id # Delete session
GET  /api/config            # Get config
PUT  /api/config            # Update config
```

---

## Environment Variables

```
MARATOS_ANTHROPIC_API_KEY   # Required for Claude
MARATOS_OPENAI_API_KEY      # Optional for GPT
MARATOS_DEFAULT_MODEL       # Default: claude-sonnet-4-20250514
MARATOS_DEBUG               # Default: false
MARATOS_PORT                # Default: 8000
```
