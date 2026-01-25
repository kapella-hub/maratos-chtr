"""Agents API endpoints."""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.agents import AgentConfig, agent_registry

router = APIRouter(prefix="/agents")


class AgentUpdate(BaseModel):
    """Agent update request."""

    name: str | None = None
    description: str | None = None
    icon: str | None = None
    model: str | None = None
    temperature: float | None = None
    system_prompt: str | None = None
    tools: list[str] | None = None


class AgentCreate(BaseModel):
    """Agent creation request."""

    id: str
    name: str
    description: str = ""
    icon: str = "🤖"
    model: str = ""
    temperature: float = 0.7
    system_prompt: str = ""
    tools: list[str] = []


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
        "system_prompt": config.system_prompt,
        "tools": config.tools,
    }


@router.put("/{agent_id}")
async def update_agent(agent_id: str, update: AgentUpdate) -> dict[str, Any]:
    """Update an agent's configuration."""
    updates = update.model_dump(exclude_none=True)
    if not agent_registry.update_config(agent_id, updates):
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_id}")

    return await get_agent(agent_id)


@router.post("")
async def create_agent(data: AgentCreate) -> dict[str, Any]:
    """Create a new custom agent."""
    # Check if ID already exists
    if agent_registry.get_config(data.id):
        raise HTTPException(status_code=400, detail=f"Agent already exists: {data.id}")

    config = AgentConfig(
        id=data.id,
        name=data.name,
        description=data.description,
        icon=data.icon,
        model=data.model,
        temperature=data.temperature,
        system_prompt=data.system_prompt,
        tools=data.tools,
    )
    agent_registry.register_config(config)

    return await get_agent(data.id)
