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


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    await init_db()
    
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
    return {
        "status": "ok", 
        "version": "0.1.0", 
        "agent": "MO",
        "channels": len(channel_manager.list_channels()),
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
            "channels": "/api/channels",
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
