#!/bin/bash
#
# MaratOS Installer for macOS/Linux
# Usage: curl -fsSL https://cdn.jsdelivr.net/gh/kapella-hub/maratos@main/install.sh | bash
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_banner() {
    echo -e "${BLUE}"
    echo "  __  __                 _    ___  ____  "
    echo " |  \/  | __ _ _ __ __ _| |_ / _ \/ ___| "
    echo " | |\/| |/ _\` | '__/ _\` | __| | | \___ \ "
    echo " | |  | | (_| | | | (_| | |_| |_| |___) |"
    echo " |_|  |_|\__,_|_|  \__,_|\__|\___/|____/ "
    echo -e "${NC}"
    echo "  Your AI Operating System - Powered by MO"
    echo ""
}

info() { echo -e "${BLUE}[INFO]${NC} $1"; }
success() { echo -e "${GREEN}[✓]${NC} $1"; }
warn() { echo -e "${YELLOW}[!]${NC} $1"; }
error() { echo -e "${RED}[✗]${NC} $1"; exit 1; }

# Check command exists
check_cmd() {
    command -v "$1" >/dev/null 2>&1
}

print_banner

INSTALL_DIR="${MARATOS_DIR:-$HOME/.maratos}"
info "Installing to: $INSTALL_DIR"
echo ""

# === Check Prerequisites ===
info "Checking prerequisites..."

# Python
if check_cmd python3; then
    PY_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
    success "Python $PY_VERSION"
else
    error "Python 3 not found. Install from https://python.org"
fi

# Node.js
if check_cmd node; then
    NODE_VERSION=$(node --version)
    success "Node.js $NODE_VERSION"
else
    error "Node.js not found. Install from https://nodejs.org"
fi

# npm
if check_cmd npm; then
    success "npm $(npm --version)"
else
    error "npm not found"
fi

# uv (optional but recommended)
if check_cmd uv; then
    success "uv $(uv --version | head -1)"
    USE_UV=true
else
    warn "uv not found (optional). Using pip instead."
    USE_UV=false
fi

echo ""

# === Download/Clone MaratOS ===
if [ -d "$INSTALL_DIR" ]; then
    warn "Directory exists: $INSTALL_DIR"
    info "Removing previous installation..."
    rm -rf "$INSTALL_DIR"
fi

info "Downloading MaratOS..."
if check_cmd git; then
    git clone --depth 1 https://github.com/kapella-hub/maratos.git "$INSTALL_DIR" 2>/dev/null || {
        # Fallback: copy from current directory if we're in the repo
        if [ -f "./backend/app/main.py" ]; then
            info "Copying from local directory..."
            cp -r . "$INSTALL_DIR"
        else
            error "Could not download MaratOS. Clone manually from GitHub."
        fi
    }
else
    error "git not found. Install git first."
fi
success "Downloaded"

cd "$INSTALL_DIR"

# === Setup Backend ===
info "Setting up backend..."
cd backend

if [ "$USE_UV" = true ]; then
    uv venv .venv
    source .venv/bin/activate
    uv pip install -e .
else
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -e .
fi
success "Backend ready"

cd ..

# === Setup Frontend ===
info "Setting up frontend..."
cd frontend
npm install --silent
success "Frontend ready"

cd ..

# === Create Launcher Script ===
info "Creating launcher..."

cat > "$INSTALL_DIR/start.sh" << 'EOF'
#!/bin/bash
cd "$(dirname "$0")"

# Load env from .env if exists
if [ -f .env ]; then
    export $(cat .env | grep -v '^#' | xargs 2>/dev/null)
fi

# Export API key if set
export MARATOS_ANTHROPIC_API_KEY="${MARATOS_ANTHROPIC_API_KEY:-$ANTHROPIC_API_KEY}"

# Check for Kiro CLI as fallback
KIRO_PATH="${HOME}/.local/bin/kiro-cli"
if [ -z "$MARATOS_ANTHROPIC_API_KEY" ]; then
    if [ -x "$KIRO_PATH" ]; then
        echo "ℹ️  No Anthropic API key - using Kiro CLI for Claude models"
    else
        echo "⚠️  No API key and Kiro CLI not found."
        echo "Either:"
        echo "  1. Set MARATOS_ANTHROPIC_API_KEY in .env"
        echo "  2. Install Kiro CLI: curl -fsSL https://cli.kiro.dev/install | bash"
        echo ""
    fi
fi

echo "🖥️  Starting MaratOS..."

# Start backend
cd backend
source .venv/bin/activate
python run.py &
BACKEND_PID=$!
cd ..

# Wait for backend
sleep 3

# Start frontend
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "✨ MaratOS is running!"
echo "   Frontend: http://localhost:5173"
echo "   Backend:  http://localhost:8000"
echo ""
echo "Press Ctrl+C to stop"

# Handle shutdown
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
EOF

chmod +x "$INSTALL_DIR/start.sh"

# Create symlink in /usr/local/bin if possible
if [ -w /usr/local/bin ]; then
    ln -sf "$INSTALL_DIR/start.sh" /usr/local/bin/maratos
    success "Created 'maratos' command"
else
    warn "Could not create global command (no write access to /usr/local/bin)"
fi

# === Create .env template ===
if [ ! -f "$INSTALL_DIR/.env" ]; then
    cat > "$INSTALL_DIR/.env" << EOF
# MaratOS Configuration
# Get your API key from: https://console.anthropic.com/

MARATOS_ANTHROPIC_API_KEY=
# MARATOS_OPENAI_API_KEY=
# MARATOS_DEFAULT_MODEL=claude-sonnet-4-20250514
EOF
fi

# === Done! ===
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  MaratOS installed successfully! 🎉${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}To start MaratOS:${NC}"
echo ""
if [ -w /usr/local/bin ]; then
echo -e "  ${BLUE}maratos${NC}"
else
echo -e "  ${BLUE}$INSTALL_DIR/start.sh${NC}"
fi
echo ""
echo "You'll be prompted for your Anthropic API key on first run."
echo "(Get one at https://console.anthropic.com)"
echo ""
echo "Then open: http://localhost:5173"
echo ""
echo "MO is ready to help! 🤖"
