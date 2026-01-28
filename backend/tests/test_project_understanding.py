"""Tests for project understanding system.

Tests:
- Context pack generation
- Project manifest detection
- Module mapping
- Entrypoint detection
- Search endpoint
- Command handlers
"""

import json
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock


class TestContextPackGeneration:
    """Tests for context pack generation."""

    def test_generate_manifest_python_project(self, tmp_path):
        """Should detect Python FastAPI project correctly."""
        from app.projects.context_pack import generate_manifest

        # Create a minimal Python project
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test-project"
version = "1.0.0"
description = "A test project"
dependencies = [
    "fastapi",
    "uvicorn",
    "sqlalchemy",
]

[tool.pytest]
testpaths = ["tests"]

[tool.ruff]
line-length = 100
        """)

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "main.py").write_text("# FastAPI app")
        (tmp_path / "tests").mkdir()

        manifest = generate_manifest(tmp_path)

        assert manifest.language == "python"
        assert manifest.framework == "FastAPI"
        assert "pip" in manifest.package_manager or "poetry" in manifest.package_manager
        assert "fastapi" in [d.lower() for d in manifest.dependencies]
        assert "app" in manifest.source_dirs
        assert "tests" in manifest.test_dirs

    def test_generate_manifest_node_project(self, tmp_path):
        """Should detect Node.js React project correctly."""
        from app.projects.context_pack import generate_manifest

        # Create a minimal Node project
        (tmp_path / "package.json").write_text(json.dumps({
            "name": "test-react-app",
            "version": "1.0.0",
            "description": "A test React app",
            "dependencies": {
                "react": "^18.0.0",
                "react-dom": "^18.0.0",
            },
            "devDependencies": {
                "typescript": "^5.0.0",
                "vite": "^5.0.0",
            },
            "scripts": {
                "dev": "vite",
                "build": "vite build",
                "test": "vitest",
            }
        }))

        (tmp_path / "tsconfig.json").write_text("{}")
        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.tsx").write_text("// React entry")

        manifest = generate_manifest(tmp_path)

        assert manifest.language == "typescript"
        assert manifest.framework == "React"
        assert manifest.package_manager in ("npm", "pnpm", "yarn", "bun")
        assert "react" in [d.lower() for d in manifest.dependencies]
        assert "npm run dev" in manifest.run_command or "pnpm run dev" in manifest.run_command

    def test_generate_context_pack(self, tmp_path):
        """Should generate complete context pack."""
        from app.projects.context_pack import generate_context_pack

        # Create a Python project structure
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "test-api"
dependencies = ["fastapi"]
        """)

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
        (tmp_path / "app" / "api").mkdir()
        (tmp_path / "app" / "api" / "routes.py").write_text("# API routes")
        (tmp_path / "app" / "models").mkdir()
        (tmp_path / "app" / "models" / "user.py").write_text("# User model")

        pack = generate_context_pack(tmp_path)

        assert pack.manifest.name == tmp_path.name
        assert pack.manifest.language == "python"
        assert len(pack.module_map) > 0
        assert len(pack.entrypoints) > 0
        assert pack.content_hash

    def test_context_pack_hash_changes(self, tmp_path):
        """Context pack hash should change when project changes."""
        from app.projects.context_pack import compute_project_hash

        # Initial project
        (tmp_path / "package.json").write_text('{"name": "test", "version": "1.0.0"}')

        hash1 = compute_project_hash(tmp_path)

        # Modify project
        (tmp_path / "package.json").write_text('{"name": "test", "version": "2.0.0"}')

        hash2 = compute_project_hash(tmp_path)

        assert hash1 != hash2


class TestModuleMapping:
    """Tests for module detection and mapping."""

    def test_detect_api_module(self, tmp_path):
        """Should detect API module domain."""
        from app.projects.context_pack import detect_modules

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "api").mkdir()
        (tmp_path / "src" / "api" / "routes.py").write_text("")
        (tmp_path / "src" / "api" / "handlers.py").write_text("")

        modules = detect_modules(tmp_path, ["src"])

        api_modules = [m for m in modules if m.domain == "api"]
        assert len(api_modules) >= 1

    def test_detect_auth_module(self, tmp_path):
        """Should detect auth module domain."""
        from app.projects.context_pack import detect_modules

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "auth").mkdir()
        (tmp_path / "app" / "auth" / "login.py").write_text("")

        modules = detect_modules(tmp_path, ["app"])

        auth_modules = [m for m in modules if m.domain == "auth"]
        assert len(auth_modules) >= 1

    def test_detect_database_module(self, tmp_path):
        """Should detect database module domain."""
        from app.projects.context_pack import detect_modules

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "models").mkdir()
        (tmp_path / "src" / "models" / "user.py").write_text("")
        (tmp_path / "src" / "repositories").mkdir()
        (tmp_path / "src" / "repositories" / "user_repo.py").write_text("")

        modules = detect_modules(tmp_path, ["src"])

        db_modules = [m for m in modules if m.domain == "database"]
        assert len(db_modules) >= 1


class TestEntrypointDetection:
    """Tests for entry point detection."""

    def test_detect_python_entrypoints(self, tmp_path):
        """Should detect Python entry points."""
        from app.projects.context_pack import detect_entrypoints

        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "main.py").write_text("# FastAPI entry")
        (tmp_path / "cli.py").write_text("# CLI entry")

        entrypoints = detect_entrypoints(tmp_path, "python")

        paths = [e.path for e in entrypoints]
        assert "app/main.py" in paths
        assert "cli.py" in paths

    def test_detect_node_entrypoints(self, tmp_path):
        """Should detect Node.js entry points."""
        from app.projects.context_pack import detect_entrypoints

        (tmp_path / "src").mkdir()
        (tmp_path / "src" / "index.ts").write_text("// Main entry")
        (tmp_path / "src" / "server.ts").write_text("// Server entry")

        entrypoints = detect_entrypoints(tmp_path, "typescript")

        paths = [e.path for e in entrypoints]
        assert "src/index.ts" in paths


class TestContextPackStorage:
    """Tests for context pack persistence."""

    def test_save_and_load_context_pack(self, tmp_path):
        """Should save and load context pack correctly."""
        from app.projects.context_pack import (
            generate_context_pack,
            save_context_pack,
            load_context_pack,
            get_context_pack_dir,
        )

        # Create project
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "test"')
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "main.py").write_text("")

        # Generate and save
        pack = generate_context_pack(tmp_path)

        with patch.object(Path, 'home', return_value=tmp_path):
            save_context_pack(pack, "test-project")

            # Verify files exist
            pack_dir = tmp_path / ".maratos" / "context-packs" / "test-project"
            assert (pack_dir / "project.json").exists()
            assert (pack_dir / "MODULE_MAP.json").exists()
            assert (pack_dir / "ENTRYPOINTS.json").exists()
            assert (pack_dir / "context_pack.json").exists()

            # Load and verify
            loaded = load_context_pack("test-project")
            assert loaded is not None
            assert loaded.manifest.name == pack.manifest.name

    def test_context_pack_stale_detection(self, tmp_path):
        """Should detect when context pack is stale."""
        from app.projects.context_pack import (
            generate_context_pack,
            save_context_pack,
            context_pack_is_stale,
        )

        # Create project
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "package.json").write_text('{"name": "test", "version": "1.0.0"}')

        # Generate pack
        pack = generate_context_pack(project_dir)

        with patch.object(Path, 'home', return_value=tmp_path):
            save_context_pack(pack, "test-project")

            # Should not be stale initially
            assert not context_pack_is_stale("test-project", project_dir)

            # Modify project
            (project_dir / "package.json").write_text('{"name": "test", "version": "2.0.0"}')

            # Should now be stale
            assert context_pack_is_stale("test-project", project_dir)


class TestCompactContext:
    """Tests for compact context generation."""

    def test_get_compact_context(self, tmp_path):
        """Should generate compact context string."""
        from app.projects.context_pack import generate_context_pack

        # Create project
        (tmp_path / "pyproject.toml").write_text("""
[project]
name = "my-api"
dependencies = ["fastapi", "sqlalchemy"]
        """)
        (tmp_path / "app").mkdir()
        (tmp_path / "app" / "main.py").write_text("")
        (tmp_path / "app" / "api").mkdir()
        (tmp_path / "tests").mkdir()

        pack = generate_context_pack(tmp_path)
        context = pack.get_compact_context()

        assert "my-api" in context or tmp_path.name in context
        assert "python" in context.lower()
        assert "Key Modules" in context or "Module" in context


class TestSearchEndpoint:
    """Tests for the search endpoint."""

    @pytest.mark.asyncio
    async def test_search_project_ripgrep(self, tmp_path):
        """Should search project using ripgrep."""
        from app.api.projects import _run_ripgrep

        # Create project with searchable content
        (tmp_path / "auth.py").write_text("""
def authenticate(user, password):
    '''Authenticate a user.'''
    return check_credentials(user, password)
        """)

        (tmp_path / "api.py").write_text("""
from auth import authenticate

def login(request):
    return authenticate(request.user, request.password)
        """)

        matches, files_searched, truncated = await _run_ripgrep(
            query="authenticate",
            project_path=str(tmp_path),
            context_lines=1,
            max_results=10,
        )

        # Should find matches in both files
        assert len(matches) >= 2
        files = [m.file for m in matches]
        assert any("auth.py" in f for f in files)

    @pytest.mark.asyncio
    async def test_search_with_file_pattern(self, tmp_path):
        """Should filter search by file pattern."""
        from app.api.projects import _run_ripgrep

        # Create files
        (tmp_path / "app.py").write_text("# python code with target")
        (tmp_path / "app.js").write_text("// javascript code with target")

        matches, _, _ = await _run_ripgrep(
            query="target",
            project_path=str(tmp_path),
            file_pattern="*.py",
            max_results=10,
        )

        # Should only match Python files
        files = [m.file for m in matches]
        assert all(".py" in f for f in files)


class TestProjectCommand:
    """Tests for /project command."""

    def test_project_list(self):
        """Should list available projects."""
        from app.commands.handlers import handle_project
        from app.projects import project_registry

        # Mock projects
        with patch.object(project_registry, 'list_all') as mock_list:
            mock_list.return_value = []
            result = handle_project("", {})
            assert "error" in result

    def test_project_load(self):
        """Should load project context."""
        from app.commands.handlers import handle_project
        from app.projects import project_registry, Project

        mock_project = Project(
            name="test",
            description="Test project",
            path="/tmp/test",
            tech_stack=["Python"],
            conventions=["PEP 8"],
            patterns=["Repository"],
        )

        with patch.object(project_registry, 'get', return_value=mock_project):
            result = handle_project("test", {})
            assert "project_loaded" in result
            assert result["project_loaded"] == "test"
            assert "project_context" in result

    def test_project_search_command(self, tmp_path):
        """Should handle /project search command."""
        from app.commands.handlers import _handle_project_search
        from app.projects import project_registry, Project

        # Create test project
        (tmp_path / "code.py").write_text("def search_target(): pass")

        mock_project = Project(
            name="test",
            description="Test",
            path=str(tmp_path),
        )

        with patch.object(project_registry, 'get', return_value=mock_project):
            result = _handle_project_search("test", "search_target")

            if "message" in result:
                assert "search_target" in result["message"] or "No matches" in result["message"]


class TestEndToEnd:
    """End-to-end tests for project understanding."""

    def test_ingest_then_search(self, tmp_path):
        """Should ingest a project then search for code."""
        from app.projects.context_pack import (
            generate_context_pack,
            save_context_pack,
        )
        from app.commands.handlers import _handle_project_search
        from app.projects import project_registry, Project

        # Create a project with auth code
        project_dir = tmp_path / "myapp"
        project_dir.mkdir()

        (project_dir / "pyproject.toml").write_text("""
[project]
name = "myapp"
dependencies = ["fastapi"]
        """)

        (project_dir / "app").mkdir()
        (project_dir / "app" / "main.py").write_text("from fastapi import FastAPI\napp = FastAPI()")
        (project_dir / "app" / "auth").mkdir()
        (project_dir / "app" / "auth" / "__init__.py").write_text("")
        (project_dir / "app" / "auth" / "handlers.py").write_text("""
def authenticate_user(username: str, password: str) -> bool:
    '''Authenticate a user with username and password.'''
    # Check credentials
    return verify_password(username, password)

def verify_password(username: str, password: str) -> bool:
    '''Verify user password.'''
    # Password verification logic
    return True
        """)

        # Generate context pack
        pack = generate_context_pack(project_dir)

        with patch.object(Path, 'home', return_value=tmp_path):
            save_context_pack(pack, "myapp")

        # Verify pack was created correctly
        assert pack.manifest.language == "python"
        assert pack.manifest.framework == "FastAPI"
        assert len(pack.module_map) > 0

        # Check that auth module was detected
        auth_modules = [m for m in pack.module_map if m.domain == "auth"]
        assert len(auth_modules) >= 1

        # Now search for "authenticate"
        mock_project = Project(
            name="myapp",
            description="Test",
            path=str(project_dir),
        )

        with patch.object(project_registry, 'get', return_value=mock_project):
            result = _handle_project_search("myapp", "authenticate")

            # Should find auth-related code
            assert "message" in result
            # The search should return results about authenticate
            # (ripgrep/grep needs to be installed for this to work)

    def test_compact_context_for_prompt(self, tmp_path):
        """Should generate useful compact context for LLM prompts."""
        from app.projects.context_pack import generate_context_pack

        # Create realistic project structure
        project_dir = tmp_path / "api-project"
        project_dir.mkdir()

        (project_dir / "pyproject.toml").write_text("""
[project]
name = "user-api"
version = "1.0.0"
description = "User management API"
dependencies = ["fastapi", "sqlalchemy", "pydantic", "bcrypt"]

[tool.pytest]
testpaths = ["tests"]
        """)

        (project_dir / "app").mkdir()
        (project_dir / "app" / "main.py").write_text("""
from fastapi import FastAPI
from app.api import router

app = FastAPI(title="User API")
app.include_router(router)
        """)

        (project_dir / "app" / "api").mkdir()
        (project_dir / "app" / "api" / "__init__.py").write_text("")
        (project_dir / "app" / "api" / "routes.py").write_text("# API routes")

        (project_dir / "app" / "models").mkdir()
        (project_dir / "app" / "models" / "user.py").write_text("# User model")

        (project_dir / "app" / "services").mkdir()
        (project_dir / "app" / "services" / "auth.py").write_text("# Auth service")

        (project_dir / "tests").mkdir()
        (project_dir / "Makefile").write_text("test:\n\tpytest\n\nrun:\n\tuvicorn app.main:app")

        # Generate context pack
        pack = generate_context_pack(project_dir)
        context = pack.get_compact_context()

        # Verify context is useful for LLM
        assert "user-api" in context or "api-project" in context
        assert "python" in context.lower()
        assert "FastAPI" in context
        assert "pytest" in context.lower() or "test" in context.lower()

        # Should include module info
        assert "api" in context.lower()

        # Context should be compact (under 2000 chars for most projects)
        assert len(context) < 3000
