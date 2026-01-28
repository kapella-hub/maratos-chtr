"""Project generator using deterministic templates.

Generates projects from Jinja2 templates with no LLM involvement for boilerplate.
"""

import logging
import time
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from app.skills.generators.config import (
    AppFactoryConfig,
    BackendStack,
    FrontendStack,
)
from app.skills.generators.manifest import (
    ArtifactManifest,
    CommandExecution,
    FileArtifact,
    ValidationResult,
    compute_config_hash,
)
from app.skills.generators.verification import (
    get_default_gates,
    run_command,
    run_verification_gates,
)

logger = logging.getLogger(__name__)

# Template directory
TEMPLATE_DIR = Path(__file__).parent / "templates"


class ProjectGenerator:
    """Deterministic project generator using Jinja2 templates.

    Generates identical output for identical input (except timestamps).
    No LLM calls for boilerplate - only templates.
    """

    def __init__(self, config: AppFactoryConfig) -> None:
        self.config = config
        self.manifest: ArtifactManifest | None = None
        self._env: Environment | None = None

    @property
    def env(self) -> Environment:
        """Get or create Jinja2 environment."""
        if self._env is None:
            self._env = Environment(
                loader=FileSystemLoader(str(TEMPLATE_DIR)),
                autoescape=select_autoescape(["html", "xml"]),
                trim_blocks=True,
                lstrip_blocks=True,
                keep_trailing_newline=True,
            )
        return self._env

    async def generate(
        self,
        run_verification: bool = True,
        install_deps: bool = True,
    ) -> ArtifactManifest:
        """Generate the complete project.

        Args:
            run_verification: Whether to run verification gates after generation
            install_deps: Whether to install dependencies (npm install, etc.)

        Returns:
            ArtifactManifest with all generated files and validation results
        """
        start_time = time.time()

        # Initialize manifest
        self.manifest = ArtifactManifest(
            project_name=self.config.name,
            project_path=str(self.config.project_path),
            config_hash=compute_config_hash(self.config.to_dict()),
        )

        try:
            # Create project directory
            self.config.project_path.mkdir(parents=True, exist_ok=True)

            # Generate based on stack
            if self.config.has_backend:
                await self._generate_backend()

            if self.config.has_frontend:
                await self._generate_frontend()

            # Generate shared files
            await self._generate_shared()

            # Install dependencies
            if install_deps:
                await self._install_dependencies()

            # Run verification gates
            if run_verification:
                await self._run_verification()

            # Calculate generation time
            self.manifest.generation_time_ms = (time.time() - start_time) * 1000

            # Save artifact manifest (ARTIFACTS.json per requirements)
            manifest_path = self.config.project_path / "ARTIFACTS.json"
            self.manifest.save(manifest_path)
            self._add_file_to_manifest(manifest_path, "artifacts.json", "generated")

            # Generate validation report (VALIDATION.md per requirements)
            report_path = self.config.project_path / "VALIDATION.md"
            report_path.write_text(self.manifest.generate_validation_markdown())
            self._add_file_to_manifest(report_path, None, "generated")

            logger.info(
                f"Project generated: {self.config.name} "
                f"({self.manifest.total_files} files, "
                f"{self.manifest.generation_time_ms:.0f}ms)"
            )

            return self.manifest

        except Exception as e:
            logger.error(f"Project generation failed: {e}", exc_info=True)
            if self.manifest:
                self.manifest.add_validation(
                    ValidationResult(
                        name="generation",
                        passed=False,
                        message=f"Generation failed: {str(e)}",
                    )
                )
            raise

    async def _generate_backend(self) -> None:
        """Generate backend files."""
        logger.info("Generating backend...")

        if self.config.backend_stack == BackendStack.FASTAPI:
            await self._generate_fastapi_backend()
        elif self.config.backend_stack == BackendStack.EXPRESS:
            await self._generate_express_backend()

    async def _generate_fastapi_backend(self) -> None:
        """Generate FastAPI backend structure."""
        backend_path = self.config.backend_path
        backend_path.mkdir(parents=True, exist_ok=True)

        ctx = self.config.to_template_context()

        # Core files
        templates = [
            ("fastapi/pyproject.toml.j2", "pyproject.toml"),
            ("fastapi/app/__init__.py.j2", "app/__init__.py"),
            ("fastapi/app/main.py.j2", "app/main.py"),
            ("fastapi/app/config.py.j2", "app/config.py"),
        ]

        # Database files
        if self.config.has_database:
            templates.extend([
                ("fastapi/app/database.py.j2", "app/database.py"),
                ("fastapi/app/models.py.j2", "app/models.py"),
            ])

        # Auth files
        if self.config.auth_mode.value != "none":
            templates.extend([
                ("fastapi/app/auth.py.j2", "app/auth.py"),
            ])

        # API routes
        templates.extend([
            ("fastapi/app/api/__init__.py.j2", "app/api/__init__.py"),
            ("fastapi/app/api/health.py.j2", "app/api/health.py"),
        ])

        # Tests
        if self.config.include_tests:
            templates.extend([
                ("fastapi/tests/__init__.py.j2", "tests/__init__.py"),
                ("fastapi/tests/conftest.py.j2", "tests/conftest.py"),
                ("fastapi/tests/test_health.py.j2", "tests/test_health.py"),
            ])

        # Dockerfile
        if self.config.dockerize:
            templates.append(("fastapi/Dockerfile.j2", "Dockerfile"))

        # Render all templates
        for template_name, output_path in templates:
            await self._render_template(template_name, backend_path / output_path, ctx)

        # Create empty __init__.py files for packages
        for pkg_path in ["app/api"]:
            init_file = backend_path / pkg_path / "__init__.py"
            if not init_file.exists():
                init_file.parent.mkdir(parents=True, exist_ok=True)
                init_file.write_text("")
                self._add_file_to_manifest(init_file, None, "generated")

    async def _generate_express_backend(self) -> None:
        """Generate Express.js backend structure."""
        # Placeholder for Express backend
        logger.warning("Express backend generation not yet implemented")

    async def _generate_frontend(self) -> None:
        """Generate frontend files."""
        logger.info("Generating frontend...")

        if self.config.frontend_stack == FrontendStack.REACT:
            await self._generate_react_frontend()
        elif self.config.frontend_stack == FrontendStack.VUE:
            await self._generate_vue_frontend()

    async def _generate_react_frontend(self) -> None:
        """Generate React/TypeScript/Vite frontend."""
        frontend_path = self.config.frontend_path
        frontend_path.mkdir(parents=True, exist_ok=True)

        ctx = self.config.to_template_context()

        # Core files
        templates = [
            ("react/package.json.j2", "package.json"),
            ("react/tsconfig.json.j2", "tsconfig.json"),
            ("react/tsconfig.node.json.j2", "tsconfig.node.json"),
            ("react/vite.config.ts.j2", "vite.config.ts"),
            ("react/index.html.j2", "index.html"),
            ("react/src/main.tsx.j2", "src/main.tsx"),
            ("react/src/App.tsx.j2", "src/App.tsx"),
            ("react/src/index.css.j2", "src/index.css"),
            ("react/src/vite-env.d.ts.j2", "src/vite-env.d.ts"),
        ]

        # Tailwind config
        if self.config.use_tailwind:
            templates.extend([
                ("react/tailwind.config.js.j2", "tailwind.config.js"),
                ("react/postcss.config.js.j2", "postcss.config.js"),
            ])

        # Router setup
        if self.config.use_react_router:
            templates.extend([
                ("react/src/routes.tsx.j2", "src/routes.tsx"),
            ])

        # State management
        if self.config.use_zustand:
            templates.extend([
                ("react/src/stores/index.ts.j2", "src/stores/index.ts"),
            ])

        # Components
        templates.extend([
            ("react/src/components/Layout.tsx.j2", "src/components/Layout.tsx"),
        ])

        # Dockerfile
        if self.config.dockerize:
            templates.append(("react/Dockerfile.j2", "Dockerfile"))

        # ESLint config
        templates.append(("react/eslint.config.js.j2", "eslint.config.js"))

        # Render all templates
        for template_name, output_path in templates:
            await self._render_template(template_name, frontend_path / output_path, ctx)

    async def _generate_vue_frontend(self) -> None:
        """Generate Vue.js frontend structure."""
        # Placeholder for Vue frontend
        logger.warning("Vue frontend generation not yet implemented")

    async def _generate_shared(self) -> None:
        """Generate shared project files."""
        logger.info("Generating shared files...")

        ctx = self.config.to_template_context()
        project_path = self.config.project_path

        templates = [
            ("shared/README.md.j2", "README.md"),
            ("shared/.gitignore.j2", ".gitignore"),
        ]

        # Docker compose
        if self.config.dockerize:
            templates.append(("shared/docker-compose.yaml.j2", "docker-compose.yaml"))

        # Makefile
        if self.config.include_makefile:
            templates.append(("shared/Makefile.j2", "Makefile"))

        # CI/CD
        if self.config.ci_provider.value == "github":
            templates.append(("shared/.github/workflows/ci.yaml.j2", ".github/workflows/ci.yaml"))
        elif self.config.ci_provider.value == "gitlab":
            templates.append(("shared/.gitlab-ci.yml.j2", ".gitlab-ci.yml"))

        # Pre-commit
        if self.config.include_pre_commit:
            templates.append(("shared/.pre-commit-config.yaml.j2", ".pre-commit-config.yaml"))

        # Render all templates
        for template_name, output_path in templates:
            await self._render_template(template_name, project_path / output_path, ctx)

    async def _render_template(
        self,
        template_name: str,
        output_path: Path,
        context: dict[str, Any],
    ) -> None:
        """Render a single template to a file."""
        try:
            template = self.env.get_template(template_name)
            content = template.render(**context)

            # Ensure parent directory exists
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Write file
            output_path.write_text(content)

            # Track in manifest
            self._add_file_to_manifest(output_path, template_name, "generated")

            logger.debug(f"Generated: {output_path}")

        except Exception as e:
            logger.error(f"Failed to render template {template_name}: {e}")
            raise

    def _add_file_to_manifest(
        self,
        file_path: Path,
        template_source: str | None,
        category: str,
    ) -> None:
        """Add a file to the manifest."""
        if self.manifest:
            artifact = FileArtifact.from_file(
                file_path,
                self.config.project_path,
                template_source,
                category,
            )
            self.manifest.add_file(artifact)

    async def _install_dependencies(self) -> None:
        """Install project dependencies."""
        logger.info("Installing dependencies...")

        # Backend dependencies
        if self.config.has_backend:
            backend_path = self.config.backend_path
            if (backend_path / "pyproject.toml").exists():
                exit_code, stdout, stderr = await run_command(
                    "pip install -e . --quiet",
                    backend_path,
                    timeout_seconds=300,
                )
                if self.manifest:
                    self.manifest.add_command(
                        CommandExecution(
                            command="pip install -e .",
                            working_dir=str(backend_path),
                            exit_code=exit_code,
                            stdout=stdout,
                            stderr=stderr,
                        )
                    )

        # Frontend dependencies
        if self.config.has_frontend:
            frontend_path = self.config.frontend_path
            if (frontend_path / "package.json").exists():
                exit_code, stdout, stderr = await run_command(
                    "npm install --legacy-peer-deps",
                    frontend_path,
                    timeout_seconds=300,
                )
                if self.manifest:
                    self.manifest.add_command(
                        CommandExecution(
                            command="npm install",
                            working_dir=str(frontend_path),
                            exit_code=exit_code,
                            stdout=stdout,
                            stderr=stderr,
                        )
                    )

    async def _run_verification(self) -> None:
        """Run verification gates."""
        logger.info("Running verification gates...")

        gates = get_default_gates(self.config)
        results = await run_verification_gates(gates, self.config.project_path)

        # Add results to manifest
        if self.manifest:
            for result in results:
                self.manifest.add_validation(
                    ValidationResult(
                        name=result.gate_name,
                        passed=result.passed,
                        message=result.message,
                        details={
                            "output": result.output[:500] if result.output else "",
                            "error": result.error[:500] if result.error else "",
                            "duration_ms": result.duration_ms,
                        },
                    )
                )

        # Log summary
        passed = sum(1 for r in results if r.passed)
        failed = sum(1 for r in results if not r.passed and r.required)
        warnings = sum(1 for r in results if not r.passed and not r.required)

        logger.info(
            f"Verification complete: {passed} passed, {failed} failed, {warnings} warnings"
        )


async def generate_project(
    config: AppFactoryConfig,
    run_verification: bool = True,
    install_deps: bool = True,
) -> ArtifactManifest:
    """Convenience function to generate a project.

    Args:
        config: Project configuration
        run_verification: Whether to run verification gates
        install_deps: Whether to install dependencies

    Returns:
        ArtifactManifest with generation results
    """
    generator = ProjectGenerator(config)
    return await generator.generate(
        run_verification=run_verification,
        install_deps=install_deps,
    )
