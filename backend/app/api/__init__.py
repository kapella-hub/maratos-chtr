"""API routes for MaratOS."""

from fastapi import APIRouter

from app.api.agents import router as agents_router
from app.api.chat import router as chat_router
from app.api.config import router as config_router
from app.api.skills import router as skills_router
from app.api.memory import router as memory_router
from app.api.subagents import router as subagents_router
from app.api.projects import router as projects_router
from app.api.autonomous import router as autonomous_router
from app.api.workspace import router as workspace_router
from app.api.sessions import router as sessions_router
from app.api.canvas import router as canvas_router

api_router = APIRouter(prefix="/api")
api_router.include_router(chat_router, tags=["chat"])
api_router.include_router(agents_router, tags=["agents"])
api_router.include_router(config_router, tags=["config"])
api_router.include_router(skills_router, tags=["skills"])
api_router.include_router(memory_router, tags=["memory"])
api_router.include_router(subagents_router, tags=["subagents"])
api_router.include_router(projects_router, tags=["projects"])
api_router.include_router(autonomous_router, tags=["autonomous"])
api_router.include_router(workspace_router, tags=["workspace"])
api_router.include_router(sessions_router, tags=["sessions"])
api_router.include_router(canvas_router, tags=["canvas"])

__all__ = ["api_router"]
