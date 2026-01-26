"""Default command handlers."""

from typing import Any
from pathlib import Path

from app.commands.registry import Command, command_registry
from app.projects import project_registry


def handle_review(args: str, context: dict[str, Any]) -> dict[str, Any]:
    """Handle /review <file> command."""
    if not args:
        return {
            "error": "Usage: /review <file_path>",
            "example": "/review app/auth.py",
        }

    file_path = args.strip()

    # Build expanded prompt
    prompt = f"""Review the following file for issues:

**File to review:** `{file_path}`

Please analyze for:
1. **Security vulnerabilities** - injection, auth bypass, data exposure
2. **Bugs** - logic errors, edge cases, race conditions
3. **Code quality** - readability, maintainability, patterns
4. **Performance** - inefficiencies, N+1 queries, memory leaks

First copy to workspace, then provide fixes for any issues found.

[SPAWN:reviewer] Review {file_path} for security vulnerabilities, bugs, and code quality issues. Copy to workspace first, then provide fixes."""

    return {"expanded_prompt": prompt, "agent_id": "mo"}


def handle_fix(args: str, context: dict[str, Any]) -> dict[str, Any]:
    """Handle /fix <description> command."""
    if not args:
        return {
            "error": "Usage: /fix <description of what to fix>",
            "example": "/fix the authentication bypass in app/auth.py",
        }

    prompt = f"""Fix the following issue:

**Issue:** {args}

First analyze the problem, then implement a fix in the workspace.

[SPAWN:coder] Fix: {args}. Copy relevant files to workspace first, then implement the fix."""

    return {"expanded_prompt": prompt, "agent_id": "mo"}


def handle_test(args: str, context: dict[str, Any]) -> dict[str, Any]:
    """Handle /test <file> command."""
    if not args:
        return {
            "error": "Usage: /test <file_path>",
            "example": "/test app/services/auth.py",
        }

    file_path = args.strip()

    prompt = f"""Generate comprehensive tests for the following file:

**File to test:** `{file_path}`

Generate tests covering:
1. Happy path scenarios
2. Edge cases (empty, null, max values)
3. Error conditions
4. Integration with dependencies

[SPAWN:tester] Generate tests for {file_path}. Copy to workspace, create test file, achieve >80% coverage."""

    return {"expanded_prompt": prompt, "agent_id": "mo"}


def handle_explain(args: str, context: dict[str, Any]) -> dict[str, Any]:
    """Handle /explain <file> command."""
    if not args:
        return {
            "error": "Usage: /explain <file_path>",
            "example": "/explain app/core/engine.py",
        }

    file_path = args.strip()

    prompt = f"""Explain the following file in detail:

**File:** `{file_path}`

Please explain:
1. **Purpose** - What does this code do?
2. **Key components** - Classes, functions, their roles
3. **Data flow** - How data moves through the code
4. **Dependencies** - What it relies on, what relies on it
5. **Patterns** - Design patterns or idioms used

Read the file and provide a clear explanation."""

    return {"expanded_prompt": prompt, "agent_id": "mo"}


def handle_security(args: str, context: dict[str, Any]) -> dict[str, Any]:
    """Handle /security <path> command."""
    if not args:
        return {
            "error": "Usage: /security <path>",
            "example": "/security app/api/",
        }

    path = args.strip()

    prompt = f"""Perform a security audit on:

**Path:** `{path}`

Check for:
1. **Injection vulnerabilities** - SQL, command, XSS, LDAP
2. **Authentication issues** - bypass, weak tokens, session problems
3. **Authorization flaws** - privilege escalation, IDOR
4. **Data exposure** - sensitive data in logs, responses, errors
5. **Cryptography** - weak algorithms, hardcoded secrets
6. **Dependencies** - known vulnerable packages

[SPAWN:reviewer] Security audit of {path}. Check OWASP Top 10, provide severity ratings, and fix all critical/high issues in workspace."""

    return {"expanded_prompt": prompt, "agent_id": "mo"}


def handle_project(args: str, context: dict[str, Any]) -> dict[str, Any]:
    """Handle /project <name> command."""
    if not args:
        # List available projects
        projects = project_registry.list_all()
        if not projects:
            return {
                "error": "No projects configured. Create ~/.maratos/projects/<name>.yaml",
                "example": "See /help projects for setup instructions",
            }

        lines = ["**Available Projects:**\n"]
        for p in projects:
            lines.append(f"- **{p.name}** - {p.description}")
            lines.append(f"  Path: `{p.path}`")

        return {"message": "\n".join(lines)}

    project_name = args.strip().lower()
    project = project_registry.get(project_name)

    if not project:
        available = [p.name for p in project_registry.list_all()]
        return {
            "error": f"Project '{project_name}' not found.",
            "available": available,
            "hint": f"Create ~/.maratos/projects/{project_name}.yaml",
        }

    # Load project context
    context_text = project.get_context()

    return {
        "project_loaded": project.name,
        "project_context": context_text,
        "message": f"**Loaded project: {project.name}**\n\n{project.description}\n\nPath: `{project.path}`\n\nContext loaded with {len(project.conventions)} conventions and {len(project.patterns)} patterns.",
    }


def handle_help(args: str, context: dict[str, Any]) -> dict[str, Any]:
    """Handle /help command."""
    help_text = command_registry.get_help()

    # Add project setup help
    help_text += """
## Project Setup

Create project profiles in `~/.maratos/projects/<name>.yaml`:

```yaml
name: myproject
description: My awesome project
path: /path/to/project

tech_stack:
  - Python 3.11
  - FastAPI
  - PostgreSQL

conventions:
  - Use pytest for testing
  - Follow PEP 8 style guide
  - Type hints required

patterns:
  - Repository pattern for data access
  - Dependency injection via FastAPI
```

Then use `/project myproject` to load it.
"""
    return {"message": help_text}


def register_default_commands():
    """Register all default commands."""

    command_registry.register(Command(
        name="review",
        description="Quick code review with security focus",
        usage="/review <file>",
        handler=handle_review,
        examples=["/review app/auth.py", "/review src/api/endpoints.py"],
    ))

    command_registry.register(Command(
        name="fix",
        description="Fix an issue with full context",
        usage="/fix <description>",
        handler=handle_fix,
        examples=["/fix SQL injection in login", "/fix the race condition in order processing"],
    ))

    command_registry.register(Command(
        name="test",
        description="Generate tests for a file",
        usage="/test <file>",
        handler=handle_test,
        examples=["/test app/services/auth.py", "/test src/models.py"],
    ))

    command_registry.register(Command(
        name="explain",
        description="Explain what code does",
        usage="/explain <file>",
        handler=handle_explain,
        examples=["/explain app/core/engine.py", "/explain config.py"],
    ))

    command_registry.register(Command(
        name="security",
        description="Security audit a path",
        usage="/security <path>",
        handler=handle_security,
        examples=["/security app/api/", "/security src/auth/"],
    ))

    command_registry.register(Command(
        name="project",
        description="Load a project profile or list available",
        usage="/project [name]",
        handler=handle_project,
        examples=["/project", "/project sacs", "/project frontend"],
    ))

    command_registry.register(Command(
        name="help",
        description="Show available commands",
        usage="/help",
        handler=handle_help,
        examples=["/help"],
    ))
