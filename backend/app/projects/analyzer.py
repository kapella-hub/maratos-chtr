"""Project analyzer for auto-detecting project context.

Analyzes a project directory to detect:
- Tech stack (languages, frameworks, databases)
- Patterns (architecture, testing, deployment)
- Conventions (linting, formatting, style)
- Dependencies (from package files)
"""

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProjectAnalysis:
    """Results of project analysis."""

    tech_stack: list[str] = field(default_factory=list)
    conventions: list[str] = field(default_factory=list)
    patterns: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    description: str = ""
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "tech_stack": self.tech_stack,
            "conventions": self.conventions,
            "patterns": self.patterns,
            "dependencies": self.dependencies,
            "description": self.description,
            "notes": self.notes,
        }


# File patterns that indicate specific technologies
TECH_INDICATORS = {
    # Python
    "requirements.txt": ("Python", None),
    "pyproject.toml": ("Python", None),
    "setup.py": ("Python", None),
    "Pipfile": ("Python", "Pipenv"),
    "poetry.lock": ("Python", "Poetry"),

    # JavaScript/TypeScript
    "package.json": ("Node.js", None),
    "tsconfig.json": ("TypeScript", None),
    "bun.lockb": ("Bun", None),
    "deno.json": ("Deno", None),

    # Frontend frameworks
    "next.config.js": ("Next.js", None),
    "next.config.mjs": ("Next.js", None),
    "next.config.ts": ("Next.js", None),
    "nuxt.config.ts": ("Nuxt", None),
    "vite.config.ts": ("Vite", None),
    "vite.config.js": ("Vite", None),
    "angular.json": ("Angular", None),
    "svelte.config.js": ("Svelte", None),

    # Backend frameworks
    "fastapi": ("FastAPI", None),  # Check in dependencies
    "django": ("Django", None),
    "flask": ("Flask", None),
    "express": ("Express.js", None),
    "nestjs": ("NestJS", None),

    # Databases
    "docker-compose.yml": (None, None),  # Check content for databases
    "prisma/schema.prisma": ("Prisma", "PostgreSQL"),
    "alembic.ini": ("Alembic", "SQLAlchemy"),

    # Rust
    "Cargo.toml": ("Rust", None),

    # Go
    "go.mod": ("Go", None),

    # Java/Kotlin
    "pom.xml": ("Java", "Maven"),
    "build.gradle": ("Java/Kotlin", "Gradle"),
    "build.gradle.kts": ("Kotlin", "Gradle"),

    # Ruby
    "Gemfile": ("Ruby", None),
    "Rakefile": ("Ruby", "Rake"),

    # PHP
    "composer.json": ("PHP", "Composer"),

    # .NET
    "*.csproj": ("C#", ".NET"),
    "*.fsproj": ("F#", ".NET"),

    # Elixir
    "mix.exs": ("Elixir", "Mix"),

    # Infrastructure
    "Dockerfile": ("Docker", None),
    "docker-compose.yml": ("Docker Compose", None),
    "terraform/": ("Terraform", None),
    "kubernetes/": ("Kubernetes", None),
    "k8s/": ("Kubernetes", None),
    ".github/workflows/": ("GitHub Actions", None),
    ".gitlab-ci.yml": ("GitLab CI", None),
    "Jenkinsfile": ("Jenkins", None),
}

# Convention indicators
CONVENTION_INDICATORS = {
    # Python
    "ruff.toml": "Use ruff for linting",
    ".ruff.toml": "Use ruff for linting",
    "pyproject.toml[tool.ruff]": "Use ruff for linting",
    ".flake8": "Use flake8 for linting",
    "mypy.ini": "Use mypy for type checking",
    ".mypy.ini": "Use mypy for type checking",
    "pyproject.toml[tool.mypy]": "Use mypy for type checking",
    ".pre-commit-config.yaml": "Use pre-commit hooks",
    "pytest.ini": "Use pytest for testing",
    "pyproject.toml[tool.pytest]": "Use pytest for testing",

    # JavaScript/TypeScript
    ".eslintrc": "Use ESLint for linting",
    ".eslintrc.js": "Use ESLint for linting",
    ".eslintrc.json": "Use ESLint for linting",
    "eslint.config.js": "Use ESLint (flat config) for linting",
    ".prettierrc": "Use Prettier for formatting",
    ".prettierrc.js": "Use Prettier for formatting",
    "prettier.config.js": "Use Prettier for formatting",
    "biome.json": "Use Biome for linting and formatting",
    "jest.config.js": "Use Jest for testing",
    "jest.config.ts": "Use Jest for testing",
    "vitest.config.ts": "Use Vitest for testing",
    "cypress.config.ts": "Use Cypress for E2E testing",
    "playwright.config.ts": "Use Playwright for E2E testing",

    # General
    ".editorconfig": "Use EditorConfig for editor settings",
    "CONTRIBUTING.md": "Has contribution guidelines",
    "CODE_OF_CONDUCT.md": "Has code of conduct",
}

# Architecture patterns
PATTERN_INDICATORS = {
    # Directory structures
    "src/domain/": "Domain-driven design",
    "src/entities/": "Entity-based architecture",
    "src/repositories/": "Repository pattern",
    "src/services/": "Service layer pattern",
    "src/controllers/": "MVC pattern",
    "src/handlers/": "Handler pattern",
    "src/routes/": "Route-based organization",
    "src/api/": "API layer separation",
    "src/lib/": "Library/utility separation",
    "src/utils/": "Utility functions",
    "src/hooks/": "React hooks pattern",
    "src/components/": "Component-based architecture",
    "src/pages/": "Page-based routing",
    "app/": "App directory structure",
    "tests/": "Separate test directory",
    "__tests__/": "Jest-style test directory",
    "spec/": "RSpec-style test directory",
}


def analyze_project(path: str | Path) -> ProjectAnalysis:
    """Analyze a project directory and return detected context.

    Args:
        path: Path to the project directory

    Returns:
        ProjectAnalysis with detected tech stack, conventions, patterns
    """
    project_path = Path(path).expanduser().resolve()

    if not project_path.exists():
        raise ValueError(f"Project path does not exist: {path}")
    if not project_path.is_dir():
        raise ValueError(f"Project path is not a directory: {path}")

    analysis = ProjectAnalysis()

    # Detect tech stack
    _detect_tech_stack(project_path, analysis)

    # Detect conventions
    _detect_conventions(project_path, analysis)

    # Detect patterns
    _detect_patterns(project_path, analysis)

    # Extract dependencies
    _extract_dependencies(project_path, analysis)

    # Generate description
    _generate_description(project_path, analysis)

    # Remove duplicates while preserving order
    analysis.tech_stack = list(dict.fromkeys(analysis.tech_stack))
    analysis.conventions = list(dict.fromkeys(analysis.conventions))
    analysis.patterns = list(dict.fromkeys(analysis.patterns))
    analysis.dependencies = list(dict.fromkeys(analysis.dependencies))

    return analysis


def _detect_tech_stack(path: Path, analysis: ProjectAnalysis) -> None:
    """Detect tech stack from project files."""

    # Check for specific files
    for file_pattern, (tech, extra) in TECH_INDICATORS.items():
        if "/" in file_pattern:
            # Directory pattern
            if (path / file_pattern.rstrip("/")).is_dir():
                if tech:
                    analysis.tech_stack.append(tech)
                if extra:
                    analysis.tech_stack.append(extra)
        elif "*" in file_pattern:
            # Glob pattern
            if list(path.glob(file_pattern)):
                if tech:
                    analysis.tech_stack.append(tech)
                if extra:
                    analysis.tech_stack.append(extra)
        else:
            # Exact file
            if (path / file_pattern).exists():
                if tech:
                    analysis.tech_stack.append(tech)
                if extra:
                    analysis.tech_stack.append(extra)

    # Check package.json for frameworks
    package_json = path / "package.json"
    if package_json.exists():
        try:
            with open(package_json) as f:
                pkg = json.load(f)

            all_deps = {
                **pkg.get("dependencies", {}),
                **pkg.get("devDependencies", {}),
            }

            # Detect frameworks from dependencies
            framework_map = {
                "react": "React",
                "vue": "Vue.js",
                "svelte": "Svelte",
                "@angular/core": "Angular",
                "next": "Next.js",
                "nuxt": "Nuxt",
                "express": "Express.js",
                "fastify": "Fastify",
                "@nestjs/core": "NestJS",
                "tailwindcss": "Tailwind CSS",
                "@mui/material": "Material UI",
                "antd": "Ant Design",
                "prisma": "Prisma",
                "drizzle-orm": "Drizzle ORM",
                "mongoose": "MongoDB (Mongoose)",
                "typeorm": "TypeORM",
                "sequelize": "Sequelize",
            }

            for dep, framework in framework_map.items():
                if dep in all_deps:
                    analysis.tech_stack.append(framework)

        except (json.JSONDecodeError, IOError):
            pass

    # Check pyproject.toml for Python frameworks
    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()

            framework_map = {
                "fastapi": "FastAPI",
                "django": "Django",
                "flask": "Flask",
                "starlette": "Starlette",
                "sqlalchemy": "SQLAlchemy",
                "pydantic": "Pydantic",
                "pytest": "pytest",
                "celery": "Celery",
                "redis": "Redis",
                "httpx": "httpx",
                "aiohttp": "aiohttp",
            }

            content_lower = content.lower()
            for dep, framework in framework_map.items():
                if dep in content_lower:
                    analysis.tech_stack.append(framework)

        except IOError:
            pass

    # Check requirements.txt
    requirements = path / "requirements.txt"
    if requirements.exists():
        try:
            content = requirements.read_text().lower()

            framework_map = {
                "fastapi": "FastAPI",
                "django": "Django",
                "flask": "Flask",
                "sqlalchemy": "SQLAlchemy",
                "pydantic": "Pydantic",
                "celery": "Celery",
            }

            for dep, framework in framework_map.items():
                if dep in content:
                    analysis.tech_stack.append(framework)

        except IOError:
            pass


def _detect_conventions(path: Path, analysis: ProjectAnalysis) -> None:
    """Detect coding conventions from config files."""

    for file_pattern, convention in CONVENTION_INDICATORS.items():
        if "[" in file_pattern:
            # Check for section in file
            file_name, section = file_pattern.split("[")
            section = section.rstrip("]")
            file_path = path / file_name
            if file_path.exists():
                try:
                    content = file_path.read_text()
                    if f"[{section}]" in content or f'["{section}"]' in content:
                        analysis.conventions.append(convention)
                except IOError:
                    pass
        else:
            if (path / file_pattern).exists():
                analysis.conventions.append(convention)


def _detect_patterns(path: Path, analysis: ProjectAnalysis) -> None:
    """Detect architecture patterns from directory structure."""

    for dir_pattern, pattern in PATTERN_INDICATORS.items():
        dir_path = path / dir_pattern.rstrip("/")
        if dir_path.is_dir():
            analysis.patterns.append(pattern)

    # Check for monorepo
    if (path / "packages").is_dir() or (path / "apps").is_dir():
        analysis.patterns.append("Monorepo structure")

    # Check for workspace
    if (path / "pnpm-workspace.yaml").exists():
        analysis.patterns.append("PNPM workspace")
    if (path / "lerna.json").exists():
        analysis.patterns.append("Lerna monorepo")

    # Check for micro frontends
    if (path / "module-federation.config.js").exists():
        analysis.patterns.append("Module Federation (Micro Frontends)")


def _extract_dependencies(path: Path, analysis: ProjectAnalysis) -> None:
    """Extract key dependencies from package files."""

    # From package.json
    package_json = path / "package.json"
    if package_json.exists():
        try:
            with open(package_json) as f:
                pkg = json.load(f)

            deps = list(pkg.get("dependencies", {}).keys())[:10]  # Top 10
            analysis.dependencies.extend(deps)
        except (json.JSONDecodeError, IOError):
            pass

    # From pyproject.toml (simplified - just extract names)
    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            # Look for dependencies section
            if "dependencies" in content:
                # Very basic extraction - just get package names
                lines = content.split("\n")
                in_deps = False
                for line in lines:
                    if "dependencies" in line and "=" in line:
                        in_deps = True
                        continue
                    if in_deps:
                        if line.strip().startswith("]"):
                            break
                        if line.strip().startswith('"'):
                            dep = line.strip().strip('",').split("[")[0].split(">")[0].split("<")[0].split("=")[0]
                            if dep:
                                analysis.dependencies.append(dep.strip())
        except IOError:
            pass


def _generate_description(path: Path, analysis: ProjectAnalysis) -> None:
    """Generate a description based on detected tech stack."""

    # Try to read from package.json description
    package_json = path / "package.json"
    if package_json.exists():
        try:
            with open(package_json) as f:
                pkg = json.load(f)
            if pkg.get("description"):
                analysis.description = pkg["description"]
                return
        except (json.JSONDecodeError, IOError):
            pass

    # Try to read from pyproject.toml
    pyproject = path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            for line in content.split("\n"):
                if line.strip().startswith("description"):
                    desc = line.split("=", 1)[1].strip().strip('"\'')
                    if desc:
                        analysis.description = desc
                        return
        except IOError:
            pass

    # Generate from tech stack
    if analysis.tech_stack:
        primary_tech = analysis.tech_stack[:3]
        analysis.description = f"Project using {', '.join(primary_tech)}"
    else:
        analysis.description = f"Project at {path.name}"

    # Add notes about structure
    notes = []

    # Check for README
    readme_files = ["README.md", "README.rst", "README.txt", "README"]
    for readme in readme_files:
        if (path / readme).exists():
            notes.append(f"Has {readme} - read for detailed documentation")
            break

    # Check for docs
    if (path / "docs").is_dir():
        notes.append("Has /docs directory with documentation")

    # Check for examples
    if (path / "examples").is_dir():
        notes.append("Has /examples directory with usage examples")

    analysis.notes = "\n".join(notes)
