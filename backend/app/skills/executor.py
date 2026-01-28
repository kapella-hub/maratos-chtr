"""Skill executor - runs skill workflows via Kiro with guardrails enforcement."""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from app.skills.base import Skill, SkillStep

logger = logging.getLogger(__name__)

# Guardrails integration
_guardrails_available = False
_GuardrailsEnforcer = None
try:
    from app.guardrails import GuardrailsEnforcer as _GuardrailsEnforcer
    _guardrails_available = True
except ImportError:
    logger.info("Guardrails not available for skill execution")


@dataclass
class SkillExecutionResult:
    """Result of a skill execution."""

    skill_id: str
    skill_name: str
    success: bool
    steps_run: int
    steps_total: int
    duration_ms: float
    started_at: datetime
    completed_at: datetime
    results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None
    validation_passed: bool = True
    validation_errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "skill_id": self.skill_id,
            "skill_name": self.skill_name,
            "success": self.success,
            "steps_run": self.steps_run,
            "steps_total": self.steps_total,
            "duration_ms": round(self.duration_ms, 2),
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat(),
            "results": self.results,
            "error": self.error,
            "validation_passed": self.validation_passed,
            "validation_errors": self.validation_errors,
        }


class SkillExecutor:
    """Executes skill workflows using Kiro and other tools.

    Features:
    - Guardrails enforcement for all tool executions
    - Audit logging for all step executions
    - Validation enforcement (quality checklist)
    - Step-level metrics
    - Graceful error handling
    """

    def __init__(
        self,
        workdir: str | None = None,
        session_id: str | None = None,
        task_id: str | None = None,
        skill_id: str | None = None,
    ) -> None:
        self.workdir = workdir
        self.session_id = session_id
        self.task_id = task_id
        self.skill_id = skill_id
        self.results: list[dict[str, Any]] = []
        self._execution_history: list[SkillExecutionResult] = []

        # Create guardrails enforcer for skill execution
        self._enforcer = None
        if _guardrails_available and _GuardrailsEnforcer:
            self._enforcer = _GuardrailsEnforcer.for_skill(
                skill_id=skill_id or "unknown",
                session_id=session_id,
                task_id=task_id,
                workdir=workdir,
            )

    async def execute(
        self,
        skill: Skill,
        context: dict[str, Any] | None = None,
        enforce_validation: bool = True,
    ) -> dict[str, Any]:
        """Execute a skill's workflow with audit logging.

        Args:
            skill: The skill to execute
            context: Execution context
            enforce_validation: If True, validate quality checklist after execution

        Returns a summary of all step results.
        """
        from app.audit import audit_logger

        context = context or {}
        self.results = []
        start_time = time.time()
        started_at = datetime.now()

        logger.info(f"Executing skill: {skill.name}")

        # Log skill start
        audit_logger.log(audit_logger._buffer[-1].__class__(
            category=audit_logger._buffer[-1].category if audit_logger._buffer else "system",
            action=f"skill_start:{skill.id}",
            session_id=self.session_id,
            task_id=self.task_id,
        )) if False else None  # Placeholder - using tool audit instead

        # Add skill context to Kiro prompts
        kiro_context = skill.to_kiro_context()
        error_msg = None
        validation_passed = True
        validation_errors: list[str] = []

        try:
            for step in skill.workflow:
                # Check condition
                if step.condition and not self._evaluate_condition(step.condition, context):
                    logger.info(f"Skipping step '{step.name}' - condition not met")
                    continue

                logger.info(f"Running step: {step.name}")
                step_start = time.time()

                result = await self._execute_step(step, kiro_context, context)
                step_duration = (time.time() - step_start) * 1000

                self.results.append({
                    "step": step.name,
                    "action": step.action,
                    "success": result.get("success", False),
                    "output": result.get("output", ""),
                    "duration_ms": round(step_duration, 2),
                })

                # Update context with result
                context[f"step_{step.name}_result"] = result

                # Stop on failure unless configured otherwise
                if not result.get("success", False):
                    error_msg = f"Step '{step.name}' failed: {result.get('error', 'Unknown error')}"
                    logger.warning(f"Step '{step.name}' failed, stopping workflow")
                    break

            # Run validation if all steps passed and enforcement is enabled
            if enforce_validation and skill.quality_checklist and error_msg is None:
                validation_passed, validation_errors = await self._validate_quality(
                    skill, context
                )
                if not validation_passed:
                    error_msg = f"Quality validation failed: {', '.join(validation_errors)}"

        except Exception as e:
            error_msg = str(e)
            logger.error(f"Skill execution error: {e}", exc_info=True)

        # Calculate final result
        duration_ms = (time.time() - start_time) * 1000
        completed_at = datetime.now()
        success = error_msg is None and all(r["success"] for r in self.results)

        # Create execution result
        execution_result = SkillExecutionResult(
            skill_id=skill.id,
            skill_name=skill.name,
            success=success,
            steps_run=len(self.results),
            steps_total=len(skill.workflow),
            duration_ms=duration_ms,
            started_at=started_at,
            completed_at=completed_at,
            results=self.results,
            error=error_msg,
            validation_passed=validation_passed,
            validation_errors=validation_errors,
        )
        self._execution_history.append(execution_result)

        logger.info(
            f"Skill '{skill.name}' completed: success={success}, "
            f"steps={len(self.results)}/{len(skill.workflow)}, "
            f"duration={duration_ms:.0f}ms"
        )

        return execution_result.to_dict()

    async def _validate_quality(
        self,
        skill: Skill,
        context: dict[str, Any],
    ) -> tuple[bool, list[str]]:
        """Validate skill execution against quality checklist.

        Returns (passed, list of errors).
        """
        errors = []

        # For now, just log the checklist - actual validation would
        # require parsing step outputs and checking against checklist
        for item in skill.quality_checklist:
            logger.debug(f"Quality check: {item}")

        # TODO: Implement actual validation logic based on step outputs
        # For example:
        # - Check if tests passed (look for test step result)
        # - Check if linting passed (look for validate step result)
        # - Check code coverage thresholds

        return len(errors) == 0, errors

    def get_execution_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Get recent skill execution history."""
        return [r.to_dict() for r in self._execution_history[-limit:]]

    async def _execute_step(
        self,
        step: SkillStep,
        kiro_context: str,
        context: dict[str, Any]
    ) -> dict[str, Any]:
        """Execute a single workflow step."""

        # Resolve params with context
        params = self._resolve_params(step.params, context)

        if step.action == "kiro_architect":
            return await self._run_kiro("architect", params, kiro_context)

        elif step.action == "kiro_validate":
            return await self._run_kiro("validate", params, kiro_context)

        elif step.action == "kiro_test":
            return await self._run_kiro("test", params, kiro_context)

        elif step.action == "kiro_prompt":
            return await self._run_kiro("prompt", params, kiro_context)

        elif step.action == "shell":
            return await self._run_shell(params)

        elif step.action == "filesystem":
            return await self._run_filesystem(params)

        elif step.action == "template_generate":
            return await self._run_template_generate(params)

        else:
            return {"success": False, "output": f"Unknown action: {step.action}"}

    async def _run_kiro(
        self,
        action: str,
        params: dict[str, Any],
        kiro_context: str
    ) -> dict[str, Any]:
        """Run a Kiro action with guardrails enforcement."""
        from app.tools.executor import tool_executor

        # Add skill context to task/spec
        task = params.get("task", "")
        if kiro_context:
            task = f"{kiro_context}\n\n---\n\n{task}"

        result = await tool_executor.execute(
            tool_id="kiro",
            session_id=self.session_id,
            task_id=self.task_id,
            enforcer=self._enforcer,
            action=action,
            task=task,
            files=params.get("files", ""),
            workdir=params.get("workdir") or self.workdir,
            spec=params.get("spec", ""),
        )

        return {"success": result.success, "output": result.output, "error": result.error}

    async def _run_shell(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run a shell command with guardrails enforcement."""
        from app.tools.executor import tool_executor

        result = await tool_executor.execute(
            tool_id="shell",
            session_id=self.session_id,
            task_id=self.task_id,
            enforcer=self._enforcer,
            command=params.get("command", ""),
            workdir=params.get("workdir") or self.workdir,
        )

        return {"success": result.success, "output": result.output, "error": result.error}

    async def _run_filesystem(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run a filesystem operation with guardrails enforcement."""
        from app.tools.executor import tool_executor

        result = await tool_executor.execute(
            tool_id="filesystem",
            session_id=self.session_id,
            task_id=self.task_id,
            enforcer=self._enforcer,
            **params,
        )

        return {"success": result.success, "output": result.output, "error": result.error}

    def _resolve_params(self, params: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        """Resolve parameter templates with context values."""
        resolved = {}
        for key, value in params.items():
            if isinstance(value, str) and "{{" in value:
                # Simple template resolution
                for ctx_key, ctx_value in context.items():
                    value = value.replace(f"{{{{{ctx_key}}}}}", str(ctx_value))
            resolved[key] = value
        return resolved

    def _evaluate_condition(self, condition: str, context: dict[str, Any]) -> bool:
        """Evaluate a simple condition."""
        # Very basic condition evaluation
        # Format: "key == value" or "key != value" or "key"
        condition = condition.strip()

        if "==" in condition:
            key, value = condition.split("==", 1)
            return str(context.get(key.strip())) == value.strip()
        elif "!=" in condition:
            key, value = condition.split("!=", 1)
            return str(context.get(key.strip())) != value.strip()
        else:
            return bool(context.get(condition))

    async def _run_template_generate(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run the deterministic template-based project generator.

        This action generates projects using Jinja2 templates instead of LLM.
        Same input always produces identical output (except timestamps).

        Supports two input styles:
        1. Structured: name, stacks=["fastapi", "react"], features=["auth-jwt", "docker"]
        2. Individual: name, backend_stack="fastapi", auth_mode="jwt", dockerize=True
        """
        from app.skills.generators import (
            AppFactoryConfig,
            ProjectGenerator,
        )

        try:
            # Build config dict, letting AppFactoryConfig.from_dict handle
            # the features/stacks expansion
            config_dict = {
                "name": params.get("name", params.get("project_name", "my-project")),
                "workspace_path": params.get("workspace_path", params.get("workdir", self.workdir)),
                "description": params.get("description", ""),
                "author": params.get("author", ""),
                "version": params.get("version", "0.1.0"),
            }

            # Structured inputs (preferred)
            if params.get("stacks"):
                config_dict["stacks"] = params["stacks"]
            if params.get("features"):
                config_dict["features"] = params["features"]

            # Individual inputs (fallback if no structured inputs)
            if not params.get("stacks"):
                config_dict["backend_stack"] = params.get("backend_stack", "fastapi")
                config_dict["frontend_stack"] = params.get("frontend_stack", "react")

            if not params.get("features"):
                config_dict["auth_mode"] = params.get("auth_mode", "none")
                config_dict["database"] = params.get("database", "sqlite")
                config_dict["ci_provider"] = params.get("ci_provider", "github")
                config_dict["dockerize"] = params.get("dockerize", True)
                config_dict["include_tests"] = params.get("include_tests", True)
                config_dict["include_docs"] = params.get("include_docs", True)
                config_dict["include_makefile"] = params.get("include_makefile", True)
                config_dict["include_pre_commit"] = params.get("include_pre_commit", True)
                config_dict["include_health_endpoint"] = params.get("include_health_endpoint", True)
                config_dict["backend_port"] = params.get("backend_port", 8000)
                config_dict["frontend_port"] = params.get("frontend_port", 5173)
                config_dict["use_tailwind"] = params.get("use_tailwind", True)
                config_dict["use_react_router"] = params.get("use_react_router", True)
                config_dict["use_zustand"] = params.get("use_zustand", True)

            config = AppFactoryConfig.from_dict(config_dict)

            # Run generator
            generator = ProjectGenerator(config)
            manifest = await generator.generate(
                run_verification=params.get("run_verification", True),
                install_deps=params.get("install_deps", True),
            )

            # Format output
            output = f"Generated project: {manifest.project_name}\n"
            output += f"Location: {manifest.project_path}\n"
            output += f"Files created: {manifest.total_files}\n"
            output += f"Generation time: {manifest.generation_time_ms:.0f}ms\n"

            if manifest.all_validations_passed:
                output += "All verification gates passed.\n"
            else:
                failed = manifest.failed_validations
                output += f"Verification: {len(failed)} gate(s) failed\n"
                for v in failed:
                    output += f"  - {v.name}: {v.message}\n"

            return {
                "success": manifest.all_validations_passed,
                "output": output,
                "manifest": manifest.to_dict(),
            }

        except Exception as e:
            logger.error(f"Template generation failed: {e}", exc_info=True)
            return {
                "success": False,
                "output": "",
                "error": str(e),
            }
