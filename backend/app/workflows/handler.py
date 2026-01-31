"""Workflow Handler - Integration between chat API and workflow policies.

This module provides the bridge between chat.py and the delivery loop policy,
handling agent spawning and SSE event streaming.
"""

import asyncio
import json
import logging
import re
from typing import Any, AsyncIterator, Callable

from app.autonomous.persistent_engine import get_persistent_engine
from app.autonomous.engine import EngineEventType, EngineEvent
from app.workflows.delivery_loop import (
    UserDecisionType,
    UserDecisionResponse,
    WorkflowState,
)
from app.subagents.runner import subagent_runner
from app.subagents.manager import subagent_manager, TaskStatus
from app.agents.base import convert_numbered_lines_to_codeblock

logger = logging.getLogger(__name__)


def clean_agent_response(text: str) -> str:
    """Clean agent response for display."""
    if not text:
        return text

    # Remove CLI artifacts
    lines = text.split('\n')
    cleaned = []
    skip_until_empty = False

    for line in lines:
        # Skip ASCII art banner
        special_count = sum(1 for c in line if c in '⠀▀▄█░▒▓│╭╮╯╰─┌┐└┘├┤┬┴┼⣴⣶⣦⣿⢰⢸⠈⠙⠁⠀')
        if special_count > len(line) * 0.3 and len(line) > 10:
            continue

        # Skip banners
        if 'Did you know?' in line or '─────' in line:
            skip_until_empty = True
            continue
        if skip_until_empty:
            if not line.strip():
                skip_until_empty = False
            continue
            
        # Skip UI artifacts from copy buttons
        stripped = line.strip()
        if stripped in ["Code", "1 line", "Copy"]:
            continue

        cleaned.append(line)

    result = '\n'.join(cleaned)
    result = re.sub(r'\n{3,}', '\n\n', result)
    
    # improved formatting for numbered lines (diffs)
    try:
        result = convert_numbered_lines_to_codeblock(result)
    except Exception as e:
        # Fallback if formatting fails
        logger.warning(f"Failed to format numbered lines: {e}")
    
    return result.strip()


def is_coding_task(message: str) -> bool:
    """Determine if a message is a coding task that should trigger the workflow.

    Args:
        message: The user's message

    Returns:
        True if this is a coding/implementation task
    """
    message_lower = message.lower()

    # Positive indicators - this IS a coding task
    coding_keywords = [
        "implement", "create", "build", "add", "fix", "write code",
        "develop", "make", "setup", "configure", "modify", "update",
        "refactor", "change the", "add feature", "code", "function",
        "class", "api", "endpoint", "component", "module", "test",
    ]

    # Negative indicators - this is NOT a coding task
    non_coding_keywords = [
        "explain", "what is", "how does", "describe", "tell me",
        "why", "when", "can you", "help me understand", "show me",
        "list", "difference between", "compare",
    ]

    # Check negative first
    if any(kw in message_lower for kw in non_coding_keywords):
        return False

    # Check positive
    return any(kw in message_lower for kw in coding_keywords)


async def spawn_agent_for_workflow(
    agent_id: str,
    prompt: str,
    context: dict[str, Any] | None,
    session_id: str,
) -> str:
    """Spawn an agent and wait for completion.

    This is the spawn_agent_fn passed to the workflow policy.

    Args:
        agent_id: Which agent to spawn
        prompt: The prompt/task for the agent
        context: Additional context
        session_id: The session ID

    Returns:
        The agent's response text
    """
    task = await subagent_runner.run_task(
        task_description=prompt,
        agent_id=agent_id,
        context=context,
        callback_session=session_id,
    )

    logger.info(f"Workflow spawned {agent_id} task {task.id}")

    # Poll for completion
    while True:
        await asyncio.sleep(1)
        current = subagent_manager.get(task.id)
        if not current:
            return ""

        if current.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
            if current.status == TaskStatus.COMPLETED:
                response = current.result.get("response", "") if current.result else ""
                response = clean_agent_response(response)
                response = convert_numbered_lines_to_codeblock(response)
                return response
            else:
                return f"Error: {current.error or 'Agent failed'}"


async def run_delivery_workflow(
    session_id: str,
    task: str,
    workspace_path: str | None = None,
    context: dict[str, Any] | None = None,
    save_message_fn: Callable | None = None,
) -> AsyncIterator[str]:
    """Run the orchestration workflow and yield SSE events.

    This uses the PersistentOrchestrationEngine for autonomous execution.
    """
    logger.info(f"Starting orchestration workflow for session {session_id}")
    
    engine = get_persistent_engine()
    
    async for event in engine.run(
        prompt=task,
        session_id=session_id,
        workspace_path=workspace_path,
        mode="autonomous"
    ):
        # Handle Plan Approval Request
        if event.type == EngineEventType.PLAN_APPROVAL_REQUESTED:
            plan = event.data.get("plan", {})
            summary = plan.get("summary", "No summary")
            task_list = "\n".join([f"- {t.get('title')}" for t in plan.get("tasks", [])])
            
            msg = f"**Plan Proposed** 📋\n\n{summary}\n\n**Tasks:**\n{task_list}\n\nDo you want to proceed?"
            
            # Map to user_decision_requested for frontend compatibility
            payload = {
                "type": "user_decision_requested",
                "workflow_id": event.run_id,
                "timestamp": event.timestamp.isoformat(),
                "data": {
                    "decision_type": "approve_plan",
                    "question": msg,
                    "options": ["Proceed", "Abort"],
                    "required": True,
                }
            }
            yield f"data: {json.dumps(payload)}\n\n"
            
        # Handle Completion
        elif event.type == EngineEventType.RUN_STATE and event.data.get("state") == "done":
            # Map to workflow_completed
            summary = event.data.get("summary", {})
            payload = {
                "type": "workflow_completed",
                "workflow_id": event.run_id,
                "timestamp": event.timestamp.isoformat(),
                "data": {
                    "user_choices": {},
                    "artifact_report": {
                        "status": "completed",
                        "summary": "Autonomous execution finished successfully.",
                        "files_modified": [], # TODO: Extract from artifacts
                    }
                }
            }
            yield f"data: {json.dumps(payload)}\n\n"
            
        # Handle Brainstorming Visualization
        elif event.type == EngineEventType.BRAINSTORMING_VISUALIZATION:
            markdown = event.data.get("markdown", "")
            if markdown:
                payload = {
                    "type": "message",
                    "content": f"**The Council is Assembled** 🧙‍♂️\n\n{markdown}",
                }
                yield f"data: {json.dumps(payload)}\n\n"

        # Default: yield engine event (supported by TaskGraph)
        else:
            # Also yield chat messages for key events to provide immediate feedback
            if event.type == EngineEventType.TASK_STARTED:
                task_title = event.data.get("title", "Task")
                agent_id = event.data.get("agent_id", "system").replace("_", " ").title()
                payload = {
                    "type": "message",
                    "content": f"\n\n🚀 **{agent_id}:** Starting Task - {task_title}\n",
                }
                yield f"data: {json.dumps(payload)}\n\n"
            
            elif event.type == EngineEventType.TASK_RETRYING:
                task_title = event.data.get("title", "Task") # Note: title might need to be looked up if not in event data, but let's assume it's similar context or generic
                reason = event.data.get("reason", "Verification failed")
                attempt = event.data.get("next_attempt", 2)
                payload = {
                    "type": "message",
                    "content": f"🔄 **Retrying Task:** (Attempt {attempt})\n*Reason: {reason}*\n",
                }
                yield f"data: {json.dumps(payload)}\n\n"

            elif event.type == EngineEventType.TASK_FAILED:
                task_title = event.data.get("title", "Task")
                error = event.data.get("error", "Unknown error")
                payload = {
                    "type": "message",
                    "content": f"❌ **Task Failed:** {task_title}\n\nError: {error}",
                }
                yield f"data: {json.dumps(payload)}\n\n"

            elif event.type == EngineEventType.RUN_ERROR:
                error = event.data.get("error", "Unknown error")
                payload = {
                    "type": "message",
                    "content": f"⚠️ **Workflow Error:** {error}",
                }
                yield f"data: {json.dumps(payload)}\n\n"
            
            # Always yield the raw event for the UI components
            yield event.to_sse()

        # Save important messages to DB
        if save_message_fn:
            if event.type == EngineEventType.TASK_COMPLETED:
                title = event.data.get("title", "Task")
                result = event.data.get("result", {}).get("response", "")
                if result:
                    await save_message_fn(f"**Task Completed: {title}**\n\n{clean_agent_response(result)[:500]}...")



async def resume_workflow_with_docs_decision(
    workflow_id: str,
    wants_docs: bool,
    context: dict[str, Any] | None = None,
    save_message_fn: Callable | None = None,
) -> AsyncIterator[str]:
    """Resume workflow after user decides about documentation.

    LEGACY: For backward compatibility. Use resume_workflow_with_decision instead.
    """
    decision = UserDecisionResponse(
        decision_type=UserDecisionType.DOCS,
        approved=wants_docs,
    )
    async for event in resume_workflow_with_decision(
        workflow_id=workflow_id,
        decision=decision,
        context=context,
        save_message_fn=save_message_fn,
    ):
        yield event


async def resume_workflow_with_decision(
    workflow_id: str,
    decision: UserDecisionResponse,
    context: dict[str, Any] | None = None,
    save_message_fn: Callable | None = None,
) -> AsyncIterator[str]:
    """Resume workflow after any user decision using OrchestrationEngine."""
    logger.info(f"Resuming workflow {workflow_id} with decision {decision}")
    
    engine = get_persistent_engine()
    
    if not decision.approved:
        # User aborted
        await engine.cancel(workflow_id)
        yield f'data: {json.dumps({"type": "cancelled", "workflow_id": workflow_id})}\n\n'
        return

    # Resume the engine
    try:
        async for event in engine.resume(workflow_id):
            if event.type == EngineEventType.RUN_STATE and event.data.get("state") == "done":
                summary = event.data.get("summary", {})
                payload = {
                    "type": "workflow_completed",
                    "workflow_id": event.run_id,
                    "timestamp": event.timestamp.isoformat(),
                    "data": {
                        "user_choices": {},
                        "artifact_report": {
                            "status": "completed",
                            "summary": "Autonomous execution finished successfully.",
                            "files_modified": [],
                        }
                    }
                }
                yield f"data: {json.dumps(payload)}\n\n"
            else:
                yield event.to_sse()

            if save_message_fn and event.type == EngineEventType.TASK_COMPLETED:
                title = event.data.get("title", "Task")
                result = event.data.get("result", {}).get("response", "")
                if result:
                    await save_message_fn(f"**Task Completed: {title}**\n\n{clean_agent_response(result)[:500]}...")

    except Exception as e:
        logger.error(f"Error resuming workflow {workflow_id}: {e}")
        yield f'data: {json.dumps({"type": "error", "data": {"error": str(e)}})}\n\n'


def parse_user_decision_from_message(
    message: str,
    pending_decision: UserDecisionType,
    context: dict[str, Any] | None = None,
) -> UserDecisionResponse:
    """Parse a user's text response into a structured decision.

    Args:
        message: The user's message
        pending_decision: What decision we're waiting for
        context: Additional context (e.g., suggested values)

    Returns:
        A structured UserDecisionResponse
    """
    message_lower = message.lower().strip()

    # Affirmative responses
    yes_responses = {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "go", "proceed", "do it", "commit", "deploy"}
    no_responses = {"no", "n", "nope", "nah", "cancel", "stop", "skip", "don't", "dont"}

    # Check for negative first (skip, don't, etc. take precedence)
    if message_lower in no_responses:
        approved = False
    elif any(neg in message_lower for neg in ["skip", "don't", "dont", "cancel", "no "]):
        approved = False
    elif message_lower in yes_responses:
        approved = True
    else:
        # Check for partial positive matches (but not if negative indicators present)
        approved = any(word in message_lower for word in ["yes", "commit", "deploy", "pr", "doc"])

    # Extract value if provided (e.g., commit message in the response)
    value = None
    metadata = {}

    if pending_decision == UserDecisionType.COMMIT:
        # If user provides a commit message in their response
        if approved and len(message) > 20 and message_lower not in yes_responses:
            value = message.strip()
        # Check for branch name
        if "branch" in message_lower:
            import re
            branch_match = re.search(r"branch[:\s]+[`\"]?([a-zA-Z0-9/_-]+)[`\"]?", message, re.I)
            if branch_match:
                metadata["branch_name"] = branch_match.group(1)

    elif pending_decision == UserDecisionType.DEPLOY:
        # Check for environment specification
        env_keywords = ["staging", "production", "prod", "dev", "development", "test"]
        for env in env_keywords:
            if env in message_lower:
                value = env
                break

    return UserDecisionResponse(
        decision_type=pending_decision,
        approved=approved,
        value=value,
        metadata=metadata,
    )


class WorkflowContextShim:
    """Shim to make Persistent Engine runs look like WorkflowContext for chat.py."""
    def __init__(self, run_data: dict):
        self._data = run_data
        self.workflow_id = run_data.get("run_id")
        self.session_id = None # Not needed by chat.py usually
        
    @property
    def state(self) -> str:
        s = self._data.get("state")
        if s == "paused":
            return WorkflowState.AWAITING_USER
        return s

    @property
    def pending_decision(self) -> UserDecisionType | None:
        if self._data.get("state") == "paused":
            # Assume plan approval for now
            # We could return a custom type if chat.py supports it, but reusing COMMIT/PR might be confusing.
            # chat.py just checks `if pending_decision:`
            # But let's check parse_user_decision_from_message
            return UserDecisionType.APPROVE_DIFF # Closest map?
        return None


async def get_active_workflow_for_session(session_id: str) -> WorkflowContextShim | None:
    """Get any active workflow for a session."""
    engine = get_persistent_engine()
    run = await engine.get_run_by_session(session_id)
    if run and run.get("state") in ("running", "paused", "plan", "execute", "verify"):
        return WorkflowContextShim(run)
    return None
