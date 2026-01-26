#!/bin/bash
# MaratOS - Stop Script

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

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

log "Stopping MaratOS services..."

# Track what we stopped
STOPPED=""

# Stop backend processes
if pgrep -f "python run.py" > /dev/null 2>&1; then
    pkill -f "python run.py" 2>/dev/null
    STOPPED="$STOPPED backend"
fi

if pgrep -f "uvicorn" > /dev/null 2>&1; then
    pkill -f "uvicorn" 2>/dev/null
    STOPPED="$STOPPED uvicorn"
fi

# Stop frontend processes
if pgrep -f "vite" > /dev/null 2>&1; then
    pkill -f "vite" 2>/dev/null
    STOPPED="$STOPPED frontend"
fi

if pgrep -f "node.*frontend" > /dev/null 2>&1; then
    pkill -f "node.*frontend" 2>/dev/null
    STOPPED="$STOPPED node"
fi

# Stop caffeinate (sleep prevention)
if pgrep -f "caffeinate.*maratos" > /dev/null 2>&1; then
    pkill -f "caffeinate.*maratos" 2>/dev/null
    STOPPED="$STOPPED caffeinate"
fi

# Also stop any caffeinate running python
if pgrep -f "caffeinate.*python" > /dev/null 2>&1; then
    pkill -f "caffeinate.*python" 2>/dev/null
    STOPPED="$STOPPED caffeinate-python"
fi

# Wait a moment for processes to terminate
sleep 1

# Verify everything is stopped
STILL_RUNNING=""

if pgrep -f "python run.py" > /dev/null 2>&1; then
    STILL_RUNNING="$STILL_RUNNING backend"
fi

if pgrep -f "vite" > /dev/null 2>&1; then
    STILL_RUNNING="$STILL_RUNNING frontend"
fi

# Report results
echo ""
if [ -n "$STOPPED" ]; then
    success "Stopped:$STOPPED"
fi

if [ -n "$STILL_RUNNING" ]; then
    error "Still running:$STILL_RUNNING"
    warn "Try: sudo pkill -9 -f 'python run.py'; sudo pkill -9 -f vite"
    exit 1
else
    success "MaratOS stopped successfully!"
fi
