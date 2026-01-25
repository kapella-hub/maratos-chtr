"""Skill executor - runs skill workflows via Kiro."""

import logging
from typing import Any

from app.skills.base import Skill, SkillStep
from app.tools import registry as tool_registry

logger = logging.getLogger(__name__)


class SkillExecutor:
    """Executes skill workflows using Kiro and other tools."""
    
    def __init__(self, workdir: str | None = None) -> None:
        self.workdir = workdir
        self.results: list[dict[str, Any]] = []
    
    async def execute(self, skill: Skill, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Execute a skill's workflow.
        
        Returns a summary of all step results.
        """
        context = context or {}
        self.results = []
        
        logger.info(f"Executing skill: {skill.name}")
        
        # Add skill context to Kiro prompts
        kiro_context = skill.to_kiro_context()
        
        for step in skill.workflow:
            # Check condition
            if step.condition and not self._evaluate_condition(step.condition, context):
                logger.info(f"Skipping step '{step.name}' - condition not met")
                continue
            
            logger.info(f"Running step: {step.name}")
            
            result = await self._execute_step(step, kiro_context, context)
            self.results.append({
                "step": step.name,
                "action": step.action,
                "success": result.get("success", False),
                "output": result.get("output", ""),
            })
            
            # Update context with result
            context[f"step_{step.name}_result"] = result
            
            # Stop on failure unless configured otherwise
            if not result.get("success", False):
                logger.warning(f"Step '{step.name}' failed, stopping workflow")
                break
        
        return {
            "skill": skill.id,
            "steps_run": len(self.results),
            "success": all(r["success"] for r in self.results),
            "results": self.results,
        }
    
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
        
        else:
            return {"success": False, "output": f"Unknown action: {step.action}"}
    
    async def _run_kiro(
        self, 
        action: str, 
        params: dict[str, Any],
        kiro_context: str
    ) -> dict[str, Any]:
        """Run a Kiro action."""
        kiro = tool_registry.get("kiro")
        if not kiro:
            return {"success": False, "output": "Kiro tool not available"}
        
        # Add skill context to task/spec
        task = params.get("task", "")
        if kiro_context:
            task = f"{kiro_context}\n\n---\n\n{task}"
        
        result = await kiro.execute(
            action=action,
            task=task,
            files=params.get("files", ""),
            workdir=params.get("workdir") or self.workdir,
            spec=params.get("spec", ""),
        )
        
        return {"success": result.success, "output": result.output, "error": result.error}
    
    async def _run_shell(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run a shell command."""
        shell = tool_registry.get("shell")
        if not shell:
            return {"success": False, "output": "Shell tool not available"}
        
        result = await shell.execute(
            command=params.get("command", ""),
            workdir=params.get("workdir") or self.workdir,
        )
        
        return {"success": result.success, "output": result.output, "error": result.error}
    
    async def _run_filesystem(self, params: dict[str, Any]) -> dict[str, Any]:
        """Run a filesystem operation."""
        fs = tool_registry.get("filesystem")
        if not fs:
            return {"success": False, "output": "Filesystem tool not available"}
        
        result = await fs.execute(**params)
        
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
