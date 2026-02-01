"""Diff API endpoints."""

import difflib
import logging
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/diff", tags=["diff"])


class DiffRequest(BaseModel):
    """Diff request model."""
    original: str
    modified: str
    context_lines: int = 3


class DiffResponse(BaseModel):
    """Diff response model."""
    diff_text: str
    added_count: int
    removed_count: int
    is_identical: bool


@router.post("")
async def generate_diff(request: DiffRequest) -> DiffResponse:
    """Generate a unified diff between two strings."""
    original_lines = request.original.splitlines(keepends=True)
    modified_lines = request.modified.splitlines(keepends=True)

    diff = difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile="Original",
        tofile="Modified",
        n=request.context_lines,
    )
    
    diff_text = "".join(diff)
    
    # Calculate stats
    added = sum(1 for line in diff_text.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_text.splitlines() if line.startswith("-") and not line.startswith("---"))
    
    return DiffResponse(
        diff_text=diff_text,
        added_count=added,
        removed_count=removed,
        is_identical=request.original == request.modified,
    )
