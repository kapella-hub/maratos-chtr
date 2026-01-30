#!/bin/bash
# MaratOS - Modern Start Script
# Usage: ./start.sh [options]
#   --backend-only    Start only the backend
#   --no-install      Skip dependency installation
#   --dev             Development mode with hot reload
#   --quiet           Minimal output

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
DATA_DIR="$PROJECT_DIR/data"
PID_DIR="$PROJECT_DIR/.pids"
LOG_DIR="/tmp/maratos"

# Modern colors
C_RESET='\033[0m'
C_BOLD='\033[1m'
C_DIM='\033[2m'
C_PURPLE='\033[38;5;141m'
C_BLUE='\033[38;5;75m'
C_GREEN='\033[38;5;114m'
C_YELLOW='\033[38;5;221m'
C_RED='\033[38;5;203m'
C_CYAN='\033[38;5;87m'

# Icons
ICON_CHECK="✓"
ICON_CROSS="✗"
ICON_ARROW="→"
ICON_SPIN="◐"
ICON_DOT="•"

# Parse arguments
BACKEND_ONLY=false
NO_INSTALL=false
DEV_MODE=false
QUIET=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --backend-only) BACKEND_ONLY=true; shift ;;
        --no-install) NO_INSTALL=true; shift ;;
        --dev) DEV_MODE=true; shift ;;
        --quiet|-q) QUIET=true; shift ;;
        --help|-h)
            echo "Usage: ./start.sh [options]"
            echo "  --backend-only  Start only the backend"
            echo "  --no-install    Skip dependency installation"
            echo "  --dev           Development mode"
            echo "  --quiet, -q     Minimal output"
            exit 0 ;;
        *) shift ;;
    esac
done

# Output functions
banner() {
    [[ "$QUIET" == true ]] && return
    echo ""
    echo -e "${C_PURPLE}${C_BOLD}  ╔══════════════════════════════════════╗${C_RESET}"
    echo -e "${C_PURPLE}${C_BOLD}  ║           ${C_CYAN}MaratOS${C_PURPLE}                    ║${C_RESET}"
    echo -e "${C_PURPLE}${C_BOLD}  ╚══════════════════════════════════════╝${C_RESET}"
    echo ""
}

log() { [[ "$QUIET" != true ]] && echo -e "  ${C_DIM}${ICON_DOT}${C_RESET} $1"; }
step() { [[ "$QUIET" != true ]] && echo -e "  ${C_BLUE}${ICON_ARROW}${C_RESET} ${C_BOLD}$1${C_RESET}"; }
ok() { echo -e "  ${C_GREEN}${ICON_CHECK}${C_RESET} $1"; }
warn() { echo -e "  ${C_YELLOW}!${C_RESET} $1"; }
fail() { echo -e "  ${C_RED}${ICON_CROSS}${C_RESET} $1"; }

# Setup directories
mkdir -p "$DATA_DIR" "$PID_DIR" "$LOG_DIR"

banner

# Check dependencies
step "Checking dependencies"
KIRO_CMD=""
if command -v kiro-cli &>/dev/null; then
    KIRO_CMD="kiro-cli"
elif command -v kiro &>/dev/null; then
    KIRO_CMD="kiro"
fi

if [[ -z "$KIRO_CMD" ]]; then
    fail "kiro-cli not found"
    echo -e "    ${C_DIM}Install: curl -fsSL https://cli.kiro.dev/install | bash${C_RESET}"
    exit 1
fi
ok "kiro-cli ready"

# Stop existing processes
if [[ -f "$PROJECT_DIR/stop.sh" ]]; then
    "$PROJECT_DIR/stop.sh" --quiet 2>/dev/null || true
fi
sleep 1

# Backend setup
step "Setting up backend"
cd "$BACKEND_DIR"

if [[ ! -d ".venv" ]]; then
    log "Creating virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

if [[ "$NO_INSTALL" == false ]]; then
    log "Installing dependencies..."
    pip install -e . -q 2>/dev/null
fi
ok "Backend configured"

# Frontend setup
if [[ "$BACKEND_ONLY" == false ]]; then
    step "Setting up frontend"
    cd "$FRONTEND_DIR"
    
    if [[ "$NO_INSTALL" == false ]]; then
        if [[ ! -d "node_modules" ]]; then
            log "Installing dependencies..."
            npm install --silent 2>/dev/null
        fi
    fi
    ok "Frontend configured"
fi

# Start backend
step "Starting services"
cd "$BACKEND_DIR"
source .venv/bin/activate

if [[ "$OSTYPE" == "darwin"* ]]; then
    caffeinate -isd python run.py > "$LOG_DIR/backend.log" 2>&1 &
else
    python run.py > "$LOG_DIR/backend.log" 2>&1 &
fi
BACKEND_PID=$!
echo $BACKEND_PID > "$PID_DIR/backend.pid"

# Wait for backend
for i in {1..30}; do
    if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

if curl -s http://localhost:8000/api/health >/dev/null 2>&1; then
    ok "Backend running ${C_DIM}(PID: $BACKEND_PID)${C_RESET}"
else
    if kill -0 $BACKEND_PID 2>/dev/null; then
        warn "Backend started but health check pending"
    else
        fail "Backend failed to start"
        tail -10 "$LOG_DIR/backend.log"
        exit 1
    fi
fi

# Start frontend
if [[ "$BACKEND_ONLY" == false ]]; then
    cd "$FRONTEND_DIR"
    npm run dev > "$LOG_DIR/frontend.log" 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > "$PID_DIR/frontend.pid"
    sleep 2
    
    if kill -0 $FRONTEND_PID 2>/dev/null; then
        ok "Frontend running ${C_DIM}(PID: $FRONTEND_PID)${C_RESET}"
    else
        warn "Frontend may have failed - check logs"
    fi
fi

# Summary
echo ""
echo -e "  ${C_GREEN}${C_BOLD}Ready!${C_RESET}"
echo ""
echo -e "  ${C_CYAN}Frontend${C_RESET}   http://localhost:5173"
echo -e "  ${C_CYAN}Backend${C_RESET}    http://localhost:8000"
echo -e "  ${C_CYAN}API Docs${C_RESET}   http://localhost:8000/docs"
echo ""
echo -e "  ${C_DIM}Logs: $LOG_DIR${C_RESET}"
echo -e "  ${C_DIM}Stop: ./stop.sh${C_RESET}"
echo ""
