"""Session API endpoints for cross-session communication."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import Session, Message, get_db

router = APIRouter(prefix="/sessions")


class SessionSummary(BaseModel):
    """Session summary response."""

    id: str
    title: str | None
    agent_id: str
    message_count: int
    preview: str | None
    updated_at: datetime


class MessageMatch(BaseModel):
    """Search result match."""

    message_id: str
    role: str
    content: str
    created_at: datetime


class SearchResult(BaseModel):
    """Search result for a session."""

    session_id: str
    title: str | None
    agent_id: str
    matches: list[MessageMatch]


class SessionContext(BaseModel):
    """Summarized session context."""

    session_id: str
    title: str | None
    agent_id: str
    message_count: int
    user_message_count: int
    created_at: datetime
    updated_at: datetime
    initial_request: str | None
    latest_request: str | None
    mentioned_files: list[str]


@router.get("/search", response_model=list[SearchResult])
async def search_sessions(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=50),
    exclude_session: str | None = Query(None, description="Session ID to exclude"),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Search for messages across all sessions."""
    search_pattern = f"%{q}%"

    # Build query
    query = (
        select(Message, Session)
        .join(Session, Message.session_id == Session.id)
        .where(Message.content.ilike(search_pattern))
        .order_by(Message.created_at.desc())
        .limit(limit * 3)  # Get more to group by session
    )

    if exclude_session:
        query = query.where(Session.id != exclude_session)

    result = await db.execute(query)
    rows = result.all()

    # Group by session
    sessions_map: dict[str, dict] = {}
    for msg, session in rows:
        if session.id not in sessions_map:
            sessions_map[session.id] = {
                "session_id": session.id,
                "title": session.title,
                "agent_id": session.agent_id,
                "matches": [],
            }
        if len(sessions_map[session.id]["matches"]) < 3:  # Max 3 matches per session
            sessions_map[session.id]["matches"].append({
                "message_id": msg.id,
                "role": msg.role,
                "content": msg.content[:300] + "..." if len(msg.content) > 300 else msg.content,
                "created_at": msg.created_at,
            })

    return list(sessions_map.values())[:limit]


@router.get("/{session_id}/context", response_model=SessionContext)
async def get_session_context(
    session_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    """Get summarized context from a session."""
    import re

    # Get session
    session_result = await db.execute(
        select(Session).where(Session.id == session_id)
    )
    session = session_result.scalar_one_or_none()

    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get messages
    messages_result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at.asc())
    )
    messages = messages_result.scalars().all()

    user_messages = [m for m in messages if m.role == "user"]

    # Extract mentioned file paths
    file_pattern = r'(?:/[\w.-]+)+(?:\.\w+)?'
    all_content = " ".join(m.content for m in messages)
    mentioned_files = list(set(re.findall(file_pattern, all_content)))[:10]

    # Get first and last user messages
    first_request = user_messages[0].content[:300] if user_messages else None
    last_request = (
        user_messages[-1].content[:300]
        if len(user_messages) > 1
        else None
    )

    return {
        "session_id": session.id,
        "title": session.title,
        "agent_id": session.agent_id,
        "message_count": len(messages),
        "user_message_count": len(user_messages),
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "initial_request": first_request,
        "latest_request": last_request if last_request != first_request else None,
        "mentioned_files": mentioned_files,
    }


@router.get("/recent", response_model=list[SessionSummary])
async def get_recent_sessions(
    limit: int = Query(20, ge=1, le=100),
    agent_id: str | None = Query(None, description="Filter by agent"),
    exclude_session: str | None = Query(None, description="Session ID to exclude"),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Get recent sessions with previews."""
    query = select(Session).order_by(Session.updated_at.desc())

    if agent_id:
        query = query.where(Session.agent_id == agent_id)
    if exclude_session:
        query = query.where(Session.id != exclude_session)

    query = query.limit(limit)

    result = await db.execute(query)
    sessions = result.scalars().all()

    session_data = []
    for session in sessions:
        # Get message count
        count_result = await db.execute(
            select(func.count(Message.id)).where(Message.session_id == session.id)
        )
        message_count = count_result.scalar() or 0

        # Get first user message as preview
        preview_result = await db.execute(
            select(Message.content)
            .where(Message.session_id == session.id)
            .where(Message.role == "user")
            .order_by(Message.created_at.asc())
            .limit(1)
        )
        preview = preview_result.scalar()
        if preview:
            preview = preview[:100] + "..." if len(preview) > 100 else preview

        session_data.append({
            "id": session.id,
            "title": session.title,
            "agent_id": session.agent_id,
            "message_count": message_count,
            "preview": preview,
            "updated_at": session.updated_at,
        })

    return session_data
