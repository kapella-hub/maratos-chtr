"""API routes for Clawd Studio."""

from fastapi import APIRouter

from app.api.agents import router as agents_router
from app.api.chat import router as chat_router
from app.api.config import router as config_router

api_router = APIRouter(prefix="/api")
api_router.include_router(chat_router, tags=["chat"])
api_router.include_router(agents_router, tags=["agents"])
api_router.include_router(config_router, tags=["config"])

__all__ = ["api_router"]
