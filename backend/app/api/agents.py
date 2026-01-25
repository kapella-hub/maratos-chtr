"""Agents API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents import AgentConfig, agent_registry

router = APIRouter(prefix="/agents")


class AgentUpdate(BaseModel):
    """Agent update request."""

    model: str | None = None
    temperature: float | None = None


@router.get("")
async def list_agents() -> list[dict[str, Any]]:
    """List all available agents."""
    return agent_registry.list_all()


@router.get("/{agent_id}")
async def get_agent(agent_id: str) -> dict[str, Any]:
    """Get agent details."""
    config = agent_registry.get_config(agent_id)
    if not config:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    return {
        "id": config.id,
        "name": config.name,
        "description": config.description,
        "icon": config.icon,
        "model": config.model,
        "temperature": config.temperature,
    }


@router.put("/{agent_id}")
async def update_agent(agent_id: str, update: AgentUpdate) -> dict[str, Any]:
    """Update an agent's model or temperature."""
    updates = update.model_dump(exclude_none=True)
    if not agent_registry.update_config(agent_id, updates):
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    return await get_agent(agent_id)


@router.post("/default/{agent_id}")
async def set_default_agent(agent_id: str) -> dict[str, str]:
    """Set the default agent."""
    if not agent_registry.set_default(agent_id):
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")
    
    return {"status": "ok", "default": agent_id}
