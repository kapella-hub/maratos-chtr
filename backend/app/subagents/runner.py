"""Subagent runner - executes agent tasks in isolation."""

import logging
from typing import Any

from app.subagents.manager import SubagentTask, subagent_manager

logger = logging.getLogger(__name__)


class SubagentRunner:
    """Runs subagent tasks using specified agents."""
    
    def __init__(self) -> None:
        pass
    
    async def run_task(
        self,
        task_description: str,
        agent_id: str = "mo",
        context: dict[str, Any] | None = None,
        callback_session: str | None = None,
    ) -> SubagentTask:
        """Spawn a subagent to complete a task.
        
        Args:
            task_description: What the agent should do
            agent_id: Which agent to use (mo, architect, reviewer)
            context: Additional context for the agent
            callback_session: Session to notify when done
        
        Returns:
            The spawned SubagentTask (can be monitored)
        """
        async def work_fn(task: SubagentTask) -> dict[str, Any]:
            """The actual work function."""
            # Import here to avoid circular imports
            from app.agents import agent_registry
            from app.agents.base import Message
            from app.memory.manager import memory_manager
            
            task.log(f"Using agent: {agent_id}")
            
            agent = agent_registry.get(agent_id)
            if not agent:
                raise ValueError(f"Agent not found: {agent_id}")
            
            # Get memory context
            task.log("Retrieving relevant memories...")
            memory_context = await memory_manager.get_context(
                query=task_description,
                max_tokens=1000,
            )
            
            # Build messages
            messages = [
                Message(role="user", content=task_description)
            ]
            
            # Build context
            full_context = context or {}
            if memory_context:
                full_context["memory"] = memory_context
            
            # Run the agent
            task.log("Running agent...")
            task.progress = 0.3
            
            response_text = ""
            async for chunk in agent.chat(messages, full_context):
                response_text += chunk
                # Update progress based on response length (rough estimate)
                task.progress = min(0.9, 0.3 + len(response_text) / 5000)
            
            task.log(f"Agent response: {len(response_text)} chars")
            task.progress = 0.9
            
            # Store learnings in memory
            task.log("Storing learnings...")
            await memory_manager.remember(
                content=f"Task: {task_description}\nResult: {response_text[:500]}",
                memory_type="task",
                tags=["subagent", agent_id],
                importance=0.5,
            )
            
            return {
                "response": response_text,
                "agent_id": agent_id,
                "memory_context_used": bool(memory_context),
            }
        
        # Spawn the task
        task = await subagent_manager.spawn(
            name=f"Task: {task_description[:50]}...",
            description=task_description,
            agent_id=agent_id,
            work_fn=work_fn,
            callback_session=callback_session,
        )
        
        return task
    
    async def run_skill(
        self,
        skill_id: str,
        context: dict[str, Any] | None = None,
        callback_session: str | None = None,
    ) -> SubagentTask:
        """Run a skill as a subagent task."""
        from app.skills.base import skill_registry
        from app.skills.executor import SkillExecutor
        
        skill = skill_registry.get(skill_id)
        if not skill:
            raise ValueError(f"Skill not found: {skill_id}")
        
        async def work_fn(task: SubagentTask) -> dict[str, Any]:
            """Execute the skill."""
            task.log(f"Executing skill: {skill.name}")
            
            executor = SkillExecutor(workdir=context.get("workdir") if context else None)
            result = await executor.execute(skill, context)
            
            task.log(f"Skill completed: {result['steps_run']} steps")
            return result
        
        task = await subagent_manager.spawn(
            name=f"Skill: {skill.name}",
            description=f"Running skill: {skill.description}",
            agent_id="mo",
            work_fn=work_fn,
            callback_session=callback_session,
        )
        
        return task


# Global runner
subagent_runner = SubagentRunner()
