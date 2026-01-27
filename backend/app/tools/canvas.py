"""Canvas tools for creating visual artifacts in the workspace."""

import uuid
from typing import Any

from app.database import CanvasArtifact, async_session_factory
from app.tools.base import Tool, ToolParameter, ToolResult, registry
from sqlalchemy import select


# Valid artifact types
ARTIFACT_TYPES = ["code", "preview", "form", "chart", "diagram", "table", "diff", "terminal", "markdown"]


class CanvasTool(Tool):
    """Tool for creating and managing visual artifacts in the canvas workspace.

    Allows agents to create interactive visual elements like:
    - Code blocks with syntax highlighting
    - Live HTML/React previews
    - Interactive forms
    - Charts and data visualizations
    - Diagrams (Mermaid)
    - Data tables
    - Code diffs
    - Terminal output
    """

    def __init__(self) -> None:
        super().__init__(
            id="canvas",
            name="Canvas",
            description="REQUIRED for visual content. Use this tool when users ask for flowcharts, diagrams, mermaid charts, architecture visuals, or any visual/graphical content. Creates interactive artifacts in a side panel. For diagrams, use artifact_type='diagram' with Mermaid syntax in content.",
            parameters=[
                ToolParameter(
                    name="action",
                    type="string",
                    description="Action to perform",
                    enum=["create", "update", "delete", "list"],
                ),
                ToolParameter(
                    name="artifact_type",
                    type="string",
                    description=f"Type of artifact: {', '.join(ARTIFACT_TYPES)}",
                    required=False,
                    enum=ARTIFACT_TYPES,
                ),
                ToolParameter(
                    name="artifact_id",
                    type="string",
                    description="Artifact ID (required for update/delete)",
                    required=False,
                ),
                ToolParameter(
                    name="title",
                    type="string",
                    description="Title for the artifact",
                    required=False,
                ),
                ToolParameter(
                    name="content",
                    type="string",
                    description="Content of the artifact (code, HTML, JSON data, etc.)",
                    required=False,
                ),
                ToolParameter(
                    name="language",
                    type="string",
                    description="Programming language for code artifacts",
                    required=False,
                ),
                ToolParameter(
                    name="editable",
                    type="boolean",
                    description="Whether the artifact should be editable by the user",
                    required=False,
                    default=False,
                ),
            ],
        )
        # Current session ID (set by chat handler)
        self._session_id: str | None = None

    def set_session(self, session_id: str) -> None:
        """Set current session for artifact creation."""
        self._session_id = session_id

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute canvas tool action."""
        action = kwargs.get("action")

        if not self._session_id:
            return ToolResult(
                success=False,
                output="",
                error="No session context. Canvas tools require an active chat session.",
            )

        if action == "create":
            return await self._create_artifact(
                artifact_type=kwargs.get("artifact_type", "code"),
                title=kwargs.get("title", "Untitled"),
                content=kwargs.get("content", ""),
                language=kwargs.get("language"),
                editable=kwargs.get("editable", False),
            )
        elif action == "update":
            artifact_id = kwargs.get("artifact_id")
            if not artifact_id:
                return ToolResult(
                    success=False,
                    output="",
                    error="artifact_id is required for update action",
                )
            return await self._update_artifact(
                artifact_id=artifact_id,
                title=kwargs.get("title"),
                content=kwargs.get("content"),
            )
        elif action == "delete":
            artifact_id = kwargs.get("artifact_id")
            if not artifact_id:
                return ToolResult(
                    success=False,
                    output="",
                    error="artifact_id is required for delete action",
                )
            return await self._delete_artifact(artifact_id=artifact_id)
        elif action == "list":
            return await self._list_artifacts(
                artifact_type=kwargs.get("artifact_type"),
            )
        else:
            return ToolResult(
                success=False,
                output="",
                error=f"Unknown action: {action}. Use: create, update, delete, list",
            )

    async def _create_artifact(
        self,
        artifact_type: str,
        title: str,
        content: str,
        language: str | None = None,
        editable: bool = False,
    ) -> ToolResult:
        """Create a new artifact in the canvas."""
        if artifact_type not in ARTIFACT_TYPES:
            return ToolResult(
                success=False,
                output="",
                error=f"Invalid artifact type. Must be one of: {', '.join(ARTIFACT_TYPES)}",
            )

        metadata = {}
        if language:
            metadata["language"] = language
        if editable:
            metadata["editable"] = True

        async with async_session_factory() as db:
            artifact = CanvasArtifact(
                id=str(uuid.uuid4()),
                session_id=self._session_id,
                artifact_type=artifact_type,
                title=title,
                content=content,
                extra_data=metadata if metadata else None,
            )

            db.add(artifact)
            await db.commit()

            return ToolResult(
                success=True,
                output=f"Created {artifact_type} artifact: {title} (id: {artifact.id[:8]}...)",
                data={
                    "action": "canvas_create",
                    "artifact": {
                        "id": artifact.id,
                        "type": artifact_type,
                        "title": title,
                        "content": content,
                        "metadata": metadata if metadata else None,
                    },
                },
            )

    async def _update_artifact(
        self,
        artifact_id: str,
        title: str | None = None,
        content: str | None = None,
    ) -> ToolResult:
        """Update an existing artifact."""
        async with async_session_factory() as db:
            result = await db.execute(
                select(CanvasArtifact)
                .where(CanvasArtifact.id == artifact_id)
                .where(CanvasArtifact.session_id == self._session_id)
            )
            artifact = result.scalar_one_or_none()

            if not artifact:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Artifact not found: {artifact_id}",
                )

            if title is not None:
                artifact.title = title
            if content is not None:
                artifact.content = content

            await db.commit()

            return ToolResult(
                success=True,
                output=f"Updated artifact: {artifact.title}",
                data={
                    "artifact_id": artifact.id,
                    "action": "canvas_update",
                },
            )

    async def _delete_artifact(self, artifact_id: str) -> ToolResult:
        """Delete an artifact."""
        async with async_session_factory() as db:
            result = await db.execute(
                select(CanvasArtifact)
                .where(CanvasArtifact.id == artifact_id)
                .where(CanvasArtifact.session_id == self._session_id)
            )
            artifact = result.scalar_one_or_none()

            if not artifact:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Artifact not found: {artifact_id}",
                )

            title = artifact.title
            await db.delete(artifact)
            await db.commit()

            return ToolResult(
                success=True,
                output=f"Deleted artifact: {title}",
                data={
                    "artifact_id": artifact_id,
                    "action": "canvas_delete",
                },
            )

    async def _list_artifacts(self, artifact_type: str | None = None) -> ToolResult:
        """List artifacts in the current session."""
        async with async_session_factory() as db:
            query = select(CanvasArtifact).where(
                CanvasArtifact.session_id == self._session_id
            )

            if artifact_type:
                query = query.where(CanvasArtifact.artifact_type == artifact_type)

            query = query.order_by(CanvasArtifact.created_at.asc())

            result = await db.execute(query)
            artifacts = result.scalars().all()

            if not artifacts:
                return ToolResult(
                    success=True,
                    output="No artifacts in this session.",
                    data={"artifacts": []},
                )

            output_lines = ["## Canvas Artifacts\n"]
            artifact_data = []

            for a in artifacts:
                preview = a.content[:50] + "..." if len(a.content) > 50 else a.content
                output_lines.append(
                    f"- **{a.title}** ({a.artifact_type}) - `{a.id[:8]}...`\n"
                    f"  {preview}\n"
                )
                artifact_data.append({
                    "id": a.id,
                    "title": a.title,
                    "artifact_type": a.artifact_type,
                })

            return ToolResult(
                success=True,
                output="\n".join(output_lines),
                data={"artifacts": artifact_data},
            )


# Register the tool
canvas_tool = CanvasTool()
registry.register(canvas_tool)
