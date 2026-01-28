#!/bin/bash
# MaratOS - Rebuild and Restart Script
# Usage: ./restart.sh [--backend-only] [--no-install]

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"
DATA_DIR="$PROJECT_DIR/data"
PID_DIR="$PROJECT_DIR/.pids"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() { echo -e "${BLUE}[MaratOS]${NC} $1"; }
success() { echo -e "${GREEN}[MaratOS]${NC} $1"; }
warn() { echo -e "${YELLOW}[MaratOS]${NC} $1"; }
error() { echo -e "${RED}[MaratOS]${NC} $1"; }

# Parse arguments
BACKEND_ONLY=false
NO_INSTALL=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --backend-only)
            BACKEND_ONLY=true
            shift
            ;;
        --no-install)
            NO_INSTALL=true
            shift
            ;;
        *)
            shift
            ;;
    esac
done

# Create directories
mkdir -p "$DATA_DIR"
mkdir -p "$PID_DIR"

# Check for kiro-cli (required for LLM access)
log "Checking dependencies..."
if ! command -v kiro-cli &> /dev/null && ! command -v kiro &> /dev/null; then
    error "kiro-cli not found!"
    echo "  Install with: curl -fsSL https://cli.kiro.dev/install | bash"
    echo "  Then authenticate: kiro-cli login"
    exit 1
fi
KIRO_CMD=$(which kiro-cli 2>/dev/null || which kiro)
success "kiro-cli found: $KIRO_CMD"

# Stop existing processes using stop.sh
log "Stopping existing processes..."
if [ -f "$PROJECT_DIR/stop.sh" ]; then
    "$PROJECT_DIR/stop.sh" 2>/dev/null || true
else
    pkill -f "python run.py" 2>/dev/null || true
    pkill -f "uvicorn" 2>/dev/null || true
    pkill -f "vite" 2>/dev/null || true
    pkill -f "caffeinate.*python" 2>/dev/null || true
fi
sleep 1

# Backend setup
log "Setting up backend..."
cd "$BACKEND_DIR"

if [ ! -d ".venv" ]; then
    log "Creating Python virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

if [ "$NO_INSTALL" = false ]; then
    log "Installing backend dependencies..."
    pip install -e . -q
fi

# Frontend setup (unless backend-only)
if [ "$BACKEND_ONLY" = false ]; then
    log "Setting up frontend..."
    cd "$FRONTEND_DIR"

    if [ "$NO_INSTALL" = false ]; then
        if [ ! -d "node_modules" ]; then
            log "Installing frontend dependencies..."
            npm install
        else
            log "Checking for frontend updates..."
            npm install -q 2>/dev/null || true
        fi
    fi
fi

# Start backend
log "Starting backend (port 8000)..."
cd "$BACKEND_DIR"
source .venv/bin/activate

# Use caffeinate on macOS to prevent sleep
if [[ "$OSTYPE" == "darwin"* ]]; then
    caffeinate -isd python run.py > /tmp/maratos-backend.log 2>&1 &
else
    python run.py > /tmp/maratos-backend.log 2>&1 &
fi
BACKEND_PID=$!
echo $BACKEND_PID > "$PID_DIR/backend.pid"

# Wait for backend to start
log "Waiting for backend to start..."
for i in {1..30}; do
    if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

# Verify backend is running
if curl -s http://localhost:8000/api/health > /dev/null 2>&1; then
    success "Backend running (PID: $BACKEND_PID) - Health check passed"
else
    if kill -0 $BACKEND_PID 2>/dev/null; then
        warn "Backend running (PID: $BACKEND_PID) but health check failed"
        warn "Check /tmp/maratos-backend.log for details"
    else
        error "Backend failed to start. Check /tmp/maratos-backend.log"
        tail -20 /tmp/maratos-backend.log
        exit 1
    fi
fi

# Start frontend (unless backend-only)
if [ "$BACKEND_ONLY" = false ]; then
    log "Starting frontend (port 5173)..."
    cd "$FRONTEND_DIR"
    npm run dev > /tmp/maratos-frontend.log 2>&1 &
    FRONTEND_PID=$!
    echo $FRONTEND_PID > "$PID_DIR/frontend.pid"

    sleep 3

    if kill -0 $FRONTEND_PID 2>/dev/null; then
        success "Frontend running (PID: $FRONTEND_PID)"
    else
        error "Frontend failed to start. Check /tmp/maratos-frontend.log"
    fi
fi

# Summary
echo ""
success "MaratOS is running!"
echo -e "  ${BLUE}Frontend:${NC}  http://localhost:5173"
echo -e "  ${BLUE}Backend:${NC}   http://localhost:8000"
echo -e "  ${BLUE}API Docs:${NC}  http://localhost:8000/docs"
echo -e "  ${BLUE}Health:${NC}    http://localhost:8000/api/health"
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "  ${BLUE}Sleep:${NC}     Prevented while running (caffeinate)"
fi
echo ""
log "Logs:"
echo "  Backend:  /tmp/maratos-backend.log"
echo "  Frontend: /tmp/maratos-frontend.log"
echo ""
log "Stop with: ./stop.sh"
