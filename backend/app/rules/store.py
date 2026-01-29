"""Rule storage and retrieval.

Stores rules in ~/.maratos/rules/ as YAML files.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Rules directory
RULES_DIR = Path.home() / ".maratos" / "rules"


@dataclass
class Rule:
    """A development rule/standard."""
    id: str
    name: str
    description: str
    content: str  # The actual rule text injected into prompts
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "content": self.content,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        """Create from dictionary."""
        return cls(
            id=data["id"],
            name=data["name"],
            description=data.get("description", ""),
            content=data["content"],
            tags=data.get("tags", []),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
        )


def _ensure_rules_dir() -> None:
    """Ensure rules directory exists."""
    RULES_DIR.mkdir(parents=True, exist_ok=True)


def _rule_path(rule_id: str) -> Path:
    """Get path to a rule file."""
    return RULES_DIR / f"{rule_id}.yaml"


def _sanitize_id(name: str) -> str:
    """Convert name to a safe file ID."""
    import re
    # Lowercase, replace spaces with hyphens, remove special chars
    safe = name.lower().strip()
    safe = re.sub(r'\s+', '-', safe)
    safe = re.sub(r'[^a-z0-9\-]', '', safe)
    safe = re.sub(r'-+', '-', safe)
    return safe[:50]  # Limit length


def list_rules() -> list[Rule]:
    """List all rules."""
    _ensure_rules_dir()
    rules = []

    for file_path in RULES_DIR.glob("*.yaml"):
        try:
            with open(file_path) as f:
                data = yaml.safe_load(f)
                if data:
                    rules.append(Rule.from_dict(data))
        except Exception as e:
            logger.warning(f"Failed to load rule {file_path}: {e}")

    # Sort by name
    rules.sort(key=lambda r: r.name.lower())
    return rules


def get_rule(rule_id: str) -> Rule | None:
    """Get a rule by ID."""
    file_path = _rule_path(rule_id)
    if not file_path.exists():
        return None

    try:
        with open(file_path) as f:
            data = yaml.safe_load(f)
            return Rule.from_dict(data) if data else None
    except Exception as e:
        logger.error(f"Failed to load rule {rule_id}: {e}")
        return None


def create_rule(
    name: str,
    description: str,
    content: str,
    tags: list[str] | None = None,
    rule_id: str | None = None,
) -> Rule:
    """Create a new rule."""
    _ensure_rules_dir()

    # Generate ID from name if not provided
    if not rule_id:
        rule_id = _sanitize_id(name)

    # Ensure unique ID
    base_id = rule_id
    counter = 1
    while _rule_path(rule_id).exists():
        rule_id = f"{base_id}-{counter}"
        counter += 1

    now = datetime.utcnow().isoformat()
    rule = Rule(
        id=rule_id,
        name=name,
        description=description,
        content=content,
        tags=tags or [],
        created_at=now,
        updated_at=now,
    )

    # Save to file
    with open(_rule_path(rule_id), 'w') as f:
        yaml.safe_dump(rule.to_dict(), f, default_flow_style=False, allow_unicode=True)

    logger.info(f"Created rule: {rule_id}")
    return rule


def update_rule(
    rule_id: str,
    name: str | None = None,
    description: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
) -> Rule | None:
    """Update an existing rule."""
    rule = get_rule(rule_id)
    if not rule:
        return None

    if name is not None:
        rule.name = name
    if description is not None:
        rule.description = description
    if content is not None:
        rule.content = content
    if tags is not None:
        rule.tags = tags

    rule.updated_at = datetime.utcnow().isoformat()

    # Save to file
    with open(_rule_path(rule_id), 'w') as f:
        yaml.safe_dump(rule.to_dict(), f, default_flow_style=False, allow_unicode=True)

    logger.info(f"Updated rule: {rule_id}")
    return rule


def delete_rule(rule_id: str) -> bool:
    """Delete a rule."""
    file_path = _rule_path(rule_id)
    if not file_path.exists():
        return False

    try:
        file_path.unlink()
        logger.info(f"Deleted rule: {rule_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete rule {rule_id}: {e}")
        return False


def get_rules_for_context(rule_ids: list[str]) -> str:
    """Get formatted rules content for prompt injection.

    Args:
        rule_ids: List of rule IDs to include

    Returns:
        Formatted rules text for injection into prompts
    """
    if not rule_ids:
        return ""

    rules = []
    for rule_id in rule_ids:
        rule = get_rule(rule_id)
        if rule:
            rules.append(rule)

    if not rules:
        return ""

    # Format rules for prompt injection
    sections = []
    for rule in rules:
        section = f"## {rule.name}\n\n{rule.content}"
        sections.append(section)

    return "# Development Rules & Standards\n\n" + "\n\n---\n\n".join(sections)


def rules_exist() -> bool:
    """Check if any rules exist."""
    _ensure_rules_dir()
    return any(RULES_DIR.glob("*.yaml"))


def create_example_rules() -> list[Rule]:
    """Create example rules for new users."""
    examples = [
        {
            "name": "Clean Code Standards",
            "description": "General clean code principles and best practices",
            "content": """Follow these clean code principles:

1. **Naming**
   - Use descriptive, meaningful names
   - Variables: nouns (user, orderList)
   - Functions: verbs (getUser, calculateTotal)
   - Booleans: is/has/can prefix (isActive, hasPermission)

2. **Functions**
   - Single responsibility - do one thing well
   - Keep functions short (< 20 lines ideally)
   - Limit parameters (max 3, use objects for more)
   - No side effects unless explicitly stated

3. **Comments**
   - Code should be self-documenting
   - Comment the "why", not the "what"
   - Delete commented-out code

4. **Error Handling**
   - Use exceptions, not error codes
   - Provide context in error messages
   - Don't return null - use Optional or throw""",
            "tags": ["general", "code-quality"],
        },
        {
            "name": "Python Standards",
            "description": "Python-specific coding standards",
            "content": """Follow these Python standards:

1. **Style**
   - Follow PEP 8
   - Use type hints for function signatures
   - Use dataclasses or Pydantic for data structures

2. **Imports**
   - Standard library first, then third-party, then local
   - Absolute imports preferred
   - No wildcard imports

3. **Testing**
   - Use pytest for testing
   - Fixtures for setup/teardown
   - Parametrize for multiple test cases
   - Aim for 80%+ coverage on new code

4. **Async**
   - Use async/await for I/O-bound operations
   - Use asyncio.gather for concurrent operations
   - Don't mix sync and async code""",
            "tags": ["python", "backend"],
        },
        {
            "name": "TypeScript Standards",
            "description": "TypeScript/React coding standards",
            "content": """Follow these TypeScript standards:

1. **Types**
   - Prefer interfaces over types for objects
   - Use strict mode
   - Avoid `any` - use `unknown` if type is truly unknown
   - Export types alongside functions

2. **React**
   - Functional components only
   - Use hooks (useState, useEffect, useMemo, useCallback)
   - Extract logic into custom hooks
   - Props interfaces: `interface Props { ... }`

3. **State Management**
   - Local state for component-specific data
   - Zustand/Context for shared state
   - React Query for server state

4. **Error Handling**
   - Use Error Boundaries for UI errors
   - Handle async errors with try/catch
   - Show user-friendly error messages""",
            "tags": ["typescript", "react", "frontend"],
        },
        {
            "name": "API Design",
            "description": "RESTful API design standards",
            "content": """Follow these API design standards:

1. **Endpoints**
   - Use nouns, not verbs: `/users`, not `/getUsers`
   - Plural resources: `/users`, `/orders`
   - Nested for relationships: `/users/{id}/orders`

2. **HTTP Methods**
   - GET: Read (idempotent)
   - POST: Create
   - PUT: Full update
   - PATCH: Partial update
   - DELETE: Remove

3. **Responses**
   - Use appropriate status codes (200, 201, 400, 404, 500)
   - Consistent response format: `{ data, error, meta }`
   - Include pagination for lists: `{ data, total, page, limit }`

4. **Validation**
   - Validate all input
   - Return helpful error messages
   - Use Pydantic/Zod for schema validation""",
            "tags": ["api", "backend"],
        },
        {
            "name": "Testing Requirements",
            "description": "Testing standards and requirements",
            "content": """Follow these testing standards:

1. **Test Types**
   - Unit tests: Test individual functions/components
   - Integration tests: Test module interactions
   - E2E tests: Test critical user flows

2. **Coverage**
   - Minimum 80% coverage on new code
   - 100% coverage on critical paths (auth, payments)
   - Don't chase coverage numbers blindly

3. **Test Quality**
   - Arrange-Act-Assert pattern
   - One assertion per test (when practical)
   - Test edge cases and error conditions
   - Use descriptive test names: `test_user_creation_fails_with_invalid_email`

4. **Mocking**
   - Mock external services
   - Don't mock what you don't own (use fakes)
   - Reset mocks between tests""",
            "tags": ["testing", "quality"],
        },
    ]

    created = []
    for example in examples:
        rule = create_rule(
            name=example["name"],
            description=example["description"],
            content=example["content"],
            tags=example["tags"],
        )
        created.append(rule)

    return created
