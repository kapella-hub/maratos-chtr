"""Tool call interpreter for agent runtime.

Parses tool call blocks from LLM output, executes them through the
tool executor, and formats results for the next LLM turn.

Protocol:
    <tool_call>{"tool": "filesystem", "args": {"action": "read", "path": "/file"}}</tool_call>

Multiple tool calls can appear in a single response and are executed sequentially.

Enterprise guardrails:
    - Budget enforcement (tool loops, shell time, etc.)
    - Audit logging for all tool calls
    - Agent-specific policy enforcement
    - Diff-first mode for high-impact actions
"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from app.tools.base import ToolResult, registry as tool_registry
from app.tools.executor import tool_executor

# Guardrails integration
from app.guardrails import (
    BudgetTracker,
    BudgetExceededError,
    BudgetType,
    AgentPolicy,
    get_agent_policy,
    AuditRepository,
    DiffApprovalManager,
    diff_approval_manager,
    ApprovalStatus,
)

logger = logging.getLogger(__name__)

# Pattern to match tool call blocks
TOOL_CALL_PATTERN = re.compile(
    r'<tool_call>\s*(\{.*?\})\s*</tool_call>',
    re.DOTALL
)

# Alternative patterns for flexibility
ALT_PATTERNS = [
    re.compile(r'```tool\s*\n(\{.*?\})\s*\n```', re.DOTALL),
    re.compile(r'<function_call>\s*(\{.*?\})\s*</function_call>', re.DOTALL),
]


@dataclass
class ToolInvocation:
    """A parsed tool invocation."""

    tool_id: str
    args: dict[str, Any]
    raw_json: str
    parse_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool_id,
            "args": self.args,
            "parse_error": self.parse_error,
        }


@dataclass
class ToolExecutionResult:
    """Result of executing a tool invocation."""

    invocation: ToolInvocation
    result: ToolResult
    duration_ms: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.invocation.tool_id,
            "args": self.invocation.args,
            "success": self.result.success,
            "output": self.result.output[:500] if self.result.output else "",
            "error": self.result.error,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class ToolPolicy:
    """Policy for tool execution.

    Note: For enterprise deployments, use AgentPolicy from guardrails module
    which provides more comprehensive controls.
    """

    allowed_tools: list[str] | None = None  # None = all allowed
    max_iterations: int = 6
    per_call_timeout_seconds: float = 300.0
    workspace_path: str | None = None  # For filesystem jail

    def is_tool_allowed(self, tool_id: str) -> bool:
        if self.allowed_tools is None:
            return True
        return tool_id in self.allowed_tools


@dataclass
class InterpreterContext:
    """Context for tool interpretation session.

    Supports both basic ToolPolicy and enterprise AgentPolicy with budgets.
    """

    session_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None
    policy: ToolPolicy = field(default_factory=ToolPolicy)
    iteration: int = 0
    total_tool_calls: int = 0
    execution_history: list[ToolExecutionResult] = field(default_factory=list)

    # Enterprise guardrails (optional)
    agent_policy: AgentPolicy | None = None
    budget_tracker: BudgetTracker | None = None
    enable_audit: bool = True  # Log to audit repository
    enable_diff_approval: bool = False  # Require approval for high-impact actions

    def __post_init__(self):
        """Initialize budget tracker from agent policy if available."""
        if self.agent_policy and not self.budget_tracker:
            self.budget_tracker = BudgetTracker(
                policy=self.agent_policy.budget,
                session_id=self.session_id,
                agent_id=self.agent_id,
            )
            # Sync policy settings
            self.policy.allowed_tools = self.agent_policy.allowed_tools
            self.policy.max_iterations = self.agent_policy.budget.max_tool_loops_per_message
            if self.agent_policy.filesystem.write_paths:
                # Use first write path as workspace
                self.policy.workspace_path = self.agent_policy.filesystem.write_paths[0]

    @classmethod
    def from_agent_id(
        cls,
        agent_id: str,
        session_id: str | None = None,
        task_id: str | None = None,
        enable_audit: bool = True,
        enable_diff_approval: bool = False,
    ) -> "InterpreterContext":
        """Create context with enterprise guardrails for a specific agent."""
        agent_policy = get_agent_policy(agent_id)
        return cls(
            session_id=session_id,
            task_id=task_id,
            agent_id=agent_id,
            agent_policy=agent_policy,
            enable_audit=enable_audit,
            enable_diff_approval=enable_diff_approval or agent_policy.diff_approval.enabled,
        )


def parse_tool_blocks(text: str) -> list[ToolInvocation]:
    """Parse tool call blocks from LLM output.

    Supports multiple formats:
    - <tool_call>{"tool": "...", "args": {...}}</tool_call>
    - ```tool\n{"tool": "...", "args": {...}}\n```
    - <function_call>...</function_call>

    Returns list of ToolInvocation objects.
    """
    invocations = []

    # Try primary pattern first
    matches = TOOL_CALL_PATTERN.findall(text)

    # Try alternative patterns if no matches
    if not matches:
        for pattern in ALT_PATTERNS:
            matches = pattern.findall(text)
            if matches:
                break

    for raw_json in matches:
        invocation = _parse_single_invocation(raw_json)
        invocations.append(invocation)

    return invocations


def _parse_single_invocation(raw_json: str) -> ToolInvocation:
    """Parse a single JSON tool invocation."""
    try:
        data = json.loads(raw_json)

        # Support both formats:
        # {"tool": "name", "args": {...}}
        # {"name": "tool_name", "arguments": {...}}
        tool_id = data.get("tool") or data.get("name", "")
        args = data.get("args") or data.get("arguments", {})

        if not tool_id:
            return ToolInvocation(
                tool_id="",
                args={},
                raw_json=raw_json,
                parse_error="Missing 'tool' or 'name' field",
            )

        return ToolInvocation(
            tool_id=tool_id,
            args=args if isinstance(args, dict) else {},
            raw_json=raw_json,
        )

    except json.JSONDecodeError as e:
        return ToolInvocation(
            tool_id="",
            args={},
            raw_json=raw_json,
            parse_error=f"Invalid JSON: {e}",
        )


def has_tool_calls(text: str) -> bool:
    """Check if text contains any tool call blocks."""
    if TOOL_CALL_PATTERN.search(text):
        return True
    for pattern in ALT_PATTERNS:
        if pattern.search(text):
            return True
    return False


def strip_tool_blocks(text: str) -> str:
    """Remove tool call blocks from text, leaving other content."""
    result = TOOL_CALL_PATTERN.sub('', text)
    for pattern in ALT_PATTERNS:
        result = pattern.sub('', result)
    return result.strip()


async def execute_invocations(
    invocations: list[ToolInvocation],
    context: InterpreterContext,
) -> list[ToolExecutionResult]:
    """Execute a list of tool invocations.

    Enforces:
    - Tool allowlist (from policy or agent_policy)
    - Budget limits (tool calls, shell time)
    - Filesystem jail for write operations
    - Per-call timeout
    - Audit logging via AuditRepository

    Returns list of execution results.
    """
    results = []
    budget_tracker = context.budget_tracker

    for invocation in invocations:
        audit_log_id: str | None = None
        sandbox_violation = False
        budget_exceeded = False
        policy_blocked = False

        # Check for parse errors
        if invocation.parse_error:
            results.append(ToolExecutionResult(
                invocation=invocation,
                result=ToolResult(
                    success=False,
                    output="",
                    error=f"Parse error: {invocation.parse_error}",
                ),
                duration_ms=0,
            ))
            continue

        # Check allowlist
        if not context.policy.is_tool_allowed(invocation.tool_id):
            policy_blocked = True
            error_msg = f"Tool '{invocation.tool_id}' not allowed for agent '{context.agent_id}'"

            # Log blocked tool call
            if context.enable_audit:
                try:
                    log = await AuditRepository.log_tool_call(
                        tool_name=invocation.tool_id,
                        parameters=invocation.args,
                        session_id=context.session_id,
                        task_id=context.task_id,
                        agent_id=context.agent_id,
                    )
                    await AuditRepository.log_tool_result(
                        log_id=log.id,
                        success=False,
                        error=error_msg,
                        policy_blocked=True,
                    )
                except Exception as e:
                    logger.error(f"Audit logging failed: {e}")

            results.append(ToolExecutionResult(
                invocation=invocation,
                result=ToolResult(
                    success=False,
                    output="",
                    error=error_msg,
                ),
                duration_ms=0,
            ))
            continue

        # Check budget before execution
        if budget_tracker:
            try:
                budget_tracker.check_tool_call()
            except BudgetExceededError as e:
                budget_exceeded = True

                # Log budget violation
                if context.enable_audit:
                    try:
                        await AuditRepository.log_budget_check(
                            budget_type=e.budget_type.value,
                            current_value=float(e.current),
                            limit_value=float(e.limit),
                            exceeded=True,
                            session_id=context.session_id,
                            task_id=context.task_id,
                            agent_id=context.agent_id,
                        )
                    except Exception as log_err:
                        logger.error(f"Budget audit logging failed: {log_err}")

                results.append(ToolExecutionResult(
                    invocation=invocation,
                    result=ToolResult(
                        success=False,
                        output="",
                        error=e.message,
                    ),
                    duration_ms=0,
                ))
                # Stop processing further invocations when budget exceeded
                break

        # Check tool exists
        tool = tool_registry.get(invocation.tool_id)
        if not tool:
            results.append(ToolExecutionResult(
                invocation=invocation,
                result=ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown tool: {invocation.tool_id}",
                ),
                duration_ms=0,
            ))
            continue

        # Inject workspace path for filesystem operations
        args = invocation.args.copy()
        if invocation.tool_id == "filesystem" and context.policy.workspace_path:
            # Enforce workspace for write operations
            action = args.get("action", "")
            if action in ("write", "delete", "copy"):
                path = args.get("path", "")
                dest = args.get("dest", "")
                target_path = dest if action == "copy" else path

                if target_path and not target_path.startswith(context.policy.workspace_path):
                    sandbox_violation = True
                    error_msg = f"Write operations only allowed in workspace: {context.policy.workspace_path}"

                    # Log sandbox violation
                    if context.enable_audit:
                        try:
                            log = await AuditRepository.log_tool_call(
                                tool_name=invocation.tool_id,
                                tool_action=action,
                                parameters=invocation.args,
                                session_id=context.session_id,
                                task_id=context.task_id,
                                agent_id=context.agent_id,
                            )
                            await AuditRepository.log_tool_result(
                                log_id=log.id,
                                success=False,
                                error=error_msg,
                                sandbox_violation=True,
                            )
                            await AuditRepository.log_file_operation(
                                file_path=target_path,
                                operation=action,
                                in_workspace=False,
                                blocked=True,
                                success=False,
                                error=error_msg,
                                session_id=context.session_id,
                                task_id=context.task_id,
                                agent_id=context.agent_id,
                            )
                        except Exception as e:
                            logger.error(f"Audit logging failed: {e}")

                    results.append(ToolExecutionResult(
                        invocation=invocation,
                        result=ToolResult(
                            success=False,
                            output="",
                            error=error_msg,
                        ),
                        duration_ms=0,
                    ))
                    continue

        # === DIFF-FIRST MODE: Check if approval is required ===
        requires_approval = False
        approval_action = None

        if context.enable_diff_approval and context.agent_policy:
            diff_policy = context.agent_policy.diff_approval
            if diff_policy.enabled:
                # Check for filesystem write/delete operations
                if invocation.tool_id == "filesystem":
                    action = args.get("action", "")
                    file_path = args.get("path", "")

                    if action == "write" and diff_policy.require_approval_for_writes:
                        if diff_policy.requires_approval("write", file_path):
                            requires_approval = True
                            approval_action = "write"
                    elif action == "delete" and diff_policy.require_approval_for_deletes:
                        requires_approval = True
                        approval_action = "delete"

                # Check for shell operations
                elif invocation.tool_id == "shell" and diff_policy.require_approval_for_shell:
                    requires_approval = True
                    approval_action = "shell"

        if requires_approval:
            try:
                # Create approval request based on action type
                if approval_action == "write":
                    file_path = args.get("path", "")
                    new_content = args.get("content", "")

                    # Try to read original content for diff
                    original_content = None
                    try:
                        from pathlib import Path
                        path_obj = Path(file_path).expanduser()
                        if path_obj.exists():
                            original_content = path_obj.read_text()
                    except Exception:
                        pass

                    approval = await diff_approval_manager.create_write_approval(
                        session_id=context.session_id or "",
                        agent_id=context.agent_id or "",
                        task_id=context.task_id,
                        file_path=file_path,
                        original_content=original_content,
                        new_content=new_content,
                    )

                elif approval_action == "delete":
                    file_path = args.get("path", "")

                    # Try to read content before deletion
                    original_content = None
                    try:
                        from pathlib import Path
                        path_obj = Path(file_path).expanduser()
                        if path_obj.exists() and path_obj.is_file():
                            original_content = path_obj.read_text()
                    except Exception:
                        pass

                    approval = await diff_approval_manager.create_delete_approval(
                        session_id=context.session_id or "",
                        agent_id=context.agent_id or "",
                        task_id=context.task_id,
                        file_path=file_path,
                        original_content=original_content,
                    )

                elif approval_action == "shell":
                    command = args.get("command", "")
                    workdir = args.get("workdir")

                    approval = await diff_approval_manager.create_shell_approval(
                        session_id=context.session_id or "",
                        agent_id=context.agent_id or "",
                        task_id=context.task_id,
                        command=command,
                        workdir=workdir,
                    )
                else:
                    approval = None

                if approval:
                    # Log the approval request
                    if context.enable_audit:
                        try:
                            await AuditRepository.log_event(
                                category="diff_approval",
                                action="requested",
                                session_id=context.session_id,
                                task_id=context.task_id,
                                agent_id=context.agent_id,
                                success=True,
                                metadata={
                                    "approval_id": approval.id,
                                    "action_type": approval_action,
                                    "file_path": args.get("path"),
                                },
                            )
                        except Exception as log_err:
                            logger.warning(f"Failed to log approval request: {log_err}")

                    # Wait for approval with timeout
                    try:
                        status = await diff_approval_manager.wait_for_approval(
                            approval.id,
                            timeout=context.agent_policy.diff_approval.approval_timeout_seconds
                            if context.agent_policy
                            else 300.0,
                        )

                        if status == ApprovalStatus.REJECTED:
                            results.append(ToolExecutionResult(
                                invocation=invocation,
                                result=ToolResult(
                                    success=False,
                                    output="",
                                    error=f"Action rejected by user: {approval.approval_note or 'No reason given'}",
                                    data={"approval_id": approval.id, "status": "rejected"},
                                ),
                                duration_ms=0,
                            ))
                            continue

                        elif status == ApprovalStatus.EXPIRED:
                            results.append(ToolExecutionResult(
                                invocation=invocation,
                                result=ToolResult(
                                    success=False,
                                    output="",
                                    error="Approval request expired",
                                    data={"approval_id": approval.id, "status": "expired"},
                                ),
                                duration_ms=0,
                            ))
                            continue

                        # Approved - continue with execution
                        logger.info(f"Approval {approval.id} granted, proceeding with {approval_action}")

                    except asyncio.TimeoutError:
                        results.append(ToolExecutionResult(
                            invocation=invocation,
                            result=ToolResult(
                                success=False,
                                output="",
                                error="Approval request timed out",
                                data={"approval_id": approval.id, "status": "timeout"},
                            ),
                            duration_ms=0,
                        ))
                        continue

            except Exception as approval_err:
                logger.error(f"Diff approval error: {approval_err}", exc_info=True)
                # Continue with execution on approval error (fail-open for now)
                # In production, you might want to fail-closed instead

        # Log tool call before execution
        if context.enable_audit:
            try:
                log = await AuditRepository.log_tool_call(
                    tool_name=invocation.tool_id,
                    tool_action=args.get("action"),
                    parameters=invocation.args,
                    session_id=context.session_id,
                    task_id=context.task_id,
                    agent_id=context.agent_id,
                )
                audit_log_id = log.id
            except Exception as e:
                logger.error(f"Audit logging failed: {e}")

        # Execute with timeout and optional shell time tracking
        start_time = time.time()
        is_shell_call = invocation.tool_id == "shell"

        try:
            # Check shell budget before execution
            if is_shell_call and budget_tracker:
                budget_tracker.check_shell_call()

            result = await asyncio.wait_for(
                tool_executor.execute(
                    tool_id=invocation.tool_id,
                    session_id=context.session_id,
                    task_id=context.task_id,
                    agent_id=context.agent_id,
                    skip_guardrails=True,  # Interpreter already enforces guardrails
                    **args,
                ),
                timeout=context.policy.per_call_timeout_seconds,
            )
        except asyncio.TimeoutError:
            result = ToolResult(
                success=False,
                output="",
                error=f"Tool execution timed out after {context.policy.per_call_timeout_seconds}s",
            )
        except BudgetExceededError as e:
            budget_exceeded = True
            result = ToolResult(
                success=False,
                output="",
                error=e.message,
            )
        except Exception as e:
            logger.error(f"Tool execution error: {e}", exc_info=True)
            result = ToolResult(
                success=False,
                output="",
                error=str(e),
            )

        duration_ms = (time.time() - start_time) * 1000
        duration_seconds = duration_ms / 1000

        # Record shell time if applicable
        if is_shell_call and budget_tracker and result.success:
            budget_tracker.record_shell_time(duration_seconds)

            # Check if shell execution exceeded per-call limit
            if context.agent_policy:
                max_shell_time = context.agent_policy.budget.max_shell_time_seconds
                if duration_seconds > max_shell_time:
                    logger.warning(
                        f"Shell execution exceeded time limit: "
                        f"{duration_seconds:.2f}s > {max_shell_time}s"
                    )

        # Record tool call in budget tracker
        if budget_tracker:
            budget_tracker.record_tool_call(
                output_size=len(result.output) if result.output else 0
            )

        # Log tool result
        if context.enable_audit and audit_log_id:
            try:
                await AuditRepository.log_tool_result(
                    log_id=audit_log_id,
                    success=result.success,
                    output=result.output,
                    error=result.error,
                    duration_ms=duration_ms,
                    sandbox_violation=sandbox_violation,
                    budget_exceeded=budget_exceeded,
                    policy_blocked=policy_blocked,
                )
            except Exception as e:
                logger.error(f"Audit logging failed: {e}")

        exec_result = ToolExecutionResult(
            invocation=invocation,
            result=result,
            duration_ms=duration_ms,
        )
        results.append(exec_result)
        context.execution_history.append(exec_result)
        context.total_tool_calls += 1

        logger.info(
            f"Tool {invocation.tool_id}: success={result.success}, "
            f"duration={duration_ms:.0f}ms"
        )

    return results


def format_tool_results_for_llm(results: list[ToolExecutionResult]) -> str:
    """Format tool execution results for the next LLM turn.

    Returns a structured message that the LLM can understand.
    """
    if not results:
        return ""

    parts = ["<tool_results>"]

    for result in results:
        parts.append(f"<result tool=\"{result.invocation.tool_id}\">")

        if result.result.success:
            parts.append(f"<status>success</status>")
            output = result.result.output
            try:
                output = _format_output_with_codeblocks(output)
            except Exception:
                pass  # Fallback to raw output if regex fails

            # Truncate very long outputs
            if len(output) > 10000:
                output = output[:10000] + "\n... [truncated]"
            parts.append(f"<output>{output}</output>")
        else:
            parts.append(f"<status>error</status>")
            parts.append(f"<error>{result.result.error}</error>")

        parts.append("</result>")

    parts.append("</tool_results>")

    return "\n".join(parts)


def _format_output_with_codeblocks(text: str) -> str:
    """Format tool output to wrap code interactions in markdown blocks.
    
    This helps the LLM recognize code in tool output and format its own response accordingly.
    """
    lang_ids = {'python', 'javascript', 'typescript', 'java', 'html', 'css', 'bash', 'sh', 'yaml', 'json', 'sql', 'go', 'rust'}
    
    def replacer(match):
        header = match.group(1)
        spacing = match.group(2)
        content = match.group(3)
        
        if '```' in content:
            return match.group(0)
            
        first_line = content.split('\n')[0].strip()
        first_word = first_line.split(' ')[0].lower() if first_line else ""
        lang = first_word if first_word in lang_ids else ""
        
        return f"{header}\n{spacing}```{lang}\n{content}\n```"

    pattern = re.compile(
        r'^(File:.+?)(\n+)(?=(?:python|javascript|typescript|bash|sh|html|css|yaml|json|sql|go|rust)\b)(.+?)(?=\n\n|━━━━━━━━|-----|\Z)', 
        re.MULTILINE | re.DOTALL
    )
    
    return pattern.sub(replacer, text)


def create_repair_prompt(raw_json: str, error: str) -> str:
    """Create a prompt asking the LLM to repair invalid JSON."""
    return f"""Your previous tool call had invalid JSON. Please fix and re-emit.

Invalid JSON:
```
{raw_json}
```

Error: {error}

Please emit a corrected tool call using this exact format:
<tool_call>{{"tool": "tool_name", "args": {{"param": "value"}}}}</tool_call>
"""


class ToolInterpreter:
    """Main interpreter class for tool execution loops.

    Handles the multi-step loop:
    1. LLM emits tool call(s)
    2. System executes tool(s)
    3. System feeds results back to LLM
    4. Repeat until LLM emits final answer (no tool calls)

    Enterprise guardrails:
    - Budget enforcement at each iteration
    - Audit logging for all operations
    - Agent-specific policy enforcement
    """

    def __init__(
        self,
        context: InterpreterContext | None = None,
    ):
        self.context = context or InterpreterContext()
        self._repair_attempted = False

    @classmethod
    def for_agent(
        cls,
        agent_id: str,
        session_id: str | None = None,
        task_id: str | None = None,
        enable_audit: bool = True,
    ) -> "ToolInterpreter":
        """Create an interpreter with enterprise guardrails for a specific agent.

        This is the recommended factory method for production use.
        """
        context = InterpreterContext.from_agent_id(
            agent_id=agent_id,
            session_id=session_id,
            task_id=task_id,
            enable_audit=enable_audit,
        )
        return cls(context=context)

    def parse(self, text: str) -> list[ToolInvocation]:
        """Parse tool calls from LLM output."""
        return parse_tool_blocks(text)

    def has_tool_calls(self, text: str) -> bool:
        """Check if text contains tool calls."""
        return has_tool_calls(text)

    def strip_tool_blocks(self, text: str) -> str:
        """Remove tool blocks from text."""
        return strip_tool_blocks(text)

    async def execute(
        self,
        invocations: list[ToolInvocation],
    ) -> list[ToolExecutionResult]:
        """Execute tool invocations."""
        return await execute_invocations(invocations, self.context)

    def format_results(self, results: list[ToolExecutionResult]) -> str:
        """Format results for LLM."""
        return format_tool_results_for_llm(results)

    def check_iteration_limit(self) -> tuple[bool, str | None]:
        """Check if we've exceeded max iterations.

        Uses budget tracker if available, falls back to basic policy check.

        Returns (can_continue, error_message).
        """
        budget_tracker = self.context.budget_tracker

        if budget_tracker:
            try:
                budget_tracker.check_tool_loop()
                return True, None
            except BudgetExceededError as e:
                return False, e.message
        else:
            # Fallback to basic policy check
            if self.context.iteration >= self.context.policy.max_iterations:
                return False, f"Maximum tool iterations ({self.context.policy.max_iterations}) exceeded"
            return True, None

    def increment_iteration(self) -> None:
        """Increment iteration counter and record in budget tracker."""
        self.context.iteration += 1

        if self.context.budget_tracker:
            self.context.budget_tracker.record_tool_loop()

    def needs_repair(self, invocations: list[ToolInvocation]) -> tuple[bool, ToolInvocation | None]:
        """Check if any invocation needs JSON repair.

        Returns (needs_repair, first_broken_invocation).
        """
        if self._repair_attempted:
            return False, None

        for inv in invocations:
            if inv.parse_error:
                return True, inv
        return False, None

    def mark_repair_attempted(self) -> None:
        """Mark that we've attempted repair (only try once)."""
        self._repair_attempted = True

    def get_repair_prompt(self, invocation: ToolInvocation) -> str:
        """Get the repair prompt for invalid JSON."""
        return create_repair_prompt(invocation.raw_json, invocation.parse_error or "Unknown error")

    def get_summary(self) -> dict[str, Any]:
        """Get execution summary."""
        summary = {
            "iterations": self.context.iteration,
            "total_tool_calls": self.context.total_tool_calls,
            "execution_history": [r.to_dict() for r in self.context.execution_history],
        }

        # Include budget usage if available
        if self.context.budget_tracker:
            summary["budget_usage"] = self.context.budget_tracker.get_usage_summary()

        return summary

    def get_budget_remaining(self) -> dict[str, Any] | None:
        """Get remaining budget if budget tracking is enabled."""
        if self.context.budget_tracker:
            return self.context.budget_tracker.get_remaining()
        return None

    def is_budget_exhausted(self) -> bool:
        """Check if any budget is exhausted."""
        if self.context.budget_tracker:
            return self.context.budget_tracker.is_budget_exhausted()
        return False

    def reset_message_counters(self) -> None:
        """Reset per-message counters (call at start of new message)."""
        if self.context.budget_tracker:
            self.context.budget_tracker.reset_message_counters()

        self.context.iteration = 0
        self._repair_attempted = False
