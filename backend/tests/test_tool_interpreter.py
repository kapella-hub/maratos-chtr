"""Tests for the tool call interpreter."""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.tools.interpreter import (
    parse_tool_blocks,
    has_tool_calls,
    strip_tool_blocks,
    format_tool_results_for_llm,
    ToolInvocation,
    ToolExecutionResult,
    ToolPolicy,
    InterpreterContext,
    ToolInterpreter,
    execute_invocations,
)
from app.tools.base import ToolResult


class TestParseToolBlocks:
    """Test tool block parsing."""

    def test_parse_single_tool_call(self):
        """Parse a single tool call block."""
        text = '''Here's what I'll do:
<tool_call>{"tool": "filesystem", "args": {"action": "read", "path": "/tmp/test.txt"}}</tool_call>
'''
        invocations = parse_tool_blocks(text)
        assert len(invocations) == 1
        assert invocations[0].tool_id == "filesystem"
        assert invocations[0].args == {"action": "read", "path": "/tmp/test.txt"}
        assert invocations[0].parse_error is None

    def test_parse_multiple_tool_calls(self):
        """Parse multiple tool call blocks."""
        text = '''I'll read two files:
<tool_call>{"tool": "filesystem", "args": {"action": "read", "path": "/file1.txt"}}</tool_call>
<tool_call>{"tool": "filesystem", "args": {"action": "read", "path": "/file2.txt"}}</tool_call>
'''
        invocations = parse_tool_blocks(text)
        assert len(invocations) == 2
        assert invocations[0].args["path"] == "/file1.txt"
        assert invocations[1].args["path"] == "/file2.txt"

    def test_parse_alternative_format(self):
        """Parse alternative tool block formats."""
        text = '''```tool
{"tool": "shell", "args": {"command": "ls -la"}}
```'''
        invocations = parse_tool_blocks(text)
        assert len(invocations) == 1
        assert invocations[0].tool_id == "shell"
        assert invocations[0].args == {"command": "ls -la"}

    def test_parse_function_call_format(self):
        """Parse function_call format."""
        text = '''<function_call>{"name": "web_search", "arguments": {"query": "test"}}</function_call>'''
        invocations = parse_tool_blocks(text)
        assert len(invocations) == 1
        assert invocations[0].tool_id == "web_search"
        assert invocations[0].args == {"query": "test"}

    def test_parse_invalid_json(self):
        """Parse invalid JSON returns error."""
        text = '''<tool_call>{"tool": "test", "args": {invalid}}</tool_call>'''
        invocations = parse_tool_blocks(text)
        assert len(invocations) == 1
        assert invocations[0].parse_error is not None
        assert "Invalid JSON" in invocations[0].parse_error

    def test_parse_missing_tool_field(self):
        """Parse JSON missing tool field returns error."""
        text = '''<tool_call>{"args": {"path": "/test"}}</tool_call>'''
        invocations = parse_tool_blocks(text)
        assert len(invocations) == 1
        assert invocations[0].parse_error is not None
        assert "Missing" in invocations[0].parse_error

    def test_parse_no_tool_calls(self):
        """Parse text with no tool calls returns empty list."""
        text = "This is just a regular response with no tools."
        invocations = parse_tool_blocks(text)
        assert len(invocations) == 0


class TestHasToolCalls:
    """Test tool call detection."""

    def test_has_tool_calls_true(self):
        """Detect presence of tool calls."""
        text = 'Some text <tool_call>{"tool": "test"}</tool_call> more text'
        assert has_tool_calls(text) is True

    def test_has_tool_calls_false(self):
        """Detect absence of tool calls."""
        text = "Just regular text without any tool calls"
        assert has_tool_calls(text) is False

    def test_has_tool_calls_alternative_format(self):
        """Detect alternative format tool calls."""
        text = '```tool\n{"tool": "test"}\n```'
        assert has_tool_calls(text) is True


class TestStripToolBlocks:
    """Test tool block stripping."""

    def test_strip_tool_blocks(self):
        """Strip tool blocks from text."""
        text = 'Before <tool_call>{"tool": "test"}</tool_call> After'
        stripped = strip_tool_blocks(text)
        assert stripped == "Before  After"

    def test_strip_multiple_blocks(self):
        """Strip multiple tool blocks."""
        text = '''Start
<tool_call>{"tool": "a"}</tool_call>
Middle
<tool_call>{"tool": "b"}</tool_call>
End'''
        stripped = strip_tool_blocks(text)
        assert "Start" in stripped
        assert "Middle" in stripped
        assert "End" in stripped
        assert "tool_call" not in stripped


class TestFormatToolResults:
    """Test result formatting for LLM."""

    def test_format_success_result(self):
        """Format successful tool result."""
        results = [
            ToolExecutionResult(
                invocation=ToolInvocation(tool_id="filesystem", args={}, raw_json="{}"),
                result=ToolResult(success=True, output="File contents here"),
                duration_ms=50.0,
            )
        ]
        formatted = format_tool_results_for_llm(results)
        assert "<tool_results>" in formatted
        assert '<result tool="filesystem">' in formatted
        assert "<status>success</status>" in formatted
        assert "<output>File contents here</output>" in formatted

    def test_format_error_result(self):
        """Format error tool result."""
        results = [
            ToolExecutionResult(
                invocation=ToolInvocation(tool_id="shell", args={}, raw_json="{}"),
                result=ToolResult(success=False, output="", error="Permission denied"),
                duration_ms=10.0,
            )
        ]
        formatted = format_tool_results_for_llm(results)
        assert "<status>error</status>" in formatted
        assert "<error>Permission denied</error>" in formatted

    def test_format_empty_results(self):
        """Format empty results list."""
        formatted = format_tool_results_for_llm([])
        assert formatted == ""

    def test_format_truncates_long_output(self):
        """Long output is truncated."""
        long_output = "x" * 15000
        results = [
            ToolExecutionResult(
                invocation=ToolInvocation(tool_id="test", args={}, raw_json="{}"),
                result=ToolResult(success=True, output=long_output),
                duration_ms=100.0,
            )
        ]
        formatted = format_tool_results_for_llm(results)
        assert "[truncated]" in formatted
        assert len(formatted) < 15000


class TestToolPolicy:
    """Test tool policy enforcement."""

    def test_allowlist_allows_listed_tool(self):
        """Tool in allowlist is allowed."""
        policy = ToolPolicy(allowed_tools=["filesystem", "shell"])
        assert policy.is_tool_allowed("filesystem") is True
        assert policy.is_tool_allowed("shell") is True

    def test_allowlist_blocks_unlisted_tool(self):
        """Tool not in allowlist is blocked."""
        policy = ToolPolicy(allowed_tools=["filesystem"])
        assert policy.is_tool_allowed("shell") is False

    def test_none_allowlist_allows_all(self):
        """None allowlist allows all tools."""
        policy = ToolPolicy(allowed_tools=None)
        assert policy.is_tool_allowed("any_tool") is True


class TestToolInterpreter:
    """Test the main interpreter class."""

    def test_check_iteration_limit(self):
        """Check iteration limit enforcement."""
        context = InterpreterContext(
            policy=ToolPolicy(max_iterations=3)
        )
        interpreter = ToolInterpreter(context=context)

        # Under limit
        context.iteration = 2
        can_continue, error = interpreter.check_iteration_limit()
        assert can_continue is True
        assert error is None

        # At limit
        context.iteration = 3
        can_continue, error = interpreter.check_iteration_limit()
        assert can_continue is False
        assert "exceeded" in error.lower()

    def test_increment_iteration(self):
        """Test iteration increment."""
        context = InterpreterContext()
        interpreter = ToolInterpreter(context=context)

        assert context.iteration == 0
        interpreter.increment_iteration()
        assert context.iteration == 1
        interpreter.increment_iteration()
        assert context.iteration == 2

    def test_needs_repair_with_broken_json(self):
        """Detect need for JSON repair."""
        interpreter = ToolInterpreter()
        invocations = [
            ToolInvocation(
                tool_id="",
                args={},
                raw_json="{invalid}",
                parse_error="Invalid JSON",
            )
        ]
        needs, broken = interpreter.needs_repair(invocations)
        assert needs is True
        assert broken is not None
        assert broken.parse_error == "Invalid JSON"

    def test_needs_repair_only_once(self):
        """Repair is only attempted once."""
        interpreter = ToolInterpreter()
        invocations = [
            ToolInvocation(tool_id="", args={}, raw_json="{}", parse_error="Error")
        ]

        needs, _ = interpreter.needs_repair(invocations)
        assert needs is True

        interpreter.mark_repair_attempted()
        needs, _ = interpreter.needs_repair(invocations)
        assert needs is False  # Already attempted

    def test_get_summary(self):
        """Get execution summary."""
        context = InterpreterContext()
        context.iteration = 3
        context.total_tool_calls = 5
        interpreter = ToolInterpreter(context=context)

        summary = interpreter.get_summary()
        assert summary["iterations"] == 3
        assert summary["total_tool_calls"] == 5
        assert "execution_history" in summary


class TestExecuteInvocations:
    """Test tool execution."""

    @pytest.mark.asyncio
    async def test_execute_with_allowlist_block(self):
        """Blocked tool returns error result."""
        context = InterpreterContext(
            policy=ToolPolicy(allowed_tools=["filesystem"])  # shell not allowed
        )
        invocations = [
            ToolInvocation(tool_id="shell", args={"command": "ls"}, raw_json="{}")
        ]

        results = await execute_invocations(invocations, context)
        assert len(results) == 1
        assert results[0].result.success is False
        assert "not allowed" in results[0].result.error

    @pytest.mark.asyncio
    async def test_execute_with_parse_error(self):
        """Invocation with parse error returns error result."""
        context = InterpreterContext()
        invocations = [
            ToolInvocation(
                tool_id="",
                args={},
                raw_json="{invalid}",
                parse_error="Invalid JSON"
            )
        ]

        results = await execute_invocations(invocations, context)
        assert len(results) == 1
        assert results[0].result.success is False
        assert "Parse error" in results[0].result.error

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Unknown tool returns error result."""
        context = InterpreterContext()
        invocations = [
            ToolInvocation(tool_id="unknown_tool", args={}, raw_json="{}")
        ]

        results = await execute_invocations(invocations, context)
        assert len(results) == 1
        assert results[0].result.success is False
        assert "Unknown tool" in results[0].result.error

    @pytest.mark.asyncio
    async def test_workspace_jail_enforcement(self):
        """Write outside workspace is blocked."""
        context = InterpreterContext(
            policy=ToolPolicy(
                allowed_tools=["filesystem"],
                workspace_path="/home/user/workspace"
            )
        )
        invocations = [
            ToolInvocation(
                tool_id="filesystem",
                args={"action": "write", "path": "/etc/passwd", "content": "hacked"},
                raw_json="{}"
            )
        ]

        results = await execute_invocations(invocations, context)
        assert len(results) == 1
        assert results[0].result.success is False
        assert "only allowed in workspace" in results[0].result.error

    @pytest.mark.asyncio
    async def test_workspace_jail_allows_workspace_writes(self):
        """Write inside workspace is allowed (execution may still fail for other reasons)."""
        context = InterpreterContext(
            policy=ToolPolicy(
                allowed_tools=["filesystem"],
                workspace_path="/home/user/workspace"
            )
        )
        invocations = [
            ToolInvocation(
                tool_id="filesystem",
                args={
                    "action": "write",
                    "path": "/home/user/workspace/test.txt",
                    "content": "test"
                },
                raw_json="{}"
            )
        ]

        # This will try to execute (and likely fail for other reasons like tool not registered)
        # but it should NOT be blocked by workspace jail
        results = await execute_invocations(invocations, context)
        assert len(results) == 1
        # Error should NOT be about workspace
        if results[0].result.error:
            assert "only allowed in workspace" not in results[0].result.error


class TestMaxIterationsGuard:
    """Test max iterations guard."""

    @pytest.mark.asyncio
    async def test_max_iterations_stops_execution(self):
        """Interpreter stops after max iterations."""
        context = InterpreterContext(
            policy=ToolPolicy(max_iterations=2)
        )
        interpreter = ToolInterpreter(context=context)

        # First iteration - OK
        interpreter.increment_iteration()
        can_continue, _ = interpreter.check_iteration_limit()
        assert can_continue is True

        # Second iteration - OK
        interpreter.increment_iteration()
        can_continue, _ = interpreter.check_iteration_limit()
        assert can_continue is False  # At limit now


class TestInvalidJsonRepair:
    """Test invalid JSON repair flow."""

    def test_repair_prompt_generation(self):
        """Repair prompt is generated correctly."""
        interpreter = ToolInterpreter()
        invocation = ToolInvocation(
            tool_id="",
            args={},
            raw_json='{"tool": "test", "args": {invalid}}',
            parse_error="Expecting property name"
        )

        prompt = interpreter.get_repair_prompt(invocation)
        assert "invalid" in prompt.lower() or "Invalid" in prompt
        assert '{"tool": "test"' in prompt
        assert "Expecting property name" in prompt
