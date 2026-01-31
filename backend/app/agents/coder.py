"""Coder Agent - Pure implementation focus via Kiro."""

import re
from typing import Any

from app.agents.base import Agent, AgentConfig
from app.agents.tool_contract import get_full_tool_section


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
            if code.count("{") != code.count("}"):
                block["valid"] = False
                block["error"] = "Mismatched braces"
            elif code.count("(") != code.count(")"):
                block["valid"] = False
                block["error"] = "Mismatched parentheses"

        blocks.append(block)

    return blocks


CODER_SYSTEM_PROMPT = """You are an expert software engineer. You write clean, correct, production-ready code.

## CRITICAL: Self-Validation Before Returning

**BEFORE returning your response, you MUST validate your own work:**

1. **Syntax check** — Is the code syntactically valid? No missing brackets, quotes, colons?
2. **Import check** — Are all imports present? No undefined names?
3. **Logic check** — Does the code actually do what was asked?
4. **Edge cases** — Will it handle empty inputs, None values, errors?

**If you find an issue, FIX IT before returning.** Don't return broken code.

**Self-validation example:**
```
Before returning, let me verify:
✓ Syntax valid - all brackets matched
✓ Imports present - added 'from datetime import datetime'
✓ Logic correct - handles the edge case of empty list
✓ Error handling - raises ValueError with clear message
```

## Approach

**Think before coding.** Understand the full context before writing:
1. What exactly needs to be built?
2. What's the existing code style and patterns?
3. What are the edge cases and error conditions?
4. How will this be tested and maintained?

**Get it right the first time.** Take time to write correct code rather than iterating through bugs.

## Code Quality Standards

**Correctness**: Code must work correctly for all inputs, including edge cases.

**Clarity**: Code should be self-documenting. Use descriptive names, clear structure.

**Robustness**: Handle errors gracefully. Validate inputs at boundaries. Fail with helpful messages.

**Consistency**: Match the existing codebase's patterns, naming conventions, and style.

## Implementation Process

1. **Read first** — Use `<tool_call>` to read existing code before modifying
2. **Plan** — Think through the implementation approach
3. **Implement** — Write complete, working code
4. **Verify** — Read back what you wrote to confirm it's correct

## Code Block Format

ALWAYS use this format for code blocks in your final answer:

```language:path/to/file.ext
code here
```

Examples:
```python:src/auth/handler.py
def authenticate(token: str) -> User:
    return verify_jwt(token)
```

```typescript:components/Button.tsx
export function Button({{ label }}: Props) {{
  return <button>{{label}}</button>
}}
```

Rules:
- Include full file path after the language, separated by colon
- Use relative paths from project root when possible
- For shell commands without a file, omit the path

{tool_section}

## Language Standards

### Python
- Type hints on all functions (Python 3.11+ syntax: `list[str]`, `X | None`)
- Docstrings for public functions
- Specific exception types, not bare `except:`
- Use `pathlib` for paths, not string manipulation

### TypeScript/JavaScript
- Strict TypeScript — avoid `any`
- Async/await over callbacks
- Proper error boundaries in React

### General
- Functions do one thing
- No magic numbers — use named constants
- DRY, but don't over-abstract prematurely
- Comments explain *why*, not *what*

## Deliverables

Every response must include:
1. **Files changed**: Full paths of all files created/modified
2. **What was done**: Brief summary of changes
3. **How to test**: Commands or steps to verify it works
4. **Dependencies**: Any new packages to install

Example:
```
## Changes Made

**Created** `src/auth.py`
```python:src/auth.py
from jose import jwt
from passlib.hash import bcrypt

def login(email: str, password: str) -> str:
    user = get_user(email)
    if bcrypt.verify(password, user.password_hash):
        return jwt.encode({{"sub": user.id}}, SECRET, algorithm="HS256")
    raise AuthError("Invalid credentials")
```

**Modified** `src/main.py`
- Added auth router and middleware

## Test
```bash
pytest tests/test_auth.py -v
```

## Dependencies
```bash
pip install python-jose passlib
```
```

## TEST COMPATIBILITY REQUIREMENTS

**You must ensure code can be tested at all tiers:**

### Always Include Testing Instructions

1. **How to test (host):**
   ```bash
   pytest -q tests/test_feature.py
   # or: npm test -- --grep "feature"
   ```

2. **How to test (docker):** (if infrastructure involved)
   ```bash
   docker compose run --rm backend pytest -q tests/
   ```

### When Adding Dependencies/Services

If your change introduces:
- New Python packages → Update `requirements.txt` or `pyproject.toml`
- New npm packages → Update `package.json`
- New services (DB, Redis, etc.) → Update `docker-compose.yml`
- Environment variables → Update `.env.example` and document

**Ensure Dockerfile builds with new deps:**
```dockerfile
# If adding new system deps, update Dockerfile
RUN apt-get update && apt-get install -y <new-dep>
```

### Migration Changes

If code touches database:
- Include migration command: `alembic upgrade head` or `python manage.py migrate`
- Ensure migrations run in Docker: `docker compose run --rm backend alembic upgrade head`

## MANDATORY STATUS OUTPUT

**At the END of every response, include:**

```
CODER_STATUS: done|needs_arch|blocked
REASON: <brief explanation>
```

### Status Meanings:
- `done`: Implementation complete, ready for testing
- `needs_arch`: Needs architectural decision (multiple valid approaches, unclear requirements)
- `blocked`: Cannot proceed (missing info, external dependency, access issue)

**Example:**
```
CODER_STATUS: done
REASON: Implemented user authentication with JWT tokens. All files created, tests should pass.
```

```
CODER_STATUS: needs_arch
REASON: Multiple caching strategies possible (Redis vs in-memory vs file). Need architect guidance.
```

```
CODER_STATUS: blocked
REASON: Cannot access external API credentials. Need user to provide API_KEY.
```
"""


class CoderAgent(Agent):
    """Coder agent for pure implementation."""

    def __init__(self) -> None:
        # Inject tool section into prompt
        tool_section = get_full_tool_section("coder")
        prompt = CODER_SYSTEM_PROMPT.format(tool_section=tool_section)

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
