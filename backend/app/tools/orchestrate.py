"""Orchestration tool - lets MO spawn subagent tasks."""

from typing import Any

from app.tools.base import Tool, ToolParameter, ToolResult, registry
from app.subagents.runner import subagent_runner
from app.subagents.manager import subagent_manager, TaskStatus


class OrchestrateTool(Tool):
    """Tool for spawning and managing subagent tasks."""

    def __init__(self) -> None:
        super().__init__(
            id="orchestrate",
            name="Orchestrate",
            description="Spawn specialized subagents for complex tasks. Use for architecture design, code review, or parallel work.",
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action: spawn (start task), status (check task), list (show all), cancel",
                    enum=["spawn", "status", "list", "cancel"],
                ),
                ToolParameter(
                    name="task",
                    type="string",
                    description="Task description for the subagent (required for spawn)",
                    required=False,
                ),
                ToolParameter(
                    name="agent",
                    type="string",
                    description="Which agent: architect (design/planning), reviewer (code review), mo (general)",
                    required=False,
                    enum=["architect", "reviewer", "mo"],
                ),
                ToolParameter(
                    name="task_id",
                    type="string",
                    description="Task ID for status/cancel actions",
                    required=False,
                ),
                ToolParameter(
                    name="wait",
                    type="boolean",
                    description="If true, wait for task completion (default: false)",
                    required=False,
                    default=False,
                ),
            ],
        )
    
    async def execute(self, **kwargs: Any) -> ToolResult:
        action = kwargs.get("action", "spawn")
        
        if action == "spawn":
            return await self._spawn(kwargs)
        elif action == "status":
            return await self._status(kwargs)
        elif action == "list":
            return await self._list(kwargs)
        elif action == "cancel":
            return await self._cancel(kwargs)
        else:
            return ToolResult(success=False, error=f"Unknown action: {action}")
    
    async def _spawn(self, kwargs: dict) -> ToolResult:
        """Spawn a new subagent task."""
        task_desc = kwargs.get("task")
        if not task_desc:
            return ToolResult(success=False, error="Task description required")
        
        agent_id = kwargs.get("agent", "mo")
        wait = kwargs.get("wait", False)
        
        # Spawn the task
        task = await subagent_runner.run_task(
            task_description=task_desc,
            agent_id=agent_id,
            context=kwargs.get("context"),
        )
        
        if wait:
            # Wait for completion (with timeout)
            import asyncio
            timeout = 120  # 2 min max wait
            elapsed = 0
            
            while elapsed < timeout:
                current = subagent_manager.get(task.id)
                if current and current.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                    break
                await asyncio.sleep(1)
                elapsed += 1
            
            # Get final state
            task = subagent_manager.get(task.id)
            if not task:
                return ToolResult(success=False, error="Task disappeared")
            
            if task.status == TaskStatus.COMPLETED:
                result = task.result.get("response", "") if task.result else ""
                return ToolResult(
                    success=True,
                    output=f"✅ Task completed ({task.id})\n\n{result}"
                )
            else:
                return ToolResult(
                    success=False,
                    error=f"Task {task.status.value}: {task.error or 'unknown'}"
                )
        
        return ToolResult(
            success=True,
            output=f"🚀 Spawned subagent task: {task.id}\nAgent: {agent_id}\nTask: {task_desc[:100]}...\n\nUse `orchestrate status task_id={task.id}` to check progress."
        )
    
    async def _status(self, kwargs: dict) -> ToolResult:
        """Get status of a task."""
        task_id = kwargs.get("task_id")
        if not task_id:
            return ToolResult(success=False, error="task_id required")
        
        task = subagent_manager.get(task_id)
        if not task:
            return ToolResult(success=False, error=f"Task not found: {task_id}")
        
        status_emoji = {
            TaskStatus.PENDING: "⏳",
            TaskStatus.RUNNING: "🔄",
            TaskStatus.COMPLETED: "✅",
            TaskStatus.FAILED: "❌",
            TaskStatus.CANCELLED: "🚫",
        }
        
        output = f"""{status_emoji.get(task.status, '❓')} Task {task.id}
Status: {task.status.value}
Progress: {task.progress * 100:.0f}%
Agent: {task.agent_id}
"""
        
        if task.logs:
            output += f"\nLogs:\n" + "\n".join(task.logs[-5:])
        
        if task.status == TaskStatus.COMPLETED and task.result:
            response = task.result.get("response", "")
            output += f"\n\nResult:\n{response[:2000]}"
        
        if task.error:
            output += f"\n\nError: {task.error}"
        
        return ToolResult(success=True, output=output)
    
    async def _list(self, kwargs: dict) -> ToolResult:
        """List recent tasks."""
        tasks = subagent_manager.list_tasks(limit=10)
        
        if not tasks:
            return ToolResult(success=True, output="No subagent tasks found.")
        
        lines = ["Recent subagent tasks:", ""]
        for t in tasks:
            status_emoji = {
                TaskStatus.PENDING: "⏳",
                TaskStatus.RUNNING: "🔄", 
                TaskStatus.COMPLETED: "✅",
                TaskStatus.FAILED: "❌",
                TaskStatus.CANCELLED: "🚫",
            }
            lines.append(f"{status_emoji.get(t.status, '❓')} {t.id} | {t.agent_id} | {t.name[:40]}")
        
        return ToolResult(success=True, output="\n".join(lines))
    
    async def _cancel(self, kwargs: dict) -> ToolResult:
        """Cancel a running task."""
        task_id = kwargs.get("task_id")
        if not task_id:
            return ToolResult(success=False, error="task_id required")
        
        if await subagent_manager.cancel(task_id):
            return ToolResult(success=True, output=f"Cancelled task {task_id}")
        else:
            return ToolResult(success=False, error=f"Task {task_id} not running")


# Register the tool
registry.register(OrchestrateTool())
