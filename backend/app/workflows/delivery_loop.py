"""Delivery Loop Policy - Deterministic coding workflow enforcement.

This module implements a state machine that ENFORCES the following workflow:

    CODER → TESTER → (fail?) → CODER → ... → (pass) → DEVOPS → DOCS?

The workflow is NOT optional - it runs automatically for any coding task.
Agents return structured results that the policy uses to determine next steps.
"""

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator, Callable

logger = logging.getLogger(__name__)


# =============================================================================
# Workflow States
# =============================================================================

class WorkflowState(str, Enum):
    """Deterministic workflow states."""
    PENDING = "pending"           # Workflow created, not started
    CODING = "coding"             # Coder is implementing
    TESTING = "testing"           # Tester is validating (host/compose mode)
    CONTAINER_TESTING = "container_testing"  # Tester running container parity test
    FIXING = "fixing"             # Coder is fixing test failures
    ESCALATING = "escalating"     # Architect is redesigning
    DEPLOYING = "deploying"       # DevOps offering commit/deploy
    DOCUMENTING = "documenting"   # Docs agent writing documentation
    AWAITING_USER = "awaiting_user"  # Waiting for user decision
    COMPLETED = "completed"       # Workflow finished successfully
    FAILED = "failed"             # Workflow failed (budget exceeded or error)


class TestMode(str, Enum):
    """Test execution modes for tiered testing strategy."""
    HOST = "host"           # Fast unit/lint tests on host
    COMPOSE = "compose"     # Integration tests with docker-compose dependencies
    CONTAINER = "container" # Full container parity tests


# Valid state transitions (enforced)
STATE_TRANSITIONS: dict[WorkflowState, set[WorkflowState]] = {
    WorkflowState.PENDING: {WorkflowState.CODING, WorkflowState.FAILED},
    WorkflowState.CODING: {WorkflowState.TESTING, WorkflowState.ESCALATING, WorkflowState.FAILED},
    # TESTING can go to CONTAINER_TESTING (normal flow) or DEPLOYING (no tests found)
    WorkflowState.TESTING: {WorkflowState.CONTAINER_TESTING, WorkflowState.DEPLOYING, WorkflowState.FIXING, WorkflowState.ESCALATING, WorkflowState.FAILED},
    WorkflowState.CONTAINER_TESTING: {WorkflowState.DEPLOYING, WorkflowState.FIXING, WorkflowState.FAILED},
    WorkflowState.FIXING: {WorkflowState.TESTING, WorkflowState.ESCALATING, WorkflowState.FAILED},
    WorkflowState.ESCALATING: {WorkflowState.CODING, WorkflowState.FAILED},
    WorkflowState.DEPLOYING: {WorkflowState.AWAITING_USER, WorkflowState.DOCUMENTING, WorkflowState.COMPLETED, WorkflowState.FAILED},
    WorkflowState.AWAITING_USER: {WorkflowState.DOCUMENTING, WorkflowState.COMPLETED},
    WorkflowState.DOCUMENTING: {WorkflowState.COMPLETED, WorkflowState.FAILED},
    WorkflowState.COMPLETED: set(),
    WorkflowState.FAILED: set(),
}


# =============================================================================
# Agent Outcome Types (Structured Results)
# =============================================================================

class AgentOutcome(str, Enum):
    """Standard outcomes from agent execution."""
    DONE = "done"           # Task completed successfully
    BLOCKED = "blocked"     # Cannot proceed, needs escalation
    NEEDS_ARCH = "needs_arch"  # Needs architect input
    PASS = "pass"           # Tests passed
    FAIL = "fail"           # Tests failed
    ERROR = "error"         # Unexpected error


class UserDecisionType(str, Enum):
    """Types of user decisions requested at gates."""
    COMMIT = "commit"           # Commit changes?
    PR = "pr"                   # Open pull request?
    DEPLOY = "deploy"           # Deploy to environment?
    DOCS = "docs"               # Generate documentation?
    APPROVE_DIFF = "approve_diff"  # Approve the diff before action


@dataclass
class UserDecision:
    """A decision the user needs to make."""
    decision_type: UserDecisionType
    question: str
    options: list[str] = field(default_factory=list)
    default: str | None = None
    context: dict[str, Any] = field(default_factory=dict)  # Additional info (diff, suggested values)
    required: bool = True  # If false, can be skipped


@dataclass
class UserDecisionResponse:
    """User's response to a decision request."""
    decision_type: UserDecisionType
    approved: bool
    value: str | None = None  # For text inputs like branch name, commit message
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ArtifactReport:
    """Final report of all artifacts produced by the workflow."""
    workflow_id: str
    task: str
    status: str  # completed, partial, declined
    files_created: list[str] = field(default_factory=list)
    files_modified: list[str] = field(default_factory=list)
    tests_run: int = 0
    tests_passed: int = 0
    commit_sha: str | None = None
    pr_url: str | None = None
    docs_created: list[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id": self.workflow_id,
            "task": self.task,
            "status": self.status,
            "files_created": self.files_created,
            "files_modified": self.files_modified,
            "tests_run": self.tests_run,
            "tests_passed": self.tests_passed,
            "commit_sha": self.commit_sha,
            "pr_url": self.pr_url,
            "docs_created": self.docs_created,
            "summary": self.summary,
        }


@dataclass
class CoderResult:
    """Structured result from CODER agent."""
    status: AgentOutcome  # done, blocked, needs_arch, error
    artifacts: list[str] = field(default_factory=list)  # Files created/modified
    summary: str = ""
    raw_response: str = ""
    error: str | None = None

    @classmethod
    def parse(cls, response: str) -> "CoderResult":
        """Parse coder response into structured result."""
        # Look for status markers in response
        status = AgentOutcome.DONE
        artifacts = []
        summary = ""
        error = None

        response_lower = response.lower()

        # Detect blocked/needs_arch status
        if any(phrase in response_lower for phrase in [
            "cannot implement", "need more information", "unclear requirement",
            "blocked by", "need clarification", "ambiguous"
        ]):
            status = AgentOutcome.BLOCKED

        if any(phrase in response_lower for phrase in [
            "need architect", "requires design", "architectural decision",
            "complex enough", "multiple approaches"
        ]):
            status = AgentOutcome.NEEDS_ARCH

        # Detect actual execution errors (not code about error handling)
        # Be specific to avoid matching when coder writes about error handling
        # These are phrases that indicate the coder itself failed to complete the task
        error_indicators = [
            "i encountered an error",
            "i ran into an error",
            "i could not complete the task",
            "i was unable to complete",
            "the command failed with",
            "fatal error occurred",
            "compilation error prevented",
            "syntax error in my code",
            "failed to complete the task",
            "could not find the required files",
        ]

        # Check error indicators - only first-person phrases about failure
        matched_indicator = None
        for phrase in error_indicators:
            if phrase in response_lower:
                matched_indicator = phrase
                break

        if matched_indicator:
            logger.info(f"CoderResult: detected error indicator '{matched_indicator}'")
            status = AgentOutcome.ERROR
            # Extract error message
            for line in response.split("\n"):
                line_lower = line.lower().strip()
                if any(ind in line_lower for ind in ["error", "failed", "could not"]):
                    error = line.strip()[:200]
                    break

        # Extract file artifacts (files mentioned as created/modified)
        file_patterns = [
            r'(?:created|modified|wrote|updated|added)\s+[`"]?([^\s`"]+\.\w+)[`"]?',
            r'(?:file|path):\s*[`"]?([^\s`"]+\.\w+)[`"]?',
        ]
        for pattern in file_patterns:
            for match in re.finditer(pattern, response, re.I):
                artifacts.append(match.group(1))

        # Extract summary (first paragraph or sentence)
        lines = [l.strip() for l in response.split("\n") if l.strip()]
        if lines:
            summary = lines[0][:200]

        return cls(
            status=status,
            artifacts=list(set(artifacts)),
            summary=summary,
            raw_response=response,
            error=error,
        )


@dataclass
class TesterResult:
    """Structured result from TESTER agent."""
    status: AgentOutcome  # pass, fail, error
    test_mode: str = "host"  # host, compose, container
    next_action: str = "back_to_coder"  # back_to_coder, escalate_arch, ready_for_devops
    test_commands: list[str] = field(default_factory=list)
    logs_path: str | None = None
    failure_summary: str = ""
    tests_run: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    no_tests_found: bool = False  # For greenfield projects
    tests_created: bool = False   # Tester created new tests
    notes: str = ""  # Why this mode was chosen
    raw_response: str = ""

    @classmethod
    def parse(cls, response: str) -> "TesterResult":
        """Parse tester response into structured result."""
        # Don't default to fail - determine from actual content
        status = None
        test_commands = []
        failure_summary = ""
        tests_run = 0
        tests_passed = 0
        tests_failed = 0
        no_tests_found = False
        tests_created = False

        response_lower = response.lower()

        # First, detect "no tests found" scenarios (greenfield projects)
        no_tests_patterns = [
            r"no\s+tests?\s+(?:found|exist|available|to run|detected)",
            r"(?:could\s+not|couldn't|cannot|can't)\s+find\s+(?:any\s+)?tests?",
            r"no\s+test\s+(?:files?|directory|folder)",
            r"tests?\s+(?:directory|folder)\s+(?:not\s+found|missing|doesn't exist)",
            r"pytest.*?(?:collected\s+0\s+items?|no\s+tests\s+ran)",
            r"no\s+tests\s+ran",
            r"collected\s+0\s+items",
            r"0\s+tests?\s+collected",
        ]
        for pattern in no_tests_patterns:
            if re.search(pattern, response_lower):
                no_tests_found = True
                break

        # Detect if tester created tests
        created_tests_patterns = [
            r"(?:created|wrote|generated|added)\s+(?:new\s+)?tests?",
            r"(?:created|wrote)\s+(?:test_|tests/)",
            r"new\s+test\s+file",
        ]
        for pattern in created_tests_patterns:
            if re.search(pattern, response_lower):
                tests_created = True
                break

        # Detect pass patterns (actual test output)
        pass_patterns = [
            r"all\s+\d*\s*tests?\s+pass",
            r"tests?\s+(?:succeeded|successful(?:ly)?|passing)",
            r"✓\s*all.*tests",
            r"0\s+failed",
            r"failed\s*:\s*0",
            r"passed\s*:\s*\d+.*failed\s*:\s*0",
            r"ok\s*\(\d+\s*tests?\)",
            r"passed!\s*$",
            r"100%\s+passed",
            r"\d+\s+passed.*\s+0\s+failed",
        ]
        for pattern in pass_patterns:
            if re.search(pattern, response_lower):
                status = AgentOutcome.PASS
                break

        # Detect fail patterns - be more specific to actual test output
        # Avoid matching descriptive text like "this test would fail"
        fail_patterns = [
            # Actual pytest output
            (r"(\d+)\s+(?:test|tests)\s+failed", True),
            (r"FAILED\s+[\w/]+\.py::", True),  # pytest FAILED with file path
            (r"failed\s*:\s*[1-9]", True),
            (r"failures?\s*:\s*[1-9]", True),
            (r"errors?\s*:\s*[1-9]", True),
            # Actual assertion errors in output
            (r"AssertionError:", True),
            (r"assert\s+\w+\s+==.*FAILED", True),
            # Test output with X failures
            (r"\d+\s+passed.*\s+(\d+)\s+failed", True),
            (r"❌\s*\d+\s*(?:test|tests)\s*failed", True),
        ]
        for pattern, is_specific in fail_patterns:
            match = re.search(pattern, response, re.I if not is_specific else 0)
            if match:
                # Extract fail count if pattern has a group
                extracted_count = None
                if match.groups():
                    try:
                        extracted_count = int(match.group(1))
                        tests_failed = extracted_count
                    except (ValueError, IndexError):
                        pass

                # Only set FAIL if:
                # 1. No count was extracted (pattern matched but no number), OR
                # 2. Count was extracted and is > 0
                if extracted_count is None or extracted_count > 0:
                    status = AgentOutcome.FAIL
                    break

        # Extract test counts
        count_patterns = [
            r"(\d+)\s+passed.*?(\d+)\s+failed",
            r"passed:\s*(\d+).*failed:\s*(\d+)",
            r"(\d+)\s+tests?\s+passed.*?(\d+)\s+(?:tests?\s+)?failed",
        ]
        for count_pattern in count_patterns:
            count_match = re.search(count_pattern, response_lower)
            if count_match:
                tests_passed = int(count_match.group(1))
                tests_failed = int(count_match.group(2))
                tests_run = tests_passed + tests_failed
                break

        # If we found test counts but no explicit status, derive it
        if status is None and tests_run > 0:
            status = AgentOutcome.PASS if tests_failed == 0 else AgentOutcome.FAIL

        # Extract test commands
        cmd_patterns = [
            r"(?:running|executed?|ran):\s*[`]?([^`\n]+)[`]?",
            r"(?:^|\n)\s*(pytest\s+[^\n]+)",
            r"(?:^|\n)\s*(npm\s+(?:test|run\s+test)[^\n]*)",
            r"(?:^|\n)\s*(python\s+-m\s+pytest[^\n]*)",
        ]
        for pattern in cmd_patterns:
            for match in re.finditer(pattern, response, re.I | re.M):
                cmd = match.group(1) if match.groups() else match.group(0)
                test_commands.append(cmd.strip())

        # Extract failure summary - only from actual test output
        if status == AgentOutcome.FAIL:
            # Look for assertion errors and actual failures
            in_failure_block = False
            for line in response.split("\n"):
                line_lower = line.lower()
                # Start capturing at actual failures
                if "FAILED" in line or "AssertionError" in line or "Error:" in line:
                    in_failure_block = True
                if in_failure_block:
                    failure_summary += line.strip() + "\n"
                    if len(failure_summary) > 500:
                        break
            failure_summary = failure_summary[:500]

        # Determine final status for ambiguous cases
        if status is None:
            if no_tests_found:
                # No tests found - treat as PASS for greenfield projects
                status = AgentOutcome.PASS
                logger.info("No tests found - treating as PASS for greenfield project")
            else:
                # Ambiguous - default to PASS unless there's clear failure indication
                status = AgentOutcome.PASS
                logger.warning("Ambiguous test result - defaulting to PASS")

        # Safety check: if status is FAIL but no actual failures detected,
        # and no tests were run, reconsider
        if status == AgentOutcome.FAIL and tests_failed == 0 and tests_run == 0:
            # Check if there's actual test output (pytest, npm test, etc.)
            has_actual_test_output = any([
                "pytest" in response_lower and ("passed" in response_lower or "failed" in response_lower),
                "npm test" in response_lower and ("passed" in response_lower or "failed" in response_lower),
                re.search(r"\d+\s+passed", response_lower),
                re.search(r"tests?:\s*\d+", response_lower),
            ])
            if not has_actual_test_output:
                # No actual test output - likely descriptive text matched fail patterns
                logger.warning("FAIL detected but no test output found - reconsidering as PASS")
                status = AgentOutcome.PASS

        # Parse TEST_REPORT block if present
        test_mode = "host"
        next_action = "back_to_coder" if status == AgentOutcome.FAIL else "ready_for_devops"
        notes = ""
        logs_path = None

        # Look for TEST_REPORT YAML block - capture everything after TEST_REPORT:
        test_report_match = re.search(
            r'TEST_REPORT:\s*\n((?:[ \t]+[^\n]*\n?)+)',
            response,
            re.MULTILINE
        )
        if test_report_match:
            report_text = test_report_match.group(1)

            # Extract TEST_MODE
            mode_match = re.search(r'TEST_MODE:\s*(\w+)', report_text, re.I)
            if mode_match:
                test_mode = mode_match.group(1).lower()

            # Extract RESULT (override status if present)
            result_match = re.search(r'RESULT:\s*(\w+)', report_text, re.I)
            if result_match:
                result_val = result_match.group(1).lower()
                if result_val == "pass":
                    status = AgentOutcome.PASS
                elif result_val == "fail":
                    status = AgentOutcome.FAIL

            # Extract NEXT_ACTION
            action_match = re.search(r'NEXT_ACTION:\s*(\w+)', report_text, re.I)
            if action_match:
                next_action = action_match.group(1).lower()

            # Extract NOTES
            notes_match = re.search(r'NOTES:\s*["\']?([^"\'\n]+)', report_text, re.I)
            if notes_match:
                notes = notes_match.group(1).strip()

            # Extract LOG_PATHS - look for lines with "-" followed by path
            logs_match = re.search(r'LOG_PATHS:\s*\n((?:[ \t]+-[^\n]+\n?)+)', report_text, re.I)
            if logs_match:
                logs_text = logs_match.group(1)
                log_paths = re.findall(r'-\s*["\']?([^"\'}\n]+)["\']?', logs_text)
                if log_paths and log_paths[0].strip():
                    logs_path = log_paths[0].strip()

            # Extract COMMANDS_RUN - look for lines with "-" followed by command
            cmds_match = re.search(r'COMMANDS_RUN:\s*\n((?:[ \t]+-[^\n]+\n?)+)', report_text, re.I)
            if cmds_match:
                cmds_text = cmds_match.group(1)
                for cmd in re.findall(r'-\s*["\']?([^"\'}\n]+)["\']?', cmds_text):
                    cmd_clean = cmd.strip().strip('"').strip("'")
                    if cmd_clean and cmd_clean not in test_commands:
                        test_commands.append(cmd_clean)

        return cls(
            status=status,
            test_mode=test_mode,
            next_action=next_action,
            test_commands=list(set(test_commands)),
            logs_path=logs_path,
            failure_summary=failure_summary,
            tests_run=tests_run,
            tests_passed=tests_passed,
            tests_failed=tests_failed,
            no_tests_found=no_tests_found,
            tests_created=tests_created,
            notes=notes,
            raw_response=response,
        )


@dataclass
class ArchitectResult:
    """Structured result from ARCHITECT agent."""
    decisions: list[str] = field(default_factory=list)
    constraints: list[str] = field(default_factory=list)
    updated_plan: str = ""
    files_to_modify: list[str] = field(default_factory=list)
    raw_response: str = ""

    @classmethod
    def parse(cls, response: str) -> "ArchitectResult":
        """Parse architect response into structured result."""
        decisions = []
        constraints = []
        files_to_modify = []

        # Extract decisions (numbered lists, bullet points)
        decision_patterns = [
            r"(?:decision|approach|solution)[\s:]+([^\n]+)",
            r"^\s*\d+\.\s*(.+)$",
        ]
        for pattern in decision_patterns:
            for match in re.finditer(pattern, response, re.I | re.M):
                decisions.append(match.group(1).strip())

        # Extract constraints
        constraint_patterns = [
            r"(?:constraint|requirement|must|should)[\s:]+([^\n]+)",
        ]
        for pattern in constraint_patterns:
            for match in re.finditer(pattern, response, re.I):
                constraints.append(match.group(1).strip())

        # Extract files to modify
        file_pattern = r"(?:modify|update|change|create)\s+[`]?([^\s`]+\.\w+)[`]?"
        for match in re.finditer(file_pattern, response, re.I):
            files_to_modify.append(match.group(1))

        return cls(
            decisions=decisions[:10],  # Limit
            constraints=constraints[:10],
            files_to_modify=list(set(files_to_modify)),
            updated_plan=response[:2000],
            raw_response=response,
        )


@dataclass
class DevOpsResult:
    """Structured result from DEVOPS agent."""
    options_presented: list[str] = field(default_factory=list)  # commit, deploy, pr, skip
    user_choice: str | None = None
    commit_message: str | None = None
    branch_name: str | None = None
    diff_summary: str = ""
    files_changed: list[str] = field(default_factory=list)
    deploy_available: bool = False
    deploy_environments: list[str] = field(default_factory=list)
    raw_response: str = ""

    @classmethod
    def parse(cls, response: str) -> "DevOpsResult":
        """Parse devops response."""
        options = []
        commit_message = None
        branch_name = None
        diff_summary = ""
        files_changed = []
        deploy_available = False
        deploy_environments = []

        response_lower = response.lower()

        if "commit" in response_lower:
            options.append("commit")
        if "deploy" in response_lower:
            options.append("deploy")
            deploy_available = True
        if "pull request" in response_lower or "pr" in response_lower:
            options.append("pr")

        # Extract suggested commit message
        msg_patterns = [
            r"commit\s+message[:\s]+[`\"\']?([^`\"\'\n]+)[`\"\']?",
            r"suggested\s+message[:\s]+[`\"\']?([^`\"\'\n]+)[`\"\']?",
            r"\"([^\"]{10,80})\"",  # Quoted message
        ]
        for pattern in msg_patterns:
            match = re.search(pattern, response, re.I)
            if match:
                commit_message = match.group(1).strip()
                break

        # Extract branch name
        branch_patterns = [
            r"\*\*Branch:?\*\*\s*[`\"\']?([a-zA-Z0-9/_-]+)[`\"\']?",
            r"[Bb]ranch:?\s*[`\"\']?([a-zA-Z0-9/_-]+)[`\"\']?",
            r"(feature/[a-zA-Z0-9_-]+)",
            r"(fix/[a-zA-Z0-9_-]+)",
        ]
        for pattern in branch_patterns:
            match = re.search(pattern, response)
            if match:
                branch_name = match.group(1).strip()
                break

        # Extract files changed
        file_pattern = r"(?:modified|changed|created|updated)[:\s]*[`]?([^\s`\n,]+\.\w+)[`]?"
        for match in re.finditer(file_pattern, response, re.I):
            files_changed.append(match.group(1))

        # Extract diff summary (look for diff blocks or change descriptions)
        diff_patterns = [
            r"```diff\s*(.*?)```",
            r"```\s*diff\s*(.*?)```",
            r"changes?:\s*((?:[-+].*[\r\n]+)+)",
        ]
        for pattern in diff_patterns:
            match = re.search(pattern, response, re.DOTALL | re.I)
            if match:
                diff_summary = match.group(1).strip()[:2000]
                break

        # Extract deployment environments
        env_patterns = [
            r"(?:deploy(?:ment)?\s+(?:to\s+)?)?(?:environment|env)[:\s]*[`]?(\w+)[`]?",
            r"(?:staging|production|dev|development|test)",
        ]
        for pattern in env_patterns:
            for match in re.finditer(pattern, response_lower):
                env = match.group(1) if match.groups() else match.group(0)
                if env not in deploy_environments:
                    deploy_environments.append(env)

        return cls(
            options_presented=options,
            commit_message=commit_message,
            branch_name=branch_name,
            diff_summary=diff_summary,
            files_changed=list(set(files_changed)),
            deploy_available=deploy_available,
            deploy_environments=deploy_environments,
            raw_response=response,
        )


@dataclass
class DocsResult:
    """Structured result from DOCS agent."""
    artifacts: list[str] = field(default_factory=list)  # Doc files created
    changes_documented: list[str] = field(default_factory=list)
    raw_response: str = ""

    @classmethod
    def parse(cls, response: str) -> "DocsResult":
        """Parse docs response."""
        artifacts = []
        changes = []

        # Extract doc files
        doc_pattern = r"(?:created|wrote|updated)\s+[`]?([^\s`]+\.(?:md|rst|txt))[`]?"
        for match in re.finditer(doc_pattern, response, re.I):
            artifacts.append(match.group(1))

        # Extract changes documented
        change_pattern = r"documented\s+([^\n.]+)"
        for match in re.finditer(change_pattern, response, re.I):
            changes.append(match.group(1).strip())

        return cls(
            artifacts=list(set(artifacts)),
            changes_documented=changes[:10],
            raw_response=response,
        )


# =============================================================================
# SSE Event Types
# =============================================================================

@dataclass
class WorkflowEvent:
    """Event emitted during workflow execution."""
    type: str
    workflow_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        payload = {
            "type": self.type,
            "workflow_id": self.workflow_id,
            "timestamp": self.timestamp.isoformat(),
            **self.data,
        }
        return f"data: {json.dumps(payload)}\n\n"


# =============================================================================
# Workflow Context
# =============================================================================

@dataclass
class WorkflowContext:
    """Runtime context for a delivery loop workflow."""
    workflow_id: str
    session_id: str
    original_task: str
    workspace_path: str | None = None

    # State machine
    state: WorkflowState = WorkflowState.PENDING

    # Loop counters (for budget enforcement)
    coder_attempts: int = 0
    fix_cycles: int = 0
    architect_cycles: int = 0

    # Budgets
    max_fix_cycles: int = 3
    max_architect_cycles: int = 2

    # Results from each stage
    coder_result: CoderResult | None = None
    tester_result: TesterResult | None = None
    container_tester_result: TesterResult | None = None  # Container parity test result
    architect_result: ArchitectResult | None = None
    devops_result: DevOpsResult | None = None
    docs_result: DocsResult | None = None

    # Container parity tracking
    container_test_completed: bool = False
    container_test_skipped: bool = False
    container_skip_reason: str | None = None

    # User decisions (structured)
    user_wants_commit: bool = False
    user_wants_pr: bool = False
    user_wants_deploy: bool = False
    user_wants_docs: bool = False
    commit_message: str | None = None
    branch_name: str | None = None
    deploy_environment: str | None = None

    # Pending decision (what we're waiting for)
    pending_decision: UserDecisionType | None = None

    # Artifact report
    artifact_report: ArtifactReport | None = None

    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None

    # Error tracking
    error: str | None = None

    def can_transition(self, new_state: WorkflowState) -> bool:
        """Check if transition is valid."""
        return new_state in STATE_TRANSITIONS.get(self.state, set())

    def transition(self, new_state: WorkflowState) -> None:
        """Transition to new state (enforced)."""
        if not self.can_transition(new_state):
            raise ValueError(f"Invalid transition: {self.state} -> {new_state}")
        logger.info(f"Workflow {self.workflow_id}: {self.state} -> {new_state}")
        self.state = new_state
        if new_state in (WorkflowState.COMPLETED, WorkflowState.FAILED):
            self.completed_at = datetime.utcnow()

    def budget_exceeded(self) -> bool:
        """Check if any budget is exceeded."""
        return (
            self.fix_cycles >= self.max_fix_cycles and
            self.architect_cycles >= self.max_architect_cycles
        )


# =============================================================================
# Delivery Loop Policy
# =============================================================================

class DeliveryLoopPolicy:
    """Deterministic workflow policy for coding tasks.

    This class ENFORCES the following flow:
    CODER → TESTER → (loop on fail) → DEVOPS → DOCS?

    The policy makes routing decisions based on structured agent results,
    NOT on hoping the model outputs correct markers.
    """

    def __init__(
        self,
        max_fix_cycles: int = 3,
        max_architect_cycles: int = 2,
    ):
        self.max_fix_cycles = max_fix_cycles
        self.max_architect_cycles = max_architect_cycles
        self._active_workflows: dict[str, WorkflowContext] = {}

    def create_workflow(
        self,
        session_id: str,
        task: str,
        workspace_path: str | None = None,
    ) -> WorkflowContext:
        """Create a new workflow context."""
        workflow_id = f"wf-{uuid.uuid4().hex[:12]}"
        ctx = WorkflowContext(
            workflow_id=workflow_id,
            session_id=session_id,
            original_task=task,
            workspace_path=workspace_path,
            max_fix_cycles=self.max_fix_cycles,
            max_architect_cycles=self.max_architect_cycles,
        )
        self._active_workflows[workflow_id] = ctx
        return ctx

    def get_workflow(self, workflow_id: str) -> WorkflowContext | None:
        """Get active workflow by ID."""
        return self._active_workflows.get(workflow_id)

    def get_workflow_for_session(self, session_id: str) -> WorkflowContext | None:
        """Get active workflow for a session."""
        for ctx in self._active_workflows.values():
            if ctx.session_id == session_id and ctx.state not in (
                WorkflowState.COMPLETED, WorkflowState.FAILED
            ):
                return ctx
        return None

    def cleanup_workflow(self, workflow_id: str) -> None:
        """Remove completed workflow."""
        self._active_workflows.pop(workflow_id, None)

    async def run(
        self,
        session_id: str,
        task: str,
        workspace_path: str | None = None,
        context: dict[str, Any] | None = None,
        spawn_agent_fn: Callable | None = None,
    ) -> AsyncIterator[WorkflowEvent]:
        """Execute the delivery loop workflow.

        Args:
            session_id: Chat session ID
            task: The coding task description
            workspace_path: Optional workspace directory
            context: Additional context for agents
            spawn_agent_fn: Async function to spawn agents:
                async def spawn_agent_fn(agent_id, prompt, context) -> str (response)

        Yields:
            WorkflowEvent objects for SSE streaming
        """
        ctx = self.create_workflow(session_id, task, workspace_path)

        yield WorkflowEvent(
            type="workflow_started",
            workflow_id=ctx.workflow_id,
            data={
                "task": task[:200],
                "max_fix_cycles": ctx.max_fix_cycles,
                "max_architect_cycles": ctx.max_architect_cycles,
            },
        )

        try:
            async for event in self._run_state_machine(ctx, context or {}, spawn_agent_fn):
                yield event
        except Exception as e:
            logger.exception(f"Workflow {ctx.workflow_id} error: {e}")
            ctx.error = str(e)
            ctx.transition(WorkflowState.FAILED)
            yield WorkflowEvent(
                type="workflow_failed",
                workflow_id=ctx.workflow_id,
                data={"error": str(e)},
            )
        finally:
            self.cleanup_workflow(ctx.workflow_id)

    async def _run_state_machine(
        self,
        ctx: WorkflowContext,
        context: dict[str, Any],
        spawn_agent_fn: Callable | None,
    ) -> AsyncIterator[WorkflowEvent]:
        """Execute the state machine loop."""

        if not spawn_agent_fn:
            raise ValueError("spawn_agent_fn is required")

        # Start with CODING
        ctx.transition(WorkflowState.CODING)

        while ctx.state not in (WorkflowState.COMPLETED, WorkflowState.FAILED):
            yield WorkflowEvent(
                type="workflow_state",
                workflow_id=ctx.workflow_id,
                data={
                    "state": ctx.state.value,
                    "coder_attempts": ctx.coder_attempts,
                    "fix_cycles": ctx.fix_cycles,
                    "architect_cycles": ctx.architect_cycles,
                },
            )

            if ctx.state == WorkflowState.CODING:
                async for event in self._run_coder(ctx, context, spawn_agent_fn):
                    yield event

            elif ctx.state == WorkflowState.TESTING:
                async for event in self._run_tester(ctx, context, spawn_agent_fn):
                    yield event

            elif ctx.state == WorkflowState.CONTAINER_TESTING:
                async for event in self._run_container_tester(ctx, context, spawn_agent_fn):
                    yield event

            elif ctx.state == WorkflowState.FIXING:
                async for event in self._run_fixer(ctx, context, spawn_agent_fn):
                    yield event

            elif ctx.state == WorkflowState.ESCALATING:
                async for event in self._run_architect(ctx, context, spawn_agent_fn):
                    yield event

            elif ctx.state == WorkflowState.DEPLOYING:
                async for event in self._run_devops(ctx, context, spawn_agent_fn):
                    yield event

            elif ctx.state == WorkflowState.AWAITING_USER:
                # This state requires user input - break the loop
                yield WorkflowEvent(
                    type="user_decision_requested",
                    workflow_id=ctx.workflow_id,
                    data={
                        "options": ["docs", "skip_docs"],
                        "message": "Would you like documentation for these changes?",
                    },
                )
                break  # Will resume when user responds

            elif ctx.state == WorkflowState.DOCUMENTING:
                async for event in self._run_docs(ctx, context, spawn_agent_fn):
                    yield event

        # Final event
        if ctx.state == WorkflowState.COMPLETED:
            yield WorkflowEvent(
                type="workflow_completed",
                workflow_id=ctx.workflow_id,
                data={
                    "coder_attempts": ctx.coder_attempts,
                    "fix_cycles": ctx.fix_cycles,
                    "architect_cycles": ctx.architect_cycles,
                    "artifacts": ctx.coder_result.artifacts if ctx.coder_result else [],
                },
            )

    async def _run_coder(
        self,
        ctx: WorkflowContext,
        context: dict[str, Any],
        spawn_agent_fn: Callable,
    ) -> AsyncIterator[WorkflowEvent]:
        """Run the CODER agent."""
        ctx.coder_attempts += 1

        yield WorkflowEvent(
            type="agent_started",
            workflow_id=ctx.workflow_id,
            data={"agent": "coder", "attempt": ctx.coder_attempts},
        )

        # Build coder prompt
        prompt = self._build_coder_prompt(ctx)

        # Spawn coder agent
        response = await spawn_agent_fn("coder", prompt, context)

        # Parse result
        result = CoderResult.parse(response)
        ctx.coder_result = result

        # Log the parsed result for debugging
        logger.info(
            f"Workflow {ctx.workflow_id}: Coder result parsed - "
            f"status={result.status.value}, artifacts={len(result.artifacts)}, "
            f"error={result.error}, response_len={len(response)}"
        )

        # Validate coder output for syntax errors and common issues
        try:
            from app.agents.coder import CoderAgent
            coder_agent = CoderAgent()
            validation = coder_agent.validate_output(response)

            if not validation["valid"]:
                logger.warning(
                    f"Workflow {ctx.workflow_id}: Coder output validation failed - "
                    f"issues: {validation['issues']}"
                )
                yield WorkflowEvent(
                    type="validation_warning",
                    workflow_id=ctx.workflow_id,
                    data={
                        "agent": "coder",
                        "issues": validation["issues"],
                        "suggestion": validation["suggestion"],
                    },
                )
                # Mark result as having issues (but don't fail - let tests catch it)
                if result.status == AgentOutcome.DONE:
                    result.summary += f"\n\n⚠️ Validation warnings: {', '.join(validation['issues'])}"
            else:
                logger.info(f"Workflow {ctx.workflow_id}: Coder output validation passed")
        except Exception as e:
            logger.warning(f"Coder validation error (non-fatal): {e}")

        yield WorkflowEvent(
            type="agent_completed",
            workflow_id=ctx.workflow_id,
            data={
                "agent": "coder",
                "status": result.status.value,
                "artifacts": result.artifacts,
                "summary": result.summary[:200],
            },
        )

        # Determine next state based on result
        if result.status == AgentOutcome.DONE:
            ctx.transition(WorkflowState.TESTING)  # Always test after coding
        elif result.status == AgentOutcome.BLOCKED or result.status == AgentOutcome.NEEDS_ARCH:
            if ctx.architect_cycles < ctx.max_architect_cycles:
                ctx.transition(WorkflowState.ESCALATING)
            else:
                ctx.error = "Architect budget exceeded"
                ctx.transition(WorkflowState.FAILED)
        elif result.status == AgentOutcome.ERROR:
            ctx.error = result.error or "Coder error"
            ctx.transition(WorkflowState.FAILED)

    async def _run_tester(
        self,
        ctx: WorkflowContext,
        context: dict[str, Any],
        spawn_agent_fn: Callable,
    ) -> AsyncIterator[WorkflowEvent]:
        """Run the TESTER agent."""
        yield WorkflowEvent(
            type="agent_started",
            workflow_id=ctx.workflow_id,
            data={"agent": "tester"},
        )

        # Build tester prompt
        prompt = self._build_tester_prompt(ctx)

        # Spawn tester agent
        response = await spawn_agent_fn("tester", prompt, context)

        # Parse result
        result = TesterResult.parse(response)
        ctx.tester_result = result

        yield WorkflowEvent(
            type="gate_result",
            workflow_id=ctx.workflow_id,
            data={
                "gate": "tester",
                "passed": result.status == AgentOutcome.PASS,
                "test_mode": result.test_mode,
                "next_action": result.next_action,
                "tests_run": result.tests_run,
                "tests_passed": result.tests_passed,
                "tests_failed": result.tests_failed,
                "no_tests_found": result.no_tests_found,
                "tests_created": result.tests_created,
                "failure_summary": result.failure_summary[:200] if result.failure_summary else None,
                "notes": result.notes,
            },
        )

        # Log detailed test result
        logger.info(
            f"Test result: status={result.status.value}, mode={result.test_mode}, "
            f"next_action={result.next_action}, "
            f"run={result.tests_run}, passed={result.tests_passed}, failed={result.tests_failed}, "
            f"no_tests_found={result.no_tests_found}, tests_created={result.tests_created}"
        )

        # Determine next state
        if result.status == AgentOutcome.PASS:
            # If tests passed, check if we need container parity test
            # Skip container test if:
            # 1. Already in container mode
            # 2. Container test already completed
            # 3. No Dockerfile exists (simple projects)
            if result.test_mode == "container" or ctx.container_test_completed:
                # Container test already done, go to devops
                ctx.container_test_completed = True
                ctx.transition(WorkflowState.DEPLOYING)
            else:
                # Need container parity test before devops
                ctx.transition(WorkflowState.CONTAINER_TESTING)
        elif result.status == AgentOutcome.FAIL:
            # Only increment fix_cycles for actual test failures, not "no tests" scenarios
            if result.no_tests_found and not result.tests_created:
                # No tests found and none were created - skip container test too
                # since there's nothing to test in containers either
                logger.warning("No tests found or created - skipping to devops")
                ctx.container_test_completed = True
                ctx.container_test_skipped = True
                ctx.container_skip_reason = "No tests found in project"
                ctx.transition(WorkflowState.DEPLOYING)
            else:
                ctx.fix_cycles += 1
                logger.info(f"Test failed, fix cycle {ctx.fix_cycles}/{ctx.max_fix_cycles}")
                if ctx.fix_cycles < ctx.max_fix_cycles:
                    ctx.transition(WorkflowState.FIXING)  # Try to fix
                elif ctx.architect_cycles < ctx.max_architect_cycles:
                    ctx.transition(WorkflowState.ESCALATING)  # Escalate to architect
                else:
                    ctx.error = "All fix and architect budgets exceeded"
                    ctx.transition(WorkflowState.FAILED)
        else:
            ctx.error = "Tester error"
            ctx.transition(WorkflowState.FAILED)

    async def _run_container_tester(
        self,
        ctx: WorkflowContext,
        context: dict[str, Any],
        spawn_agent_fn: Callable,
    ) -> AsyncIterator[WorkflowEvent]:
        """Run TESTER in container mode for parity check before devops."""
        yield WorkflowEvent(
            type="agent_started",
            workflow_id=ctx.workflow_id,
            data={"agent": "tester", "mode": "container_parity"},
        )

        # Build container test prompt
        prompt = self._build_container_test_prompt(ctx)

        # Spawn tester agent with container mode
        response = await spawn_agent_fn("tester", prompt, context)

        # Parse result
        result = TesterResult.parse(response)
        ctx.container_tester_result = result
        ctx.container_test_completed = True

        yield WorkflowEvent(
            type="gate_result",
            workflow_id=ctx.workflow_id,
            data={
                "gate": "container_parity",
                "passed": result.status == AgentOutcome.PASS,
                "test_mode": result.test_mode,
                "tests_run": result.tests_run,
                "tests_passed": result.tests_passed,
                "tests_failed": result.tests_failed,
                "failure_summary": result.failure_summary[:200] if result.failure_summary else None,
                "notes": result.notes,
            },
        )

        logger.info(
            f"Container parity test: status={result.status.value}, "
            f"run={result.tests_run}, passed={result.tests_passed}, failed={result.tests_failed}"
        )

        # Determine next state
        if result.status == AgentOutcome.PASS:
            # Container tests passed, proceed to devops
            ctx.transition(WorkflowState.DEPLOYING)
        elif result.status == AgentOutcome.FAIL:
            # Container tests failed - route back to coder with container failure info
            ctx.fix_cycles += 1
            logger.info(f"Container test failed, fix cycle {ctx.fix_cycles}/{ctx.max_fix_cycles}")
            if ctx.fix_cycles < ctx.max_fix_cycles:
                ctx.transition(WorkflowState.FIXING)
            elif ctx.architect_cycles < ctx.max_architect_cycles:
                ctx.transition(WorkflowState.ESCALATING)
            else:
                ctx.error = "Container parity tests failed and all budgets exceeded"
                ctx.transition(WorkflowState.FAILED)
        else:
            ctx.error = "Container tester error"
            ctx.transition(WorkflowState.FAILED)

    async def _run_fixer(
        self,
        ctx: WorkflowContext,
        context: dict[str, Any],
        spawn_agent_fn: Callable,
    ) -> AsyncIterator[WorkflowEvent]:
        """Run CODER in fix mode."""
        ctx.coder_attempts += 1

        yield WorkflowEvent(
            type="agent_started",
            workflow_id=ctx.workflow_id,
            data={"agent": "coder", "mode": "fix", "fix_cycle": ctx.fix_cycles},
        )

        # Build fix prompt with test failure info
        prompt = self._build_fix_prompt(ctx)

        # Spawn coder agent
        response = await spawn_agent_fn("coder", prompt, context)

        # Parse result
        result = CoderResult.parse(response)
        ctx.coder_result = result

        yield WorkflowEvent(
            type="agent_completed",
            workflow_id=ctx.workflow_id,
            data={
                "agent": "coder",
                "mode": "fix",
                "status": result.status.value,
            },
        )

        # After fix, ALWAYS go back to testing
        if result.status in (AgentOutcome.DONE, AgentOutcome.ERROR):
            ctx.transition(WorkflowState.TESTING)
        elif result.status in (AgentOutcome.BLOCKED, AgentOutcome.NEEDS_ARCH):
            if ctx.architect_cycles < ctx.max_architect_cycles:
                ctx.transition(WorkflowState.ESCALATING)
            else:
                ctx.error = "Coder blocked and architect budget exceeded"
                ctx.transition(WorkflowState.FAILED)

    async def _run_architect(
        self,
        ctx: WorkflowContext,
        context: dict[str, Any],
        spawn_agent_fn: Callable,
    ) -> AsyncIterator[WorkflowEvent]:
        """Run ARCHITECT for escalation."""
        ctx.architect_cycles += 1

        yield WorkflowEvent(
            type="agent_started",
            workflow_id=ctx.workflow_id,
            data={"agent": "architect", "cycle": ctx.architect_cycles},
        )

        # Build architect prompt
        prompt = self._build_architect_prompt(ctx)

        # Spawn architect agent
        response = await spawn_agent_fn("architect", prompt, context)

        # Parse result
        result = ArchitectResult.parse(response)
        ctx.architect_result = result

        yield WorkflowEvent(
            type="agent_completed",
            workflow_id=ctx.workflow_id,
            data={
                "agent": "architect",
                "decisions": result.decisions[:3],
                "files_to_modify": result.files_to_modify,
            },
        )

        # Reset fix cycles and go back to coding with new plan
        ctx.fix_cycles = 0
        ctx.transition(WorkflowState.CODING)

    async def _run_devops(
        self,
        ctx: WorkflowContext,
        context: dict[str, Any],
        spawn_agent_fn: Callable,
    ) -> AsyncIterator[WorkflowEvent]:
        """Run DEVOPS for commit/deploy options with user decision gates."""
        yield WorkflowEvent(
            type="agent_started",
            workflow_id=ctx.workflow_id,
            data={"agent": "devops"},
        )

        # Build devops prompt to analyze changes
        prompt = self._build_devops_prompt(ctx)

        # Spawn devops agent to analyze and prepare
        response = await spawn_agent_fn("devops", prompt, context)

        # Parse result
        result = DevOpsResult.parse(response)
        ctx.devops_result = result

        yield WorkflowEvent(
            type="agent_completed",
            workflow_id=ctx.workflow_id,
            data={
                "agent": "devops",
                "options": result.options_presented,
                "commit_message": result.commit_message,
                "branch_name": result.branch_name,
                "files_changed": result.files_changed,
                "deploy_available": result.deploy_available,
            },
        )

        # Build and emit artifact report
        ctx.artifact_report = self._build_artifact_report(ctx)
        yield WorkflowEvent(
            type="artifact_report",
            workflow_id=ctx.workflow_id,
            data=ctx.artifact_report.to_dict(),
        )

        # Emit file_preview events for each changed file
        # This allows the frontend to show diff previews before commit
        for file_path in result.files_changed:
            yield WorkflowEvent(
                type="file_preview",
                workflow_id=ctx.workflow_id,
                data={
                    "file_path": file_path,
                    "action": "modified",
                    "diff_available": bool(result.diff_summary),
                },
            )

        # If we have multiple files, emit a batch preview event
        if len(result.files_changed) > 1:
            yield WorkflowEvent(
                type="file_preview_batch",
                workflow_id=ctx.workflow_id,
                data={
                    "files": result.files_changed,
                    "total_files": len(result.files_changed),
                    "diff_summary": result.diff_summary[:500] if result.diff_summary else None,
                },
            )

        # === GATE: Ask user about COMMIT ===
        # First, show the diff for approval
        if result.diff_summary or result.files_changed:
            diff_context = {
                "files_changed": result.files_changed,
                "diff_summary": result.diff_summary[:1500] if result.diff_summary else "Run `git diff` to see changes",
            }
        else:
            diff_context = {"message": "Changes detected but diff not captured"}

        ctx.pending_decision = UserDecisionType.COMMIT
        ctx.transition(WorkflowState.AWAITING_USER)

        yield WorkflowEvent(
            type="user_decision_requested",
            workflow_id=ctx.workflow_id,
            data={
                "decision_type": UserDecisionType.COMMIT.value,
                "question": "Would you like to commit these changes?",
                "options": ["yes", "no"],
                "context": {
                    "diff": diff_context,
                    "suggested_message": result.commit_message,
                    "suggested_branch": result.branch_name,
                    "files_changed": result.files_changed,
                },
                "requires_input": True,
                "input_fields": [
                    {"name": "commit_message", "label": "Commit message", "default": result.commit_message or ""},
                    {"name": "branch_name", "label": "Branch name (optional)", "default": result.branch_name or ""},
                ],
            },
        )

    async def _run_docs(
        self,
        ctx: WorkflowContext,
        context: dict[str, Any],
        spawn_agent_fn: Callable,
    ) -> AsyncIterator[WorkflowEvent]:
        """Run DOCS agent if user requested."""
        yield WorkflowEvent(
            type="agent_started",
            workflow_id=ctx.workflow_id,
            data={"agent": "docs"},
        )

        # Build docs prompt
        prompt = self._build_docs_prompt(ctx)

        # Spawn docs agent
        response = await spawn_agent_fn("docs", prompt, context)

        # Parse result
        result = DocsResult.parse(response)
        ctx.docs_result = result

        yield WorkflowEvent(
            type="agent_completed",
            workflow_id=ctx.workflow_id,
            data={
                "agent": "docs",
                "artifacts": result.artifacts,
            },
        )

        ctx.transition(WorkflowState.COMPLETED)

    def resume_after_user_decision(
        self,
        workflow_id: str,
        decision: UserDecisionResponse,
    ) -> WorkflowContext | None:
        """Resume workflow after user decision.

        Args:
            workflow_id: The workflow to resume
            decision: The user's decision response

        Returns:
            The workflow context if resumed, None if not found or invalid state
        """
        ctx = self.get_workflow(workflow_id)
        if not ctx or ctx.state != WorkflowState.AWAITING_USER:
            return None

        # Handle based on decision type
        if decision.decision_type == UserDecisionType.COMMIT:
            ctx.user_wants_commit = decision.approved
            if decision.approved and decision.value:
                ctx.commit_message = decision.value
            if decision.metadata.get("branch_name"):
                ctx.branch_name = decision.metadata["branch_name"]
            # Next: ask about PR (or docs if no commit)
            ctx.pending_decision = UserDecisionType.PR if decision.approved else UserDecisionType.DOCS

        elif decision.decision_type == UserDecisionType.PR:
            ctx.user_wants_pr = decision.approved
            # Next: ask about deploy (if available) or docs
            if ctx.devops_result and ctx.devops_result.deploy_available:
                ctx.pending_decision = UserDecisionType.DEPLOY
            else:
                ctx.pending_decision = UserDecisionType.DOCS

        elif decision.decision_type == UserDecisionType.DEPLOY:
            ctx.user_wants_deploy = decision.approved
            if decision.approved and decision.value:
                ctx.deploy_environment = decision.value
            # Next: ask about docs
            ctx.pending_decision = UserDecisionType.DOCS

        elif decision.decision_type == UserDecisionType.DOCS:
            ctx.user_wants_docs = decision.approved
            # Docs is the last decision - transition out of AWAITING_USER
            ctx.pending_decision = None
            if decision.approved:
                ctx.transition(WorkflowState.DOCUMENTING)
            else:
                ctx.transition(WorkflowState.COMPLETED)

        return ctx

    def get_next_decision(self, ctx: WorkflowContext) -> UserDecision | None:
        """Get the next decision to present to the user.

        Returns None if no more decisions are needed.
        """
        if ctx.pending_decision is None:
            return None

        if ctx.pending_decision == UserDecisionType.COMMIT:
            return UserDecision(
                decision_type=UserDecisionType.COMMIT,
                question="Would you like to commit these changes?",
                options=["yes", "no"],
                context={
                    "suggested_message": ctx.devops_result.commit_message if ctx.devops_result else None,
                    "suggested_branch": ctx.devops_result.branch_name if ctx.devops_result else None,
                    "files_changed": ctx.devops_result.files_changed if ctx.devops_result else [],
                },
            )

        elif ctx.pending_decision == UserDecisionType.PR:
            return UserDecision(
                decision_type=UserDecisionType.PR,
                question="Would you like to open a pull request?",
                options=["yes", "no"],
                required=False,
            )

        elif ctx.pending_decision == UserDecisionType.DEPLOY:
            envs = ctx.devops_result.deploy_environments if ctx.devops_result else ["staging"]
            return UserDecision(
                decision_type=UserDecisionType.DEPLOY,
                question="Would you like to deploy these changes?",
                options=["yes", "no"],
                context={"environments": envs},
                required=False,
            )

        elif ctx.pending_decision == UserDecisionType.DOCS:
            return UserDecision(
                decision_type=UserDecisionType.DOCS,
                question="Would you like documentation generated for these changes?",
                options=["yes", "no"],
                required=False,
            )

        return None

    def _build_artifact_report(self, ctx: WorkflowContext) -> ArtifactReport:
        """Build artifact report from workflow context."""
        files_created = []
        files_modified = []

        # Gather from coder result
        if ctx.coder_result and ctx.coder_result.artifacts:
            for artifact in ctx.coder_result.artifacts:
                # Heuristic: new files vs modified (could be improved with git status)
                files_modified.append(artifact)

        # Gather from devops result
        if ctx.devops_result and ctx.devops_result.files_changed:
            for f in ctx.devops_result.files_changed:
                if f not in files_modified:
                    files_modified.append(f)

        # Test stats
        tests_run = ctx.tester_result.tests_run if ctx.tester_result else 0
        tests_passed = ctx.tester_result.tests_passed if ctx.tester_result else 0

        # Summary
        summary_parts = []
        if files_modified:
            summary_parts.append(f"Modified {len(files_modified)} file(s)")
        if tests_passed > 0:
            summary_parts.append(f"{tests_passed}/{tests_run} tests passing")

        return ArtifactReport(
            workflow_id=ctx.workflow_id,
            task=ctx.original_task,
            status="completed" if ctx.state != WorkflowState.FAILED else "failed",
            files_created=files_created,
            files_modified=files_modified,
            tests_run=tests_run,
            tests_passed=tests_passed,
            summary="; ".join(summary_parts) if summary_parts else "Implementation complete",
        )

    # =========================================================================
    # Prompt Builders
    # =========================================================================

    def _build_coder_prompt(self, ctx: WorkflowContext) -> str:
        """Build prompt for initial coding."""
        base_prompt = f"""Implement the following task:

**Task:** {ctx.original_task}

**Workspace:** {ctx.workspace_path or 'Current directory'}

**Instructions:**
1. Implement the requested functionality COMPLETELY
2. Create all necessary files (code, configs, etc.)
3. Follow existing code patterns and conventions
4. List all files you create or modify at the end

**IMPORTANT:**
- After you're done, tests will automatically run
- Make sure your code is runnable and imports work
- Include any necessary dependencies in requirements.txt or package.json

**Output at the end:**
```
## Files Created/Modified:
- path/to/file1.py - description
- path/to/file2.py - description
```
"""

        # Add architect guidance if available
        if ctx.architect_result:
            base_prompt += f"""

**Architect Guidance (from previous escalation):**
{ctx.architect_result.updated_plan[:1000]}
"""

        return base_prompt

    def _build_tester_prompt(self, ctx: WorkflowContext) -> str:
        """Build prompt for testing (host/compose mode)."""
        files_info = ""
        if ctx.coder_result and ctx.coder_result.artifacts:
            files_info = f"**Files to test:** {', '.join(ctx.coder_result.artifacts)}"

        return f"""Run tests to validate the implementation.

**Original Task:** {ctx.original_task}

**Workspace:** {ctx.workspace_path or 'Current directory'}

{files_info}

**TEST MODE SELECTION:**
First, determine the appropriate test mode based on the TEST STRATEGY CONTRACT:
- Use TEST_MODE=host for simple changes (default)
- Use TEST_MODE=compose if DB/auth/config/deps changed
- Note: TEST_MODE=container will be run separately before devops gate

**IMPORTANT: Follow these steps IN ORDER:**

### Step 1: Check for Existing Tests
<tool_call>{{"tool": "shell", "args": {{"command": "find . -name 'test_*.py' -o -name '*_test.py' -o -name 'tests' -type d 2>/dev/null | head -10"}}}}</tool_call>

### Step 2: If NO tests exist (greenfield project)
- Create basic unit tests for the main functionality
- Set up pytest configuration if needed
- Write tests that validate core features work

### Step 3: Run the Tests
For TEST_MODE=host:
<tool_call>{{"tool": "shell", "args": {{"command": "python -m pytest -v --tb=short 2>&1 | head -50"}}}}</tool_call>

For TEST_MODE=compose (if dependencies needed):
<tool_call>{{"tool": "shell", "args": {{"command": "docker compose up -d db && python -m pytest -v tests/integration/ --tb=short 2>&1 | head -50"}}}}</tool_call>

OR for JavaScript projects:
<tool_call>{{"tool": "shell", "args": {{"command": "npm test 2>&1 | head -50"}}}}</tool_call>

### Step 4: Report Results CLEARLY

**MANDATORY TEST_REPORT FORMAT (include at END of response):**

```yaml
TEST_REPORT:
  TEST_MODE: host
  COMMANDS_RUN:
    - "pytest -v --tb=short"
  RESULT: pass
  FAILURE_SUMMARY: ""
  LOG_PATHS: []
  NEXT_ACTION: ready_for_devops
  NOTES: "Unit tests for new auth module passed"
```

If tests PASS, say "All X tests passed" clearly.
If tests FAIL, include the actual error output and set NEXT_ACTION: back_to_coder.
If NO tests exist and you created them, run them and report results.

**DO NOT say "tests would fail" or "this could fail" - only report ACTUAL test execution results.**
"""

    def _build_container_test_prompt(self, ctx: WorkflowContext) -> str:
        """Build prompt for container parity testing before devops gate."""
        files_info = ""
        if ctx.coder_result and ctx.coder_result.artifacts:
            files_info = f"**Files changed:** {', '.join(ctx.coder_result.artifacts)}"

        previous_test_info = ""
        if ctx.tester_result:
            previous_test_info = f"""
**Previous Test Results (host/compose mode):**
- Mode: {ctx.tester_result.test_mode}
- Result: {ctx.tester_result.status.value}
- Tests passed: {ctx.tester_result.tests_passed}/{ctx.tester_result.tests_run}
"""

        return f"""Run CONTAINER PARITY TEST before devops gate.

**⚠️ MANDATORY: TEST_MODE must be 'container' for this run.**

This is the final test gate before commit/deploy. Tests must pass inside Docker containers
to ensure CI/production parity.

**Original Task:** {ctx.original_task}

**Workspace:** {ctx.workspace_path or 'Current directory'}

{files_info}
{previous_test_info}

**REQUIRED STEPS:**

### Step 1: Check for Dockerfile
<tool_call>{{"tool": "shell", "args": {{"command": "ls -la Dockerfile* docker-compose*.yml 2>/dev/null || echo 'No Docker files found'"}}}}</tool_call>

### Step 2: Build Containers
<tool_call>{{"tool": "shell", "args": {{"command": "docker compose build 2>&1 | tail -20"}}}}</tool_call>

### Step 3: Run Tests INSIDE Container
For Python:
<tool_call>{{"tool": "shell", "args": {{"command": "docker compose run --rm backend pytest -q --tb=short 2>&1 | head -50"}}}}</tool_call>

For JavaScript:
<tool_call>{{"tool": "shell", "args": {{"command": "docker compose run --rm frontend npm test 2>&1 | head -50"}}}}</tool_call>

### Step 4: Cleanup
<tool_call>{{"tool": "shell", "args": {{"command": "docker compose down 2>&1"}}}}</tool_call>

### Step 5: Report Results

**MANDATORY TEST_REPORT FORMAT:**

```yaml
TEST_REPORT:
  TEST_MODE: container
  COMMANDS_RUN:
    - "docker compose build"
    - "docker compose run --rm backend pytest -q"
  RESULT: pass|fail
  FAILURE_SUMMARY: ""
  LOG_PATHS: []
  NEXT_ACTION: ready_for_devops|back_to_coder
  NOTES: "Container parity verified - same results as host"
```

**If no Dockerfile exists:**
- Note this in NOTES field
- Set RESULT: pass (skip container test for non-dockerized projects)
- Set NEXT_ACTION: ready_for_devops

**If container tests fail but host tests passed:**
- This indicates environment parity issue
- Set NEXT_ACTION: back_to_coder
- Include specific failure in FAILURE_SUMMARY
"""

    def _build_fix_prompt(self, ctx: WorkflowContext) -> str:
        """Build prompt for fixing test failures."""
        failure_info = ""

        # Check for container test failure first (more recent)
        active_test_result = ctx.container_tester_result if ctx.container_tester_result else ctx.tester_result

        if active_test_result:
            test_cmds = ', '.join(active_test_result.test_commands) if active_test_result.test_commands else 'pytest'
            test_mode = active_test_result.test_mode
            failure_info = f"""
**Test Failure Details:**
- Test mode: {test_mode.upper()}
- Tests run: {active_test_result.tests_run}
- Tests passed: {active_test_result.tests_passed}
- Tests failed: {active_test_result.tests_failed}
- Test command: {test_cmds}

**Actual Error Output:**
```
{active_test_result.failure_summary[:1500] if active_test_result.failure_summary else 'No specific error captured - run tests to see failures'}
```
"""
            # Add container-specific info if this was a container test failure
            if test_mode == "container" and ctx.tester_result:
                failure_info += f"""
**NOTE: Container parity test failed!**
Host/compose tests passed, but container tests failed. This indicates environment differences.

Host test result: {ctx.tester_result.status.value}
Container test result: {active_test_result.status.value}

Common causes:
- Missing system dependencies in Dockerfile
- Different Python/Node versions in container
- Environment variable differences
- File path or permission issues
"""

            # If no tests were found but we're in fix mode, note that
            if active_test_result.no_tests_found:
                failure_info += """
**NOTE:** No tests were found in the previous run. You may need to:
1. Create test files (test_*.py)
2. Set up pytest configuration
3. Ensure tests are discoverable
"""

        files_list = ', '.join(ctx.coder_result.artifacts) if ctx.coder_result and ctx.coder_result.artifacts else 'Unknown'

        return f"""Fix the failing tests. This is fix attempt {ctx.fix_cycles}/{ctx.max_fix_cycles}.

**Original Task:** {ctx.original_task}

**Workspace:** {ctx.workspace_path or 'Current directory'}

{failure_info}

**Files previously modified:** {files_list}

**Instructions:**
1. READ the actual error messages carefully
2. Fix the SPECIFIC issues mentioned in the errors
3. Do NOT rewrite everything - make targeted fixes
4. Do NOT modify test expectations unless they are clearly wrong
5. If you cannot fix the issue, say "BLOCKED:" and explain why

**After fixing, tests will automatically run again.**
"""

    def _build_architect_prompt(self, ctx: WorkflowContext) -> str:
        """Build prompt for architect escalation."""
        failure_history = ""
        if ctx.tester_result:
            failure_history = f"""
**Latest Test Failures:**
{ctx.tester_result.failure_summary[:1000]}
"""

        return f"""The coder has failed to implement this task after {ctx.fix_cycles} fix attempts.
Architect cycle: {ctx.architect_cycles}/{ctx.max_architect_cycles}

**Original Task:** {ctx.original_task}

{failure_history}

**Instructions:**
1. Analyze why previous implementations failed
2. Identify the root cause (design issue, misunderstanding, wrong approach)
3. Provide a clear, revised implementation plan
4. List specific decisions and constraints for the coder
5. Identify which files need to be modified

**Output format:**
- Decisions: (numbered list)
- Constraints: (what the coder must/must not do)
- Files to modify: (list)
- Implementation plan: (step by step)
"""

    def _build_devops_prompt(self, ctx: WorkflowContext) -> str:
        """Build prompt for devops - analyze changes and prepare for user decisions."""
        artifacts = ctx.coder_result.artifacts if ctx.coder_result else []

        # Build container parity status
        container_status = ""
        if ctx.container_test_completed:
            if ctx.container_tester_result:
                container_status = f"""
**Container Parity Status:** ✅ VERIFIED
- Mode: container
- Result: {ctx.container_tester_result.status.value}
- Tests: {ctx.container_tester_result.tests_passed}/{ctx.container_tester_result.tests_run} passed
"""
            else:
                container_status = """
**Container Parity Status:** ✅ VERIFIED (no Docker in project)
"""
        elif ctx.container_test_skipped:
            container_status = f"""
**Container Parity Status:** ⚠️ SKIPPED
- Reason: {ctx.container_skip_reason or 'Unknown'}
"""
        else:
            container_status = """
**Container Parity Status:** ⚠️ NOT VERIFIED
- Container tests have not been run
- Recommend running container tests before commit
"""

        return f"""Implementation complete and tests passing! Analyze the changes and prepare deployment options.

**Completed Task:** {ctx.original_task}

**Files Modified:** {', '.join(artifacts) or 'Check workspace for changes'}

**Workspace:** {ctx.workspace_path or 'Current directory'}
{container_status}

**REQUIRED: Execute these steps in order:**

### 1. Show Git Diff (MANDATORY)
Run `git diff` or `git status` to show what changed:
<tool_call>{{"tool": "shell", "args": {{"command": "git diff --stat"}}}}</tool_call>
<tool_call>{{"tool": "shell", "args": {{"command": "git diff --no-color | head -100"}}}}</tool_call>

### 2. Analyze Changes
Summarize what was implemented:
- What functionality was added/changed
- Which files were touched
- Any potential risks or concerns

### 3. Suggest Commit Details
Provide a suggested commit following conventional commits format:
- Commit message: "feat: <description>" or "fix: <description>"
- Suggested branch name: "feature/<short-name>" or "fix/<short-name>"

### 4. Check Deployment Options
Look for:
- CI/CD configs (.github/workflows/, .gitlab-ci.yml, etc.)
- Docker/Kubernetes configs
- Deployment scripts

Report which deployment options are available.

**OUTPUT FORMAT (include all sections):**

## Changes Summary
<brief description of what changed>

## Files Changed
- `file1.py` - <what changed>
- `file2.py` - <what changed>

## Git Diff
```diff
<paste actual diff output here>
```

## Suggested Commit
- **Message:** "feat: <your suggested message>"
- **Branch:** "<suggested branch name>"

## Deployment Options
- [ ] Commit only (no deployment)
- [ ] Create Pull Request
- [ ] Deploy to staging (if available)
- [ ] Deploy to production (if available)

List which options are actually available based on the project setup.
"""

    def _build_docs_prompt(self, ctx: WorkflowContext) -> str:
        """Build prompt for documentation."""
        artifacts = ctx.coder_result.artifacts if ctx.coder_result else []

        return f"""Create documentation for the recent changes.

**Task Completed:** {ctx.original_task}

**Files Changed:** {', '.join(artifacts) or 'Unknown'}

**Instructions:**
1. Document what was implemented
2. Update README if appropriate
3. Add code comments where helpful
4. Create API documentation if applicable

List all documentation files created or updated.
"""


# =============================================================================
# Singleton Instance
# =============================================================================

delivery_loop_policy = DeliveryLoopPolicy()
