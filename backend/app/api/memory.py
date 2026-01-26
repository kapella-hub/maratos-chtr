"""Memory API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.memory.manager import memory_manager

router = APIRouter(prefix="/memory")


class RememberRequest(BaseModel):
    """Request to store a memory."""
    content: str = Field(min_length=1, max_length=50000)
    memory_type: str = Field(default="fact", min_length=1, max_length=50)
    tags: list[str] | None = None
    importance: float = Field(default=0.5, ge=0.0, le=1.0)


class RecallRequest(BaseModel):
    """Request to recall memories."""
    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(default=10, ge=1, le=100)
    memory_types: list[str] | None = None


@router.get("/stats")
async def get_memory_stats() -> dict[str, Any]:
    """Get memory statistics."""
    return memory_manager.stats()


@router.post("/remember")
async def remember(request: RememberRequest) -> dict[str, Any]:
    """Store a new memory."""
    entry = await memory_manager.remember(
        content=request.content,
        memory_type=request.memory_type,
        tags=request.tags,
        importance=request.importance,
    )
    return entry.to_dict()


@router.post("/recall")
async def recall(request: RecallRequest) -> list[dict[str, Any]]:
    """Recall relevant memories."""
    memories = await memory_manager.recall(
        query=request.query,
        limit=request.limit,
        memory_types=request.memory_types,
    )
    return [m.to_dict() for m in memories]


@router.get("/recent")
async def get_recent(limit: int = Query(default=20, ge=1, le=500)) -> list[dict[str, Any]]:
    """Get recent memories."""
    memories = memory_manager.store.get_recent(limit=limit)
    return [m.to_dict() for m in memories]


@router.get("/important")
async def get_important(
    limit: int = Query(default=20, ge=1, le=500),
    min_importance: float = Query(default=0.7, ge=0.0, le=1.0),
) -> list[dict[str, Any]]:
    """Get important memories."""
    memories = memory_manager.store.get_important(limit=limit, min_importance=min_importance)
    return [m.to_dict() for m in memories]


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str) -> dict[str, str]:
    """Delete a memory."""
    if not memory_manager.store.delete(memory_id):
        raise HTTPException(status_code=404, detail=f"Memory not found: {memory_id}")
    return {"status": "deleted"}


@router.post("/compact")
async def compact_memory(keep_top_n: int = 1000) -> dict[str, int]:
    """Compact memory to save space."""
    removed = memory_manager.compact(keep_top_n=keep_top_n)
    return {"removed": removed}
