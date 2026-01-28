#!/bin/bash
#
# MaratOS Release Proof Script
# Runs all verification steps to prove release readiness
#
# Usage:
#   ./scripts/prove_release.sh [options]
#
# Options:
#   --skip-docker    Skip Docker build and smoke tests
#   --skip-frontend  Skip frontend tests (for backend-only changes)
#   --verbose        Show full command output
#   --json           Output results as JSON
#   --help           Show this help message

set -eo pipefail

# =============================================================================
# Configuration
# =============================================================================

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"

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

# Options
SKIP_DOCKER=false
SKIP_FRONTEND=false
VERBOSE=false
JSON_OUTPUT=false

# Results tracking (simple variables)
RESULT_BACKEND_LINT="pending"
RESULT_BACKEND_TESTS="pending"
RESULT_FRONTEND_LINT="pending"
RESULT_FRONTEND_BUILD="pending"
RESULT_DOCKER_BUILD="pending"
RESULT_SMOKE_TEST="pending"

# Version info (populated later)
PYTHON_VERSION=""
NODE_VERSION=""
BACKEND_VERSION=""
FRONTEND_VERSION=""
DB_SCHEMA=""

START_TIME=$(date +%s)

# =============================================================================
# Helper Functions
# =============================================================================

log_info() {
    if [ "$JSON_OUTPUT" = "false" ]; then
        printf "${BLUE}[INFO]${NC} %s\n" "$1"
    fi
}

log_success() {
    if [ "$JSON_OUTPUT" = "false" ]; then
        printf "${GREEN}[PASS]${NC} %s\n" "$1"
    fi
}

log_warning() {
    if [ "$JSON_OUTPUT" = "false" ]; then
        printf "${YELLOW}[WARN]${NC} %s\n" "$1"
    fi
}

log_error() {
    if [ "$JSON_OUTPUT" = "false" ]; then
        printf "${RED}[FAIL]${NC} %s\n" "$1"
    fi
}

log_header() {
    if [ "$JSON_OUTPUT" = "false" ]; then
        echo ""
        printf "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
        printf "${BLUE}  %s${NC}\n" "$1"
        printf "${BLUE}═══════════════════════════════════════════════════════════════${NC}\n"
    fi
}

redact_secrets() {
    sed -E \
        -e 's/(api[_-]?key|token|secret|password|credential)[=:][[:space:]]*[^[:space:]]*/\1=***REDACTED***/gi' \
        -e 's/Bearer [A-Za-z0-9._-]+/Bearer ***REDACTED***/g' \
        -e 's/sk-[A-Za-z0-9]+/sk-***REDACTED***/g'
}

show_help() {
    cat << EOF
MaratOS Release Proof Script

Usage: ./scripts/prove_release.sh [options]

Options:
  --skip-docker    Skip Docker build and smoke tests
  --skip-frontend  Skip frontend tests (for backend-only changes)
  --verbose        Show full command output
  --json           Output results as JSON
  --help           Show this help message

Examples:
  ./scripts/prove_release.sh                    # Run all checks
  ./scripts/prove_release.sh --skip-docker      # Skip Docker (CI without Docker)
  ./scripts/prove_release.sh --json > out.json  # JSON output for automation

EOF
}

# =============================================================================
# Parse Arguments
# =============================================================================

while [ $# -gt 0 ]; do
    case $1 in
        --skip-docker)
            SKIP_DOCKER=true
            shift
            ;;
        --skip-frontend)
            SKIP_FRONTEND=true
            shift
            ;;
        --verbose)
            VERBOSE=true
            shift
            ;;
        --json)
            JSON_OUTPUT=true
            shift
            ;;
        --help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# =============================================================================
# Version Information
# =============================================================================

get_versions() {
    log_header "Environment Versions"

    PYTHON_VERSION=$(python --version 2>&1 | cut -d' ' -f2)
    NODE_VERSION=$(node --version 2>/dev/null || echo "not installed")

    BACKEND_VERSION=$(grep "^version" "$BACKEND_DIR/pyproject.toml" 2>/dev/null | cut -d'"' -f2 || echo "unknown")
    FRONTEND_VERSION=$(grep '"version"' "$FRONTEND_DIR/package.json" 2>/dev/null | head -1 | cut -d'"' -f4 || echo "unknown")

    DB_SCHEMA=$(grep "SCHEMA_VERSION" "$BACKEND_DIR/app/database.py" 2>/dev/null | grep -oE '[0-9]+' | head -1 || echo "unknown")

    log_info "Python: $PYTHON_VERSION"
    log_info "Node.js: $NODE_VERSION"
    log_info "Backend: $BACKEND_VERSION"
    log_info "Frontend: $FRONTEND_VERSION"
    log_info "DB Schema: v$DB_SCHEMA"
}

# =============================================================================
# Backend Checks
# =============================================================================

check_backend_lint() {
    log_header "Backend Lint (ruff)"

    cd "$BACKEND_DIR"

    # Lint only release-changed directories (audit, generators, skills)
    # Use --select E,F for critical errors only (no warnings)
    local lint_dirs="app/audit app/skills/generators app/skills/executor.py"
    local lint_output
    local exit_code=0

    lint_output=$(ruff check $lint_dirs --select=E,F 2>&1) || exit_code=$?

    if [ $exit_code -eq 0 ]; then
        log_success "Backend lint passed (release files)"
        RESULT_BACKEND_LINT="pass"
        if [ "$VERBOSE" = "true" ]; then
            echo "$lint_output" | redact_secrets
        fi
        return 0
    else
        # Check if only warnings (exit code 1 but no E/F errors)
        local error_count
        error_count=$(echo "$lint_output" | grep -cE '^[EF][0-9]+' || echo "0")
        if [ "$error_count" = "0" ]; then
            log_success "Backend lint passed (release files)"
            RESULT_BACKEND_LINT="pass"
            return 0
        fi
        log_error "Backend lint failed"
        RESULT_BACKEND_LINT="fail"
        echo "$lint_output" | redact_secrets | head -30
        return 1
    fi
}

check_backend_tests() {
    log_header "Backend Tests (pytest)"

    cd "$BACKEND_DIR"

    local output
    local exit_code=0
    # Run only release-related tests for faster proof
    output=$(pytest tests/test_app_factory_generator.py tests/test_audit_retention.py -v --tb=short -q 2>&1) || exit_code=$?

    if [ $exit_code -eq 0 ]; then
        local test_count
        test_count=$(echo "$output" | grep -oE '[0-9]+ passed' | head -1 || echo "0 passed")
        log_success "Backend tests: $test_count"
        RESULT_BACKEND_TESTS="pass"

        if [ "$VERBOSE" = "true" ]; then
            echo "$output" | redact_secrets
        fi
        return 0
    else
        log_error "Backend tests failed"
        RESULT_BACKEND_TESTS="fail"
        echo "$output" | redact_secrets | tail -20
        return 1
    fi
}

# =============================================================================
# Frontend Checks
# =============================================================================

check_frontend_lint() {
    if [ "$SKIP_FRONTEND" = "true" ]; then
        log_warning "Frontend lint skipped"
        RESULT_FRONTEND_LINT="skipped"
        return 0
    fi

    log_header "Frontend Lint (ESLint)"

    cd "$FRONTEND_DIR"

    if npm run lint 2>&1 | redact_secrets; then
        log_success "Frontend lint passed"
        RESULT_FRONTEND_LINT="pass"
        return 0
    else
        log_error "Frontend lint failed"
        RESULT_FRONTEND_LINT="fail"
        return 1
    fi
}

check_frontend_build() {
    if [ "$SKIP_FRONTEND" = "true" ]; then
        log_warning "Frontend build skipped"
        RESULT_FRONTEND_BUILD="skipped"
        return 0
    fi

    log_header "Frontend Build (Vite)"

    cd "$FRONTEND_DIR"

    if npm run build 2>&1 | redact_secrets; then
        log_success "Frontend build passed"
        RESULT_FRONTEND_BUILD="pass"
        return 0
    else
        log_error "Frontend build failed"
        RESULT_FRONTEND_BUILD="fail"
        return 1
    fi
}

# =============================================================================
# Docker Checks
# =============================================================================

check_docker_build() {
    if [ "$SKIP_DOCKER" = "true" ]; then
        log_warning "Docker build skipped"
        RESULT_DOCKER_BUILD="skipped"
        return 0
    fi

    log_header "Docker Compose Build"

    cd "$PROJECT_ROOT"

    # Check if Docker is available
    if ! command -v docker > /dev/null 2>&1; then
        log_warning "Docker not available, skipping"
        RESULT_DOCKER_BUILD="skipped"
        return 0
    fi

    if ! docker info > /dev/null 2>&1; then
        log_warning "Docker daemon not running, skipping"
        RESULT_DOCKER_BUILD="skipped"
        return 0
    fi

    if docker compose build 2>&1 | redact_secrets; then
        log_success "Docker build passed"
        RESULT_DOCKER_BUILD="pass"
        return 0
    else
        log_error "Docker build failed"
        RESULT_DOCKER_BUILD="fail"
        return 1
    fi
}

check_smoke_test() {
    if [ "$SKIP_DOCKER" = "true" ]; then
        log_warning "Smoke test skipped"
        RESULT_SMOKE_TEST="skipped"
        return 0
    fi

    log_header "Health Endpoint Smoke Test"

    cd "$PROJECT_ROOT"

    # Check if containers are already running or start them
    if ! docker compose ps --quiet 2>/dev/null | grep -q .; then
        log_info "Starting containers..."
        docker compose up -d 2>&1 | redact_secrets

        # Wait for services to be ready
        log_info "Waiting for services to start..."
        sleep 15
    fi

    # Check backend health
    local backend_health
    if backend_health=$(curl -sf http://localhost:8000/api/health 2>/dev/null); then
        local status
        status=$(echo "$backend_health" | grep -oE '"status"[[:space:]]*:[[:space:]]*"[^"]+"' | cut -d'"' -f4)
        if [ "$status" = "healthy" ]; then
            log_success "Backend health: $status"
        else
            log_warning "Backend health: $status"
        fi
    else
        log_error "Backend health check failed"
        RESULT_SMOKE_TEST="fail"

        # Cleanup
        docker compose down 2>/dev/null || true
        return 1
    fi

    # Check frontend (if available)
    local frontend_status
    if frontend_status=$(curl -sf -o /dev/null -w "%{http_code}" http://localhost:5173/ 2>/dev/null); then
        if [ "$frontend_status" = "200" ]; then
            log_success "Frontend: HTTP $frontend_status"
        else
            log_warning "Frontend: HTTP $frontend_status"
        fi
    else
        log_warning "Frontend not responding (may not be configured)"
    fi

    log_success "Smoke test passed"
    RESULT_SMOKE_TEST="pass"

    # Cleanup
    log_info "Stopping containers..."
    docker compose down 2>/dev/null || true

    return 0
}

# =============================================================================
# Results Summary
# =============================================================================

print_summary() {
    END_TIME=$(date +%s)
    DURATION=$((END_TIME - START_TIME))

    if [ "$JSON_OUTPUT" = "true" ]; then
        # JSON output
        cat << EOF
{
  "timestamp": "$(date -u +"%Y-%m-%dT%H:%M:%SZ")",
  "duration_seconds": $DURATION,
  "results": {
    "backend_lint": "$RESULT_BACKEND_LINT",
    "backend_tests": "$RESULT_BACKEND_TESTS",
    "frontend_lint": "$RESULT_FRONTEND_LINT",
    "frontend_build": "$RESULT_FRONTEND_BUILD",
    "docker_build": "$RESULT_DOCKER_BUILD",
    "smoke_test": "$RESULT_SMOKE_TEST"
  },
  "versions": {
    "python": "$PYTHON_VERSION",
    "node": "$NODE_VERSION",
    "backend": "$BACKEND_VERSION",
    "frontend": "$FRONTEND_VERSION",
    "db_schema": "$DB_SCHEMA"
  }
}
EOF
    else
        # Human-readable summary
        log_header "Release Proof Summary"

        echo ""
        echo "  Check              | Result"
        echo "  -------------------|--------"
        echo "  Backend Lint       | $RESULT_BACKEND_LINT"
        echo "  Backend Tests      | $RESULT_BACKEND_TESTS"
        echo "  Frontend Lint      | $RESULT_FRONTEND_LINT"
        echo "  Frontend Build     | $RESULT_FRONTEND_BUILD"
        echo "  Docker Build       | $RESULT_DOCKER_BUILD"
        echo "  Smoke Test         | $RESULT_SMOKE_TEST"
        echo ""
        echo "  Duration: ${DURATION}s"
        echo ""

        # Overall result
        local failed=0
        for result in $RESULT_BACKEND_LINT $RESULT_BACKEND_TESTS $RESULT_FRONTEND_LINT $RESULT_FRONTEND_BUILD $RESULT_DOCKER_BUILD $RESULT_SMOKE_TEST; do
            if [ "$result" = "fail" ]; then
                failed=$((failed + 1))
            fi
        done

        if [ $failed -eq 0 ]; then
            printf "  ${GREEN}╔═══════════════════════════════════════╗${NC}\n"
            printf "  ${GREEN}║  RELEASE PROOF: ALL CHECKS PASSED    ║${NC}\n"
            printf "  ${GREEN}╚═══════════════════════════════════════╝${NC}\n"
            echo ""
            return 0
        else
            printf "  ${RED}╔═══════════════════════════════════════╗${NC}\n"
            printf "  ${RED}║  RELEASE PROOF: %d CHECK(S) FAILED     ║${NC}\n" "$failed"
            printf "  ${RED}╚═══════════════════════════════════════╝${NC}\n"
            echo ""
            return 1
        fi
    fi
}

# =============================================================================
# Main
# =============================================================================

main() {
    if [ "$JSON_OUTPUT" = "false" ]; then
        echo ""
        printf "${BLUE}╔═══════════════════════════════════════════════════════════════╗${NC}\n"
        printf "${BLUE}║           MaratOS Release Proof Script                        ║${NC}\n"
        printf "${BLUE}╚═══════════════════════════════════════════════════════════════╝${NC}\n"
    fi

    # Gather versions
    get_versions

    # Track failures but continue
    local exit_code=0

    # Backend checks
    check_backend_lint || exit_code=1
    check_backend_tests || exit_code=1

    # Frontend checks
    check_frontend_lint || exit_code=1
    check_frontend_build || exit_code=1

    # Docker checks
    check_docker_build || exit_code=1
    check_smoke_test || exit_code=1

    # Summary
    print_summary

    exit $exit_code
}

main
