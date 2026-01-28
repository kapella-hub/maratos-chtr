"""Structured configuration for app-factory project generation.

Defines all input parameters for deterministic project scaffolding.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any


class BackendStack(str, Enum):
    """Supported backend frameworks."""

    FASTAPI = "fastapi"
    EXPRESS = "express"
    NONE = "none"


class FrontendStack(str, Enum):
    """Supported frontend frameworks."""

    REACT = "react"
    VUE = "vue"
    NONE = "none"


class AuthMode(str, Enum):
    """Authentication modes."""

    NONE = "none"
    JWT = "jwt"
    SESSION = "session"
    OAUTH = "oauth"


class DatabaseType(str, Enum):
    """Supported database types."""

    NONE = "none"
    SQLITE = "sqlite"
    POSTGRES = "postgres"
    MYSQL = "mysql"


class CIProvider(str, Enum):
    """CI/CD providers."""

    NONE = "none"
    GITHUB = "github"
    GITLAB = "gitlab"


class Feature(str, Enum):
    """Available features for structured input."""

    AUTH_JWT = "auth-jwt"
    AUTH_SESSION = "auth-session"
    AUTH_OAUTH = "auth-oauth"
    DATABASE_SQLITE = "database-sqlite"
    DATABASE_POSTGRES = "database-postgres"
    DATABASE_MYSQL = "database-mysql"
    TESTS = "tests"
    DOCS = "docs"
    DOCKER = "docker"
    CI_GITHUB = "ci-github"
    CI_GITLAB = "ci-gitlab"
    MAKEFILE = "makefile"
    PRE_COMMIT = "pre-commit"
    TAILWIND = "tailwind"
    REACT_ROUTER = "react-router"
    ZUSTAND = "zustand"


@dataclass
class AppFactoryConfig:
    """Configuration for app-factory project generation.

    All parameters are explicit - no LLM inference needed.
    Same config always produces identical output (except timestamps).
    """

    # Required parameters
    name: str  # Project name (lowercase, hyphenated)
    workspace_path: Path  # Destination directory

    # Stack selection
    backend_stack: BackendStack = BackendStack.FASTAPI
    frontend_stack: FrontendStack = FrontendStack.REACT

    # Features
    auth_mode: AuthMode = AuthMode.NONE
    database: DatabaseType = DatabaseType.SQLITE

    # Infrastructure
    ci_provider: CIProvider = CIProvider.GITHUB
    dockerize: bool = True

    # Feature toggles
    include_tests: bool = True
    include_docs: bool = True
    include_makefile: bool = True
    include_pre_commit: bool = True
    include_health_endpoint: bool = True

    # Backend-specific
    backend_port: int = 8000
    use_async_db: bool = True
    include_alembic: bool = True

    # Frontend-specific
    frontend_port: int = 5173
    use_tailwind: bool = True
    use_react_router: bool = True
    use_zustand: bool = True

    # Metadata (not affecting output)
    description: str = ""
    author: str = ""
    version: str = "0.1.0"

    # Feature list (alternative to individual toggles)
    # If provided, overrides individual feature flags
    features: list[str] | None = None

    def __post_init__(self) -> None:
        # Apply features list if provided
        if self.features:
            self._apply_features(self.features)
        """Validate configuration."""
        # Normalize name
        self.name = self.name.lower().replace("_", "-").replace(" ", "-")

        # Ensure workspace_path is Path
        if isinstance(self.workspace_path, str):
            self.workspace_path = Path(self.workspace_path)

        # Validate name format
        if not self.name or not self.name[0].isalpha():
            raise ValueError(f"Project name must start with a letter: {self.name}")

        # Validate combinations
        if self.include_alembic and self.database == DatabaseType.NONE:
            self.include_alembic = False

        if self.auth_mode != AuthMode.NONE and self.database == DatabaseType.NONE:
            raise ValueError("Authentication requires a database")

    def _apply_features(self, features: list[str]) -> None:
        """Apply feature list to config flags.

        Features list provides a cleaner API than individual booleans.
        Example: ["auth-jwt", "database-postgres", "docker", "ci-github"]
        """
        feature_set = set(f.lower() for f in features)

        # Auth
        if "auth-jwt" in feature_set:
            self.auth_mode = AuthMode.JWT
        elif "auth-session" in feature_set:
            self.auth_mode = AuthMode.SESSION
        elif "auth-oauth" in feature_set:
            self.auth_mode = AuthMode.OAUTH

        # Database
        if "database-sqlite" in feature_set:
            self.database = DatabaseType.SQLITE
        elif "database-postgres" in feature_set:
            self.database = DatabaseType.POSTGRES
        elif "database-mysql" in feature_set:
            self.database = DatabaseType.MYSQL
        elif "no-database" in feature_set:
            self.database = DatabaseType.NONE

        # CI
        if "ci-github" in feature_set:
            self.ci_provider = CIProvider.GITHUB
        elif "ci-gitlab" in feature_set:
            self.ci_provider = CIProvider.GITLAB
        elif "no-ci" in feature_set:
            self.ci_provider = CIProvider.NONE

        # Boolean features
        self.dockerize = "docker" in feature_set or "dockerize" in feature_set
        self.include_tests = "tests" in feature_set
        self.include_docs = "docs" in feature_set
        self.include_makefile = "makefile" in feature_set
        self.include_pre_commit = "pre-commit" in feature_set
        self.use_tailwind = "tailwind" in feature_set
        self.use_react_router = "react-router" in feature_set
        self.use_zustand = "zustand" in feature_set

    @property
    def project_path(self) -> Path:
        """Full path to the project directory."""
        return self.workspace_path / self.name

    @property
    def backend_path(self) -> Path:
        """Path to backend directory."""
        if self.frontend_stack == FrontendStack.NONE:
            return self.project_path
        return self.project_path / "backend"

    @property
    def frontend_path(self) -> Path:
        """Path to frontend directory."""
        return self.project_path / "frontend"

    @property
    def has_backend(self) -> bool:
        """Whether project includes a backend."""
        return self.backend_stack != BackendStack.NONE

    @property
    def has_frontend(self) -> bool:
        """Whether project includes a frontend."""
        return self.frontend_stack != FrontendStack.NONE

    @property
    def has_database(self) -> bool:
        """Whether project includes a database."""
        return self.database != DatabaseType.NONE

    @property
    def is_fullstack(self) -> bool:
        """Whether project is full-stack (backend + frontend)."""
        return self.has_backend and self.has_frontend

    def to_template_context(self) -> dict[str, Any]:
        """Convert config to template context dictionary."""
        return {
            # Core
            "name": self.name,
            "project_name": self.name,
            "description": self.description or f"{self.name} - Generated by App Factory",
            "author": self.author,
            "version": self.version,
            # Stacks
            "backend_stack": self.backend_stack.value,
            "frontend_stack": self.frontend_stack.value,
            "has_backend": self.has_backend,
            "has_frontend": self.has_frontend,
            "is_fullstack": self.is_fullstack,
            # Features
            "auth_mode": self.auth_mode.value,
            "has_auth": self.auth_mode != AuthMode.NONE,
            "database": self.database.value,
            "has_database": self.has_database,
            "ci_provider": self.ci_provider.value,
            "has_ci": self.ci_provider != CIProvider.NONE,
            "dockerize": self.dockerize,
            # Toggles
            "include_tests": self.include_tests,
            "include_docs": self.include_docs,
            "include_makefile": self.include_makefile,
            "include_pre_commit": self.include_pre_commit,
            "include_health_endpoint": self.include_health_endpoint,
            # Backend
            "backend_port": self.backend_port,
            "use_async_db": self.use_async_db,
            "include_alembic": self.include_alembic,
            # Frontend
            "frontend_port": self.frontend_port,
            "use_tailwind": self.use_tailwind,
            "use_react_router": self.use_react_router,
            "use_zustand": self.use_zustand,
            # Database connection strings
            "db_url": self._get_db_url(),
            "db_async_url": self._get_db_async_url(),
        }

    def _get_db_url(self) -> str:
        """Get sync database URL."""
        if self.database == DatabaseType.SQLITE:
            return "sqlite:///./data.db"
        elif self.database == DatabaseType.POSTGRES:
            return f"postgresql://postgres:postgres@localhost:5432/{self.name}"
        elif self.database == DatabaseType.MYSQL:
            return f"mysql://root:root@localhost:3306/{self.name}"
        return ""

    def _get_db_async_url(self) -> str:
        """Get async database URL."""
        if self.database == DatabaseType.SQLITE:
            return "sqlite+aiosqlite:///./data.db"
        elif self.database == DatabaseType.POSTGRES:
            return f"postgresql+asyncpg://postgres:postgres@localhost:5432/{self.name}"
        elif self.database == DatabaseType.MYSQL:
            return f"mysql+aiomysql://root:root@localhost:3306/{self.name}"
        return ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppFactoryConfig":
        """Create config from dictionary (e.g., from YAML or JSON).

        Supports two input styles:
        1. Individual flags: auth_mode="jwt", include_tests=True, etc.
        2. Features list: features=["auth-jwt", "tests", "docker"]
        """
        # Convert string enums
        if "backend_stack" in data and isinstance(data["backend_stack"], str):
            data["backend_stack"] = BackendStack(data["backend_stack"])
        if "frontend_stack" in data and isinstance(data["frontend_stack"], str):
            data["frontend_stack"] = FrontendStack(data["frontend_stack"])
        if "auth_mode" in data and isinstance(data["auth_mode"], str):
            data["auth_mode"] = AuthMode(data["auth_mode"])
        if "database" in data and isinstance(data["database"], str):
            data["database"] = DatabaseType(data["database"])
        if "ci_provider" in data and isinstance(data["ci_provider"], str):
            data["ci_provider"] = CIProvider(data["ci_provider"])

        # Handle stacks shorthand
        if "stacks" in data:
            stacks = data.pop("stacks")
            if isinstance(stacks, dict):
                if "backend" in stacks:
                    data["backend_stack"] = BackendStack(stacks["backend"])
                if "frontend" in stacks:
                    data["frontend_stack"] = FrontendStack(stacks["frontend"])
            elif isinstance(stacks, list):
                # e.g., ["fastapi", "react"]
                for stack in stacks:
                    if stack in ("fastapi", "express"):
                        data["backend_stack"] = BackendStack(stack)
                    elif stack in ("react", "vue"):
                        data["frontend_stack"] = FrontendStack(stack)

        return cls(**data)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "name": self.name,
            "workspace_path": str(self.workspace_path),
            "backend_stack": self.backend_stack.value,
            "frontend_stack": self.frontend_stack.value,
            "auth_mode": self.auth_mode.value,
            "database": self.database.value,
            "ci_provider": self.ci_provider.value,
            "dockerize": self.dockerize,
            "include_tests": self.include_tests,
            "include_docs": self.include_docs,
            "include_makefile": self.include_makefile,
            "include_pre_commit": self.include_pre_commit,
            "include_health_endpoint": self.include_health_endpoint,
            "backend_port": self.backend_port,
            "use_async_db": self.use_async_db,
            "include_alembic": self.include_alembic,
            "frontend_port": self.frontend_port,
            "use_tailwind": self.use_tailwind,
            "use_react_router": self.use_react_router,
            "use_zustand": self.use_zustand,
            "description": self.description,
            "author": self.author,
            "version": self.version,
        }

    def get_active_features(self) -> list[str]:
        """Get list of active features for display."""
        features = []
        if self.auth_mode != AuthMode.NONE:
            features.append(f"auth-{self.auth_mode.value}")
        if self.database != DatabaseType.NONE:
            features.append(f"database-{self.database.value}")
        if self.ci_provider != CIProvider.NONE:
            features.append(f"ci-{self.ci_provider.value}")
        if self.dockerize:
            features.append("docker")
        if self.include_tests:
            features.append("tests")
        if self.include_docs:
            features.append("docs")
        if self.include_makefile:
            features.append("makefile")
        if self.include_pre_commit:
            features.append("pre-commit")
        if self.use_tailwind:
            features.append("tailwind")
        if self.use_react_router:
            features.append("react-router")
        if self.use_zustand:
            features.append("zustand")
        return features
