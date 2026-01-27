#!/bin/bash
# MaratOS - Rebuild and Restart Script

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_DIR="$PROJECT_DIR/backend"
FRONTEND_DIR="$PROJECT_DIR/frontend"

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

# Check for kiro-cli (required for LLM access)
if ! command -v kiro-cli &> /dev/null && ! command -v kiro &> /dev/null; then
    error "kiro-cli not found! Install with: curl -fsSL https://cli.kiro.dev/install | bash"
    error "Then authenticate: kiro-cli login"
    exit 1
fi
success "kiro-cli found: $(which kiro-cli 2>/dev/null || which kiro)"

# Kill existing processes
log "Stopping existing processes..."
pkill -f "python run.py" 2>/dev/null || true
pkill -f "uvicorn" 2>/dev/null || true
pkill -f "vite" 2>/dev/null || true
pkill -f "node.*frontend" 2>/dev/null || true
pkill -f "caffeinate.*maratos" 2>/dev/null || true
sleep 1

# Backend setup
log "Setting up backend..."
cd "$BACKEND_DIR"

if [ ! -d ".venv" ]; then
    log "Creating Python virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate

log "Installing backend dependencies..."
pip install -e . -q

# Frontend setup
log "Setting up frontend..."
cd "$FRONTEND_DIR"

if [ ! -d "node_modules" ]; then
    log "Installing frontend dependencies..."
    npm install
else
    log "Checking for frontend updates..."
    npm install -q 2>/dev/null || true
fi

# Start services
log "Starting backend (port 8000) with sleep prevention..."
cd "$BACKEND_DIR"
source .venv/bin/activate
# Use caffeinate to prevent sleep while backend runs
# -i = prevent idle sleep, -s = prevent sleep on AC power, -d = prevent display sleep
caffeinate -isd python run.py > /tmp/maratos-backend.log 2>&1 &
BACKEND_PID=$!

log "Starting frontend (port 5173)..."
cd "$FRONTEND_DIR"
npm run dev > /tmp/maratos-frontend.log 2>&1 &
FRONTEND_PID=$!

# Wait for services to start
sleep 3

# Check if services are running
if kill -0 $BACKEND_PID 2>/dev/null; then
    success "Backend running (PID: $BACKEND_PID)"
else
    error "Backend failed to start. Check /tmp/maratos-backend.log"
fi

if kill -0 $FRONTEND_PID 2>/dev/null; then
    success "Frontend running (PID: $FRONTEND_PID)"
else
    error "Frontend failed to start. Check /tmp/maratos-frontend.log"
fi

echo ""
success "MaratOS is running!"
echo -e "  ${BLUE}Frontend:${NC} http://localhost:5173"
echo -e "  ${BLUE}Backend:${NC}  http://localhost:8000"
echo -e "  ${BLUE}API Docs:${NC} http://localhost:8000/docs"
echo -e "  ${BLUE}Sleep:${NC}    Prevented while running (caffeinate)"
echo ""
log "Logs: /tmp/maratos-backend.log, /tmp/maratos-frontend.log"
log "Stop with: pkill -f 'caffeinate.*python'; pkill -f vite"
