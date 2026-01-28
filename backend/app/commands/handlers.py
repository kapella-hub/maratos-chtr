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
    """Handle /project <name> command.

    Subcommands:
    - /project - list all projects
    - /project <name> - load project context
    - /project ingest <name> - generate context pack
    - /project search <name> <query> - search project code
    """
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
            has_pack = p.has_context_pack()
            pack_status = " ✓" if has_pack else ""
            stale = " (stale)" if has_pack and p.is_context_pack_stale() else ""
            lines.append(f"- **{p.name}**{pack_status}{stale} - {p.description}")
            lines.append(f"  Path: `{p.path}`")

        lines.append("\n**Commands:**")
        lines.append("- `/project <name>` - Load project context")
        lines.append("- `/project ingest <name>` - Generate/refresh context pack")
        lines.append("- `/project search <name> <query>` - Search project code")

        return {"message": "\n".join(lines)}

    parts = args.strip().split(None, 2)
    subcommand = parts[0].lower()

    # Handle subcommands
    if subcommand == "ingest":
        if len(parts) < 2:
            return {"error": "Usage: /project ingest <name>", "example": "/project ingest myapp"}
        return _handle_project_ingest(parts[1])

    if subcommand == "search":
        if len(parts) < 3:
            return {"error": "Usage: /project search <name> <query>", "example": "/project search myapp authenticate"}
        return _handle_project_search(parts[1], parts[2])

    # Load project
    project_name = subcommand
    project = project_registry.get(project_name)

    if not project:
        available = [p.name for p in project_registry.list_all()]
        return {
            "error": f"Project '{project_name}' not found.",
            "available": available,
            "hint": f"Create ~/.maratos/projects/{project_name}.yaml",
        }

    # Load project context (uses context pack if available)
    context_text = project.get_context()

    # Build status message
    has_pack = project.has_context_pack()
    if has_pack:
        stale = project.is_context_pack_stale()
        pack_status = "Context pack: ✓ loaded" + (" (stale - run `/project ingest` to refresh)" if stale else "")
    else:
        pack_status = "Context pack: not generated (run `/project ingest` for better understanding)"

    return {
        "project_loaded": project.name,
        "project_context": context_text,
        "message": f"**Loaded project: {project.name}**\n\n{project.description}\n\nPath: `{project.path}`\n\n{pack_status}\n\nContext loaded with {len(project.conventions)} conventions and {len(project.patterns)} patterns.",
    }


def _handle_project_ingest(project_name: str) -> dict[str, Any]:
    """Handle /project ingest <name> - generate context pack."""
    from app.projects import (
        generate_context_pack,
        save_context_pack,
        load_context_pack,
        context_pack_is_stale,
    )

    project = project_registry.get(project_name.lower())
    if not project:
        available = [p.name for p in project_registry.list_all()]
        return {
            "error": f"Project '{project_name}' not found.",
            "available": available,
        }

    project_path = Path(project.path).expanduser().resolve()
    if not project_path.exists():
        return {"error": f"Project path does not exist: {project.path}"}

    try:
        # Generate context pack
        pack = generate_context_pack(str(project_path), project_name=project.name)
        pack_path = save_context_pack(pack, project.name)

        # Update registry metadata
        project_registry.update_context_pack_metadata(
            project.name,
            pack.version,
            pack.content_hash,
            pack.generated_at,
        )

        # Build summary
        lines = [
            f"**Context pack generated for: {project.name}**\n",
            f"**Language:** {pack.manifest.language}" + (f" ({pack.manifest.framework})" if pack.manifest.framework else ""),
            "",
        ]

        if pack.manifest.run_command or pack.manifest.test_command:
            lines.append("**Commands:**")
            if pack.manifest.run_command:
                lines.append(f"- Run: `{pack.manifest.run_command}`")
            if pack.manifest.test_command:
                lines.append(f"- Test: `{pack.manifest.test_command}`")
            lines.append("")

        lines.append(f"**Modules detected:** {len(pack.module_map)}")
        lines.append(f"**Entry points:** {len(pack.entrypoints)}")
        lines.append(f"**Dependencies:** {len(pack.manifest.dependencies)}")
        lines.append("")
        lines.append(f"Pack saved to: `{pack_path}`")
        lines.append("\nUse `/project search {project.name} <query>` to search code.")

        return {"message": "\n".join(lines)}

    except Exception as e:
        return {"error": f"Failed to generate context pack: {str(e)}"}


def _handle_project_search(project_name: str, query: str) -> dict[str, Any]:
    """Handle /project search <name> <query> - search project code."""
    import asyncio
    import subprocess
    import json

    project = project_registry.get(project_name.lower())
    if not project:
        available = [p.name for p in project_registry.list_all()]
        return {
            "error": f"Project '{project_name}' not found.",
            "available": available,
        }

    project_path = Path(project.path).expanduser().resolve()
    if not project_path.exists():
        return {"error": f"Project path does not exist: {project.path}"}

    # Run ripgrep search
    cmd = [
        "rg", "-n", "-i", "-C", "2",
        "--glob", "!node_modules/**",
        "--glob", "!.git/**",
        "--glob", "!__pycache__/**",
        "--glob", "!.venv/**",
        "--glob", "!dist/**",
        "--glob", "!build/**",
        "--max-count", "5",  # Limit per file
        query,
        str(project_path),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()

        if not output:
            return {"message": f"**No matches found** for `{query}` in {project.name}"}

        # Parse and format results
        lines = [f"**Search results for `{query}` in {project.name}:**\n"]
        lines.append("```")

        # Make paths relative
        for line in output.split("\n")[:50]:  # Limit output
            if line.startswith(str(project_path)):
                line = line[len(str(project_path)):].lstrip("/")
            lines.append(line)

        lines.append("```")

        if len(output.split("\n")) > 50:
            lines.append("\n*Results truncated. Use the API for full search.*")

        return {"message": "\n".join(lines)}

    except subprocess.TimeoutExpired:
        return {"error": "Search timed out"}
    except FileNotFoundError:
        # ripgrep not installed, try grep
        try:
            result = subprocess.run(
                ["grep", "-rn", "-i", "-C", "2", query, str(project_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            output = result.stdout.strip()
            if not output:
                return {"message": f"**No matches found** for `{query}` in {project.name}"}
            return {"message": f"**Search results for `{query}` in {project.name}:**\n```\n{output[:3000]}\n```"}
        except Exception as e:
            return {"error": f"Search failed: {str(e)}"}
    except Exception as e:
        return {"error": f"Search failed: {str(e)}"}


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
        description="Manage projects: load context, generate context pack, search code",
        usage="/project [name|ingest|search] [args]",
        handler=handle_project,
        examples=[
            "/project",
            "/project myapp",
            "/project ingest myapp",
            "/project search myapp authenticate",
        ],
    ))

    command_registry.register(Command(
        name="help",
        description="Show available commands",
        usage="/help",
        handler=handle_help,
        examples=["/help"],
    ))
