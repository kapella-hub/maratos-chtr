"""System status and health check endpoints."""

import os
import resource
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db, Session as DBSession, SubagentTaskRecord
from app.subagents.manager import subagent_manager

router = APIRouter()

@router.get("/status")
async def get_system_status(db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Get system health status and active task metrics."""
    
    # Memory usage (RSS)
    usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    # MacOS returns bytes, Linux returns KB
    # Just normalize to MB roughly for display
    memory_mb = usage / 1024 / 1024 if os.uname().sysname == "Darwin" else usage / 1024

    # Active sessions (updated in last hour)
    # We can't easily query "active" without a proper heartbeat from frontend,
    # but we can count recent updates.
    # For now, just count total for simplicity or check DB.
    # Let's count sessions created/updated today.
    
    # Count sessions
    # Note: select(func.count()) is better but let's keep it simple
    result = await db.execute(select(func.count()).select_from(DBSession))
    total_sessions = result.scalar() or 0

    # Subagent stats from manager (in-memory state)
    running_tasks = subagent_manager.get_running_tasks()
    
    return {
        "status": "healthy",
        "memory_mb": round(memory_mb, 2),
        "total_sessions": total_sessions,
        "running_subagents": len(running_tasks),
        "subagent_tasks": [
            {
                "id": t.id,
                "agent": t.agent_id,
                "description": t.description[:50],
                "duration_seconds": (
                    (t.started_at - t.created_at).total_seconds() 
                    if t.started_at else 0
                )
            }
            for t in running_tasks
        ]
    }
