#!/bin/bash
#
# MaratOS Backup Script
# Creates timestamped backups of database, config, and optionally workspace
#
# Usage:
#   ./scripts/backup.sh [options]
#
# Options:
#   --include-workspace   Include workspace directory in backup
#   --output-dir DIR      Custom output directory (default: ./backups)
#   --prefix NAME         Prefix for backup filename (default: maratos)
#   --keep N              Number of backups to keep (default: 7, 0=unlimited)
#   --help                Show this help message

set -eo pipefail

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
DATA_DIR="$PROJECT_ROOT/data"
CONFIG_DIR="$HOME/.maratos"
WORKSPACE_DIR="$HOME/maratos-workspace"

# Colors (disabled if not a terminal)
if [ -t 1 ]; then
    RED='\033[0;31m'
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    BLUE='\033[0;34m'
    NC='\033[0m'
else
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    NC=''
fi

# Default options
INCLUDE_WORKSPACE=false
OUTPUT_DIR="$PROJECT_ROOT/backups"
PREFIX="maratos"
KEEP_BACKUPS=7

# =============================================================================
# Helper Functions
# =============================================================================

log() { printf "${BLUE}[MaratOS]${NC} %s\n" "$1"; }
success() { printf "${GREEN}[MaratOS]${NC} %s\n" "$1"; }
warn() { printf "${YELLOW}[MaratOS]${NC} %s\n" "$1"; }
error() { printf "${RED}[MaratOS]${NC} %s\n" "$1"; }

show_help() {
    cat << EOF
MaratOS Backup Script

Creates timestamped backups of:
  - Database files (data/*.db, data/*.sqlite)
  - Configuration (~/.maratos/)
  - Optionally: Workspace (~/maratos-workspace)

Usage: ./scripts/backup.sh [options]

Options:
  --include-workspace   Include workspace directory in backup (can be large)
  --output-dir DIR      Custom output directory (default: ./backups)
  --prefix NAME         Prefix for backup filename (default: maratos)
  --keep N              Number of backups to keep (default: 7, 0=unlimited)
  --help                Show this help message

Examples:
  ./scripts/backup.sh                           # Basic backup (db + config)
  ./scripts/backup.sh --include-workspace       # Full backup with workspace
  ./scripts/backup.sh --output-dir /mnt/backup  # Custom destination
  ./scripts/backup.sh --keep 30                 # Keep last 30 backups

Output:
  Creates: backups/maratos-backup-YYYYMMDD-HHMMSS.tar.gz

EOF
}

# =============================================================================
# Parse Arguments
# =============================================================================

while [ $# -gt 0 ]; do
    case $1 in
        --include-workspace)
            INCLUDE_WORKSPACE=true
            shift
            ;;
        --output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        --prefix)
            PREFIX="$2"
            shift 2
            ;;
        --keep)
            KEEP_BACKUPS="$2"
            shift 2
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# =============================================================================
# Main Backup Logic
# =============================================================================

main() {
    log "Starting MaratOS backup..."

    # Create output directory
    mkdir -p "$OUTPUT_DIR"

    # Generate timestamp
    TIMESTAMP=$(date +"%Y%m%d-%H%M%S")
    BACKUP_NAME="${PREFIX}-backup-${TIMESTAMP}"
    BACKUP_ARCHIVE="$OUTPUT_DIR/${BACKUP_NAME}.tar.gz"

    # Create temporary staging directory
    STAGING_DIR=$(mktemp -d)
    BACKUP_STAGING="$STAGING_DIR/$BACKUP_NAME"
    mkdir -p "$BACKUP_STAGING"

    log "Backup timestamp: $TIMESTAMP"

    # ==========================================================================
    # Backup Database
    # ==========================================================================

    if [ -d "$DATA_DIR" ]; then
        log "Backing up database files..."
        mkdir -p "$BACKUP_STAGING/data"

        # Copy SQLite databases
        DB_COUNT=0
        for db in "$DATA_DIR"/*.db "$DATA_DIR"/*.sqlite; do
            if [ -f "$db" ]; then
                cp "$db" "$BACKUP_STAGING/data/"
                DB_COUNT=$((DB_COUNT + 1))
                log "  - $(basename "$db")"
            fi
        done

        if [ $DB_COUNT -eq 0 ]; then
            warn "No database files found in $DATA_DIR"
        else
            success "Backed up $DB_COUNT database file(s)"
        fi
    else
        warn "Data directory not found: $DATA_DIR"
    fi

    # ==========================================================================
    # Backup Configuration
    # ==========================================================================

    if [ -d "$CONFIG_DIR" ]; then
        log "Backing up configuration..."
        mkdir -p "$BACKUP_STAGING/config"

        # Copy config files, excluding sensitive files
        cp -r "$CONFIG_DIR"/* "$BACKUP_STAGING/config/" 2>/dev/null || true

        # Remove any files that might contain secrets
        rm -f "$BACKUP_STAGING/config"/*.key 2>/dev/null || true
        rm -f "$BACKUP_STAGING/config"/secrets* 2>/dev/null || true

        CONFIG_COUNT=$(find "$BACKUP_STAGING/config" -type f 2>/dev/null | wc -l | tr -d ' ')
        success "Backed up $CONFIG_COUNT config file(s)"
    else
        warn "Config directory not found: $CONFIG_DIR"
    fi

    # ==========================================================================
    # Backup Workspace (optional)
    # ==========================================================================

    if [ "$INCLUDE_WORKSPACE" = true ]; then
        if [ -d "$WORKSPACE_DIR" ]; then
            log "Backing up workspace (this may take a while)..."
            mkdir -p "$BACKUP_STAGING/workspace"

            # Exclude common large/generated directories
            rsync -a \
                --exclude 'node_modules' \
                --exclude '.venv' \
                --exclude '__pycache__' \
                --exclude '.git/objects' \
                --exclude '*.pyc' \
                --exclude '.pytest_cache' \
                --exclude 'dist' \
                --exclude 'build' \
                "$WORKSPACE_DIR"/ "$BACKUP_STAGING/workspace/" 2>/dev/null || true

            WORKSPACE_SIZE=$(du -sh "$BACKUP_STAGING/workspace" 2>/dev/null | cut -f1)
            success "Backed up workspace: $WORKSPACE_SIZE"
        else
            warn "Workspace directory not found: $WORKSPACE_DIR"
        fi
    fi

    # ==========================================================================
    # Create Backup Manifest
    # ==========================================================================

    log "Creating backup manifest..."
    cat > "$BACKUP_STAGING/BACKUP_MANIFEST.txt" << EOF
MaratOS Backup Manifest
=======================

Timestamp:     $TIMESTAMP
Hostname:      $(hostname)
User:          $(whoami)
Created by:    scripts/backup.sh

Contents:
---------
$(ls -la "$BACKUP_STAGING")

Options used:
  Include Workspace: $INCLUDE_WORKSPACE
  Output Directory:  $OUTPUT_DIR
  Prefix:            $PREFIX

Restore Instructions:
---------------------
1. Extract: tar -xzf ${BACKUP_NAME}.tar.gz
2. Stop MaratOS: ./stop.sh
3. Copy data files: cp -r ${BACKUP_NAME}/data/* ./data/
4. Copy config: cp -r ${BACKUP_NAME}/config/* ~/.maratos/
5. (Optional) Copy workspace: cp -r ${BACKUP_NAME}/workspace/* ~/maratos-workspace/
6. Restart: ./restart.sh

EOF

    # ==========================================================================
    # Create Archive
    # ==========================================================================

    log "Creating archive..."
    cd "$STAGING_DIR"
    tar -czf "$BACKUP_ARCHIVE" "$BACKUP_NAME"

    # Get archive size
    ARCHIVE_SIZE=$(du -h "$BACKUP_ARCHIVE" | cut -f1)

    # Cleanup staging
    rm -rf "$STAGING_DIR"

    success "Backup created: $BACKUP_ARCHIVE ($ARCHIVE_SIZE)"

    # ==========================================================================
    # Cleanup Old Backups
    # ==========================================================================

    if [ "$KEEP_BACKUPS" -gt 0 ]; then
        log "Cleaning up old backups (keeping last $KEEP_BACKUPS)..."

        # Count existing backups
        BACKUP_COUNT=$(ls -1 "$OUTPUT_DIR"/${PREFIX}-backup-*.tar.gz 2>/dev/null | wc -l | tr -d ' ')

        if [ "$BACKUP_COUNT" -gt "$KEEP_BACKUPS" ]; then
            # Remove oldest backups
            DELETE_COUNT=$((BACKUP_COUNT - KEEP_BACKUPS))
            ls -1t "$OUTPUT_DIR"/${PREFIX}-backup-*.tar.gz 2>/dev/null | tail -n "$DELETE_COUNT" | while read -r old_backup; do
                log "  Removing: $(basename "$old_backup")"
                rm -f "$old_backup"
            done
            success "Removed $DELETE_COUNT old backup(s)"
        fi
    fi

    # ==========================================================================
    # Summary
    # ==========================================================================

    echo ""
    success "Backup complete!"
    echo ""
    echo "  Archive:  $BACKUP_ARCHIVE"
    echo "  Size:     $ARCHIVE_SIZE"
    echo ""
    echo "  To restore:"
    echo "    tar -xzf $BACKUP_ARCHIVE"
    echo "    cat ${BACKUP_NAME}/BACKUP_MANIFEST.txt"
    echo ""
}

main
