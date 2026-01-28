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

# kiro-cli (required for LLM access)
if check_cmd kiro-cli || check_cmd kiro; then
    KIRO_CMD=$(which kiro-cli 2>/dev/null || which kiro)
    success "kiro-cli found: $KIRO_CMD"
else
    warn "kiro-cli not found (required for LLM access)"
    info "Install with: curl -fsSL https://cli.kiro.dev/install | bash"
    info "Then authenticate: kiro-cli login"
fi

echo ""

# === Download/Clone MaratOS ===
if [ -d "$INSTALL_DIR" ]; then
    warn "Directory exists: $INSTALL_DIR"
    info "Updating existing installation..."
    cd "$INSTALL_DIR"
    git pull origin main || {
        warn "Git pull failed, removing and re-cloning..."
        cd ..
        rm -rf "$INSTALL_DIR"
    }
fi

if [ ! -d "$INSTALL_DIR" ]; then
    info "Downloading MaratOS..."
    if check_cmd git; then
        git clone --depth 1 https://github.com/kapella-hub/maratos.git "$INSTALL_DIR" || {
            warn "Git clone failed. Trying ZIP download..."
            # Try downloading as ZIP
            if check_cmd curl && check_cmd unzip; then
                TEMP_ZIP="/tmp/maratos-$$.zip"
                curl -fsSL "https://github.com/kapella-hub/maratos/archive/main.zip" -o "$TEMP_ZIP"
                unzip -q "$TEMP_ZIP" -d /tmp
                mv /tmp/maratos-main "$INSTALL_DIR"
                rm -f "$TEMP_ZIP"
            else
                echo ""
                error "Could not download MaratOS. Try manually:\n  git clone https://github.com/kapella-hub/maratos.git ~/.maratos"
            fi
        }
    else
        error "git not found. Install git first."
    fi
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

# Check for kiro-cli (required for LLM access)
if ! command -v kiro-cli &> /dev/null && ! command -v kiro &> /dev/null; then
    echo "Error: kiro-cli not found!"
    echo "  Install with: curl -fsSL https://cli.kiro.dev/install | bash"
    echo "  Then authenticate: kiro-cli login"
    exit 1
fi

echo "Starting MaratOS..."

# Start backend
cd backend
source .venv/bin/activate
python run.py &
BACKEND_PID=$!
cd ..

# Wait for backend to be ready
echo "Waiting for backend..."
for i in {1..30}; do
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Start frontend
cd frontend
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "MaratOS is running!"
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
# All LLM calls route through kiro-cli (no API keys needed)

# MARATOS_DEFAULT_MODEL=claude-sonnet-4
# Available: Auto, claude-sonnet-4, claude-sonnet-4.5, claude-haiku-4.5, claude-opus-4.5
EOF
fi

# === Done! ===
echo ""
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo -e "${GREEN}  MaratOS installed successfully!${NC}"
echo -e "${GREEN}════════════════════════════════════════${NC}"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo ""
echo "1. Ensure kiro-cli is authenticated:"
echo -e "   ${BLUE}kiro-cli login${NC}"
echo ""
echo "2. Start MaratOS:"
if [ -w /usr/local/bin ]; then
echo -e "   ${BLUE}maratos${NC}"
else
echo -e "   ${BLUE}$INSTALL_DIR/start.sh${NC}"
fi
echo ""
echo "3. Open: http://localhost:5173"
echo ""
echo "MO is ready to help!"
