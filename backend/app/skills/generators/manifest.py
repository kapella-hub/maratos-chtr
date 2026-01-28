"""Artifact manifest for tracking generated files.

Provides deterministic tracking of all files created during project generation.
"""

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass
class FileArtifact:
    """A single generated file artifact."""

    path: str  # Relative path from project root
    size_bytes: int
    content_hash: str  # SHA-256 of content
    template_source: str | None = None  # Template that generated this file
    is_binary: bool = False
    category: str = "generated"  # generated, copied, external

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "content_hash": self.content_hash,
            "template_source": self.template_source,
            "is_binary": self.is_binary,
            "category": self.category,
        }

    @classmethod
    def from_file(
        cls,
        file_path: Path,
        project_root: Path,
        template_source: str | None = None,
        category: str = "generated",
    ) -> "FileArtifact":
        """Create artifact from an existing file."""
        relative_path = str(file_path.relative_to(project_root))
        content = file_path.read_bytes()
        content_hash = hashlib.sha256(content).hexdigest()

        # Detect binary
        is_binary = False
        try:
            content.decode("utf-8")
        except UnicodeDecodeError:
            is_binary = True

        return cls(
            path=relative_path,
            size_bytes=len(content),
            content_hash=content_hash,
            template_source=template_source,
            is_binary=is_binary,
            category=category,
        )


@dataclass
class CommandExecution:
    """Record of a command executed during generation."""

    command: str
    working_dir: str
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "command": self.command,
            "working_dir": self.working_dir,
            "exit_code": self.exit_code,
            "stdout": self.stdout[:1000] if len(self.stdout) > 1000 else self.stdout,
            "stderr": self.stderr[:1000] if len(self.stderr) > 1000 else self.stderr,
            "duration_ms": round(self.duration_ms, 2),
        }


@dataclass
class ValidationResult:
    """Result of a validation check."""

    name: str
    passed: bool
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "passed": self.passed,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class ArtifactManifest:
    """Complete manifest of all artifacts from project generation.

    This manifest provides:
    1. Deterministic tracking of all files created
    2. Content hashes for verification
    3. Command execution log
    4. Validation results
    """

    project_name: str
    project_path: str
    config_hash: str  # Hash of the input config (for reproducibility)
    created_at: datetime = field(default_factory=datetime.utcnow)
    files: list[FileArtifact] = field(default_factory=list)
    commands: list[CommandExecution] = field(default_factory=list)
    validations: list[ValidationResult] = field(default_factory=list)
    generation_time_ms: float = 0.0
    generator_version: str = "1.0.0"

    def add_file(self, artifact: FileArtifact) -> None:
        """Add a file artifact to the manifest."""
        self.files.append(artifact)

    def add_command(self, execution: CommandExecution) -> None:
        """Add a command execution to the manifest."""
        self.commands.append(execution)

    def add_validation(self, result: ValidationResult) -> None:
        """Add a validation result to the manifest."""
        self.validations.append(result)

    @property
    def total_files(self) -> int:
        """Total number of files generated."""
        return len(self.files)

    @property
    def total_size_bytes(self) -> int:
        """Total size of all generated files."""
        return sum(f.size_bytes for f in self.files)

    @property
    def all_validations_passed(self) -> bool:
        """Whether all validations passed."""
        return all(v.passed for v in self.validations)

    @property
    def failed_validations(self) -> list[ValidationResult]:
        """List of failed validations."""
        return [v for v in self.validations if not v.passed]

    def files_by_category(self) -> dict[str, list[FileArtifact]]:
        """Group files by category."""
        result: dict[str, list[FileArtifact]] = {}
        for f in self.files:
            if f.category not in result:
                result[f.category] = []
            result[f.category].append(f)
        return result

    def to_dict(self) -> dict[str, Any]:
        """Convert manifest to dictionary."""
        return {
            "project_name": self.project_name,
            "project_path": self.project_path,
            "config_hash": self.config_hash,
            "created_at": self.created_at.isoformat(),
            "generator_version": self.generator_version,
            "generation_time_ms": round(self.generation_time_ms, 2),
            "summary": {
                "total_files": self.total_files,
                "total_size_bytes": self.total_size_bytes,
                "total_commands": len(self.commands),
                "validations_passed": self.all_validations_passed,
                "failed_validations": len(self.failed_validations),
            },
            "files": [f.to_dict() for f in self.files],
            "commands": [c.to_dict() for c in self.commands],
            "validations": [v.to_dict() for v in self.validations],
        }

    def to_json(self, indent: int = 2) -> str:
        """Convert manifest to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, output_path: Path) -> None:
        """Save manifest to file."""
        output_path.write_text(self.to_json())

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ArtifactManifest":
        """Load manifest from dictionary."""
        manifest = cls(
            project_name=data["project_name"],
            project_path=data["project_path"],
            config_hash=data["config_hash"],
            created_at=datetime.fromisoformat(data["created_at"]),
            generator_version=data.get("generator_version", "1.0.0"),
            generation_time_ms=data.get("generation_time_ms", 0.0),
        )

        for f_data in data.get("files", []):
            manifest.files.append(FileArtifact(**f_data))

        for c_data in data.get("commands", []):
            manifest.commands.append(CommandExecution(**c_data))

        for v_data in data.get("validations", []):
            manifest.validations.append(ValidationResult(**v_data))

        return manifest

    @classmethod
    def load(cls, input_path: Path) -> "ArtifactManifest":
        """Load manifest from file."""
        data = json.loads(input_path.read_text())
        return cls.from_dict(data)

    def generate_report_markdown(self) -> str:
        """Generate a markdown report of the manifest (legacy name)."""
        return self.generate_validation_markdown()

    def generate_validation_markdown(self) -> str:
        """Generate VALIDATION.md report of the manifest."""
        lines = [
            f"# Validation Report: {self.project_name}",
            "",
            "This report validates the deterministic generation of this project.",
            "Same inputs should always produce identical outputs (verified via config hash).",
            "",
            "## Generation Metadata",
            "",
            "| Property | Value |",
            "|----------|-------|",
            f"| **Config Hash** | `{self.config_hash[:16]}...` |",
            f"| **Generated** | {self.created_at.isoformat()} |",
            f"| **Generator Version** | {self.generator_version} |",
            f"| **Generation Time** | {self.generation_time_ms:.0f}ms |",
            "",
            "## Summary",
            "",
            f"- **Total Files:** {self.total_files}",
            f"- **Total Size:** {self._format_size(self.total_size_bytes)}",
            f"- **Commands Run:** {len(self.commands)}",
            f"- **Validations:** {len(self.validations)} "
            f"({'all passed' if self.all_validations_passed else 'some failed'})",
            "",
        ]

        # Validation Results FIRST (this is the focus)
        if self.validations:
            lines.append("## Validation Gates")
            lines.append("")
            passed = sum(1 for v in self.validations if v.passed)
            failed = len(self.validations) - passed
            lines.append(f"**Result:** {passed} passed, {failed} failed")
            lines.append("")
            lines.append("| Gate | Status | Message |")
            lines.append("|------|--------|---------|")
            for v in self.validations:
                status = "PASS" if v.passed else "FAIL"
                lines.append(f"| {v.name} | {status} | {v.message} |")
            lines.append("")

        # Files by category
        lines.append("## Generated Artifacts")
        lines.append("")
        lines.append("All files are tracked with SHA-256 content hashes for verification.")
        lines.append("")
        for category, files in self.files_by_category().items():
            lines.append(f"### {category.title()} ({len(files)} files)")
            lines.append("")
            lines.append("| File | Size | Content Hash |")
            lines.append("|------|------|--------------|")
            for f in sorted(files, key=lambda x: x.path):
                lines.append(
                    f"| `{f.path}` | {self._format_size(f.size_bytes)} | "
                    f"`{f.content_hash[:12]}...` |"
                )
            lines.append("")

        # Commands
        if self.commands:
            lines.append("## Commands Executed")
            lines.append("")
            for i, cmd in enumerate(self.commands, 1):
                status = "OK" if cmd.exit_code == 0 else "FAIL"
                lines.append(f"{i}. [{status}] `{cmd.command}` ({cmd.duration_ms:.0f}ms)")
            lines.append("")

        # Reproducibility note
        lines.append("---")
        lines.append("")
        lines.append("## Reproducibility")
        lines.append("")
        lines.append("To verify this project was generated deterministically:")
        lines.append("")
        lines.append("1. Re-run app-factory with identical inputs")
        lines.append("2. Compare `config_hash` in ARTIFACTS.json")
        lines.append("3. If hashes match, file content hashes should be identical")
        lines.append("")
        lines.append("*Generated by App Factory v2.0*")
        lines.append("")

        return "\n".join(lines)

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        """Format size in human-readable format."""
        for unit in ["B", "KB", "MB", "GB"]:
            if size_bytes < 1024:
                return f"{size_bytes:.1f}{unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f}TB"


def compute_config_hash(config_dict: dict[str, Any]) -> str:
    """Compute a deterministic hash of the config.

    This hash can be used to verify reproducibility:
    same config hash should always produce same output files.
    """
    # Sort keys for determinism
    sorted_json = json.dumps(config_dict, sort_keys=True)
    return hashlib.sha256(sorted_json.encode()).hexdigest()
