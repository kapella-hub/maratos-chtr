"""Canvas API endpoints for visual artifact management."""

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import CanvasArtifact, get_db

router = APIRouter(prefix="/canvas")


# Valid artifact types
ARTIFACT_TYPES = ["code", "preview", "form", "chart", "diagram", "table", "diff", "terminal", "markdown", "image"]


class ArtifactCreate(BaseModel):
    """Create a new artifact."""

    artifact_type: str = Field(..., description="Type of artifact")
    title: str = Field(..., max_length=200)
    content: str
    metadata: dict[str, Any] | None = None


class ArtifactUpdate(BaseModel):
    """Update an existing artifact."""

    title: str | None = None
    content: str | None = None
    metadata: dict[str, Any] | None = None


class ArtifactResponse(BaseModel):
    """Artifact response."""

    id: str
    session_id: str
    message_id: str | None
    artifact_type: str
    title: str
    content: str
    metadata: dict[str, Any] | None
    created_at: datetime
    updated_at: datetime


@router.get("/{session_id}", response_model=list[ArtifactResponse])
async def list_artifacts(
    session_id: str,
    artifact_type: str | None = Query(None, description="Filter by type"),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """List all artifacts for a session."""
    query = select(CanvasArtifact).where(CanvasArtifact.session_id == session_id)

    if artifact_type:
        query = query.where(CanvasArtifact.artifact_type == artifact_type)

    query = query.order_by(CanvasArtifact.created_at.asc())

    result = await db.execute(query)
    artifacts = result.scalars().all()

    return [
        {
            "id": a.id,
            "session_id": a.session_id,
            "message_id": a.message_id,
            "artifact_type": a.artifact_type,
            "title": a.title,
            "content": a.content,
            "metadata": a.extra_data,
            "created_at": a.created_at,
            "updated_at": a.updated_at,
        }
        for a in artifacts
    ]


@router.post("/{session_id}", response_model=ArtifactResponse)
async def create_artifact(
    session_id: str,
    artifact: ArtifactCreate,
    message_id: str | None = Query(None, description="Source message ID"),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Create a new artifact in the canvas."""
    if artifact.artifact_type not in ARTIFACT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid artifact type. Must be one of: {', '.join(ARTIFACT_TYPES)}",
        )

    db_artifact = CanvasArtifact(
        id=str(uuid.uuid4()),
        session_id=session_id,
        message_id=message_id,
        artifact_type=artifact.artifact_type,
        title=artifact.title,
        content=artifact.content,
        extra_data=artifact.metadata,
    )

    db.add(db_artifact)
    await db.commit()
    await db.refresh(db_artifact)

    return {
        "id": db_artifact.id,
        "session_id": db_artifact.session_id,
        "message_id": db_artifact.message_id,
        "artifact_type": db_artifact.artifact_type,
        "title": db_artifact.title,
        "content": db_artifact.content,
        "metadata": db_artifact.extra_data,
        "created_at": db_artifact.created_at,
        "updated_at": db_artifact.updated_at,
    }


@router.get("/{session_id}/{artifact_id}", response_model=ArtifactResponse)
async def get_artifact(
    session_id: str,
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get a specific artifact."""
    result = await db.execute(
        select(CanvasArtifact)
        .where(CanvasArtifact.id == artifact_id)
        .where(CanvasArtifact.session_id == session_id)
    )
    artifact = result.scalar_one_or_none()

    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    return {
        "id": artifact.id,
        "session_id": artifact.session_id,
        "message_id": artifact.message_id,
        "artifact_type": artifact.artifact_type,
        "title": artifact.title,
        "content": artifact.content,
        "metadata": artifact.extra_data,
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }


@router.patch("/{session_id}/{artifact_id}", response_model=ArtifactResponse)
async def update_artifact(
    session_id: str,
    artifact_id: str,
    updates: ArtifactUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Update an existing artifact."""
    result = await db.execute(
        select(CanvasArtifact)
        .where(CanvasArtifact.id == artifact_id)
        .where(CanvasArtifact.session_id == session_id)
    )
    artifact = result.scalar_one_or_none()

    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    if updates.title is not None:
        artifact.title = updates.title
    if updates.content is not None:
        artifact.content = updates.content
    if updates.metadata is not None:
        # Merge metadata
        existing = artifact.extra_data or {}
        existing.update(updates.metadata)
        artifact.extra_data = existing

    await db.commit()
    await db.refresh(artifact)

    return {
        "id": artifact.id,
        "session_id": artifact.session_id,
        "message_id": artifact.message_id,
        "artifact_type": artifact.artifact_type,
        "title": artifact.title,
        "content": artifact.content,
        "metadata": artifact.extra_data,
        "created_at": artifact.created_at,
        "updated_at": artifact.updated_at,
    }


@router.delete("/{session_id}/{artifact_id}")
async def delete_artifact(
    session_id: str,
    artifact_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Delete an artifact."""
    result = await db.execute(
        select(CanvasArtifact)
        .where(CanvasArtifact.id == artifact_id)
        .where(CanvasArtifact.session_id == session_id)
    )
    artifact = result.scalar_one_or_none()

    if not artifact:
        raise HTTPException(status_code=404, detail="Artifact not found")

    await db.delete(artifact)
    await db.commit()

    return {"status": "deleted", "id": artifact_id}
