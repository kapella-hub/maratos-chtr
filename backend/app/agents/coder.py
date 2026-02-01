"""Coder Agent - Pure implementation focus via Kiro."""

import re
from typing import Any

from app.agents.base import Agent, AgentConfig
from app.agents.tool_contract import get_full_tool_section
from app.prompts import get_prompt


def validate_python_syntax(code: str) -> tuple[bool, str | None]:
    """Validate Python code syntax. Returns (is_valid, error_message)."""
    try:
        compile(code, "<string>", "exec")
        return True, None
    except SyntaxError as e:
        return False, f"Line {e.lineno}: {e.msg}"


def validate_code_blocks(output: str) -> list[dict[str, Any]]:
    """Extract and validate code blocks from agent output.

    Returns list of {language, path, code, valid, error} dicts.
    """
    # Pattern for ```language:path or ```language
    pattern = r'```(\w+)(?::([^\n]+))?\n(.*?)```'
    blocks = []

    for match in re.finditer(pattern, output, re.DOTALL):
        lang = match.group(1)
        path = match.group(2)
        code = match.group(3).strip()

        block = {
            "language": lang,
            "path": path,
            "code": code[:200] + "..." if len(code) > 200 else code,
            "valid": True,
            "error": None,
        }

        # Validate based on language
        if lang == "python":
            valid, error = validate_python_syntax(code)
            block["valid"] = valid
            block["error"] = error
        elif lang in ("javascript", "typescript", "tsx", "jsx"):
            # Basic JS/TS validation - check for obvious issues
        elif lang in ("javascript", "typescript", "tsx", "jsx"):
            # Basic JS/TS validation - check for obvious issues
            pass # TODO: Implement better validation logic (e.g. using a parser)
            # Brace counting is too brittle for production code containing strings/regex/etc.

        blocks.append(block)

    return blocks


class CoderAgent(Agent):
    """Coder agent for pure implementation."""

    def __init__(self) -> None:
        # Load system prompt from yaml
        base_prompt = get_prompt("agent_prompts.coder")
        
        # Inject tool section into prompt
        tool_section = get_full_tool_section("coder")
        prompt = base_prompt.format(tool_section=tool_section)

        super().__init__(
            AgentConfig(
                id="coder",
                name="Coder",
                description="Pure implementation — clean, production-ready code",
                icon="💻",
                model="",  # Inherit from settings
                temperature=0.3,  # Slightly higher for better variable naming and idiomatic code
                system_prompt=prompt,
                tools=["filesystem", "shell", "kiro", "create_handoff"],
            )
        )

    def get_system_prompt(self, context: dict[str, Any] | None = None) -> tuple[str, list]:
        """Build system prompt with context."""
        prompt, matched_skills = super().get_system_prompt(context)

        if context:
            if "workspace" in context:
                prompt += f"\n\n## Workspace\n`{context['workspace']}`\n"
            if "language" in context:
                prompt += f"\n\n## Language\n{context['language']}\n"

        return prompt, matched_skills

    def validate_output(self, output: str) -> dict[str, Any]:
        """Validate coder output for common issues.

        Returns:
            {
                "valid": bool,
                "issues": list of issue descriptions,
                "code_blocks": list of validated code blocks,
                "suggestion": str or None - fix suggestion if issues found
            }
        """
        issues = []
        code_blocks = validate_code_blocks(output)

        # Check for syntax errors in code blocks
        for block in code_blocks:
            if not block["valid"]:
                issues.append(
                    f"{block['language']} syntax error in {block['path'] or 'code block'}: {block['error']}"
                )

        # Check for common issues in output
        if "TODO" in output and "implement" in output.lower():
            issues.append("Contains unfinished TODO - implementation may be incomplete")

        if "..." in output and "```" in output:
            # Check if ... is inside a code block (truncated code)
            if re.search(r'```\w+[^\`]*\.\.\.[^\`]*```', output, re.DOTALL):
                issues.append("Code block appears truncated (contains ...)")

        # Check for missing imports in Python
        for block in code_blocks:
            if block["language"] == "python" and block["valid"]:
                code = block.get("code", "")
                # Simple heuristic: if using common modules without importing
                common_modules = ["json", "os", "sys", "re", "datetime", "pathlib"]
                for mod in common_modules:
                    if f"{mod}." in code and f"import {mod}" not in code:
                        issues.append(f"Possibly missing 'import {mod}'")

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "code_blocks": code_blocks,
            "suggestion": self._generate_fix_suggestion(issues) if issues else None,
        }

    def _generate_fix_suggestion(self, issues: list[str]) -> str:
        """Generate a suggestion for fixing the issues."""
        if not issues:
            return ""

        suggestions = ["Fix the following issues before proceeding:"]
        for i, issue in enumerate(issues, 1):
            suggestions.append(f"{i}. {issue}")

        return "\n".join(suggestions)
