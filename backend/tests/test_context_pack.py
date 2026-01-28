"""Tests for context pack generation."""

import json
import tempfile
from pathlib import Path

import pytest

from app.projects.context_pack import (
    ContextPack,
    Entrypoint,
    ModuleMapping,
    ProjectManifest,
    compute_project_hash,
    context_pack_exists,
    context_pack_is_stale,
    detect_commands,
    detect_config_files,
    detect_dependencies,
    detect_entrypoints,
    detect_language_and_framework,
    detect_modules,
    detect_source_and_test_dirs,
    extract_readme_summary,
    generate_context_pack,
    generate_file_tree,
    generate_manifest,
    get_context_pack_dir,
    load_context_pack,
    save_context_pack,
)


@pytest.fixture
def python_project(tmp_path: Path) -> Path:
    """Create a sample Python project structure."""
    # Create pyproject.toml
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("""
[project]
name = "sample-project"
version = "1.0.0"
description = "A sample Python project for testing"
dependencies = [
    "fastapi",
    "pydantic",
    "sqlalchemy",
]

[project.optional-dependencies]
dev = ["pytest", "ruff"]

[tool.pytest.ini_options]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
""")

    # Create README.md
    readme = tmp_path / "README.md"
    readme.write_text("""# Sample Project

A sample Python project for testing context pack generation.

This project demonstrates the context pack functionality.

## Installation

pip install -e .

## Usage

Run the server with `uvicorn app.main:app --reload`.
""")

    # Create app directory
    app_dir = tmp_path / "app"
    app_dir.mkdir()

    # Create main.py
    main = app_dir / "main.py"
    main.write_text("""
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def root():
    return {"message": "Hello"}
""")

    # Create __init__.py
    (app_dir / "__init__.py").write_text("")

    # Create api module
    api_dir = app_dir / "api"
    api_dir.mkdir()
    (api_dir / "__init__.py").write_text("")
    (api_dir / "routes.py").write_text("# API routes")

    # Create models module
    models_dir = app_dir / "models"
    models_dir.mkdir()
    (models_dir / "__init__.py").write_text("")
    (models_dir / "user.py").write_text("# User model")

    # Create utils
    utils_dir = app_dir / "utils"
    utils_dir.mkdir()
    (utils_dir / "__init__.py").write_text("")
    (utils_dir / "helpers.py").write_text("# Helper functions")

    # Create tests directory
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("")
    (tests_dir / "test_main.py").write_text("# Tests")

    return tmp_path


@pytest.fixture
def node_project(tmp_path: Path) -> Path:
    """Create a sample Node.js project structure."""
    # Create package.json
    pkg = tmp_path / "package.json"
    pkg.write_text(json.dumps({
        "name": "node-sample",
        "version": "1.0.0",
        "description": "A sample Node.js project",
        "scripts": {
            "build": "tsc",
            "test": "jest",
            "start": "node dist/index.js",
            "dev": "ts-node src/index.ts",
            "lint": "eslint ."
        },
        "dependencies": {
            "express": "^4.18.0",
            "typescript": "^5.0.0"
        },
        "devDependencies": {
            "jest": "^29.0.0",
            "@types/node": "^20.0.0"
        }
    }, indent=2))

    # Create tsconfig.json
    (tmp_path / "tsconfig.json").write_text("{}")

    # Create README
    (tmp_path / "README.md").write_text("""# Node Sample

A sample Node.js TypeScript project.
""")

    # Create src directory
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    (src_dir / "index.ts").write_text("console.log('hello');")

    # Create components
    components_dir = src_dir / "components"
    components_dir.mkdir()
    (components_dir / "Button.tsx").write_text("// Button component")

    return tmp_path


class TestLanguageDetection:
    """Tests for language and framework detection."""

    def test_detect_python_fastapi(self, python_project: Path):
        language, framework, languages, pkg_mgr = detect_language_and_framework(python_project)
        assert language == "python"
        assert framework == "FastAPI"
        assert "python" in languages
        assert pkg_mgr == "pip"

    def test_detect_node_express(self, node_project: Path):
        language, framework, languages, pkg_mgr = detect_language_and_framework(node_project)
        assert language == "typescript"
        assert framework == "Express"
        assert "typescript" in languages
        assert pkg_mgr == "npm"

    def test_detect_unknown_project(self, tmp_path: Path):
        language, framework, languages, pkg_mgr = detect_language_and_framework(tmp_path)
        assert language == "unknown"
        assert framework == ""
        assert languages == []


class TestCommandDetection:
    """Tests for build/test/run command detection."""

    def test_python_commands(self, python_project: Path):
        commands = detect_commands(python_project, "python", "pip")
        assert commands["test"] == "pytest"
        assert commands["lint"] == "ruff check ."
        assert "uvicorn" in commands["run"]

    def test_node_commands(self, node_project: Path):
        commands = detect_commands(node_project, "typescript", "npm")
        assert "npm run test" in commands["test"]
        assert "npm run build" in commands["build"]
        assert "npm run start" in commands["run"] or "npm run dev" in commands["run"]


class TestDirectoryDetection:
    """Tests for source and test directory detection."""

    def test_detect_dirs_python(self, python_project: Path):
        source_dirs, test_dirs = detect_source_and_test_dirs(python_project)
        assert "app" in source_dirs
        assert "tests" in test_dirs

    def test_detect_dirs_node(self, node_project: Path):
        source_dirs, test_dirs = detect_source_and_test_dirs(node_project)
        assert "src" in source_dirs


class TestDependencyDetection:
    """Tests for dependency extraction."""

    def test_python_deps(self, python_project: Path):
        deps, dev_deps = detect_dependencies(python_project, "python")
        assert "fastapi" in deps
        assert "pydantic" in deps

    def test_node_deps(self, node_project: Path):
        deps, dev_deps = detect_dependencies(node_project, "typescript")
        assert "express" in deps
        assert "jest" in dev_deps


class TestModuleDetection:
    """Tests for module mapping detection."""

    def test_python_modules(self, python_project: Path):
        modules = detect_modules(python_project, ["app"])
        domains = {m.domain for m in modules}
        assert "api" in domains
        assert "database" in domains or "general" in domains  # models -> database
        assert "utilities" in domains


class TestEntrypointDetection:
    """Tests for entrypoint detection."""

    def test_python_entrypoints(self, python_project: Path):
        entrypoints = detect_entrypoints(python_project, "python")
        paths = [e.path for e in entrypoints]
        assert "app/main.py" in paths

    def test_node_entrypoints(self, node_project: Path):
        entrypoints = detect_entrypoints(node_project, "typescript")
        paths = [e.path for e in entrypoints]
        assert "src/index.ts" in paths


class TestReadmeExtraction:
    """Tests for README summary extraction."""

    def test_extract_summary(self, python_project: Path):
        summary = extract_readme_summary(python_project)
        assert "sample Python project" in summary.lower() or "testing" in summary.lower()

    def test_no_readme(self, tmp_path: Path):
        summary = extract_readme_summary(tmp_path)
        assert summary == ""

    def test_readme_with_badges(self, tmp_path: Path):
        readme = tmp_path / "README.md"
        readme.write_text("""# My Project

[![Build](https://shields.io/badge)](https://example.com)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

This is the actual description of the project.

## Installation
""")
        summary = extract_readme_summary(tmp_path)
        assert "actual description" in summary.lower()
        assert "shields.io" not in summary


class TestFileTree:
    """Tests for file tree generation."""

    def test_generate_tree(self, python_project: Path):
        tree = generate_file_tree(python_project)
        assert "app/" in tree
        assert "tests/" in tree

    def test_tree_excludes_hidden(self, tmp_path: Path):
        (tmp_path / ".git").mkdir()
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "main.py").write_text("")

        tree = generate_file_tree(tmp_path)
        assert ".git" not in tree
        assert "src/" in tree


class TestProjectHash:
    """Tests for project hash computation."""

    def test_hash_changes_with_deps(self, python_project: Path):
        hash1 = compute_project_hash(python_project)

        # Modify pyproject.toml
        pyproject = python_project / "pyproject.toml"
        content = pyproject.read_text()
        pyproject.write_text(content + '\n# comment\n')

        hash2 = compute_project_hash(python_project)
        assert hash1 != hash2

    def test_hash_stable(self, python_project: Path):
        hash1 = compute_project_hash(python_project)
        hash2 = compute_project_hash(python_project)
        assert hash1 == hash2


class TestManifestGeneration:
    """Tests for manifest generation."""

    def test_generate_manifest(self, python_project: Path):
        manifest = generate_manifest(python_project)
        assert manifest.name == python_project.name
        assert manifest.language == "python"
        assert manifest.framework == "FastAPI"
        assert "app" in manifest.source_dirs
        assert "tests" in manifest.test_dirs

    def test_manifest_serialization(self, python_project: Path):
        manifest = generate_manifest(python_project)
        data = manifest.to_dict()
        restored = ProjectManifest.from_dict(data)
        assert restored.name == manifest.name
        assert restored.language == manifest.language


class TestContextPackGeneration:
    """Tests for full context pack generation."""

    def test_generate_pack(self, python_project: Path):
        pack = generate_context_pack(python_project)
        assert pack.manifest.name == python_project.name
        assert pack.manifest.language == "python"
        assert len(pack.module_map) > 0
        assert len(pack.entrypoints) > 0
        assert pack.readme_summary != ""
        assert pack.file_tree != ""
        assert pack.content_hash != ""

    def test_generate_pack_invalid_path(self):
        with pytest.raises(ValueError, match="does not exist"):
            generate_context_pack("/nonexistent/path")

    def test_pack_serialization(self, python_project: Path):
        pack = generate_context_pack(python_project)
        data = pack.to_dict()
        restored = ContextPack.from_dict(data)
        assert restored.manifest.name == pack.manifest.name
        assert restored.readme_summary == pack.readme_summary
        assert restored.file_tree == pack.file_tree


class TestContextPackStorage:
    """Tests for context pack persistence."""

    def test_save_and_load(self, python_project: Path, tmp_path: Path, monkeypatch):
        # Use temp directory for storage
        storage_dir = tmp_path / "context-packs"
        monkeypatch.setattr(
            "app.projects.context_pack.get_context_pack_dir",
            lambda name: storage_dir / name
        )

        pack = generate_context_pack(python_project)
        save_context_pack(pack, "test-project")

        # Verify files created
        pack_dir = storage_dir / "test-project"
        assert (pack_dir / "project.json").exists()
        assert (pack_dir / "MODULE_MAP.json").exists()
        assert (pack_dir / "ENTRYPOINTS.json").exists()
        assert (pack_dir / "context_pack.json").exists()

        # Load and verify
        loaded = load_context_pack("test-project")
        assert loaded is not None
        assert loaded.manifest.name == pack.manifest.name

    def test_context_pack_exists(self, python_project: Path, tmp_path: Path, monkeypatch):
        storage_dir = tmp_path / "context-packs"
        monkeypatch.setattr(
            "app.projects.context_pack.get_context_pack_dir",
            lambda name: storage_dir / name
        )

        assert not context_pack_exists("test-project")

        pack = generate_context_pack(python_project)
        save_context_pack(pack, "test-project")

        assert context_pack_exists("test-project")

    def test_context_pack_staleness(self, tmp_path: Path, monkeypatch):
        # Create project in a subdirectory to avoid conflicts
        project_dir = tmp_path / "myproject"
        project_dir.mkdir()

        # Create minimal Python project
        pyproject = project_dir / "pyproject.toml"
        pyproject.write_text("""
[project]
name = "test"
version = "1.0.0"
dependencies = ["fastapi"]
""")
        (project_dir / "app").mkdir()
        (project_dir / "app" / "__init__.py").write_text("")

        # Create storage in separate location
        storage_dir = tmp_path / "storage"
        storage_dir.mkdir()

        monkeypatch.setattr(
            "app.projects.context_pack.get_context_pack_dir",
            lambda name: storage_dir / name
        )

        pack = generate_context_pack(project_dir)
        save_context_pack(pack, "test-project")

        # Fresh pack is not stale (hash should match)
        assert not context_pack_is_stale("test-project", project_dir)

        # Modify project dependencies to change hash
        pyproject.write_text("""
[project]
name = "test"
version = "2.0.0"
dependencies = ["fastapi", "pydantic"]
""")

        # Now it's stale because hash changed
        assert context_pack_is_stale("test-project", project_dir)


class TestCompactContext:
    """Tests for compact context generation."""

    def test_get_compact_context(self, python_project: Path):
        pack = generate_context_pack(python_project)
        context = pack.get_compact_context()

        assert "## Project:" in context
        assert "python" in context.lower()
        assert "**Commands:**" in context
        assert "**Key Modules:**" in context
        assert "**Entry Points:**" in context

    def test_compact_context_includes_readme(self, python_project: Path):
        pack = generate_context_pack(python_project)
        context = pack.get_compact_context()

        assert "**Overview:**" in context

    def test_compact_context_includes_tree(self, python_project: Path):
        pack = generate_context_pack(python_project)
        context = pack.get_compact_context()

        assert "**Structure:**" in context
        assert "```" in context
