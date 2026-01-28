"""Tests for app-factory template-based project generator.

Tests verify:
1. Deterministic output (same config → same files)
2. Config validation
3. Template rendering
4. Manifest generation
5. Verification gates
"""

import asyncio
import shutil
import tempfile
from pathlib import Path

import pytest

from app.skills.generators import (
    AppFactoryConfig,
    BackendStack,
    FrontendStack,
    AuthMode,
    DatabaseType,
    CIProvider,
    ProjectGenerator,
    ArtifactManifest,
)
from app.skills.generators.manifest import compute_config_hash


class TestAppFactoryConfig:
    """Test configuration validation and normalization."""

    def test_basic_config(self):
        """Test basic config creation."""
        config = AppFactoryConfig(
            name="my-project",
            workspace_path=Path("/tmp/test"),
        )
        assert config.name == "my-project"
        assert config.project_path == Path("/tmp/test/my-project")

    def test_name_normalization(self):
        """Test that project names are normalized."""
        config = AppFactoryConfig(
            name="My Project_Name",
            workspace_path=Path("/tmp/test"),
        )
        assert config.name == "my-project-name"

    def test_name_validation(self):
        """Test that invalid names are rejected."""
        with pytest.raises(ValueError):
            AppFactoryConfig(
                name="123invalid",  # Starts with number
                workspace_path=Path("/tmp/test"),
            )

    def test_auth_requires_database(self):
        """Test that auth mode requires a database."""
        with pytest.raises(ValueError):
            AppFactoryConfig(
                name="my-project",
                workspace_path=Path("/tmp/test"),
                auth_mode=AuthMode.JWT,
                database=DatabaseType.NONE,
            )

    def test_alembic_disabled_without_database(self):
        """Test that Alembic is disabled when no database."""
        config = AppFactoryConfig(
            name="my-project",
            workspace_path=Path("/tmp/test"),
            database=DatabaseType.NONE,
            include_alembic=True,  # Should be auto-disabled
        )
        assert config.include_alembic is False

    def test_template_context(self):
        """Test template context generation."""
        config = AppFactoryConfig(
            name="my-project",
            workspace_path=Path("/tmp/test"),
            backend_stack=BackendStack.FASTAPI,
            frontend_stack=FrontendStack.REACT,
            database=DatabaseType.POSTGRES,
        )
        ctx = config.to_template_context()

        assert ctx["name"] == "my-project"
        assert ctx["backend_stack"] == "fastapi"
        assert ctx["frontend_stack"] == "react"
        assert ctx["has_backend"] is True
        assert ctx["has_frontend"] is True
        assert ctx["is_fullstack"] is True
        assert ctx["has_database"] is True
        assert "asyncpg" in ctx["db_async_url"]

    def test_from_dict(self):
        """Test creating config from dictionary."""
        config = AppFactoryConfig.from_dict({
            "name": "test-project",
            "workspace_path": "/tmp/test",
            "backend_stack": "fastapi",
            "frontend_stack": "none",
            "database": "sqlite",
        })
        assert config.name == "test-project"
        assert config.backend_stack == BackendStack.FASTAPI
        assert config.frontend_stack == FrontendStack.NONE
        assert config.database == DatabaseType.SQLITE

    def test_from_dict_with_features_list(self):
        """Test creating config from features list."""
        config = AppFactoryConfig.from_dict({
            "name": "feature-test",
            "workspace_path": "/tmp/test",
            "features": ["auth-jwt", "database-postgres", "docker", "tests", "ci-github"],
        })
        assert config.auth_mode == AuthMode.JWT
        assert config.database == DatabaseType.POSTGRES
        assert config.dockerize is True
        assert config.include_tests is True
        assert config.ci_provider == CIProvider.GITHUB

    def test_from_dict_with_stacks_list(self):
        """Test creating config from stacks list."""
        config = AppFactoryConfig.from_dict({
            "name": "stack-test",
            "workspace_path": "/tmp/test",
            "stacks": ["fastapi", "react"],
        })
        assert config.backend_stack == BackendStack.FASTAPI
        assert config.frontend_stack == FrontendStack.REACT

    def test_from_dict_with_stacks_dict(self):
        """Test creating config from stacks dictionary."""
        config = AppFactoryConfig.from_dict({
            "name": "stack-dict-test",
            "workspace_path": "/tmp/test",
            "stacks": {"backend": "fastapi", "frontend": "react"},
        })
        assert config.backend_stack == BackendStack.FASTAPI
        assert config.frontend_stack == FrontendStack.REACT

    def test_get_active_features(self):
        """Test getting active features list."""
        config = AppFactoryConfig(
            name="feature-list-test",
            workspace_path=Path("/tmp/test"),
            auth_mode=AuthMode.JWT,
            database=DatabaseType.POSTGRES,
            dockerize=True,
            include_tests=True,
        )
        features = config.get_active_features()
        assert "auth-jwt" in features
        assert "database-postgres" in features
        assert "docker" in features
        assert "tests" in features


class TestConfigHash:
    """Test config hash determinism."""

    def test_same_config_same_hash(self):
        """Same config should produce same hash."""
        config1 = AppFactoryConfig(
            name="my-project",
            workspace_path=Path("/tmp/test"),
            backend_stack=BackendStack.FASTAPI,
        )
        config2 = AppFactoryConfig(
            name="my-project",
            workspace_path=Path("/tmp/test"),
            backend_stack=BackendStack.FASTAPI,
        )

        hash1 = compute_config_hash(config1.to_dict())
        hash2 = compute_config_hash(config2.to_dict())

        assert hash1 == hash2

    def test_different_config_different_hash(self):
        """Different config should produce different hash."""
        config1 = AppFactoryConfig(
            name="project-a",
            workspace_path=Path("/tmp/test"),
        )
        config2 = AppFactoryConfig(
            name="project-b",
            workspace_path=Path("/tmp/test"),
        )

        hash1 = compute_config_hash(config1.to_dict())
        hash2 = compute_config_hash(config2.to_dict())

        assert hash1 != hash2


class TestDeterministicGeneration:
    """Test that generation is deterministic."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for tests."""
        workspace = tempfile.mkdtemp()
        yield Path(workspace)
        shutil.rmtree(workspace, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_same_input_same_output(self, temp_workspace):
        """Same input should produce files with same content hashes."""
        # Generate project twice with same config
        manifests = []

        for i in range(2):
            workspace = temp_workspace / f"run{i}"
            workspace.mkdir()

            config = AppFactoryConfig(
                name="test-project",
                workspace_path=workspace,
                backend_stack=BackendStack.FASTAPI,
                frontend_stack=FrontendStack.NONE,
                database=DatabaseType.SQLITE,
                dockerize=False,
                ci_provider=CIProvider.NONE,
                include_pre_commit=False,
            )

            generator = ProjectGenerator(config)
            manifest = await generator.generate(
                run_verification=False,
                install_deps=False,
            )
            manifests.append(manifest)

        # Compare file content hashes (excluding timestamp-dependent files)
        # ARTIFACTS.json and VALIDATION.md contain timestamps so they will differ
        excluded = {"ARTIFACTS.json", "VALIDATION.md", "MANIFEST.json", "BUILD_REPORT.md"}
        files1 = {f.path: f.content_hash for f in manifests[0].files
                  if f.path not in excluded}
        files2 = {f.path: f.content_hash for f in manifests[1].files
                  if f.path not in excluded}

        assert files1.keys() == files2.keys(), "File lists should match"
        for path in files1:
            assert files1[path] == files2[path], f"File {path} content should match"

    @pytest.mark.asyncio
    async def test_fullstack_project_structure(self, temp_workspace):
        """Test that full-stack project has correct structure."""
        config = AppFactoryConfig(
            name="fullstack-app",
            workspace_path=temp_workspace,
            backend_stack=BackendStack.FASTAPI,
            frontend_stack=FrontendStack.REACT,
            database=DatabaseType.SQLITE,
            dockerize=True,
            ci_provider=CIProvider.GITHUB,
        )

        generator = ProjectGenerator(config)
        manifest = await generator.generate(
            run_verification=False,
            install_deps=False,
        )

        file_paths = {f.path for f in manifest.files}

        # Check backend files
        assert "backend/pyproject.toml" in file_paths
        assert "backend/app/main.py" in file_paths
        assert "backend/app/config.py" in file_paths
        assert "backend/app/database.py" in file_paths
        assert "backend/tests/test_health.py" in file_paths
        assert "backend/Dockerfile" in file_paths

        # Check frontend files
        assert "frontend/package.json" in file_paths
        assert "frontend/src/main.tsx" in file_paths
        assert "frontend/src/App.tsx" in file_paths
        assert "frontend/Dockerfile" in file_paths

        # Check shared files
        assert "README.md" in file_paths
        assert ".gitignore" in file_paths
        assert "docker-compose.yaml" in file_paths
        assert "Makefile" in file_paths
        assert ".github/workflows/ci.yaml" in file_paths

    @pytest.mark.asyncio
    async def test_backend_only_project(self, temp_workspace):
        """Test backend-only project structure."""
        config = AppFactoryConfig(
            name="api-only",
            workspace_path=temp_workspace,
            backend_stack=BackendStack.FASTAPI,
            frontend_stack=FrontendStack.NONE,
            database=DatabaseType.NONE,
            dockerize=False,
        )

        generator = ProjectGenerator(config)
        manifest = await generator.generate(
            run_verification=False,
            install_deps=False,
        )

        file_paths = {f.path for f in manifest.files}

        # Backend files should be at root
        assert "pyproject.toml" in file_paths
        assert "app/main.py" in file_paths

        # No frontend files
        assert not any(p.startswith("frontend/") for p in file_paths)

        # No database files
        assert "app/database.py" not in file_paths


class TestManifest:
    """Test artifact manifest functionality."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for tests."""
        workspace = tempfile.mkdtemp()
        yield Path(workspace)
        shutil.rmtree(workspace, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_manifest_saved(self, temp_workspace):
        """Test that manifest is saved to project."""
        config = AppFactoryConfig(
            name="manifest-test",
            workspace_path=temp_workspace,
            backend_stack=BackendStack.FASTAPI,
            frontend_stack=FrontendStack.NONE,
        )

        generator = ProjectGenerator(config)
        await generator.generate(run_verification=False, install_deps=False)

        manifest_path = config.project_path / "ARTIFACTS.json"
        assert manifest_path.exists()

        # Load and verify manifest
        loaded = ArtifactManifest.load(manifest_path)
        assert loaded.project_name == "manifest-test"
        assert loaded.total_files > 0

    @pytest.mark.asyncio
    async def test_validation_report_generated(self, temp_workspace):
        """Test that validation report (VALIDATION.md) is generated."""
        config = AppFactoryConfig(
            name="report-test",
            workspace_path=temp_workspace,
            backend_stack=BackendStack.FASTAPI,
            frontend_stack=FrontendStack.NONE,
        )

        generator = ProjectGenerator(config)
        await generator.generate(run_verification=False, install_deps=False)

        report_path = config.project_path / "VALIDATION.md"
        assert report_path.exists()

        content = report_path.read_text()
        assert "# Validation Report: report-test" in content
        assert "## Summary" in content
        assert "## Generated Artifacts" in content


class TestTemplateContent:
    """Test that generated files have correct content."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for tests."""
        workspace = tempfile.mkdtemp()
        yield Path(workspace)
        shutil.rmtree(workspace, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_fastapi_main_content(self, temp_workspace):
        """Test FastAPI main.py has correct content."""
        config = AppFactoryConfig(
            name="content-test",
            workspace_path=temp_workspace,
            backend_stack=BackendStack.FASTAPI,
            frontend_stack=FrontendStack.NONE,
            database=DatabaseType.SQLITE,
        )

        generator = ProjectGenerator(config)
        await generator.generate(run_verification=False, install_deps=False)

        main_path = config.backend_path / "app" / "main.py"
        content = main_path.read_text()

        assert "FastAPI" in content
        assert "content-test" in content
        assert "init_db" in content  # Database import
        assert "health_router" in content

    @pytest.mark.asyncio
    async def test_react_package_json(self, temp_workspace):
        """Test React package.json has correct dependencies."""
        config = AppFactoryConfig(
            name="react-test",
            workspace_path=temp_workspace,
            backend_stack=BackendStack.FASTAPI,
            frontend_stack=FrontendStack.REACT,
            use_tailwind=True,
            use_react_router=True,
            use_zustand=True,
        )

        generator = ProjectGenerator(config)
        await generator.generate(run_verification=False, install_deps=False)

        package_path = config.frontend_path / "package.json"
        content = package_path.read_text()

        assert '"react"' in content
        assert '"react-router-dom"' in content
        assert '"zustand"' in content
        assert '"tailwindcss"' in content

    @pytest.mark.asyncio
    async def test_docker_compose_services(self, temp_workspace):
        """Test docker-compose.yaml has correct services."""
        config = AppFactoryConfig(
            name="docker-test",
            workspace_path=temp_workspace,
            backend_stack=BackendStack.FASTAPI,
            frontend_stack=FrontendStack.REACT,
            database=DatabaseType.POSTGRES,
            dockerize=True,
        )

        generator = ProjectGenerator(config)
        await generator.generate(run_verification=False, install_deps=False)

        compose_path = config.project_path / "docker-compose.yaml"
        content = compose_path.read_text()

        assert "backend:" in content
        assert "frontend:" in content
        assert "db:" in content
        assert "postgres:" in content


class TestNoWriteOutsideWorkspace:
    """Test that generator doesn't write outside workspace."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for tests."""
        workspace = tempfile.mkdtemp()
        yield Path(workspace)
        shutil.rmtree(workspace, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_all_files_in_workspace(self, temp_workspace):
        """Test all generated files are within workspace."""
        config = AppFactoryConfig(
            name="workspace-test",
            workspace_path=temp_workspace,
            backend_stack=BackendStack.FASTAPI,
            frontend_stack=FrontendStack.REACT,
        )

        generator = ProjectGenerator(config)
        manifest = await generator.generate(run_verification=False, install_deps=False)

        project_path = config.project_path

        for file in manifest.files:
            full_path = project_path / file.path
            # Verify file is actually within project
            assert str(full_path).startswith(str(project_path))
            assert full_path.exists()


class TestConfigIsolation:
    """Test that different configs don't affect each other."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace for tests."""
        workspace = tempfile.mkdtemp()
        yield Path(workspace)
        shutil.rmtree(workspace, ignore_errors=True)

    @pytest.mark.asyncio
    async def test_parallel_generation(self, temp_workspace):
        """Test generating multiple projects in parallel."""
        configs = [
            AppFactoryConfig(
                name=f"project-{i}",
                workspace_path=temp_workspace,
                backend_stack=BackendStack.FASTAPI,
                frontend_stack=FrontendStack.NONE,
            )
            for i in range(3)
        ]

        # Generate all projects concurrently
        generators = [ProjectGenerator(c) for c in configs]
        manifests = await asyncio.gather(*[
            g.generate(run_verification=False, install_deps=False)
            for g in generators
        ])

        # Verify each project is independent
        for i, manifest in enumerate(manifests):
            assert manifest.project_name == f"project-{i}"
            project_path = configs[i].project_path
            main_py = project_path / "app" / "main.py"
            content = main_py.read_text()
            assert f"project-{i}" in content
