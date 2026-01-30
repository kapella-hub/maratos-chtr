"""MaratOS - Main FastAPI application."""

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import api_router
from app.api.channels import router as channels_router
from app.config import settings, get_channel_config
from app.database import init_db
from app.channels.manager import channel_manager, init_channels
from app.skills.loader import load_skills_from_dir
from app.api.models import HealthResponse
from app.logging_config import setup_logging
from app.audit import audit_logger

# Configure logging early
setup_logging(debug=settings.debug, json_logs=not settings.debug)

logger = logging.getLogger(__name__)

# Rate limiter - uses remote address as key
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[settings.rate_limit_default] if settings.rate_limit_enabled else [],
    enabled=settings.rate_limit_enabled,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler with graceful shutdown."""
    # === STARTUP ===
    logger.info("MaratOS starting up...")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Start audit logger
    await audit_logger.start()
    logger.info("Audit logger started")

    # Load skills
    skills_dir = Path(__file__).parent.parent / "skills"
    if skills_dir.exists():
        count = load_skills_from_dir(skills_dir)
        logger.info(f"Loaded {count} skills from {skills_dir}")

    # Also load user skills
    user_skills_dir = Path.home() / ".maratos" / "skills"
    if user_skills_dir.exists():
        count = load_skills_from_dir(user_skills_dir)
        logger.info(f"Loaded {count} user skills from {user_skills_dir}")

    # Initialize and start channels
    channel_config = get_channel_config()
    if channel_config:
        init_channels(channel_config)
        await channel_manager.start_all()
        logger.info(f"Started {len(channel_config)} channels")

    # Handle any interrupted tasks from previous run
    try:
        from app.subagents.manager import subagent_manager
        interrupted_count = await subagent_manager.mark_interrupted_as_failed()
        if interrupted_count > 0:
            logger.info(f"Marked {interrupted_count} interrupted tasks as failed")
    except Exception as e:
        logger.warning(f"Failed to handle interrupted tasks: {e}")

    logger.info("MaratOS ready to serve requests")

    yield

    # === SHUTDOWN ===
    logger.info("MaratOS shutting down...")

    # Cancel running subagent tasks
    try:
        from app.subagents.manager import subagent_manager
        running_count = subagent_manager.get_running_count()
        if running_count > 0:
            logger.info(f"Cancelling {running_count} running subagent tasks...")
            await subagent_manager.cancel_all()
            logger.info("All subagent tasks cancelled")
    except Exception as e:
        logger.error(f"Error cancelling subagent tasks: {e}")

    # Stop channels
    try:
        await channel_manager.stop_all()
        logger.info("All channels stopped")
    except Exception as e:
        logger.error(f"Error stopping channels: {e}")

    # Stop audit logger (flush remaining events)
    try:
        await audit_logger.stop()
        logger.info("Audit logger stopped")
    except Exception as e:
        logger.error(f"Error stopping audit logger: {e}")

    # Close database connections
    try:
        from app.database import close_db
        await close_db()
        logger.info("Database connections closed")
    except ImportError:
        pass  # close_db may not exist
    except Exception as e:
        logger.error(f"Error closing database: {e}")

    logger.info("MaratOS shutdown complete")


# OpenAPI documentation tags
tags_metadata = [
    {
        "name": "chat",
        "description": "Chat sessions and message streaming with AI agents",
    },
    {
        "name": "agents",
        "description": "AI agent configuration and management",
    },
    {
        "name": "autonomous",
        "description": "Autonomous development projects with multi-agent orchestration",
    },
    {
        "name": "subagents",
        "description": "Background task spawning and monitoring",
    },
    {
        "name": "memory",
        "description": "Persistent memory storage and retrieval",
    },
    {
        "name": "config",
        "description": "System configuration and settings",
    },
    {
        "name": "skills",
        "description": "Reusable workflow skills",
    },
    {
        "name": "projects",
        "description": "Project management and workspace operations",
    },
    {
        "name": "workspace",
        "description": "Workspace cleanup, archival, and maintenance",
    },
    {
        "name": "channels",
        "description": "Multi-channel messaging (Telegram, iMessage, Webex)",
    },
]

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="MaratOS - Your AI Operating System powered by MO. "
    "Features include multi-agent orchestration, persistent memory, "
    "autonomous development projects, and multi-channel messaging.",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS for frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all HTTP requests with timing information."""
    start_time = time.time()

    # Process request
    response = await call_next(request)

    # Calculate duration
    duration_ms = (time.time() - start_time) * 1000

    # Skip logging for static files and health checks to reduce noise
    path = request.url.path
    if not path.startswith("/assets") and path != "/health":
        logger.info(
            "http_request",
            extra={
                "method": request.method,
                "path": path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "client_ip": request.client.host if request.client else "unknown",
            },
        )

    return response


# API routes
app.include_router(api_router)
app.include_router(channels_router, prefix="/api", tags=["channels"])


async def _get_health_response() -> HealthResponse:
    """Get health check data."""
    from app.skills.base import skill_registry
    from app.memory.manager import memory_manager
    from app.subagents.manager import subagent_manager

    return HealthResponse(
        status="ok",
        version="0.1.0",
        agent="MO",
        channels=len(channel_manager.list_channels()),
        skills=len(skill_registry.list_all()),
        memories=memory_manager.stats().get("total_memories", 0),
        running_tasks=subagent_manager.get_running_count(),
    )


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health() -> HealthResponse:
    """Health check endpoint.

    Returns the current status of the MaratOS system including
    active channels, loaded skills, stored memories, and running tasks.
    """
    return await _get_health_response()


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
async def api_health() -> HealthResponse:
    """Health check endpoint (API prefix alias).

    Same as /health but accessible at /api/health for frontend convenience.
    """
    return await _get_health_response()


# Catch-all WebSocket handler to prevent StaticFiles from erroring on WebSocket connections
# This handles cases where frontend dev server HMR or other WebSocket clients connect
@app.websocket("/{path:path}")
async def websocket_catch_all(websocket: WebSocket, path: str):
    """Reject WebSocket connections that don't match any specific route."""
    await websocket.close(code=4004, reason="No WebSocket handler at this path")


# Serve frontend static files in production (not debug mode)
# In debug mode, the Vite dev server serves the frontend and handles HMR WebSockets
frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists() and not settings.debug:
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        """Root endpoint when frontend not built or in debug mode."""
        return {
            "name": "MaratOS",
            "agent": "MO",
            "docs": "/docs",
            "api": "/api",
            "features": ["skills", "memory", "subagents", "channels"],
            "note": "Use frontend dev server at http://localhost:5173 during development",
        }


def main():
    """Run the application."""
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
