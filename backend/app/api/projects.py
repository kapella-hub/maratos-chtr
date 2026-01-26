"""Projects API for managing project profiles."""

from typing import Any
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.projects import project_registry, Project, analyze_project, ProjectAnalysis

router = APIRouter(prefix="/projects")


def _add_to_allowed_dirs(path: str) -> bool:
    """Add a path to allowed write directories.

    Returns True if added, False if already present.
    """
    resolved = Path(path).expanduser().resolve()
    if not resolved.exists() or not resolved.is_dir():
        return False

    current = [d.strip() for d in settings.allowed_write_dirs.split(",") if d.strip()]
    resolved_str = str(resolved)

    if resolved_str not in current:
        current.append(resolved_str)
        settings.allowed_write_dirs = ",".join(current)
        return True
    return False


class ProjectCreate(BaseModel):
    """Request body for creating a project."""
    name: str
    description: str
    path: str
    tech_stack: list[str] = []
    conventions: list[str] = []
    patterns: list[str] = []
    dependencies: list[str] = []
    notes: str = ""
    auto_add_filesystem: bool = True  # Automatically add to allowed dirs


class ProjectResponse(BaseModel):
    """Project response."""
    name: str
    description: str
    path: str
    tech_stack: list[str]
    conventions: list[str]
    patterns: list[str]
    dependencies: list[str]
    notes: str
    filesystem_access: bool = False  # Whether path is in allowed dirs


class AnalyzeRequest(BaseModel):
    """Request to analyze a project path."""
    path: str


class AnalyzeResponse(BaseModel):
    """Analysis results."""
    tech_stack: list[str]
    conventions: list[str]
    patterns: list[str]
    dependencies: list[str]
    description: str
    notes: str


def _has_filesystem_access(path: str) -> bool:
    """Check if a path is in allowed write directories."""
    from app.config import get_allowed_write_dirs

    resolved = Path(path).expanduser().resolve()
    allowed = get_allowed_write_dirs()

    for allowed_dir in allowed:
        try:
            resolved.relative_to(allowed_dir)
            return True
        except ValueError:
            continue
    return False


@router.get("")
async def list_projects() -> list[ProjectResponse]:
    """List all projects."""
    projects = project_registry.list_all()
    return [
        ProjectResponse(
            name=p.name,
            description=p.description,
            path=p.path,
            tech_stack=p.tech_stack,
            conventions=p.conventions,
            patterns=p.patterns,
            dependencies=p.dependencies,
            notes=p.notes,
            filesystem_access=_has_filesystem_access(p.path),
        )
        for p in projects
    ]


@router.post("/analyze")
async def analyze_path(request: AnalyzeRequest) -> AnalyzeResponse:
    """Analyze a project path to detect tech stack, patterns, etc.

    Use this before creating a project to auto-fill fields.
    """
    try:
        analysis = analyze_project(request.path)
        return AnalyzeResponse(
            tech_stack=analysis.tech_stack,
            conventions=analysis.conventions,
            patterns=analysis.patterns,
            dependencies=analysis.dependencies,
            description=analysis.description,
            notes=analysis.notes,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{name}")
async def get_project(name: str) -> ProjectResponse:
    """Get a project by name."""
    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    return ProjectResponse(
        name=project.name,
        description=project.description,
        path=project.path,
        tech_stack=project.tech_stack,
        conventions=project.conventions,
        patterns=project.patterns,
        dependencies=project.dependencies,
        notes=project.notes,
        filesystem_access=_has_filesystem_access(project.path),
    )


@router.post("")
async def create_project(data: ProjectCreate) -> ProjectResponse:
    """Create a new project profile.

    Optionally auto-adds the project path to allowed write directories.
    """
    import yaml

    # Validate name
    name = data.name.lower().strip()
    if not name or not name.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid project name")

    # Check if exists
    if project_registry.get(name):
        raise HTTPException(status_code=409, detail=f"Project already exists: {name}")

    # Validate path exists
    project_path = Path(data.path).expanduser().resolve()
    if not project_path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {data.path}")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {data.path}")

    # Auto-add to filesystem access if requested
    if data.auto_add_filesystem:
        _add_to_allowed_dirs(str(project_path))

    # Create YAML file
    config_dir = Path.home() / ".maratos" / "projects"
    config_dir.mkdir(parents=True, exist_ok=True)

    project_file = config_dir / f"{name}.yaml"

    project_data = {
        "name": name,
        "description": data.description,
        "path": str(project_path),  # Store resolved path
        "tech_stack": data.tech_stack,
        "conventions": data.conventions,
        "patterns": data.patterns,
        "dependencies": data.dependencies,
        "notes": data.notes,
    }

    with open(project_file, "w") as f:
        yaml.dump(project_data, f, default_flow_style=False, allow_unicode=True)

    # Reload registry
    project_registry.reload()

    project = project_registry.get(name)
    return ProjectResponse(
        name=project.name,
        description=project.description,
        path=project.path,
        tech_stack=project.tech_stack,
        conventions=project.conventions,
        patterns=project.patterns,
        dependencies=project.dependencies,
        notes=project.notes,
        filesystem_access=_has_filesystem_access(project.path),
    )


@router.put("/{name}")
async def update_project(name: str, data: ProjectCreate) -> ProjectResponse:
    """Update a project profile."""
    import yaml

    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    # Validate new path if changed
    project_path = Path(data.path).expanduser().resolve()
    if not project_path.exists():
        raise HTTPException(status_code=400, detail=f"Path does not exist: {data.path}")
    if not project_path.is_dir():
        raise HTTPException(status_code=400, detail=f"Path is not a directory: {data.path}")

    # Auto-add to filesystem access if requested
    if data.auto_add_filesystem:
        _add_to_allowed_dirs(str(project_path))

    # Update YAML file
    config_dir = Path.home() / ".maratos" / "projects"
    project_file = config_dir / f"{name}.yaml"

    project_data = {
        "name": name,  # Keep original name
        "description": data.description,
        "path": str(project_path),  # Store resolved path
        "tech_stack": data.tech_stack,
        "conventions": data.conventions,
        "patterns": data.patterns,
        "dependencies": data.dependencies,
        "notes": data.notes,
    }

    with open(project_file, "w") as f:
        yaml.dump(project_data, f, default_flow_style=False, allow_unicode=True)

    # Reload registry
    project_registry.reload()

    project = project_registry.get(name)
    return ProjectResponse(
        name=project.name,
        description=project.description,
        path=project.path,
        tech_stack=project.tech_stack,
        conventions=project.conventions,
        patterns=project.patterns,
        dependencies=project.dependencies,
        notes=project.notes,
        filesystem_access=_has_filesystem_access(project.path),
    )


@router.delete("/{name}")
async def delete_project(name: str) -> dict[str, str]:
    """Delete a project profile."""
    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    # Delete YAML file
    config_dir = Path.home() / ".maratos" / "projects"
    project_file = config_dir / f"{name}.yaml"

    if project_file.exists():
        project_file.unlink()

    # Also try .yml extension
    project_file_yml = config_dir / f"{name}.yml"
    if project_file_yml.exists():
        project_file_yml.unlink()

    # Reload registry
    project_registry.reload()

    return {"status": "deleted", "name": name}
