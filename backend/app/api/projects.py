"""Projects API for managing project profiles."""

from typing import Any
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.projects import project_registry, Project

router = APIRouter(prefix="/projects")


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
        )
        for p in projects
    ]


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
    )


@router.post("")
async def create_project(data: ProjectCreate) -> ProjectResponse:
    """Create a new project profile."""
    import yaml

    # Validate name
    name = data.name.lower().strip()
    if not name or not name.replace("_", "").replace("-", "").isalnum():
        raise HTTPException(status_code=400, detail="Invalid project name")

    # Check if exists
    if project_registry.get(name):
        raise HTTPException(status_code=409, detail=f"Project already exists: {name}")

    # Create YAML file
    config_dir = Path.home() / ".maratos" / "projects"
    config_dir.mkdir(parents=True, exist_ok=True)

    project_file = config_dir / f"{name}.yaml"

    project_data = {
        "name": name,
        "description": data.description,
        "path": data.path,
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
    )


@router.put("/{name}")
async def update_project(name: str, data: ProjectCreate) -> ProjectResponse:
    """Update a project profile."""
    import yaml

    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    # Update YAML file
    config_dir = Path.home() / ".maratos" / "projects"
    project_file = config_dir / f"{name}.yaml"

    project_data = {
        "name": name,  # Keep original name
        "description": data.description,
        "path": data.path,
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
