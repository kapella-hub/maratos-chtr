"""Context Pack - Lightweight project understanding without full repo context.

Generates and manages:
- project.json: manifest with language, commands, deps
- ARCHITECTURE.md: modules/services/data flows
- MODULE_MAP.json: folders -> domains mapping
- ENTRYPOINTS.json: main entry files
"""

import hashlib
import json
import logging
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Context Pack Models
# =============================================================================


@dataclass
class ProjectManifest:
    """Project manifest with metadata and commands.

    Stored as project.json in context pack.
    """
    name: str
    language: str  # Primary language: python, javascript, typescript, go, rust, etc.
    languages: list[str] = field(default_factory=list)  # All detected languages
    framework: str = ""  # Primary framework

    # Build/run commands
    build_command: str = ""
    test_command: str = ""
    run_command: str = ""
    lint_command: str = ""

    # Package info
    package_manager: str = ""  # pip, npm, pnpm, yarn, cargo, go
    dependencies: list[str] = field(default_factory=list)  # Top dependencies
    dev_dependencies: list[str] = field(default_factory=list)

    # Structure info
    source_dirs: list[str] = field(default_factory=list)  # src/, app/, lib/
    test_dirs: list[str] = field(default_factory=list)  # tests/, __tests__/
    config_files: list[str] = field(default_factory=list)  # Config files found

    # Metadata
    description: str = ""
    version: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "language": self.language,
            "languages": self.languages,
            "framework": self.framework,
            "commands": {
                "build": self.build_command,
                "test": self.test_command,
                "run": self.run_command,
                "lint": self.lint_command,
            },
            "package_manager": self.package_manager,
            "dependencies": self.dependencies,
            "dev_dependencies": self.dev_dependencies,
            "source_dirs": self.source_dirs,
            "test_dirs": self.test_dirs,
            "config_files": self.config_files,
            "description": self.description,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectManifest":
        commands = data.get("commands", {})
        return cls(
            name=data.get("name", ""),
            language=data.get("language", ""),
            languages=data.get("languages", []),
            framework=data.get("framework", ""),
            build_command=commands.get("build", ""),
            test_command=commands.get("test", ""),
            run_command=commands.get("run", ""),
            lint_command=commands.get("lint", ""),
            package_manager=data.get("package_manager", ""),
            dependencies=data.get("dependencies", []),
            dev_dependencies=data.get("dev_dependencies", []),
            source_dirs=data.get("source_dirs", []),
            test_dirs=data.get("test_dirs", []),
            config_files=data.get("config_files", []),
            description=data.get("description", ""),
            version=data.get("version", ""),
        )


@dataclass
class ModuleMapping:
    """Maps folders to semantic domains.

    Stored as MODULE_MAP.json in context pack.
    """
    path: str  # Relative path from project root
    domain: str  # Semantic domain: api, auth, database, models, utils, etc.
    description: str = ""  # Brief description
    key_files: list[str] = field(default_factory=list)  # Important files in this module
    exports: list[str] = field(default_factory=list)  # Main exports/classes/functions

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "domain": self.domain,
            "description": self.description,
            "key_files": self.key_files,
            "exports": self.exports,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModuleMapping":
        return cls(
            path=data.get("path", ""),
            domain=data.get("domain", ""),
            description=data.get("description", ""),
            key_files=data.get("key_files", []),
            exports=data.get("exports", []),
        )


@dataclass
class Entrypoint:
    """Main entry point file.

    Stored in ENTRYPOINTS.json in context pack.
    """
    path: str  # Relative path
    type: str  # main, cli, api, worker, test, config
    description: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "type": self.type,
            "description": self.description,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Entrypoint":
        return cls(
            path=data.get("path", ""),
            type=data.get("type", ""),
            description=data.get("description", ""),
        )


@dataclass
class ContextPack:
    """Complete context pack for a project.

    Contains all generated artifacts for project understanding.
    """
    project_path: str
    manifest: ProjectManifest
    module_map: list[ModuleMapping] = field(default_factory=list)
    entrypoints: list[Entrypoint] = field(default_factory=list)
    architecture_md: str = ""  # Generated ARCHITECTURE.md content
    readme_summary: str = ""  # Summary from README.md
    file_tree: str = ""  # File tree summary
    developer_docs: str = ""  # User-added documentation snippets

    # Metadata
    version: str = "1.0"
    generated_at: str = ""
    content_hash: str = ""  # Hash of project files for change detection

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "project_path": self.project_path,
            "generated_at": self.generated_at,
            "content_hash": self.content_hash,
            "manifest": self.manifest.to_dict(),
            "module_map": [m.to_dict() for m in self.module_map],
            "entrypoints": [e.to_dict() for e in self.entrypoints],
            "readme_summary": self.readme_summary,
            "file_tree": self.file_tree,
            "developer_docs": self.developer_docs,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContextPack":
        return cls(
            project_path=data.get("project_path", ""),
            manifest=ProjectManifest.from_dict(data.get("manifest", {})),
            module_map=[ModuleMapping.from_dict(m) for m in data.get("module_map", [])],
            entrypoints=[Entrypoint.from_dict(e) for e in data.get("entrypoints", [])],
            architecture_md=data.get("architecture_md", ""),
            readme_summary=data.get("readme_summary", ""),
            file_tree=data.get("file_tree", ""),
            developer_docs=data.get("developer_docs", ""),
            version=data.get("version", "1.0"),
            generated_at=data.get("generated_at", ""),
            content_hash=data.get("content_hash", ""),
        )

    def get_compact_context(self) -> str:
        """Get compact context string for injection into prompts.

        This is the minimal context always loaded.
        """
        lines = [
            f"## Project: {self.manifest.name}",
            f"**Language:** {self.manifest.language} ({self.manifest.framework})" if self.manifest.framework else f"**Language:** {self.manifest.language}",
            "",
        ]

        # README summary
        if self.readme_summary:
            lines.append("**Overview:**")
            lines.append(self.readme_summary)
            lines.append("")

        # Commands
        if any([self.manifest.build_command, self.manifest.test_command, self.manifest.run_command]):
            lines.append("**Commands:**")
            if self.manifest.run_command:
                lines.append(f"- Run: `{self.manifest.run_command}`")
            if self.manifest.test_command:
                lines.append(f"- Test: `{self.manifest.test_command}`")
            if self.manifest.build_command:
                lines.append(f"- Build: `{self.manifest.build_command}`")
            lines.append("")

        # File tree summary
        if self.file_tree:
            lines.append("**Structure:**")
            lines.append("```")
            lines.append(self.file_tree)
            lines.append("```")
            lines.append("")

        # Key modules (top 10)
        if self.module_map:
            lines.append("**Key Modules:**")
            for module in self.module_map[:10]:
                desc = f" - {module.description}" if module.description else ""
                lines.append(f"- `{module.path}` ({module.domain}){desc}")
            lines.append("")

        # Entrypoints
        if self.entrypoints:
            lines.append("**Entry Points:**")
            for ep in self.entrypoints[:5]:
                lines.append(f"- `{ep.path}` ({ep.type})")
            lines.append("")

        # Top dependencies
        if self.manifest.dependencies:
            lines.append(f"**Key Dependencies:** {', '.join(self.manifest.dependencies[:10])}")
            lines.append("")

        # Developer docs
        if self.developer_docs:
            lines.append(self.developer_docs)

        return "\n".join(lines)


# =============================================================================
# Context Pack Generation
# =============================================================================


def compute_project_hash(project_path: Path) -> str:
    """Compute hash of key project files for change detection.

    Hashes: package files, key config files, directory structure.
    """
    hasher = hashlib.sha256()

    # Key files to hash
    key_files = [
        "package.json", "package-lock.json", "pnpm-lock.yaml", "yarn.lock",
        "pyproject.toml", "requirements.txt", "Pipfile.lock", "poetry.lock",
        "Cargo.toml", "Cargo.lock", "go.mod", "go.sum",
        "Gemfile", "Gemfile.lock", "composer.json", "composer.lock",
    ]

    for filename in key_files:
        filepath = project_path / filename
        if filepath.exists():
            try:
                hasher.update(filepath.read_bytes())
            except IOError:
                pass

    # Hash directory structure (top-level dirs)
    try:
        dirs = sorted([d.name for d in project_path.iterdir() if d.is_dir() and not d.name.startswith(".")])
        hasher.update(",".join(dirs).encode())
    except IOError:
        pass

    return hasher.hexdigest()[:16]


def detect_language_and_framework(project_path: Path) -> tuple[str, str, list[str], str]:
    """Detect primary language, framework, all languages, and package manager.

    Returns: (language, framework, languages, package_manager)
    """
    languages = []
    framework = ""
    package_manager = ""

    # Python
    if (project_path / "pyproject.toml").exists() or (project_path / "requirements.txt").exists():
        languages.append("python")
        if (project_path / "poetry.lock").exists():
            package_manager = "poetry"
        elif (project_path / "Pipfile").exists():
            package_manager = "pipenv"
        else:
            package_manager = "pip"

        # Detect Python framework
        for pkg_file in ["pyproject.toml", "requirements.txt"]:
            filepath = project_path / pkg_file
            if filepath.exists():
                try:
                    content = filepath.read_text().lower()
                    if "fastapi" in content:
                        framework = "FastAPI"
                    elif "django" in content:
                        framework = "Django"
                    elif "flask" in content:
                        framework = "Flask"
                    elif "starlette" in content:
                        framework = "Starlette"
                except IOError:
                    pass

    # JavaScript/TypeScript
    if (project_path / "package.json").exists():
        if "typescript" not in languages:
            if (project_path / "tsconfig.json").exists():
                languages.append("typescript")
            else:
                languages.append("javascript")

        if (project_path / "pnpm-lock.yaml").exists():
            package_manager = package_manager or "pnpm"
        elif (project_path / "yarn.lock").exists():
            package_manager = package_manager or "yarn"
        elif (project_path / "bun.lockb").exists():
            package_manager = package_manager or "bun"
        else:
            package_manager = package_manager or "npm"

        # Detect JS framework
        try:
            pkg = json.loads((project_path / "package.json").read_text())
            all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}

            if "next" in all_deps:
                framework = framework or "Next.js"
            elif "nuxt" in all_deps:
                framework = framework or "Nuxt"
            elif "react" in all_deps:
                framework = framework or "React"
            elif "vue" in all_deps:
                framework = framework or "Vue"
            elif "svelte" in all_deps:
                framework = framework or "Svelte"
            elif "@angular/core" in all_deps:
                framework = framework or "Angular"
            elif "express" in all_deps:
                framework = framework or "Express"
            elif "@nestjs/core" in all_deps:
                framework = framework or "NestJS"
        except (json.JSONDecodeError, IOError):
            pass

    # Go
    if (project_path / "go.mod").exists():
        languages.append("go")
        package_manager = package_manager or "go"

    # Rust
    if (project_path / "Cargo.toml").exists():
        languages.append("rust")
        package_manager = package_manager or "cargo"

    # Ruby
    if (project_path / "Gemfile").exists():
        languages.append("ruby")
        package_manager = package_manager or "bundler"

        if (project_path / "config" / "application.rb").exists():
            framework = framework or "Rails"

    # Java/Kotlin
    if (project_path / "pom.xml").exists():
        languages.append("java")
        package_manager = package_manager or "maven"
    elif (project_path / "build.gradle").exists() or (project_path / "build.gradle.kts").exists():
        if (project_path / "build.gradle.kts").exists():
            languages.append("kotlin")
        else:
            languages.append("java")
        package_manager = package_manager or "gradle"

    # Primary language is first detected
    primary = languages[0] if languages else "unknown"

    return primary, framework, languages, package_manager


def detect_commands(project_path: Path, language: str, package_manager: str) -> dict[str, str]:
    """Detect build/test/run/lint commands for the project."""
    commands = {
        "build": "",
        "test": "",
        "run": "",
        "lint": "",
    }

    # Check package.json scripts
    pkg_json = project_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            scripts = pkg.get("scripts", {})

            run_cmd = f"{package_manager} run" if package_manager in ("npm", "pnpm", "yarn") else ""

            if "build" in scripts:
                commands["build"] = f"{run_cmd} build"
            if "test" in scripts:
                commands["test"] = f"{run_cmd} test"
            if "start" in scripts:
                commands["run"] = f"{run_cmd} start"
            elif "dev" in scripts:
                commands["run"] = f"{run_cmd} dev"
            if "lint" in scripts:
                commands["lint"] = f"{run_cmd} lint"
        except (json.JSONDecodeError, IOError):
            pass

    # Python
    if language == "python":
        # Test command
        if (project_path / "pytest.ini").exists() or (project_path / "tests").is_dir():
            commands["test"] = commands["test"] or "pytest"
        elif (project_path / "pyproject.toml").exists():
            try:
                content = (project_path / "pyproject.toml").read_text()
                if "[tool.pytest" in content:
                    commands["test"] = "pytest"
            except IOError:
                pass

        # Lint command
        if (project_path / "ruff.toml").exists() or (project_path / ".ruff.toml").exists():
            commands["lint"] = "ruff check ."
        elif (project_path / "pyproject.toml").exists():
            try:
                content = (project_path / "pyproject.toml").read_text()
                if "[tool.ruff" in content:
                    commands["lint"] = "ruff check ."
            except IOError:
                pass

        # Run command
        if (project_path / "app" / "main.py").exists():
            commands["run"] = commands["run"] or "uvicorn app.main:app --reload"
        elif (project_path / "src" / "main.py").exists():
            commands["run"] = commands["run"] or "python src/main.py"
        elif (project_path / "main.py").exists():
            commands["run"] = commands["run"] or "python main.py"
        elif (project_path / "manage.py").exists():
            commands["run"] = commands["run"] or "python manage.py runserver"

    # Go
    if language == "go":
        commands["build"] = commands["build"] or "go build"
        commands["test"] = commands["test"] or "go test ./..."
        commands["run"] = commands["run"] or "go run ."

    # Rust
    if language == "rust":
        commands["build"] = commands["build"] or "cargo build"
        commands["test"] = commands["test"] or "cargo test"
        commands["run"] = commands["run"] or "cargo run"
        commands["lint"] = commands["lint"] or "cargo clippy"

    # Makefile overrides
    makefile = project_path / "Makefile"
    if makefile.exists():
        try:
            content = makefile.read_text()
            if "test:" in content:
                commands["test"] = "make test"
            if "build:" in content:
                commands["build"] = "make build"
            if "run:" in content or "serve:" in content:
                commands["run"] = "make run" if "run:" in content else "make serve"
            if "lint:" in content:
                commands["lint"] = "make lint"
        except IOError:
            pass

    return commands


def detect_source_and_test_dirs(project_path: Path) -> tuple[list[str], list[str]]:
    """Detect source and test directories."""
    source_dirs = []
    test_dirs = []

    # Common source directories
    for src_dir in ["src", "app", "lib", "pkg", "internal", "cmd", "backend", "frontend"]:
        if (project_path / src_dir).is_dir():
            source_dirs.append(src_dir)

    # Common test directories
    for test_dir in ["tests", "test", "__tests__", "spec", "specs", "e2e"]:
        if (project_path / test_dir).is_dir():
            test_dirs.append(test_dir)

    return source_dirs, test_dirs


def detect_config_files(project_path: Path) -> list[str]:
    """Detect configuration files."""
    config_files = []

    config_patterns = [
        "*.config.js", "*.config.ts", "*.config.mjs",
        ".env*", "*.toml", "*.yaml", "*.yml", "*.json",
        "Dockerfile*", "docker-compose*", ".github/workflows/*",
    ]

    # Common config files
    common_configs = [
        "package.json", "tsconfig.json", "pyproject.toml", "Cargo.toml",
        "go.mod", "Gemfile", "pom.xml", "build.gradle",
        ".env", ".env.example", ".env.local",
        "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
        "Makefile", ".gitignore", ".dockerignore",
    ]

    for cfg in common_configs:
        if (project_path / cfg).exists():
            config_files.append(cfg)

    return config_files[:20]  # Limit


def detect_dependencies(project_path: Path, language: str) -> tuple[list[str], list[str]]:
    """Extract top dependencies from package files."""
    deps = []
    dev_deps = []

    # package.json
    pkg_json = project_path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            deps.extend(list(pkg.get("dependencies", {}).keys())[:15])
            dev_deps.extend(list(pkg.get("devDependencies", {}).keys())[:10])
        except (json.JSONDecodeError, IOError):
            pass

    # pyproject.toml
    pyproject = project_path / "pyproject.toml"
    if pyproject.exists():
        try:
            content = pyproject.read_text()
            # Simple extraction
            in_deps = False
            in_dev_deps = False
            for line in content.split("\n"):
                if "dependencies" in line.lower() and "=" in line:
                    if "dev" in line.lower() or "optional" in line.lower():
                        in_dev_deps = True
                        in_deps = False
                    else:
                        in_deps = True
                        in_dev_deps = False
                    continue

                if line.strip().startswith("[") and not "dependencies" in line.lower():
                    in_deps = False
                    in_dev_deps = False
                    continue

                if in_deps or in_dev_deps:
                    if line.strip().startswith('"'):
                        dep = line.strip().strip('",').split("[")[0].split(">")[0].split("<")[0].split("=")[0].strip()
                        if dep:
                            if in_deps:
                                deps.append(dep)
                            else:
                                dev_deps.append(dep)
        except IOError:
            pass

    # requirements.txt
    req_txt = project_path / "requirements.txt"
    if req_txt.exists():
        try:
            for line in req_txt.read_text().split("\n"):
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("-"):
                    dep = line.split("[")[0].split(">")[0].split("<")[0].split("=")[0].split("!")[0].strip()
                    if dep:
                        deps.append(dep)
        except IOError:
            pass

    return deps[:15], dev_deps[:10]


def detect_modules(project_path: Path, source_dirs: list[str]) -> list[ModuleMapping]:
    """Detect modules and their domains."""
    modules = []

    # Domain detection patterns
    domain_patterns = {
        r"api|routes|endpoints|handlers|views": "api",
        r"auth|authentication|login|oauth": "auth",
        r"db|database|models|entities|orm|repositories": "database",
        r"services|business|logic": "services",
        r"utils|helpers|common|shared|lib": "utilities",
        r"config|settings|constants": "config",
        r"tests?|spec|__tests__": "tests",
        r"types|interfaces|schemas": "types",
        r"components|ui|widgets": "ui",
        r"pages|views|screens": "pages",
        r"hooks": "hooks",
        r"store|state|redux|context": "state",
        r"middleware": "middleware",
        r"workers|jobs|tasks|queues": "workers",
        r"cli|commands": "cli",
        r"docs|documentation": "docs",
    }

    def get_domain(name: str) -> str:
        name_lower = name.lower()
        for pattern, domain in domain_patterns.items():
            if re.search(pattern, name_lower):
                return domain
        return "general"

    # Scan source directories
    scan_dirs = source_dirs if source_dirs else ["."]

    for src_dir in scan_dirs:
        src_path = project_path / src_dir
        if not src_path.is_dir():
            continue

        # Get immediate subdirectories
        try:
            for item in src_path.iterdir():
                if item.is_dir() and not item.name.startswith(".") and not item.name.startswith("__"):
                    rel_path = str(item.relative_to(project_path))
                    domain = get_domain(item.name)

                    # Get key files
                    key_files = []
                    try:
                        for f in item.iterdir():
                            if f.is_file() and f.suffix in (".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs"):
                                if not f.name.startswith("_") or f.name == "__init__.py":
                                    key_files.append(f.name)
                    except IOError:
                        pass

                    modules.append(ModuleMapping(
                        path=rel_path,
                        domain=domain,
                        description="",  # Will be filled by LLM if needed
                        key_files=key_files[:10],
                    ))
        except IOError:
            pass

    return modules


def detect_entrypoints(project_path: Path, language: str) -> list[Entrypoint]:
    """Detect main entry point files."""
    entrypoints = []

    # Python entrypoints
    python_mains = [
        ("app/main.py", "api", "FastAPI application entry"),
        ("src/main.py", "main", "Main entry point"),
        ("main.py", "main", "Main entry point"),
        ("manage.py", "cli", "Django management script"),
        ("run.py", "main", "Run script"),
        ("app/__init__.py", "api", "Application package"),
        ("cli.py", "cli", "CLI entry point"),
        ("__main__.py", "main", "Package main"),
    ]

    if language == "python":
        for path, ep_type, desc in python_mains:
            if (project_path / path).exists():
                entrypoints.append(Entrypoint(path=path, type=ep_type, description=desc))

    # Node entrypoints
    node_mains = [
        ("src/index.ts", "main", "TypeScript entry"),
        ("src/index.js", "main", "JavaScript entry"),
        ("src/main.ts", "main", "Main entry"),
        ("src/main.js", "main", "Main entry"),
        ("src/app.ts", "api", "App entry"),
        ("src/app.js", "api", "App entry"),
        ("src/server.ts", "api", "Server entry"),
        ("src/server.js", "api", "Server entry"),
        ("index.ts", "main", "Root entry"),
        ("index.js", "main", "Root entry"),
        ("pages/_app.tsx", "main", "Next.js app"),
        ("pages/_app.js", "main", "Next.js app"),
        ("app/layout.tsx", "main", "Next.js app router"),
    ]

    if language in ("javascript", "typescript"):
        for path, ep_type, desc in node_mains:
            if (project_path / path).exists():
                entrypoints.append(Entrypoint(path=path, type=ep_type, description=desc))

    # Go entrypoints
    if language == "go":
        if (project_path / "main.go").exists():
            entrypoints.append(Entrypoint(path="main.go", type="main", description="Main entry"))
        if (project_path / "cmd").is_dir():
            try:
                for item in (project_path / "cmd").iterdir():
                    if item.is_dir():
                        main_go = item / "main.go"
                        if main_go.exists():
                            entrypoints.append(Entrypoint(
                                path=str(main_go.relative_to(project_path)),
                                type="cli",
                                description=f"{item.name} command"
                            ))
            except IOError:
                pass

    # Rust entrypoints
    if language == "rust":
        if (project_path / "src" / "main.rs").exists():
            entrypoints.append(Entrypoint(path="src/main.rs", type="main", description="Binary entry"))
        if (project_path / "src" / "lib.rs").exists():
            entrypoints.append(Entrypoint(path="src/lib.rs", type="library", description="Library entry"))

    return entrypoints[:10]


def extract_readme_summary(project_path: Path, max_chars: int = 500) -> str:
    """Extract a brief summary from README.md.

    Looks for the first paragraph or description section.
    """
    readme_names = ["README.md", "readme.md", "README.rst", "README.txt", "README"]

    for readme_name in readme_names:
        readme_path = project_path / readme_name
        if readme_path.exists():
            try:
                content = readme_path.read_text(encoding="utf-8", errors="replace")
                return _parse_readme_summary(content, max_chars)
            except IOError:
                pass

    return ""


def _parse_readme_summary(content: str, max_chars: int) -> str:
    """Parse README content to extract summary."""
    lines = content.split("\n")
    summary_lines = []
    in_summary = False
    past_badges = False

    for line in lines:
        stripped = line.strip()

        # Skip empty lines at start
        if not stripped and not summary_lines:
            continue

        # Skip the main title (first h1)
        if stripped.startswith("# ") and not summary_lines:
            continue

        # Skip badge lines (common at start of READMEs)
        # Badges look like: [![text](url)](url) or ![text](url)
        if not past_badges and (
            re.match(r'^\[?!\[', stripped) or
            "shields.io" in stripped.lower() or
            "badge" in stripped.lower() or
            "img.shields" in stripped.lower()
        ):
            continue

        # Stop at next heading or specific sections
        if stripped.startswith("#"):
            break
        if stripped.lower() in ("## installation", "## getting started", "## usage", "## features"):
            break

        # Once we find a non-badge, non-empty line, we're past badges
        if stripped:
            past_badges = True
            summary_lines.append(stripped)
            in_summary = True

            # Stop after first paragraph (enough lines collected)
            if len(summary_lines) >= 3:
                break
        elif in_summary:
            # Empty line after collecting content - paragraph end
            break

    summary = " ".join(summary_lines)

    # Clean up markdown formatting
    summary = re.sub(r"\*\*([^*]+)\*\*", r"\1", summary)  # Bold
    summary = re.sub(r"\*([^*]+)\*", r"\1", summary)  # Italic
    summary = re.sub(r"`([^`]+)`", r"\1", summary)  # Code
    summary = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", summary)  # Links

    if len(summary) > max_chars:
        summary = summary[:max_chars - 3] + "..."

    return summary


def generate_file_tree(project_path: Path, max_depth: int = 3, max_items: int = 50) -> str:
    """Generate a compact file tree summary.

    Shows top-level structure with important directories expanded.
    """
    tree_lines = []
    item_count = 0

    # Directories to skip
    skip_dirs = {
        "node_modules", ".git", "__pycache__", ".venv", "venv",
        "dist", "build", ".next", "coverage", ".pytest_cache",
        ".mypy_cache", ".ruff_cache", "target", ".idea", ".vscode",
        "vendor", "bower_components", ".tox", "eggs", "*.egg-info",
    }

    def should_skip(name: str) -> bool:
        if name.startswith("."):
            return True
        if name in skip_dirs:
            return True
        if name.endswith(".egg-info"):
            return True
        return False

    def add_tree(path: Path, prefix: str = "", depth: int = 0) -> None:
        nonlocal item_count

        if depth > max_depth or item_count >= max_items:
            return

        try:
            items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        except PermissionError:
            return

        dirs = [i for i in items if i.is_dir() and not should_skip(i.name)]
        files = [i for i in items if i.is_file() and not i.name.startswith(".")]

        # Show directories first
        for i, item in enumerate(dirs):
            if item_count >= max_items:
                tree_lines.append(f"{prefix}...")
                return

            is_last = i == len(dirs) - 1 and not files
            connector = "└── " if is_last else "├── "
            tree_lines.append(f"{prefix}{connector}{item.name}/")
            item_count += 1

            # Expand important directories
            new_prefix = prefix + ("    " if is_last else "│   ")
            add_tree(item, new_prefix, depth + 1)

        # Show key files (limit per directory)
        shown_files = 0
        important_files = {"main.py", "index.ts", "index.js", "app.py", "main.go", "lib.rs", "main.rs"}

        for item in files:
            if item_count >= max_items:
                if shown_files < len(files):
                    tree_lines.append(f"{prefix}... ({len(files) - shown_files} more files)")
                return

            # Prioritize important files
            if shown_files >= 5 and item.name not in important_files:
                continue

            is_last = item == files[-1]
            connector = "└── " if is_last else "├── "
            tree_lines.append(f"{prefix}{connector}{item.name}")
            item_count += 1
            shown_files += 1

    tree_lines.append(f"{project_path.name}/")
    add_tree(project_path)

    return "\n".join(tree_lines)


def generate_manifest(project_path: Path) -> ProjectManifest:
    """Generate project manifest from analysis."""
    path = Path(project_path)
    name = path.name

    # Detect language and framework
    language, framework, languages, package_manager = detect_language_and_framework(path)

    # Detect commands
    commands = detect_commands(path, language, package_manager)

    # Detect directories
    source_dirs, test_dirs = detect_source_and_test_dirs(path)

    # Detect config files
    config_files = detect_config_files(path)

    # Get dependencies
    deps, dev_deps = detect_dependencies(path, language)

    # Get description from package files
    description = ""
    version = ""

    pkg_json = path / "package.json"
    if pkg_json.exists():
        try:
            pkg = json.loads(pkg_json.read_text())
            description = pkg.get("description", "")
            version = pkg.get("version", "")
        except (json.JSONDecodeError, IOError):
            pass

    pyproject = path / "pyproject.toml"
    if not description and pyproject.exists():
        try:
            content = pyproject.read_text()
            for line in content.split("\n"):
                if line.strip().startswith("description"):
                    description = line.split("=", 1)[1].strip().strip('"\'')
                    break
                if line.strip().startswith("version") and not version:
                    version = line.split("=", 1)[1].strip().strip('"\'')
        except IOError:
            pass

    return ProjectManifest(
        name=name,
        language=language,
        languages=languages,
        framework=framework,
        build_command=commands["build"],
        test_command=commands["test"],
        run_command=commands["run"],
        lint_command=commands["lint"],
        package_manager=package_manager,
        dependencies=deps,
        dev_dependencies=dev_deps,
        source_dirs=source_dirs,
        test_dirs=test_dirs,
        config_files=config_files,
        description=description,
        version=version,
    )


def generate_context_pack(
    project_path: str | Path,
    project_name: str | None = None,
    include_architecture: bool = False,
) -> ContextPack:
    """Generate a complete context pack for a project.

    Args:
        project_path: Path to the project directory
        project_name: Optional project name for fetching developer docs
        include_architecture: If True, will generate ARCHITECTURE.md (requires LLM)

    Returns:
        ContextPack with all generated artifacts
    """
    path = Path(project_path).expanduser().resolve()

    if not path.exists():
        raise ValueError(f"Project path does not exist: {project_path}")
    if not path.is_dir():
        raise ValueError(f"Project path is not a directory: {project_path}")

    # Generate manifest
    manifest = generate_manifest(path)

    # Detect modules
    modules = detect_modules(path, manifest.source_dirs)

    # Detect entrypoints
    entrypoints = detect_entrypoints(path, manifest.language)

    # Extract README summary
    readme_summary = extract_readme_summary(path)

    # Generate file tree
    file_tree = generate_file_tree(path)

    # Get developer docs if project name provided
    developer_docs = ""
    if project_name:
        from app.projects.docs_store import get_docs_for_context
        developer_docs = get_docs_for_context(project_name)

    # Compute hash
    content_hash = compute_project_hash(path)

    return ContextPack(
        project_path=str(path),
        manifest=manifest,
        module_map=modules,
        entrypoints=entrypoints,
        architecture_md="",  # Generated separately via LLM if needed
        readme_summary=readme_summary,
        file_tree=file_tree,
        developer_docs=developer_docs,
        version="1.0",
        generated_at=datetime.utcnow().isoformat(),
        content_hash=content_hash,
    )


# =============================================================================
# Context Pack Storage
# =============================================================================


def get_context_pack_dir(project_name: str) -> Path:
    """Get the directory for storing context packs."""
    return Path.home() / ".maratos" / "context-packs" / project_name


def save_context_pack(pack: ContextPack, project_name: str) -> Path:
    """Save context pack to disk.

    Creates:
    - project.json (manifest)
    - MODULE_MAP.json
    - ENTRYPOINTS.json
    - ARCHITECTURE.md (if generated)
    - context_pack.json (full pack metadata)
    """
    pack_dir = get_context_pack_dir(project_name)
    pack_dir.mkdir(parents=True, exist_ok=True)

    # Save manifest
    manifest_path = pack_dir / "project.json"
    with open(manifest_path, "w") as f:
        json.dump(pack.manifest.to_dict(), f, indent=2)

    # Save module map
    module_map_path = pack_dir / "MODULE_MAP.json"
    with open(module_map_path, "w") as f:
        json.dump([m.to_dict() for m in pack.module_map], f, indent=2)

    # Save entrypoints
    entrypoints_path = pack_dir / "ENTRYPOINTS.json"
    with open(entrypoints_path, "w") as f:
        json.dump([e.to_dict() for e in pack.entrypoints], f, indent=2)

    # Save architecture if generated
    if pack.architecture_md:
        arch_path = pack_dir / "ARCHITECTURE.md"
        with open(arch_path, "w") as f:
            f.write(pack.architecture_md)

    # Save full pack metadata
    pack_path = pack_dir / "context_pack.json"
    with open(pack_path, "w") as f:
        json.dump(pack.to_dict(), f, indent=2)

    logger.info(f"Saved context pack for {project_name} to {pack_dir}")
    return pack_dir


def load_context_pack(project_name: str) -> ContextPack | None:
    """Load context pack from disk."""
    pack_dir = get_context_pack_dir(project_name)
    pack_path = pack_dir / "context_pack.json"

    if not pack_path.exists():
        return None

    try:
        with open(pack_path) as f:
            data = json.load(f)

        pack = ContextPack.from_dict(data)

        # Load architecture if exists
        arch_path = pack_dir / "ARCHITECTURE.md"
        if arch_path.exists():
            pack.architecture_md = arch_path.read_text()

        return pack
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load context pack for {project_name}: {e}")
        return None


def context_pack_exists(project_name: str) -> bool:
    """Check if a context pack exists for a project."""
    pack_dir = get_context_pack_dir(project_name)
    return (pack_dir / "context_pack.json").exists()


def context_pack_is_stale(project_name: str, project_path: str | Path) -> bool:
    """Check if context pack needs regeneration.

    Returns True if:
    - No context pack exists
    - Project hash has changed
    """
    pack = load_context_pack(project_name)
    if not pack:
        return True

    current_hash = compute_project_hash(Path(project_path))
    return pack.content_hash != current_hash
