#!/bin/bash
# MaratOS - Stop Script
# Usage: ./stop.sh [--force]

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
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
FORCE=false
if [[ "$1" == "--force" ]]; then
    FORCE=true
fi

log "Stopping MaratOS services..."

# Track what we stopped
STOPPED=""

# Function to stop a process by PID file
stop_by_pid() {
    local name="$1"
    local pid_file="$PID_DIR/$name.pid"
    local signal="-TERM"

    if [[ "$FORCE" == true ]]; then
        signal="-9"
    fi

    if [[ -f "$pid_file" ]]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            log "Stopping $name (PID: $pid)..."
            kill $signal "$pid" 2>/dev/null
            STOPPED="$STOPPED $name"
        else
            log "PID file exists but process $pid not running"
        fi
        rm -f "$pid_file"
        return 0
    fi
    return 1
}

# Try PID files first (preferred method)
stop_by_pid "backend"
stop_by_pid "frontend"

# Fallback: stop by process pattern (for processes started without PID tracking)
if ! echo "$STOPPED" | grep -q "backend"; then
    if pgrep -f "python run.py" > /dev/null 2>&1; then
        pkill -f "python run.py" 2>/dev/null
        STOPPED="$STOPPED backend"
    fi
fi

if pgrep -f "uvicorn" > /dev/null 2>&1; then
    pkill -f "uvicorn" 2>/dev/null
    STOPPED="$STOPPED uvicorn"
fi

if ! echo "$STOPPED" | grep -q "frontend"; then
    if pgrep -f "vite" > /dev/null 2>&1; then
        pkill -f "vite" 2>/dev/null
        STOPPED="$STOPPED frontend"
    fi
fi

if pgrep -f "node.*frontend" > /dev/null 2>&1; then
    pkill -f "node.*frontend" 2>/dev/null
    STOPPED="$STOPPED node"
fi

# Stop caffeinate (sleep prevention on macOS)
if pgrep -f "caffeinate.*python" > /dev/null 2>&1; then
    pkill -f "caffeinate.*python" 2>/dev/null
    STOPPED="$STOPPED caffeinate"
fi

# Wait for processes to terminate
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
    if [[ "$FORCE" != true ]]; then
        warn "Try: ./stop.sh --force"
    else
        warn "Try: sudo pkill -9 -f 'python run.py'; sudo pkill -9 -f vite"
    fi
    exit 1
else
    success "MaratOS stopped successfully!"
fi
