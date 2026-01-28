"""Template-based project generators for deterministic output.

This module provides deterministic template rendering for project scaffolding,
replacing LLM "freehand" file generation with predictable, testable templates.
"""

from app.skills.generators.config import (
    AppFactoryConfig,
    BackendStack,
    FrontendStack,
    AuthMode,
    DatabaseType,
    CIProvider,
)
from app.skills.generators.generator import ProjectGenerator
from app.skills.generators.manifest import ArtifactManifest, FileArtifact
from app.skills.generators.verification import (
    VerificationGate,
    VerificationResult,
    run_verification_gates,
)

__all__ = [
    # Config
    "AppFactoryConfig",
    "BackendStack",
    "FrontendStack",
    "AuthMode",
    "DatabaseType",
    "CIProvider",
    # Generator
    "ProjectGenerator",
    # Manifest
    "ArtifactManifest",
    "FileArtifact",
    # Verification
    "VerificationGate",
    "VerificationResult",
    "run_verification_gates",
]
