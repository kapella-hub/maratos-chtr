"""Projects API for managing project profiles."""

import asyncio
import json
import logging
import subprocess
from typing import Any
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.config import settings
from app.projects import (
    project_registry,
    Project,
    analyze_project,
    ProjectAnalysis,
    generate_context_pack,
    save_context_pack,
    load_context_pack,
    context_pack_exists,
    context_pack_is_stale,
    ContextPack,
)

logger = logging.getLogger(__name__)

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
    analyze_on_save: bool = True  # Auto-generate context pack on create/update


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

    # Auto-generate context pack if enabled
    if data.analyze_on_save:
        try:
            pack = generate_context_pack(str(project_path), project_name=name)
            save_context_pack(pack, name)
            logger.info(f"Generated context pack for project: {name}")
        except Exception as e:
            logger.warning(f"Failed to generate context pack for {name}: {e}")

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

    # Auto-generate context pack if enabled
    if data.analyze_on_save:
        try:
            pack = generate_context_pack(str(project_path), project_name=name)
            save_context_pack(pack, name)
            logger.info(f"Regenerated context pack for project: {name}")
        except Exception as e:
            logger.warning(f"Failed to generate context pack for {name}: {e}")

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


# =============================================================================
# Search Endpoint
# =============================================================================


class SearchMatch(BaseModel):
    """A single search match."""
    file: str
    line_number: int
    content: str
    context_before: list[str] = Field(default_factory=list)
    context_after: list[str] = Field(default_factory=list)


class SearchResult(BaseModel):
    """Search results for a project."""
    query: str
    project_name: str
    project_path: str
    matches: list[SearchMatch]
    total_matches: int
    files_searched: int
    truncated: bool = False  # True if results were limited


class SearchRequest(BaseModel):
    """Search request parameters."""
    query: str = Field(..., min_length=1, description="Search query (regex supported)")
    file_pattern: str = Field(default="", description="File glob pattern (e.g., '*.py')")
    context_lines: int = Field(default=2, ge=0, le=10, description="Lines of context")
    max_results: int = Field(default=50, ge=1, le=200, description="Maximum results")
    case_sensitive: bool = Field(default=False, description="Case sensitive search")


async def _run_ripgrep(
    query: str,
    project_path: str,
    file_pattern: str = "",
    context_lines: int = 2,
    max_results: int = 50,
    case_sensitive: bool = False,
) -> tuple[list[SearchMatch], int, bool]:
    """Run ripgrep search on a project.

    Returns: (matches, files_searched, truncated)
    """
    # Build ripgrep command
    cmd = ["rg", "--json"]

    # Case sensitivity
    if not case_sensitive:
        cmd.append("-i")

    # Context lines
    if context_lines > 0:
        cmd.extend(["-C", str(context_lines)])

    # File pattern
    if file_pattern:
        cmd.extend(["-g", file_pattern])

    # Exclude common non-code directories
    cmd.extend([
        "--glob", "!node_modules/**",
        "--glob", "!.git/**",
        "--glob", "!__pycache__/**",
        "--glob", "!*.pyc",
        "--glob", "!.venv/**",
        "--glob", "!venv/**",
        "--glob", "!dist/**",
        "--glob", "!build/**",
        "--glob", "!.next/**",
        "--glob", "!coverage/**",
        "--glob", "!*.min.js",
        "--glob", "!*.map",
        "--glob", "!package-lock.json",
        "--glob", "!yarn.lock",
        "--glob", "!pnpm-lock.yaml",
    ])

    # Max results (ripgrep uses -m for max count per file, we'll limit in post-processing)
    cmd.extend(["--max-count", "20"])  # Limit per file

    # Query and path
    cmd.append(query)
    cmd.append(project_path)

    matches: list[SearchMatch] = []
    files_searched = set()
    truncated = False

    try:
        # Run ripgrep
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)

        # Parse JSON output
        for line in stdout.decode("utf-8", errors="replace").strip().split("\n"):
            if not line:
                continue

            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            msg_type = data.get("type")

            if msg_type == "match":
                match_data = data.get("data", {})
                path_data = match_data.get("path", {})
                file_path = path_data.get("text", "")

                # Make path relative
                if file_path.startswith(project_path):
                    file_path = file_path[len(project_path):].lstrip("/")

                files_searched.add(file_path)

                line_number = match_data.get("line_number", 0)
                lines = match_data.get("lines", {})
                content = lines.get("text", "").rstrip("\n")

                # Get submatches for highlighting (optional)
                submatches = match_data.get("submatches", [])

                matches.append(SearchMatch(
                    file=file_path,
                    line_number=line_number,
                    content=content,
                    context_before=[],  # Filled from context messages
                    context_after=[],
                ))

                if len(matches) >= max_results:
                    truncated = True
                    break

            elif msg_type == "context":
                # Context lines around matches
                if matches:
                    context_data = data.get("data", {})
                    lines = context_data.get("lines", {})
                    context_text = lines.get("text", "").rstrip("\n")
                    line_num = context_data.get("line_number", 0)

                    # Determine if before or after the last match
                    last_match = matches[-1]
                    if line_num < last_match.line_number:
                        last_match.context_before.append(context_text)
                    else:
                        last_match.context_after.append(context_text)

            elif msg_type == "summary":
                # Stats from ripgrep
                stats = data.get("data", {}).get("stats", {})
                files_searched.update([])  # Already tracked above

    except asyncio.TimeoutError:
        logger.warning(f"Ripgrep search timed out for query: {query}")
        truncated = True
    except FileNotFoundError:
        # ripgrep not installed, fall back to grep
        logger.warning("ripgrep not found, falling back to grep")
        return await _run_grep_fallback(
            query, project_path, file_pattern, context_lines, max_results, case_sensitive
        )
    except Exception as e:
        logger.error(f"Search error: {e}")
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")

    return matches, len(files_searched), truncated


async def _run_grep_fallback(
    query: str,
    project_path: str,
    file_pattern: str = "",
    context_lines: int = 2,
    max_results: int = 50,
    case_sensitive: bool = False,
) -> tuple[list[SearchMatch], int, bool]:
    """Fallback to grep if ripgrep is not available."""
    cmd = ["grep", "-rn"]

    if not case_sensitive:
        cmd.append("-i")

    if context_lines > 0:
        cmd.extend(["-C", str(context_lines)])

    # Exclude directories
    cmd.extend([
        "--exclude-dir=node_modules",
        "--exclude-dir=.git",
        "--exclude-dir=__pycache__",
        "--exclude-dir=.venv",
        "--exclude-dir=venv",
    ])

    if file_pattern:
        cmd.extend(["--include", file_pattern])

    cmd.append(query)
    cmd.append(project_path)

    matches: list[SearchMatch] = []
    files_searched = set()
    truncated = False

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30.0)

        for line in stdout.decode("utf-8", errors="replace").strip().split("\n"):
            if not line or line.startswith("--"):
                continue

            # Parse grep output: file:line:content
            parts = line.split(":", 2)
            if len(parts) >= 3:
                file_path = parts[0]
                if file_path.startswith(project_path):
                    file_path = file_path[len(project_path):].lstrip("/")

                files_searched.add(file_path)

                try:
                    line_number = int(parts[1])
                except ValueError:
                    continue

                content = parts[2]

                matches.append(SearchMatch(
                    file=file_path,
                    line_number=line_number,
                    content=content,
                ))

                if len(matches) >= max_results:
                    truncated = True
                    break

    except asyncio.TimeoutError:
        truncated = True
    except Exception as e:
        logger.error(f"Grep search error: {e}")

    return matches, len(files_searched), truncated


@router.post("/{name}/search", response_model=SearchResult)
async def search_project(name: str, request: SearchRequest) -> SearchResult:
    """Search for code in a project using ripgrep.

    Performs fast regex search across project files.
    Returns matches with context lines and file paths.

    Example queries:
    - "def authenticate" - find function definitions
    - "TODO|FIXME" - find todos
    - "import.*auth" - find auth imports
    """
    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    project_path = Path(project.path).expanduser().resolve()
    if not project_path.exists():
        raise HTTPException(status_code=400, detail=f"Project path does not exist: {project.path}")

    matches, files_searched, truncated = await _run_ripgrep(
        query=request.query,
        project_path=str(project_path),
        file_pattern=request.file_pattern,
        context_lines=request.context_lines,
        max_results=request.max_results,
        case_sensitive=request.case_sensitive,
    )

    return SearchResult(
        query=request.query,
        project_name=name,
        project_path=str(project_path),
        matches=matches,
        total_matches=len(matches),
        files_searched=files_searched,
        truncated=truncated,
    )


@router.get("/{name}/search", response_model=SearchResult)
async def search_project_get(
    name: str,
    q: str = Query(..., min_length=1, description="Search query"),
    pattern: str = Query(default="", description="File glob pattern"),
    context: int = Query(default=2, ge=0, le=10, description="Context lines"),
    limit: int = Query(default=50, ge=1, le=200, description="Max results"),
    case_sensitive: bool = Query(default=False, description="Case sensitive"),
) -> SearchResult:
    """Search for code in a project (GET version).

    Simpler alternative to POST endpoint for quick searches.
    """
    request = SearchRequest(
        query=q,
        file_pattern=pattern,
        context_lines=context,
        max_results=limit,
        case_sensitive=case_sensitive,
    )
    return await search_project(name, request)


# =============================================================================
# Context Pack Endpoints
# =============================================================================


class ContextPackResponse(BaseModel):
    """Context pack metadata response."""
    project_name: str
    project_path: str
    language: str
    framework: str
    version: str
    generated_at: str
    content_hash: str
    module_count: int
    entrypoint_count: int
    has_architecture: bool
    is_stale: bool


class IngestRequest(BaseModel):
    """Request to ingest/generate context pack."""
    force: bool = Field(default=False, description="Force regeneration even if fresh")
    generate_architecture: bool = Field(default=False, description="Generate ARCHITECTURE.md")


class IngestResponse(BaseModel):
    """Response from ingestion."""
    project_name: str
    status: str
    pack_path: str
    manifest: dict
    module_count: int
    entrypoint_count: int
    was_regenerated: bool


@router.get("/{name}/context-pack", response_model=ContextPackResponse)
async def get_context_pack(name: str) -> ContextPackResponse:
    """Get context pack metadata for a project.

    Returns information about the generated context pack including
    whether it's stale and needs regeneration.
    """
    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    pack = load_context_pack(name)
    if not pack:
        raise HTTPException(status_code=404, detail=f"No context pack for project: {name}. Run ingest first.")

    is_stale = context_pack_is_stale(name, project.path)

    return ContextPackResponse(
        project_name=name,
        project_path=project.path,
        language=pack.manifest.language,
        framework=pack.manifest.framework,
        version=pack.version,
        generated_at=pack.generated_at,
        content_hash=pack.content_hash,
        module_count=len(pack.module_map),
        entrypoint_count=len(pack.entrypoints),
        has_architecture=bool(pack.architecture_md),
        is_stale=is_stale,
    )


@router.post("/{name}/ingest", response_model=IngestResponse)
async def ingest_project(name: str, request: IngestRequest | None = None) -> IngestResponse:
    """Generate or regenerate context pack for a project.

    This analyzes the project and generates:
    - project.json (manifest)
    - MODULE_MAP.json (folder -> domain mapping)
    - ENTRYPOINTS.json (main files)
    - ARCHITECTURE.md (optional, requires LLM)
    """
    request = request or IngestRequest()

    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    project_path = Path(project.path).expanduser().resolve()
    if not project_path.exists():
        raise HTTPException(status_code=400, detail=f"Project path does not exist: {project.path}")

    # Check if we need to regenerate
    was_regenerated = False
    if not request.force and context_pack_exists(name):
        if not context_pack_is_stale(name, project.path):
            pack = load_context_pack(name)
            if pack:
                return IngestResponse(
                    project_name=name,
                    status="fresh",
                    pack_path=str(Path.home() / ".maratos" / "context-packs" / name),
                    manifest=pack.manifest.to_dict(),
                    module_count=len(pack.module_map),
                    entrypoint_count=len(pack.entrypoints),
                    was_regenerated=False,
                )

    # Generate new context pack
    try:
        pack = generate_context_pack(str(project_path), project_name=name)
        pack_path = save_context_pack(pack, name)
        was_regenerated = True
    except Exception as e:
        logger.error(f"Failed to generate context pack: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to generate context pack: {str(e)}")

    return IngestResponse(
        project_name=name,
        status="generated",
        pack_path=str(pack_path),
        manifest=pack.manifest.to_dict(),
        module_count=len(pack.module_map),
        entrypoint_count=len(pack.entrypoints),
        was_regenerated=was_regenerated,
    )


@router.get("/{name}/context", response_model=dict)
async def get_project_context(name: str) -> dict:
    """Get compact context for prompt injection.

    Returns a minimal context string suitable for including in LLM prompts.
    This includes project overview, key modules, and entry points.
    """
    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    pack = load_context_pack(name)
    if not pack:
        # Return basic project context if no pack exists
        return {
            "project_name": name,
            "has_context_pack": False,
            "context": project.get_context(),
        }

    return {
        "project_name": name,
        "has_context_pack": True,
        "context": pack.get_compact_context(),
        "manifest": pack.manifest.to_dict(),
    }
