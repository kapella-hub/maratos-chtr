"""Workflow Handler - Integration between chat API and workflow policies.

This module provides the bridge between chat.py and the delivery loop policy,
handling agent spawning and SSE event streaming.
"""

import asyncio
import json
import logging
import re
from typing import Any, AsyncIterator, Callable

from app.workflows.delivery_loop import (
    DeliveryLoopPolicy,
    WorkflowContext,
    WorkflowEvent,
    WorkflowState,
    UserDecision,
    UserDecisionType,
    UserDecisionResponse,
    ArtifactReport,
    delivery_loop_policy,
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

        cleaned.append(line)

    result = '\n'.join(cleaned)
    result = re.sub(r'\n{3,}', '\n\n', result)
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
    """Run the delivery loop workflow and yield SSE events.

    This is the main entry point called from chat.py.

    Args:
        session_id: The chat session ID
        task: The coding task description
        workspace_path: Optional workspace directory
        context: Additional context
        save_message_fn: Async function to save messages to DB

    Yields:
        SSE event strings
    """
    logger.info(f"Starting delivery workflow for session {session_id}")

    # Create spawn function with session context
    async def spawn_fn(agent_id: str, prompt: str, ctx: dict) -> str:
        return await spawn_agent_for_workflow(agent_id, prompt, ctx, session_id)

    # Run the workflow
    async for event in delivery_loop_policy.run(
        session_id=session_id,
        task=task,
        workspace_path=workspace_path,
        context=context,
        spawn_agent_fn=spawn_fn,
    ):
        # Convert workflow event to SSE
        yield event.to_sse()

        # Save agent results to DB if save function provided
        if save_message_fn and event.type == "agent_completed":
            agent = event.data.get("agent", "unknown")
            summary = event.data.get("summary", "")
            if summary:
                try:
                    await save_message_fn(f"**[{agent.upper()}]**\n\n{summary}")
                except Exception as e:
                    logger.warning(f"Failed to save workflow message: {e}")


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
    """Resume workflow after any user decision.

    This handles the multi-step decision flow:
    COMMIT -> PR -> DEPLOY -> DOCS -> COMPLETED

    Args:
        workflow_id: The workflow ID
        decision: The user's decision response
        context: Additional context
        save_message_fn: Function to save messages

    Yields:
        SSE event strings
    """
    ctx = delivery_loop_policy.resume_after_user_decision(workflow_id, decision)
    if not ctx:
        yield 'data: {"error": "Workflow not found or not awaiting user decision"}\n\n'
        return

    # Emit decision result
    yield WorkflowEvent(
        type="decision_result",
        workflow_id=ctx.workflow_id,
        data={
            "decision_type": decision.decision_type.value,
            "approved": decision.approved,
            "value": decision.value,
        },
    ).to_sse()

    # Create spawn function
    async def spawn_fn(agent_id: str, prompt: str, _ctx: dict) -> str:
        return await spawn_agent_for_workflow(agent_id, prompt, _ctx, ctx.session_id)

    # If there's a next decision, emit it
    next_decision = delivery_loop_policy.get_next_decision(ctx)
    if next_decision and ctx.state == WorkflowState.AWAITING_USER:
        yield WorkflowEvent(
            type="user_decision_requested",
            workflow_id=ctx.workflow_id,
            data={
                "decision_type": next_decision.decision_type.value,
                "question": next_decision.question,
                "options": next_decision.options,
                "context": next_decision.context,
                "required": next_decision.required,
            },
        ).to_sse()
        return  # Wait for next user decision

    # If we've transitioned to DOCUMENTING, run docs agent
    if ctx.state == WorkflowState.DOCUMENTING:
        async for event in delivery_loop_policy._run_docs(ctx, context or {}, spawn_fn):
            yield event.to_sse()

            # Save docs result if save function provided
            if save_message_fn and event.type == "agent_completed" and event.data.get("agent") == "docs":
                artifacts = event.data.get("artifacts", [])
                if artifacts:
                    try:
                        await save_message_fn(f"**[DOCS]** Created documentation: {', '.join(artifacts)}")
                    except Exception as e:
                        logger.warning(f"Failed to save docs message: {e}")

        # After docs, complete the workflow
        if ctx.state == WorkflowState.DOCUMENTING:
            ctx.transition(WorkflowState.COMPLETED)

    # Emit completion if we're done
    if ctx.state == WorkflowState.COMPLETED:
        # Build final artifact report
        report = ctx.artifact_report or delivery_loop_policy._build_artifact_report(ctx)

        # Update report with user choices
        if ctx.user_wants_docs and ctx.docs_result:
            report.docs_created = ctx.docs_result.artifacts

        yield WorkflowEvent(
            type="workflow_completed",
            workflow_id=ctx.workflow_id,
            data={
                "user_choices": {
                    "committed": ctx.user_wants_commit,
                    "pr_created": ctx.user_wants_pr,
                    "deployed": ctx.user_wants_deploy,
                    "documented": ctx.user_wants_docs,
                },
                "artifact_report": report.to_dict(),
            },
        ).to_sse()

        delivery_loop_policy.cleanup_workflow(workflow_id)


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


def get_active_workflow_for_session(session_id: str) -> WorkflowContext | None:
    """Get any active workflow for a session."""
    return delivery_loop_policy.get_workflow_for_session(session_id)
