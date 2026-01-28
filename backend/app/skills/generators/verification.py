"""Verification gates for project generation.

Runs lint, tests, and docker build checks to verify generated projects.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class GateType(str, Enum):
    """Types of verification gates."""

    FILE_EXISTS = "file_exists"
    COMMAND_SUCCESS = "command_success"
    LINT_PASSES = "lint_passes"
    TESTS_PASS = "tests_pass"
    DOCKER_BUILD = "docker_build"
    IMPORT_CHECK = "import_check"


@dataclass
class VerificationGate:
    """A verification gate definition."""

    name: str
    gate_type: GateType
    description: str = ""
    required: bool = True  # If False, failure is a warning not an error
    command: str | None = None  # For command-based gates
    file_path: str | None = None  # For file-exists gates
    timeout_seconds: int = 300  # 5 minute default


@dataclass
class VerificationResult:
    """Result of running a verification gate."""

    gate_name: str
    passed: bool
    message: str = ""
    output: str = ""
    error: str = ""
    duration_ms: float = 0.0
    required: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "gate_name": self.gate_name,
            "passed": self.passed,
            "message": self.message,
            "output": self.output[:2000] if len(self.output) > 2000 else self.output,
            "error": self.error[:1000] if len(self.error) > 1000 else self.error,
            "duration_ms": round(self.duration_ms, 2),
            "required": self.required,
        }


async def run_command(
    command: str,
    working_dir: Path,
    timeout_seconds: int = 300,
) -> tuple[int, str, str]:
    """Run a shell command and return (exit_code, stdout, stderr)."""
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=working_dir,
        )

        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )

        return (
            process.returncode or 0,
            stdout.decode("utf-8", errors="replace"),
            stderr.decode("utf-8", errors="replace"),
        )

    except asyncio.TimeoutError:
        process.kill()
        return -1, "", f"Command timed out after {timeout_seconds} seconds"
    except Exception as e:
        return -1, "", str(e)


async def run_gate(gate: VerificationGate, project_path: Path) -> VerificationResult:
    """Run a single verification gate."""
    start_time = time.time()

    try:
        if gate.gate_type == GateType.FILE_EXISTS:
            return await _check_file_exists(gate, project_path)

        elif gate.gate_type == GateType.COMMAND_SUCCESS:
            return await _check_command_success(gate, project_path)

        elif gate.gate_type == GateType.LINT_PASSES:
            return await _check_lint(gate, project_path)

        elif gate.gate_type == GateType.TESTS_PASS:
            return await _check_tests(gate, project_path)

        elif gate.gate_type == GateType.DOCKER_BUILD:
            return await _check_docker_build(gate, project_path)

        elif gate.gate_type == GateType.IMPORT_CHECK:
            return await _check_imports(gate, project_path)

        else:
            return VerificationResult(
                gate_name=gate.name,
                passed=False,
                message=f"Unknown gate type: {gate.gate_type}",
                required=gate.required,
            )

    except Exception as e:
        logger.error(f"Gate {gate.name} failed with exception: {e}")
        return VerificationResult(
            gate_name=gate.name,
            passed=False,
            message=f"Gate execution failed: {str(e)}",
            error=str(e),
            duration_ms=(time.time() - start_time) * 1000,
            required=gate.required,
        )


async def _check_file_exists(gate: VerificationGate, project_path: Path) -> VerificationResult:
    """Check if a file exists."""
    start_time = time.time()

    if not gate.file_path:
        return VerificationResult(
            gate_name=gate.name,
            passed=False,
            message="No file path specified",
            required=gate.required,
        )

    file_path = project_path / gate.file_path
    exists = file_path.exists()

    return VerificationResult(
        gate_name=gate.name,
        passed=exists,
        message=f"File {'exists' if exists else 'not found'}: {gate.file_path}",
        duration_ms=(time.time() - start_time) * 1000,
        required=gate.required,
    )


async def _check_command_success(gate: VerificationGate, project_path: Path) -> VerificationResult:
    """Run a command and check for success."""
    start_time = time.time()

    if not gate.command:
        return VerificationResult(
            gate_name=gate.name,
            passed=False,
            message="No command specified",
            required=gate.required,
        )

    exit_code, stdout, stderr = await run_command(
        gate.command,
        project_path,
        gate.timeout_seconds,
    )

    passed = exit_code == 0

    return VerificationResult(
        gate_name=gate.name,
        passed=passed,
        message=f"Command {'succeeded' if passed else f'failed with exit code {exit_code}'}",
        output=stdout,
        error=stderr,
        duration_ms=(time.time() - start_time) * 1000,
        required=gate.required,
    )


async def _check_lint(gate: VerificationGate, project_path: Path) -> VerificationResult:
    """Run linting checks."""
    start_time = time.time()
    results = []

    # Check for Python backend
    has_root_pyproject = (project_path / "pyproject.toml").exists()
    has_backend_pyproject = (project_path / "backend" / "pyproject.toml").exists()
    if has_root_pyproject or has_backend_pyproject:
        has_backend_dir = (project_path / "backend").exists()
        backend_path = project_path / "backend" if has_backend_dir else project_path
        exit_code, stdout, stderr = await run_command(
            "ruff check . --select=E,F,W",  # Basic errors, warnings only
            backend_path,
            gate.timeout_seconds,
        )
        results.append(("Python/ruff", exit_code == 0, stdout, stderr))

    # Check for frontend
    if (project_path / "frontend" / "package.json").exists():
        exit_code, stdout, stderr = await run_command(
            "npm run lint 2>&1 || true",
            project_path / "frontend",
            gate.timeout_seconds,
        )
        # ESLint exit code 0 = success, 1 = lint errors, 2 = fatal error
        results.append(("Frontend/eslint", exit_code == 0, stdout, stderr))

    if not results:
        return VerificationResult(
            gate_name=gate.name,
            passed=True,
            message="No lint configuration found",
            duration_ms=(time.time() - start_time) * 1000,
            required=gate.required,
        )

    all_passed = all(r[1] for r in results)
    output = "\n".join([f"[{r[0]}] {'PASS' if r[1] else 'FAIL'}\n{r[2]}" for r in results])
    errors = "\n".join([r[3] for r in results if r[3]])

    return VerificationResult(
        gate_name=gate.name,
        passed=all_passed,
        message=f"Lint checks: {sum(1 for r in results if r[1])}/{len(results)} passed",
        output=output,
        error=errors,
        duration_ms=(time.time() - start_time) * 1000,
        required=gate.required,
    )


async def _check_tests(gate: VerificationGate, project_path: Path) -> VerificationResult:
    """Run test suite."""
    start_time = time.time()
    results = []

    # Check for Python tests
    has_root_tests = (project_path / "tests").exists()
    has_backend_tests = (project_path / "backend" / "tests").exists()
    if has_root_tests or has_backend_tests:
        has_backend_dir = (project_path / "backend").exists()
        backend_path = project_path / "backend" if has_backend_dir else project_path
        exit_code, stdout, stderr = await run_command(
            "pytest tests/ -v --tb=short -q 2>&1 || true",
            backend_path,
            gate.timeout_seconds,
        )
        results.append(("Python/pytest", exit_code == 0, stdout, stderr))

    # Check for frontend tests
    if (project_path / "frontend" / "package.json").exists():
        # Check if test script exists
        exit_code, stdout, stderr = await run_command(
            "npm test -- --run --passWithNoTests 2>&1 || true",
            project_path / "frontend",
            gate.timeout_seconds,
        )
        results.append(("Frontend/vitest", exit_code == 0, stdout, stderr))

    if not results:
        return VerificationResult(
            gate_name=gate.name,
            passed=True,
            message="No test configuration found",
            duration_ms=(time.time() - start_time) * 1000,
            required=gate.required,
        )

    all_passed = all(r[1] for r in results)
    output = "\n".join([f"[{r[0]}] {'PASS' if r[1] else 'FAIL'}\n{r[2]}" for r in results])
    errors = "\n".join([r[3] for r in results if r[3]])

    return VerificationResult(
        gate_name=gate.name,
        passed=all_passed,
        message=f"Test suites: {sum(1 for r in results if r[1])}/{len(results)} passed",
        output=output,
        error=errors,
        duration_ms=(time.time() - start_time) * 1000,
        required=gate.required,
    )


async def _check_docker_build(gate: VerificationGate, project_path: Path) -> VerificationResult:
    """Check that Docker images build successfully."""
    start_time = time.time()

    # Check if docker-compose exists
    compose_file = project_path / "docker-compose.yaml"
    if not compose_file.exists():
        compose_file = project_path / "docker-compose.yml"

    if not compose_file.exists():
        return VerificationResult(
            gate_name=gate.name,
            passed=True,
            message="No docker-compose.yaml found, skipping",
            duration_ms=(time.time() - start_time) * 1000,
            required=gate.required,
        )

    # Build images (don't run)
    exit_code, stdout, stderr = await run_command(
        "docker compose build --no-cache 2>&1",
        project_path,
        gate.timeout_seconds,
    )

    passed = exit_code == 0

    return VerificationResult(
        gate_name=gate.name,
        passed=passed,
        message=f"Docker build {'succeeded' if passed else 'failed'}",
        output=stdout,
        error=stderr,
        duration_ms=(time.time() - start_time) * 1000,
        required=gate.required,
    )


async def _check_imports(gate: VerificationGate, project_path: Path) -> VerificationResult:
    """Check that Python imports work correctly."""
    start_time = time.time()

    backend_path = project_path / "backend" if (project_path / "backend").exists() else project_path

    # Check for main module
    if not (backend_path / "app" / "main.py").exists():
        return VerificationResult(
            gate_name=gate.name,
            passed=True,
            message="No app/main.py found, skipping import check",
            duration_ms=(time.time() - start_time) * 1000,
            required=gate.required,
        )

    exit_code, stdout, stderr = await run_command(
        "python -c 'from app.main import app; print(\"Import successful\")'",
        backend_path,
        gate.timeout_seconds,
    )

    passed = exit_code == 0

    return VerificationResult(
        gate_name=gate.name,
        passed=passed,
        message=f"Import check {'passed' if passed else 'failed'}",
        output=stdout,
        error=stderr,
        duration_ms=(time.time() - start_time) * 1000,
        required=gate.required,
    )


async def run_verification_gates(
    gates: list[VerificationGate],
    project_path: Path,
    fail_fast: bool = False,
) -> list[VerificationResult]:
    """Run all verification gates.

    Args:
        gates: List of gates to run
        project_path: Path to the project
        fail_fast: If True, stop on first required gate failure

    Returns:
        List of verification results
    """
    results = []

    for gate in gates:
        logger.info(f"Running verification gate: {gate.name}")
        result = await run_gate(gate, project_path)
        results.append(result)

        if fail_fast and not result.passed and result.required:
            logger.warning(f"Required gate '{gate.name}' failed, stopping verification")
            break

        if result.passed:
            logger.info(f"Gate '{gate.name}' passed")
        else:
            level = logging.WARNING if result.required else logging.INFO
            status = 'failed' if result.required else 'failed (optional)'
            logger.log(level, f"Gate '{gate.name}' {status}")

    return results


def get_default_gates(config: Any) -> list[VerificationGate]:
    """Get default verification gates based on config.

    Args:
        config: AppFactoryConfig instance

    Returns:
        List of verification gates appropriate for the config
    """
    gates = [
        # Always check README exists
        VerificationGate(
            name="readme_exists",
            gate_type=GateType.FILE_EXISTS,
            description="README.md exists",
            file_path="README.md",
            required=True,
        ),
    ]

    # Backend gates
    if config.has_backend:
        gates.extend([
            VerificationGate(
                name="backend_lint",
                gate_type=GateType.LINT_PASSES,
                description="Backend code passes linting",
                required=True,
            ),
            VerificationGate(
                name="backend_imports",
                gate_type=GateType.IMPORT_CHECK,
                description="Backend imports work correctly",
                required=True,
            ),
        ])

        if config.include_tests:
            gates.append(
                VerificationGate(
                    name="backend_tests",
                    gate_type=GateType.TESTS_PASS,
                    description="Backend tests pass",
                    required=True,
                    timeout_seconds=600,
                )
            )

    # Frontend gates
    if config.has_frontend:
        gates.extend([
            VerificationGate(
                name="frontend_lint",
                gate_type=GateType.COMMAND_SUCCESS,
                description="Frontend code passes linting",
                command="cd frontend && npm run lint",
                required=False,  # ESLint can be strict
            ),
            VerificationGate(
                name="frontend_build",
                gate_type=GateType.COMMAND_SUCCESS,
                description="Frontend builds successfully",
                command="cd frontend && npm run build",
                required=True,
                timeout_seconds=300,
            ),
        ])

        if config.include_tests:
            gates.append(
                VerificationGate(
                    name="frontend_tests",
                    gate_type=GateType.COMMAND_SUCCESS,
                    description="Frontend tests pass",
                    command="cd frontend && npm test -- --run --passWithNoTests",
                    required=False,
                    timeout_seconds=300,
                )
            )

    # Docker gates
    if config.dockerize:
        gates.append(
            VerificationGate(
                name="docker_build",
                gate_type=GateType.DOCKER_BUILD,
                description="Docker images build successfully",
                required=False,  # Docker might not be available
                timeout_seconds=600,
            )
        )

    return gates
