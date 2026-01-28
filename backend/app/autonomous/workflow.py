"""Autonomous Agent Workflow - Test-Driven Development Loop.

This module implements the autonomous workflow:
1. Coder implements
2. Tester tests automatically
3. If tests fail → back to coder (or escalate to architect)
4. Loop until tests pass
5. DevOps asks about commit/deploy

The workflow is triggered when a coder spawn completes, and continues
autonomously until tests pass.
"""

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator

logger = logging.getLogger(__name__)


class WorkflowStatus(str, Enum):
    """Status of the autonomous workflow."""
    IDLE = "idle"
    CODING = "coding"
    TESTING = "testing"
    FIXING = "fixing"          # Coder fixing test failures
    ESCALATING = "escalating"  # Architect redesigning
    DEPLOYING = "deploying"    # DevOps handling commit/deploy
    COMPLETED = "completed"
    FAILED = "failed"
    AWAITING_USER = "awaiting_user"  # Waiting for user decision


@dataclass
class WorkflowState:
    """State of an autonomous workflow run."""
    id: str
    session_id: str
    original_task: str
    status: WorkflowStatus = WorkflowStatus.IDLE

    # Tracking
    coder_attempts: int = 0
    architect_attempts: int = 0
    max_coder_attempts: int = 3  # Before escalating to architect
    max_architect_attempts: int = 2  # Total redesigns allowed

    # Results
    test_results: list[dict[str, Any]] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)

    # Context for retries
    last_error: str | None = None
    last_test_output: str | None = None
    workspace_path: str | None = None

    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None


# Patterns to detect test results in tester output
TEST_PASS_PATTERNS = [
    re.compile(r'all tests pass(ed)?', re.I),
    re.compile(r'tests? (succeeded|successful|passing)', re.I),
    re.compile(r'✓ all.*tests', re.I),
    re.compile(r'0 failed', re.I),
    re.compile(r'passed\s*:\s*\d+.*failed\s*:\s*0', re.I),
    re.compile(r'OK \(\d+ tests?\)', re.I),
]

TEST_FAIL_PATTERNS = [
    re.compile(r'(\d+) (test|tests) failed', re.I),
    re.compile(r'FAILED', re.I),
    re.compile(r'❌', re.I),
    re.compile(r'AssertionError', re.I),
    re.compile(r'Error:', re.I),
    re.compile(r'failure', re.I),
    re.compile(r'failed\s*:\s*[1-9]', re.I),
]


def analyze_test_results(tester_output: str) -> tuple[bool, str]:
    """Analyze tester output to determine if tests passed.

    Args:
        tester_output: The output from the tester agent

    Returns:
        Tuple of (tests_passed, summary_message)
    """
    # Check for explicit pass patterns
    for pattern in TEST_PASS_PATTERNS:
        if pattern.search(tester_output):
            return True, "All tests passed"

    # Check for explicit fail patterns
    for pattern in TEST_FAIL_PATTERNS:
        match = pattern.search(tester_output)
        if match:
            # Extract failure count if possible
            count_match = re.search(r'(\d+)\s*(test|tests)\s*failed', tester_output, re.I)
            if count_match:
                return False, f"{count_match.group(1)} test(s) failed"
            return False, "Tests failed"

    # No clear indication - assume tests need to be run
    if "no tests" in tester_output.lower() or "test file not found" in tester_output.lower():
        return False, "No tests found or executed"

    # Default to pass if no failure indicators (might be just test generation)
    if "created" in tester_output.lower() or "generated" in tester_output.lower():
        return True, "Tests created/generated"

    return False, "Test status unclear - treating as failed for safety"


def build_fix_prompt(
    original_task: str,
    test_output: str,
    files_modified: list[str],
    attempt: int,
) -> str:
    """Build a prompt for the coder to fix failing tests.

    Args:
        original_task: The original coding task
        test_output: The test failure output
        files_modified: Files that were modified
        attempt: Current fix attempt number

    Returns:
        Prompt for the coder agent
    """
    return f"""Fix the failing tests. This is attempt {attempt}.

**Original Task:**
{original_task}

**Files Modified:**
{', '.join(files_modified) if files_modified else 'Not tracked'}

**Test Failure Output:**
```
{test_output[:3000]}
```

**Instructions:**
1. Analyze the test failures carefully
2. Fix the code to make the tests pass
3. Do NOT modify the test expectations unless they are clearly wrong
4. If you cannot fix the issue, explain why in detail

Focus on fixing the actual bug, not just making the tests pass superficially.
"""


def build_escalation_prompt(
    original_task: str,
    coder_attempts: list[str],
    test_output: str,
) -> str:
    """Build a prompt for the architect to redesign after coder failures.

    Args:
        original_task: The original task
        coder_attempts: Summary of coder attempts
        test_output: Latest test failure output

    Returns:
        Prompt for the architect agent
    """
    attempts_summary = "\n".join([
        f"- Attempt {i+1}: {attempt[:200]}..."
        for i, attempt in enumerate(coder_attempts)
    ])

    return f"""The coder has failed to implement this task after multiple attempts. Please analyze and redesign.

**Original Task:**
{original_task}

**Previous Attempts:**
{attempts_summary}

**Latest Test Failure:**
```
{test_output[:2000]}
```

**Instructions:**
1. Analyze why previous implementations failed
2. Identify the root cause (design issue, misunderstanding, wrong approach)
3. Create a new, clearer implementation plan
4. Spawn coder with the new plan

[SPAWN:coder] <your new implementation instructions here>
"""


def build_devops_prompt(
    original_task: str,
    files_modified: list[str],
    workspace_path: str | None,
) -> str:
    """Build a prompt for devops to handle commit/deploy.

    Args:
        original_task: The original task
        files_modified: Files that were modified
        workspace_path: The workspace directory

    Returns:
        Prompt for the devops agent
    """
    return f"""Implementation complete and tests passing! Help the user commit and optionally deploy.

**Completed Task:**
{original_task}

**Files Modified:**
{', '.join(files_modified) if files_modified else 'Check workspace for changes'}

**Workspace:**
{workspace_path or 'Not specified'}

**Instructions:**
1. Show the user a summary of changes made
2. Ask if they want to:
   - Commit the changes (and suggest a commit message)
   - Deploy the changes
   - Skip commit/deploy
3. Execute their choice

Present options clearly and wait for user confirmation before taking action.
"""


class AutonomousWorkflow:
    """Manages the autonomous coding workflow.

    This class orchestrates the test-driven development loop:
    coder → tester → fix/escalate → repeat until pass → devops
    """

    def __init__(self):
        self._active_workflows: dict[str, WorkflowState] = {}

    def create_workflow(
        self,
        session_id: str,
        original_task: str,
        workspace_path: str | None = None,
    ) -> WorkflowState:
        """Create a new workflow state.

        Args:
            session_id: The chat session ID
            original_task: The original coding task
            workspace_path: Optional workspace directory

        Returns:
            New WorkflowState
        """
        import uuid

        workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
        state = WorkflowState(
            id=workflow_id,
            session_id=session_id,
            original_task=original_task,
            status=WorkflowStatus.CODING,
            workspace_path=workspace_path,
        )
        self._active_workflows[session_id] = state
        return state

    def get_workflow(self, session_id: str) -> WorkflowState | None:
        """Get active workflow for a session."""
        return self._active_workflows.get(session_id)

    def clear_workflow(self, session_id: str) -> None:
        """Clear completed/failed workflow."""
        self._active_workflows.pop(session_id, None)

    async def process_coder_result(
        self,
        session_id: str,
        coder_result: str,
        files_modified: list[str] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Process coder completion and spawn tester.

        Args:
            session_id: The session ID
            coder_result: The coder's response
            files_modified: Files that were modified

        Yields:
            Events for SSE streaming
        """
        state = self.get_workflow(session_id)
        if not state:
            return

        state.coder_attempts += 1
        if files_modified:
            state.files_modified.extend(files_modified)

        # Update status
        state.status = WorkflowStatus.TESTING

        yield {
            "type": "workflow_update",
            "status": "testing",
            "message": "Code implementation complete. Running tests...",
            "coder_attempts": state.coder_attempts,
        }

        # Build test prompt
        test_prompt = f"""Run tests for the following implementation:

**Task:** {state.original_task}

**Instructions:**
1. Find and run all relevant tests
2. If no tests exist, create appropriate tests first
3. Report test results clearly
4. Include any error messages if tests fail
"""

        yield {
            "type": "spawn_tester",
            "prompt": test_prompt,
        }

    async def process_tester_result(
        self,
        session_id: str,
        tester_result: str,
        context: dict[str, Any] | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """Process tester result and decide next action.

        Args:
            session_id: The session ID
            tester_result: The tester's response
            context: Additional context

        Yields:
            Events for SSE streaming
        """
        state = self.get_workflow(session_id)
        if not state:
            return

        # Analyze test results
        tests_passed, summary = analyze_test_results(tester_result)
        state.test_results.append({
            "passed": tests_passed,
            "summary": summary,
            "output": tester_result[:1000],
            "timestamp": datetime.utcnow().isoformat(),
        })
        state.last_test_output = tester_result

        yield {
            "type": "test_results",
            "passed": tests_passed,
            "summary": summary,
            "attempt": state.coder_attempts,
        }

        if tests_passed:
            # Success! Move to devops
            state.status = WorkflowStatus.DEPLOYING

            yield {
                "type": "workflow_update",
                "status": "deploying",
                "message": "All tests passed! Moving to commit/deploy phase.",
            }

            # Build devops prompt
            devops_prompt = build_devops_prompt(
                state.original_task,
                state.files_modified,
                state.workspace_path,
            )

            yield {
                "type": "spawn_devops",
                "prompt": devops_prompt,
            }
        else:
            # Tests failed - decide whether to fix or escalate
            if state.coder_attempts >= state.max_coder_attempts:
                # Escalate to architect
                if state.architect_attempts >= state.max_architect_attempts:
                    # Give up
                    state.status = WorkflowStatus.FAILED
                    state.completed_at = datetime.utcnow()

                    yield {
                        "type": "workflow_failed",
                        "message": f"Failed after {state.coder_attempts} coder attempts and {state.architect_attempts} architect redesigns.",
                        "last_error": summary,
                    }
                else:
                    # Escalate to architect
                    state.status = WorkflowStatus.ESCALATING
                    state.architect_attempts += 1

                    yield {
                        "type": "workflow_update",
                        "status": "escalating",
                        "message": f"Coder failed {state.coder_attempts} times. Escalating to architect for redesign...",
                    }

                    # Get summaries of previous attempts
                    attempt_summaries = [r.get("output", "")[:500] for r in state.test_results]

                    escalation_prompt = build_escalation_prompt(
                        state.original_task,
                        attempt_summaries,
                        tester_result,
                    )

                    yield {
                        "type": "spawn_architect",
                        "prompt": escalation_prompt,
                    }
            else:
                # Try fixing with coder again
                state.status = WorkflowStatus.FIXING

                yield {
                    "type": "workflow_update",
                    "status": "fixing",
                    "message": f"Tests failed. Attempting fix #{state.coder_attempts + 1}...",
                }

                fix_prompt = build_fix_prompt(
                    state.original_task,
                    tester_result,
                    state.files_modified,
                    state.coder_attempts + 1,
                )

                yield {
                    "type": "spawn_coder_fix",
                    "prompt": fix_prompt,
                }

    async def process_architect_result(
        self,
        session_id: str,
        architect_result: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Process architect redesign result.

        Args:
            session_id: The session ID
            architect_result: The architect's response

        Yields:
            Events for SSE streaming
        """
        state = self.get_workflow(session_id)
        if not state:
            return

        # Reset coder attempts for the new design
        state.coder_attempts = 0
        state.status = WorkflowStatus.CODING

        yield {
            "type": "workflow_update",
            "status": "coding",
            "message": "Architect provided new design. Restarting implementation...",
            "architect_attempts": state.architect_attempts,
        }

        # The architect result should contain [SPAWN:coder] which will be handled
        # by the normal spawn processing

    async def process_devops_result(
        self,
        session_id: str,
        devops_result: str,
    ) -> AsyncIterator[dict[str, Any]]:
        """Process devops completion.

        Args:
            session_id: The session ID
            devops_result: The devops response

        Yields:
            Events for SSE streaming
        """
        state = self.get_workflow(session_id)
        if not state:
            return

        state.status = WorkflowStatus.COMPLETED
        state.completed_at = datetime.utcnow()

        duration = (state.completed_at - state.started_at).total_seconds()

        yield {
            "type": "workflow_completed",
            "message": "Workflow complete!",
            "summary": {
                "coder_attempts": state.coder_attempts,
                "architect_attempts": state.architect_attempts,
                "tests_run": len(state.test_results),
                "files_modified": state.files_modified,
                "duration_seconds": duration,
            },
        }

        # Clear the workflow
        self.clear_workflow(session_id)

    def should_trigger_workflow(self, agent_id: str, task_desc: str) -> bool:
        """Determine if this spawn should trigger autonomous workflow.

        The workflow is triggered when:
        - A coder is spawned for implementation (not just explaining/reviewing)

        Args:
            agent_id: The agent being spawned
            task_desc: The task description

        Returns:
            True if workflow should be triggered
        """
        if agent_id != "coder":
            return False

        # Check if this is an implementation task (not just explanation)
        implementation_keywords = [
            "implement", "create", "build", "add", "fix", "write",
            "develop", "make", "setup", "configure", "modify", "update"
        ]

        task_lower = task_desc.lower()
        return any(kw in task_lower for kw in implementation_keywords)


# Global singleton
autonomous_workflow = AutonomousWorkflow()
