"""Shared Tool Call Contract for all agents.

This module defines the canonical tool call protocol that all agents must follow.
Import TOOL_CALL_CONTRACT into agent system prompts to ensure consistency.
"""

# The canonical tool call format
TOOL_CALL_FORMAT = '<tool_call>{"tool": "tool_name", "args": {"param": "value"}}</tool_call>'

# Shared contract paragraph - include in all agent prompts
TOOL_CALL_CONTRACT = """
## TOOL EXECUTION CONTRACT

You have access to tools that you MUST invoke using this exact format:

```
<tool_call>{"tool": "tool_name", "args": {"param1": "value1", "param2": "value2"}}</tool_call>
```

### CRITICAL RULES:
1. **ONLY use `<tool_call>` blocks** - Never use pseudo-syntax like `filesystem action=read` or describe tools without calling them
2. **Never claim execution without proof** - Do NOT say "I read the file" or "I ran the tests" unless you emitted a `<tool_call>` block and received results
3. **Wait for results** - After emitting tool calls, you will receive `<tool_results>` with the actual output
4. **Separate tool calls from final answer** - First emit all needed tool calls, then after receiving results, provide your final response
5. **One JSON object per block** - Each `<tool_call>` contains exactly one tool invocation

### AVAILABLE TOOLS:

**filesystem** - File operations
```
<tool_call>{"tool": "filesystem", "args": {"action": "read", "path": "/path/to/file"}}</tool_call>
<tool_call>{"tool": "filesystem", "args": {"action": "write", "path": "/path/to/file", "content": "..."}}</tool_call>
<tool_call>{"tool": "filesystem", "args": {"action": "list", "path": "/directory"}}</tool_call>
<tool_call>{"tool": "filesystem", "args": {"action": "exists", "path": "/path"}}</tool_call>
```

**shell** - Command execution
```
<tool_call>{"tool": "shell", "args": {"command": "pytest tests/", "workdir": "/project"}}</tool_call>
```

**kiro** - LLM-powered code operations
```
<tool_call>{"tool": "kiro", "args": {"action": "architect", "task": "Design...", "workdir": "/project"}}</tool_call>
<tool_call>{"tool": "kiro", "args": {"action": "validate", "files": "src/*.py", "workdir": "/project"}}</tool_call>
<tool_call>{"tool": "kiro", "args": {"action": "test", "files": "src/module.py", "workdir": "/project"}}</tool_call>
```

**web_search** - Web search
```
<tool_call>{"tool": "web_search", "args": {"query": "search terms"}}</tool_call>
```

**web_fetch** - Fetch URL content
```
<tool_call>{"tool": "web_fetch", "args": {"url": "https://example.com"}}</tool_call>
```
"""

# Tool policies by agent type
TOOL_POLICIES = {
    "mo": {
        "allowed": ["routing", "filesystem", "shell", "web_search", "web_fetch", "kiro", "sessions", "canvas"],
        "read_paths": ["*"],  # Can read anywhere
        "write_paths": ["/Projects", "~/maratos-workspace"],
        "notes": "Orchestrator - delegates heavy implementation to specialists"
    },
    "architect": {
        "allowed": ["filesystem", "shell", "kiro"],
        "read_paths": ["*"],
        "write_paths": ["~/maratos-workspace"],
        "notes": "Plans and designs - spawns coders for implementation"
    },
    "coder": {
        "allowed": ["filesystem", "shell", "kiro"],
        "read_paths": ["*"],
        "write_paths": ["/Projects", "~/maratos-workspace"],
        "notes": "Pure implementation - reads existing code, writes new code"
    },
    "reviewer": {
        "allowed": ["filesystem", "shell", "kiro"],
        "read_paths": ["*"],
        "write_paths": [],  # Read-only for reviews
        "notes": "Code review - reads and analyzes, does not modify"
    },
    "tester": {
        "allowed": ["filesystem", "shell", "kiro"],
        "read_paths": ["*"],
        "write_paths": ["~/maratos-workspace"],
        "notes": "Must copy to workspace before writing tests"
    },
    "docs": {
        "allowed": ["filesystem", "shell", "kiro"],
        "read_paths": ["*"],
        "write_paths": ["/Projects", "~/maratos-workspace"],
        "notes": "Documentation writer - can write docs directly"
    },
    "devops": {
        "allowed": ["filesystem", "shell", "kiro"],
        "read_paths": ["*"],
        "write_paths": ["/Projects", "~/maratos-workspace"],
        "notes": "Infrastructure - writes config files, Dockerfiles, CI/CD"
    },
}


def get_tool_policy_section(agent_type: str) -> str:
    """Generate the TOOL POLICY section for an agent's system prompt."""
    policy = TOOL_POLICIES.get(agent_type, TOOL_POLICIES["coder"])

    allowed_list = ", ".join(policy["allowed"])
    read_paths = ", ".join(policy["read_paths"]) if policy["read_paths"] else "None"
    write_paths = ", ".join(policy["write_paths"]) if policy["write_paths"] else "None (read-only)"

    return f"""
## TOOL POLICY

**Allowed Tools:** {allowed_list}
**Read Access:** {read_paths}
**Write Access:** {write_paths}
**Notes:** {policy["notes"]}

IMPORTANT: Attempting to use tools not in your allowed list will fail.
Write operations outside allowed paths will be blocked.
"""


def get_full_tool_section(agent_type: str) -> str:
    """Get the complete tool section (contract + policy) for an agent."""
    return TOOL_CALL_CONTRACT + "\n" + get_tool_policy_section(agent_type)
