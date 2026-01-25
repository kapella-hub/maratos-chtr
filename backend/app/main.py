"""MaratOS - Main FastAPI application."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import api_router
from app.api.channels import router as channels_router
from app.config import settings, get_channel_config
from app.database import init_db
from app.channels.manager import channel_manager, init_channels
from app.skills.loader import load_skills_from_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    await init_db()
    
    # Load skills
    skills_dir = Path(__file__).parent.parent / "skills"
    if skills_dir.exists():
        count = load_skills_from_dir(skills_dir)
        print(f"Loaded {count} skills from {skills_dir}")
    
    # Also load user skills
    user_skills_dir = Path.home() / ".maratos" / "skills"
    if user_skills_dir.exists():
        count = load_skills_from_dir(user_skills_dir)
        print(f"Loaded {count} user skills from {user_skills_dir}")
    
    # Initialize and start channels
    channel_config = get_channel_config()
    if channel_config:
        init_channels(channel_config)
        await channel_manager.start_all()
    
    yield
    
    # Shutdown
    await channel_manager.stop_all()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="MaratOS - Your AI Operating System powered by MO",
    lifespan=lifespan,
)

# CORS for frontend dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(api_router)
app.include_router(channels_router, prefix="/api", tags=["channels"])


@app.get("/health")
async def health():
    """Health check endpoint."""
    from app.skills.base import skill_registry
    from app.memory.manager import memory_manager
    from app.subagents.manager import subagent_manager
    
    return {
        "status": "ok", 
        "version": "0.1.0", 
        "agent": "MO",
        "channels": len(channel_manager.list_channels()),
        "skills": len(skill_registry.list_all()),
        "memories": memory_manager.stats().get("total_memories", 0),
        "running_tasks": subagent_manager.get_running_count(),
    }


# Serve frontend static files if they exist
frontend_dist = Path(__file__).parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
else:
    @app.get("/")
    async def root():
        """Root endpoint when frontend not built."""
        return {
            "name": "MaratOS",
            "agent": "MO",
            "docs": "/docs",
            "api": "/api",
            "features": ["skills", "memory", "subagents", "channels"],
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
