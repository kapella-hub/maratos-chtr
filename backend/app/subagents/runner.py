"""Subagent runner - executes agent tasks in isolation."""

import logging
import re
from datetime import datetime
from typing import Any

from app.subagents.manager import SubagentTask, subagent_manager
from app.subagents.metrics import task_metrics

logger = logging.getLogger(__name__)

# Patterns for sub-goal tracking
GOAL_PATTERN = re.compile(r'\[GOAL:(\d+)\]\s*(.+?)(?=\[GOAL:|\[CHECKPOINT:|\[GOAL_DONE:|\Z)', re.DOTALL)
GOAL_DONE_PATTERN = re.compile(r'\[GOAL_DONE:(\d+)\]')
GOAL_FAILED_PATTERN = re.compile(r'\[GOAL_FAILED:(\d+)\]\s*(.+?)(?=\[|\Z)', re.DOTALL)
CHECKPOINT_PATTERN = re.compile(r'\[CHECKPOINT:(\w+)\]\s*(.+?)(?=\[|\Z)', re.DOTALL)

# Patterns for inter-agent communication
# [REQUEST:reviewer] Please review this code for security issues
REQUEST_PATTERN = re.compile(r'\[REQUEST:(\w+)\]\s*(.+?)(?=\[REQUEST:|\[RESPONSE:|\[GOAL|\[CHECKPOINT|\Z)', re.DOTALL)
# [REVIEW_REQUEST] is shorthand for [REQUEST:reviewer]
REVIEW_REQUEST_PATTERN = re.compile(r'\[REVIEW_REQUEST\]\s*(.+?)(?=\[|\Z)', re.DOTALL)

# Valid agents for requests
VALID_REQUEST_AGENTS = {"reviewer", "tester", "architect", "coder", "docs", "devops"}


def parse_goals(text: str, task: SubagentTask) -> None:
    """Parse and register goals from agent response."""
    for match in GOAL_PATTERN.finditer(text):
        goal_id = int(match.group(1))
        description = match.group(2).strip().split('\n')[0][:200]  # First line, max 200 chars
        # Only add if not already registered
        if not any(g.id == goal_id for g in task.goals):
            task.add_goal(goal_id, description)


def parse_goal_completions(text: str, task: SubagentTask) -> None:
    """Parse goal completion markers."""
    for match in GOAL_DONE_PATTERN.finditer(text):
        goal_id = int(match.group(1))
        task.complete_goal(goal_id)


def parse_goal_failures(text: str, task: SubagentTask) -> None:
    """Parse goal failure markers."""
    for match in GOAL_FAILED_PATTERN.finditer(text):
        goal_id = int(match.group(1))
        error = match.group(2).strip().split('\n')[0][:200]
        task.fail_goal(goal_id, error)


def parse_checkpoints(text: str, task: SubagentTask) -> None:
    """Parse checkpoint markers."""
    for match in CHECKPOINT_PATTERN.finditer(text):
        name = match.group(1)
        description = match.group(2).strip().split('\n')[0][:200]
        # Only add if not already registered
        if not any(c.name == name for c in task.checkpoints):
            task.add_checkpoint(name, description)


class AgentRequest:
    """A request from one agent to another."""

    def __init__(self, agent_type: str, request_text: str, request_id: str | None = None):
        self.agent_type = agent_type
        self.request_text = request_text.strip()
        self.request_id = request_id or f"req_{id(self)}"
        self.response: str | None = None
        self.completed = False

    def __repr__(self) -> str:
        return f"AgentRequest({self.agent_type}, {self.request_text[:50]}...)"


def parse_agent_requests(text: str, processed_positions: set[int]) -> list[AgentRequest]:
    """Parse inter-agent request markers from text.

    Args:
        text: The agent response text
        processed_positions: Set of already processed match positions to avoid duplicates

    Returns:
        List of new AgentRequest objects
    """
    requests = []

    # Parse [REQUEST:agent] markers
    for match in REQUEST_PATTERN.finditer(text):
        pos = match.start()
        if pos in processed_positions:
            continue
        processed_positions.add(pos)

        agent_type = match.group(1).lower()
        request_text = match.group(2).strip()

        if agent_type in VALID_REQUEST_AGENTS and request_text:
            requests.append(AgentRequest(agent_type, request_text))
            logger.info(f"Parsed request to {agent_type}: {request_text[:100]}...")

    # Parse [REVIEW_REQUEST] shorthand (maps to reviewer)
    for match in REVIEW_REQUEST_PATTERN.finditer(text):
        pos = match.start()
        if pos in processed_positions:
            continue
        processed_positions.add(pos)

        request_text = match.group(1).strip()
        if request_text:
            requests.append(AgentRequest("reviewer", request_text))
            logger.info(f"Parsed review request: {request_text[:100]}...")

    return requests


async def execute_agent_request(
    request: AgentRequest,
    parent_task: SubagentTask,
    context: dict[str, Any] | None = None,
) -> str:
    """Execute an inter-agent request and return the response.

    Args:
        request: The AgentRequest to execute
        parent_task: The parent task making the request
        context: Additional context to pass

    Returns:
        The response text from the requested agent
    """
    from app.agents import agent_registry
    from app.agents.base import Message

    parent_task.log(f"Requesting help from {request.agent_type}: {request.request_text[:50]}...")

    agent = agent_registry.get(request.agent_type)
    if not agent:
        error_msg = f"Agent not found: {request.agent_type}"
        parent_task.log(f"Request failed: {error_msg}")
        return f"[ERROR: {error_msg}]"

    # Build request message with context
    request_msg = f"""You are being consulted by another agent ({parent_task.agent_id}) who needs your help.

**Request:**
{request.request_text}

**Context:**
- Parent task: {parent_task.name}
- Current progress: {parent_task.progress:.0%}

Please provide a focused, actionable response. Keep it concise but complete."""

    messages = [Message(role="user", content=request_msg)]

    # Build context
    full_context = context or {}
    full_context["is_consultation"] = True
    full_context["parent_agent"] = parent_task.agent_id
    full_context["parent_task_id"] = parent_task.id

    # Run the consulted agent
    response_text = ""
    try:
        async for chunk in agent.chat(messages, full_context):
            response_text += chunk
    except Exception as e:
        error_msg = f"Consultation error: {e}"
        parent_task.log(error_msg)
        logger.error(f"Agent request failed: {e}", exc_info=True)
        return f"[ERROR: {error_msg}]"

    request.response = response_text
    request.completed = True
    parent_task.log(f"Received response from {request.agent_type}: {len(response_text)} chars")

    return response_text


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
            
            task.log(f"Using agent: {agent_id}")
            
            agent = agent_registry.get(agent_id)
            if not agent:
                raise ValueError(f"Agent not found: {agent_id}")
            
            # Memory is optional - don't fail if it doesn't work
            memory_context = None
            try:
                from app.memory.manager import memory_manager
                from app.memory import MemoryStorageError
                task.log("Retrieving relevant memories...")
                memory_context = await memory_manager.get_context(
                    query=task_description,
                    max_tokens=1000,
                )
            except MemoryStorageError as e:
                task.log(f"Memory storage error: {e}")
                logger.error(f"Subagent memory storage error: {e}", exc_info=True)
            except ImportError:
                task.log("Memory module not available")
            except Exception as e:
                task.log(f"Memory retrieval failed: {e}")
                logger.warning(f"Subagent memory retrieval error: {e}")
            
            # Build messages
            messages = [
                Message(role="user", content=task_description)
            ]
            
            # Build context - include task for skill auto-detection
            full_context = context or {}
            full_context["task"] = task_description  # For skill auto-selection
            if memory_context:
                full_context["memory"] = memory_context
            
            # Run the agent
            task.log("Running agent...")
            task.progress = 0.1

            response_text = ""
            chunk_count = 0
            last_parse_len = 0
            try:
                async for chunk in agent.chat(messages, full_context):
                    response_text += chunk
                    chunk_count += 1

                    # Track response for recovery
                    task.response_so_far = response_text

                    # Parse goals/checkpoints periodically (every 500 chars)
                    if len(response_text) - last_parse_len > 500:
                        parse_goals(response_text, task)
                        parse_goal_completions(response_text, task)
                        parse_goal_failures(response_text, task)
                        parse_checkpoints(response_text, task)
                        last_parse_len = len(response_text)

                    # Update progress based on goals if available, else response length
                    if task.goals:
                        completed = sum(1 for g in task.goals if g.status.value == "completed")
                        task.progress = min(0.95, 0.1 + (completed / len(task.goals)) * 0.85)
                    else:
                        task.progress = min(0.9, 0.1 + len(response_text) / 5000)

                    # Log periodically
                    if chunk_count % 50 == 0:
                        goals_info = f", goals: {len(task.goals)}" if task.goals else ""
                        task.log(f"Streaming: {len(response_text)} chars{goals_info}")
            except Exception as e:
                # Store partial response for recovery analysis
                task.response_so_far = response_text
                task.log(f"Agent error: {e}")
                logger.error(f"Subagent agent.chat error: {e}", exc_info=True)
                raise

            # Final parse for any remaining markers
            parse_goals(response_text, task)
            parse_goal_completions(response_text, task)
            parse_goal_failures(response_text, task)
            parse_checkpoints(response_text, task)

            goals_summary = ""
            if task.goals:
                completed = sum(1 for g in task.goals if g.status.value == "completed")
                goals_summary = f", {completed}/{len(task.goals)} goals completed"

            task.log(f"Agent response: {len(response_text)} chars{goals_summary}")
            task.progress = 0.9

            # Handle inter-agent requests
            processed_positions: set[int] = set()
            agent_requests = parse_agent_requests(response_text, processed_positions)
            request_responses: list[dict[str, Any]] = []

            if agent_requests:
                task.log(f"Processing {len(agent_requests)} inter-agent request(s)")

                for req in agent_requests:
                    task.log(f"Consulting {req.agent_type}...")
                    response = await execute_agent_request(req, task, context)
                    request_responses.append({
                        "agent": req.agent_type,
                        "request": req.request_text[:200],
                        "response": response[:500] if response else None,
                        "completed": req.completed,
                    })
                    task.progress = min(0.95, task.progress + 0.01)

            task.progress = 0.95
            
            # Store learnings in memory (optional)
            try:
                from app.memory.manager import memory_manager
                from app.memory import MemoryStorageError
                task.log("Storing learnings...")
                await memory_manager.remember(
                    content=f"Task: {task_description}\nResult: {response_text[:500]}",
                    memory_type="task",
                    tags=["subagent", agent_id],
                    importance=0.5,
                )
            except MemoryStorageError as e:
                task.log(f"Memory storage error: {e}")
                logger.error(f"Subagent memory storage error: {e}", exc_info=True)
            except ImportError:
                pass  # Memory module not available
            except Exception as e:
                task.log(f"Memory storage failed: {e}")
                logger.warning(f"Subagent memory storage error: {e}")
            
            return {
                "response": response_text,
                "agent_id": agent_id,
                "memory_context_used": bool(memory_context),
                "goals_total": len(task.goals),
                "goals_completed": sum(1 for g in task.goals if g.status.value == "completed"),
                "checkpoints": len(task.checkpoints),
                "agent_requests": request_responses,
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


    async def run_fallback_task(
        self,
        failed_task: SubagentTask,
        fallback_agent_id: str,
        context: dict[str, Any] | None = None,
    ) -> SubagentTask:
        """Spawn a fallback task after the original failed.

        Args:
            failed_task: The task that failed
            fallback_agent_id: Agent to use for fallback
            context: Additional context

        Returns:
            The spawned fallback SubagentTask
        """
        from app.subagents.recovery import _create_fallback_prompt, FailureContext, FailureType

        # Create failure context for fallback prompt generation
        goals_completed = sum(1 for g in failed_task.goals if g.status.value == "completed")
        last_checkpoint = failed_task.checkpoints[-1].name if failed_task.checkpoints else None

        failure_context = FailureContext(
            task_id=failed_task.id,
            agent_id=failed_task.agent_id,
            task_description=failed_task.description,
            failure_type=FailureType.AGENT_ERROR,
            error_message=failed_task.error or "Unknown error",
            attempt=failed_task.attempt,
            max_attempts=failed_task.max_attempts,
            started_at=failed_task.started_at or failed_task.created_at,
            failed_at=failed_task.completed_at or datetime.now(),
            duration_seconds=0,
            last_checkpoint=last_checkpoint,
            goals_completed=goals_completed,
            goals_total=len(failed_task.goals),
            response_so_far=failed_task.response_so_far,
        )

        fallback_prompt = _create_fallback_prompt(failure_context, fallback_agent_id)

        async def fallback_work_fn(task: SubagentTask) -> dict[str, Any]:
            """Work function for fallback task."""
            from app.agents import agent_registry
            from app.agents.base import Message

            task.log(f"Fallback task using agent: {fallback_agent_id}")

            agent = agent_registry.get(fallback_agent_id)
            if not agent:
                raise ValueError(f"Fallback agent not found: {fallback_agent_id}")

            messages = [Message(role="user", content=fallback_prompt)]

            full_context = context or {}
            full_context["is_fallback"] = True
            full_context["original_task_id"] = failed_task.id
            full_context["original_agent_id"] = failed_task.agent_id
            full_context["original_error"] = failed_task.error

            response_text = ""
            async for chunk in agent.chat(messages, full_context):
                response_text += chunk
                task.response_so_far = response_text
                task.progress = min(0.9, 0.1 + len(response_text) / 3000)

            task.log(f"Fallback response: {len(response_text)} chars")

            return {
                "response": response_text,
                "agent_id": fallback_agent_id,
                "is_fallback": True,
                "original_task_id": failed_task.id,
            }

        # Spawn via manager
        return await subagent_manager.spawn_fallback(
            original_task=failed_task,
            fallback_agent_id=fallback_agent_id,
            modified_prompt=fallback_prompt,
            work_fn=fallback_work_fn,
        )

    async def diagnose_failure(
        self,
        failed_task: SubagentTask,
        context: dict[str, Any] | None = None,
    ) -> SubagentTask:
        """Spawn a diagnostic task to analyze why a task failed.

        Args:
            failed_task: The task that failed
            context: Additional context

        Returns:
            The diagnostic SubagentTask
        """
        from app.subagents.recovery import _create_diagnostic_prompt, FailureContext, FailureType

        goals_completed = sum(1 for g in failed_task.goals if g.status.value == "completed")
        last_checkpoint = failed_task.checkpoints[-1].name if failed_task.checkpoints else None

        failure_context = FailureContext(
            task_id=failed_task.id,
            agent_id=failed_task.agent_id,
            task_description=failed_task.description,
            failure_type=FailureType.AGENT_ERROR,
            error_message=failed_task.error or "Unknown error",
            attempt=failed_task.attempt,
            max_attempts=failed_task.max_attempts,
            started_at=failed_task.started_at or failed_task.created_at,
            failed_at=failed_task.completed_at or datetime.now(),
            duration_seconds=0,
            last_checkpoint=last_checkpoint,
            goals_completed=goals_completed,
            goals_total=len(failed_task.goals),
            response_so_far=failed_task.response_so_far,
        )

        diagnostic_prompt = _create_diagnostic_prompt(failure_context)

        return await self.run_task(
            task_description=diagnostic_prompt,
            agent_id="reviewer",  # Reviewer is best for diagnosis
            context={
                **(context or {}),
                "is_diagnosis": True,
                "failed_task_id": failed_task.id,
            },
        )


# Global runner
subagent_runner = SubagentRunner()
