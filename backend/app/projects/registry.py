"""Project registry for loading project profiles."""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


@dataclass
class Project:
    """A project profile with context."""

    name: str
    description: str
    path: str
    tech_stack: list[str] = field(default_factory=list)
    conventions: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    notes: str = ""

    def get_context(self) -> str:
        """Get formatted context for injection into prompts."""
        lines = [
            f"## Project: {self.name}",
            f"**Path:** `{self.path}`",
            f"**Description:** {self.description}",
            "",
        ]

        if self.tech_stack:
            lines.append("**Tech Stack:**")
            for tech in self.tech_stack:
                lines.append(f"- {tech}")
            lines.append("")

        if self.conventions:
            lines.append("**Conventions (MUST follow):**")
            for conv in self.conventions:
                lines.append(f"- {conv}")
            lines.append("")

        if self.patterns:
            lines.append("**Patterns in use:**")
            for pattern in self.patterns:
                lines.append(f"- {pattern}")
            lines.append("")

        if self.dependencies:
            lines.append("**Key dependencies:**")
            for dep in self.dependencies:
                lines.append(f"- {dep}")
            lines.append("")

        if self.notes:
            lines.append("**Notes:**")
            lines.append(self.notes)
            lines.append("")

        return "\n".join(lines)


class ProjectRegistry:
    """Registry for project profiles."""

    def __init__(self, config_dir: Path | None = None):
        self._projects: dict[str, Project] = {}
        self._config_dir = config_dir or Path.home() / ".maratos" / "projects"
        self._loaded = False

    def _ensure_loaded(self):
        """Load projects from config directory if not already loaded."""
        if self._loaded:
            return

        self._config_dir.mkdir(parents=True, exist_ok=True)
        self._load_projects()
        self._loaded = True

    def _load_projects(self):
        """Load all project YAML files from config directory."""
        if not self._config_dir.exists():
            return

        for yaml_file in self._config_dir.glob("*.yaml"):
            try:
                self._load_project_file(yaml_file)
            except Exception as e:
                logger.warning(f"Failed to load project {yaml_file}: {e}")

        for yml_file in self._config_dir.glob("*.yml"):
            try:
                self._load_project_file(yml_file)
            except Exception as e:
                logger.warning(f"Failed to load project {yml_file}: {e}")

    def _load_project_file(self, file_path: Path):
        """Load a single project file."""
        with open(file_path) as f:
            data = yaml.safe_load(f)

        if not data:
            return

        project = Project(
            name=data.get("name", file_path.stem),
            description=data.get("description", ""),
            path=data.get("path", ""),
            tech_stack=data.get("tech_stack", []),
            conventions=data.get("conventions", []),
            patterns=data.get("patterns", []),
            dependencies=data.get("dependencies", []),
            notes=data.get("notes", ""),
        )

        self._projects[project.name.lower()] = project
        logger.info(f"Loaded project: {project.name}")

    def get(self, name: str) -> Project | None:
        """Get a project by name."""
        self._ensure_loaded()
        return self._projects.get(name.lower())

    def list_all(self) -> list[Project]:
        """List all registered projects."""
        self._ensure_loaded()
        return list(self._projects.values())

    def reload(self):
        """Force reload of all projects."""
        self._projects.clear()
        self._loaded = False
        self._ensure_loaded()

    def create_example(self):
        """Create an example project file."""
        example_file = self._config_dir / "example.yaml"
        if example_file.exists():
            return

        self._config_dir.mkdir(parents=True, exist_ok=True)

        example_content = """# Example project profile
# Copy this file and customize for your project

name: example
description: Example project showing all available fields
path: /path/to/your/project

tech_stack:
  - Python 3.11
  - FastAPI
  - PostgreSQL
  - Redis

conventions:
  - Use pytest for all tests
  - Follow PEP 8 style guide
  - Type hints required on all functions
  - Docstrings required on public APIs

patterns:
  - Repository pattern for data access
  - Dependency injection via FastAPI Depends
  - Service layer for business logic
  - Pydantic models for validation

dependencies:
  - SQLAlchemy for ORM
  - Alembic for migrations
  - Pydantic for validation
  - httpx for HTTP clients

notes: |
  This project uses a hexagonal architecture.
  The core domain logic is in src/domain/.
  API endpoints are in src/api/.
  Database models are in src/models/.
"""

        with open(example_file, "w") as f:
            f.write(example_content)

        logger.info(f"Created example project file: {example_file}")


# Global registry
project_registry = ProjectRegistry()

# Create example file on first import
project_registry.create_example()
