"""Project documentation API endpoints."""

import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.projects import project_registry, generate_context_pack, save_context_pack
from app.projects.docs_store import (
    create_doc,
    delete_doc,
    get_doc,
    list_docs,
    update_doc,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class DocCreate(BaseModel):
    """Request body for creating a doc."""
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)


class DocUpdate(BaseModel):
    """Request body for updating a doc."""
    title: str | None = Field(default=None, max_length=200)
    content: str | None = None
    tags: list[str] | None = None


class DocResponse(BaseModel):
    """Full doc response with content."""
    id: str
    title: str
    content: str
    tags: list[str]
    created_at: str
    updated_at: str


class DocListItem(BaseModel):
    """Doc list item (metadata only)."""
    id: str
    title: str
    tags: list[str]
    created_at: str
    updated_at: str
    content_length: int


def _regenerate_context_pack(project_name: str) -> None:
    """Regenerate context pack for a project after doc changes."""
    project = project_registry.get(project_name)
    if not project:
        return

    try:
        pack = generate_context_pack(project.path, project_name=project_name)
        save_context_pack(pack, project_name)
        logger.info(f"Regenerated context pack for {project_name} after doc change")
    except Exception as e:
        logger.warning(f"Failed to regenerate context pack for {project_name}: {e}")


@router.get("/{name}/docs", response_model=list[DocListItem])
async def list_project_docs(name: str) -> list[DocListItem]:
    """List all docs for a project.

    Returns metadata only (no content) sorted by most recently updated.
    """
    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    docs = list_docs(name)
    return [DocListItem(**d) for d in docs]


@router.get("/{name}/docs/{doc_id}", response_model=DocResponse)
async def get_project_doc(name: str, doc_id: str) -> DocResponse:
    """Get a single doc with full content."""
    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    doc = get_doc(name, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail=f"Doc not found: {doc_id}")

    return DocResponse(**doc.to_dict())


@router.post("/{name}/docs", response_model=DocResponse)
async def create_project_doc(name: str, data: DocCreate) -> DocResponse:
    """Create a new doc for a project.

    Automatically regenerates the context pack after creation.
    """
    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    doc = create_doc(
        project_name=name,
        title=data.title,
        content=data.content,
        tags=data.tags,
    )

    # Regenerate context pack
    _regenerate_context_pack(name)

    return DocResponse(**doc.to_dict())


@router.put("/{name}/docs/{doc_id}", response_model=DocResponse)
async def update_project_doc(name: str, doc_id: str, data: DocUpdate) -> DocResponse:
    """Update an existing doc.

    Automatically regenerates the context pack after update.
    """
    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    doc = update_doc(
        project_name=name,
        doc_id=doc_id,
        title=data.title,
        content=data.content,
        tags=data.tags,
    )

    if not doc:
        raise HTTPException(status_code=404, detail=f"Doc not found: {doc_id}")

    # Regenerate context pack
    _regenerate_context_pack(name)

    return DocResponse(**doc.to_dict())


@router.delete("/{name}/docs/{doc_id}")
async def delete_project_doc(name: str, doc_id: str) -> dict[str, str]:
    """Delete a doc.

    Automatically regenerates the context pack after deletion.
    """
    project = project_registry.get(name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project not found: {name}")

    deleted = delete_doc(name, doc_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Doc not found: {doc_id}")

    # Regenerate context pack
    _regenerate_context_pack(name)

    return {"status": "deleted", "id": doc_id}
