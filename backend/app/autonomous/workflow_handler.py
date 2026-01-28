"""Workflow Handler - Integration between chat.py and autonomous workflow.

This module provides helper functions to run the autonomous test-driven
development loop from within the chat endpoint.
"""

import asyncio
import json
import logging
import uuid
from typing import Any, AsyncIterator

from app.autonomous.workflow import (
    autonomous_workflow,
    analyze_test_results,
    build_fix_prompt,
    build_escalation_prompt,
    build_devops_prompt,
    WorkflowStatus,
)
from app.subagents.runner import subagent_runner
from app.subagents.manager import subagent_manager, TaskStatus

logger = logging.getLogger(__name__)


async def run_autonomous_workflow(
    session_id: str,
    original_task: str,
    coder_result: str,
    context: dict[str, Any] | None = None,
    db_session: Any = None,
    save_message_fn: Any = None,
) -> AsyncIterator[str]:
    """Run the autonomous test-driven workflow after coder completion.

    This function implements:
    1. Spawn tester to run tests
    2. If tests fail, spawn coder to fix (up to 3 times)
    3. If coder can't fix, escalate to architect
    4. Once tests pass, spawn devops to offer commit/deploy

    Args:
        session_id: The chat session ID
        original_task: The original coding task description
        coder_result: The coder's implementation result
        context: Additional context
        db_session: Database session for saving messages
        save_message_fn: Async function to save messages

    Yields:
        SSE event strings
    """
    workspace_path = context.get("workspace") if context else None

    # Create workflow state
    state = autonomous_workflow.create_workflow(
        session_id=session_id,
        original_task=original_task,
        workspace_path=workspace_path,
    )

    logger.info(f"Starting autonomous workflow {state.id} for session {session_id}")

    yield f'data: {{"workflow_started": true, "workflow_id": "{state.id}"}}\n\n'
    yield 'data: {"workflow_status": "testing", "message": "Code implementation complete. Running tests..."}\n\n'

    try:
        # Loop until tests pass or we give up
        while state.status not in (
            WorkflowStatus.COMPLETED,
            WorkflowStatus.FAILED,
            WorkflowStatus.AWAITING_USER,
        ):
            if state.status in (WorkflowStatus.CODING, WorkflowStatus.FIXING):
                # Spawn tester
                state.status = WorkflowStatus.TESTING
                state.coder_attempts += 1

                yield f'data: {{"workflow_status": "testing", "coder_attempts": {state.coder_attempts}}}\n\n'

                test_prompt = f"""Run tests for the following implementation:

**Task:** {state.original_task}

**Implementation complete.** Please:
1. Find and run all relevant tests
2. If no tests exist, create appropriate unit tests first
3. Run the tests and report results clearly
4. Include full error messages if tests fail
"""

                async for event in _spawn_and_wait(
                    "tester",
                    test_prompt,
                    session_id,
                    context,
                    save_message_fn,
                ):
                    yield event

                # Get tester result
                tester_result = _last_result.get("response", "") if _last_result else ""

                # Analyze test results
                tests_passed, summary = analyze_test_results(tester_result)
                state.test_results.append({
                    "passed": tests_passed,
                    "summary": summary,
                })
                state.last_test_output = tester_result

                yield f'data: {{"test_result": {{"passed": {str(tests_passed).lower()}, "summary": "{summary}"}}}}\n\n'

                if tests_passed:
                    # Success! Move to devops
                    state.status = WorkflowStatus.DEPLOYING
                    yield 'data: {"workflow_status": "deploying", "message": "All tests passed! Moving to commit/deploy..."}\n\n'

                    devops_prompt = build_devops_prompt(
                        state.original_task,
                        state.files_modified,
                        state.workspace_path,
                    )

                    async for event in _spawn_and_wait(
                        "devops",
                        devops_prompt,
                        session_id,
                        context,
                        save_message_fn,
                    ):
                        yield event

                    state.status = WorkflowStatus.COMPLETED
                    yield 'data: {"workflow_status": "completed", "message": "Workflow complete!"}\n\n'

                else:
                    # Tests failed - fix or escalate
                    if state.coder_attempts >= state.max_coder_attempts:
                        # Check if we should escalate to architect
                        if state.architect_attempts >= state.max_architect_attempts:
                            # Give up
                            state.status = WorkflowStatus.FAILED
                            yield f'data: {{"workflow_status": "failed", "message": "Failed after {state.coder_attempts} attempts", "summary": "{summary}"}}\n\n'
                        else:
                            # Escalate to architect
                            state.status = WorkflowStatus.ESCALATING
                            state.architect_attempts += 1

                            yield f'data: {{"workflow_status": "escalating", "architect_attempts": {state.architect_attempts}, "message": "Escalating to architect for redesign..."}}\n\n'

                            escalation_prompt = build_escalation_prompt(
                                state.original_task,
                                [r.get("summary", "") for r in state.test_results],
                                tester_result,
                            )

                            async for event in _spawn_and_wait(
                                "architect",
                                escalation_prompt,
                                session_id,
                                context,
                                save_message_fn,
                            ):
                                yield event

                            # Reset coder attempts and continue with architect's new plan
                            state.coder_attempts = 0
                            state.status = WorkflowStatus.CODING

                            # The architect should have spawned coder with [SPAWN:coder]
                            # Check if there's a spawn in the result
                            architect_result = _last_result.get("response", "") if _last_result else ""

                            # If architect spawned coder, wait for it
                            # Otherwise, try again with the new approach
                            if "[SPAWN:coder]" not in architect_result:
                                # Architect didn't spawn coder, we need to
                                yield 'data: {"workflow_status": "coding", "message": "Implementing architect new design..."}\n\n'

                                # Extract new approach from architect
                                coder_prompt = f"""Implement based on the architect's analysis:

{architect_result}

**Original Task:** {state.original_task}

Follow the architect's recommendations to fix the failing tests.
"""
                                async for event in _spawn_and_wait(
                                    "coder",
                                    coder_prompt,
                                    session_id,
                                    context,
                                    save_message_fn,
                                ):
                                    yield event

                    else:
                        # Try fixing with coder
                        state.status = WorkflowStatus.FIXING

                        yield f'data: {{"workflow_status": "fixing", "attempt": {state.coder_attempts + 1}, "message": "Attempting to fix failing tests..."}}\n\n'

                        fix_prompt = build_fix_prompt(
                            state.original_task,
                            tester_result,
                            state.files_modified,
                            state.coder_attempts + 1,
                        )

                        async for event in _spawn_and_wait(
                            "coder",
                            fix_prompt,
                            session_id,
                            context,
                            save_message_fn,
                        ):
                            yield event

            elif state.status == WorkflowStatus.ESCALATING:
                # Already handled above
                pass

            elif state.status == WorkflowStatus.DEPLOYING:
                # Already handled above
                pass

            elif state.status == WorkflowStatus.TESTING:
                # Should be handled in the fixing/coding branches
                pass

            await asyncio.sleep(0.1)  # Prevent tight loop

    except Exception as e:
        logger.exception(f"Autonomous workflow error: {e}")
        state.status = WorkflowStatus.FAILED
        escaped_err = str(e).replace('"', '\\"').replace('\n', ' ')
        yield f'data: {{"workflow_error": "{escaped_err}"}}\n\n'

    finally:
        # Clean up workflow state
        autonomous_workflow.clear_workflow(session_id)
        yield f'data: {{"workflow_ended": true, "workflow_id": "{state.id}"}}\n\n'


# Module-level variable to store last task result
_last_result: dict[str, Any] = {}


async def _spawn_and_wait(
    agent_id: str,
    task_desc: str,
    session_id: str,
    context: dict[str, Any] | None,
    save_message_fn: Any,
) -> AsyncIterator[str]:
    """Spawn an agent task and wait for completion, yielding events.

    Args:
        agent_id: The agent to spawn
        task_desc: Task description
        session_id: Session ID
        context: Context dict
        save_message_fn: Function to save messages

    Yields:
        SSE event strings
    """
    global _last_result
    _last_result = {}

    escaped_task = task_desc[:100].replace("\n", " ").replace('"', '\\"')

    try:
        task = await subagent_runner.run_task(
            task_description=task_desc,
            agent_id=agent_id,
            context=context,
            callback_session=session_id,
        )

        yield f'data: {{"subagent": "{agent_id}", "task_id": "{task.id}", "task": "{escaped_task}", "status": "running"}}\n\n'
        logger.info(f"Workflow spawned {agent_id} with task_id {task.id}")

        # Poll for completion
        last_progress = 0.0
        while True:
            await asyncio.sleep(1)

            current = subagent_manager.get(task.id)
            if not current:
                break

            # Send progress updates
            if current.progress != last_progress:
                last_progress = current.progress
                yield f'data: {{"subagent": "{agent_id}", "task_id": "{task.id}", "progress": {round(current.progress, 2)}}}\n\n'

            if current.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                if current.status == TaskStatus.COMPLETED:
                    result_text = current.result.get("response", "") if current.result else ""
                    _last_result = current.result or {}

                    logger.info(f"Workflow {agent_id} completed: {len(result_text)} chars")

                    yield f'data: {{"subagent": "{agent_id}", "task_id": "{task.id}", "status": "completed"}}\n\n'

                    # Stream result
                    result_event = json.dumps({
                        "subagent_result": agent_id,
                        "content": result_text
                    })
                    yield f'data: {result_event}\n\n'

                    # Save message if function provided
                    if save_message_fn:
                        try:
                            await save_message_fn(
                                f"**[{agent_id.upper()}]**\n\n{result_text}"
                            )
                        except Exception as e:
                            logger.warning(f"Failed to save workflow message: {e}")

                else:
                    error = current.error or "Unknown error"
                    _last_result = {"error": error}
                    yield f'data: {{"subagent": "{agent_id}", "task_id": "{task.id}", "status": "failed", "error": "{error}"}}\n\n'

                break

    except Exception as e:
        logger.error(f"Failed to spawn workflow agent {agent_id}: {e}")
        escaped_err = str(e).replace('"', '\\"').replace('\n', ' ')
        _last_result = {"error": str(e)}
        yield f'data: {{"subagent": "{agent_id}", "status": "error", "error": "{escaped_err}"}}\n\n'


def should_trigger_autonomous_workflow(
    agent_id: str,
    task_desc: str,
    context: dict[str, Any] | None = None,
) -> bool:
    """Check if autonomous workflow should be triggered after this spawn.

    The workflow is triggered when:
    - A coder agent completes an implementation task
    - The context doesn't explicitly disable autonomous mode

    Args:
        agent_id: The agent that just completed
        task_desc: The task description
        context: Additional context

    Returns:
        True if workflow should be triggered
    """
    # Check if explicitly disabled
    if context and context.get("disable_autonomous_workflow"):
        return False

    # Only trigger for coder agents
    if agent_id != "coder":
        return False

    # Check if this looks like an implementation task
    implementation_keywords = [
        "implement", "create", "build", "add", "fix", "write",
        "develop", "make", "setup", "configure", "modify", "update",
        "change", "refactor", "add feature", "code"
    ]

    task_lower = task_desc.lower()

    # Don't trigger for explanation or analysis tasks
    skip_keywords = ["explain", "analyze", "review", "describe", "list", "show", "what is"]
    if any(kw in task_lower for kw in skip_keywords):
        return False

    return any(kw in task_lower for kw in implementation_keywords)
