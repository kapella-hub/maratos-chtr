"""Common API response models."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class StatusResponse(BaseModel):
    """Generic status response."""

    status: str = Field(description="Operation status (ok, deleted, etc.)")


class ErrorDetail(BaseModel):
    """Error detail for API responses."""

    detail: str = Field(description="Error message")
    code: str | None = Field(default=None, description="Error code for programmatic handling")


class HealthResponse(BaseModel):
    """Health check response."""

    status: str = Field(description="Service status")
    version: str = Field(description="Application version")
    agent: str = Field(description="Primary agent name")
    channels: int = Field(description="Number of active channels")
    skills: int = Field(description="Number of loaded skills")
    memories: int = Field(description="Total memories stored")
    running_tasks: int = Field(description="Number of running subagent tasks")


class TaskResponse(BaseModel):
    """Subagent task response."""

    id: str = Field(description="Task ID")
    name: str = Field(description="Task name")
    description: str = Field(description="Task description")
    agent_id: str = Field(description="Agent handling the task")
    status: str = Field(description="Task status (pending, running, completed, failed)")
    progress: float = Field(description="Progress 0.0 to 1.0")
    result: dict[str, Any] | None = Field(default=None, description="Task result if completed")
    error: str | None = Field(default=None, description="Error message if failed")
    created_at: datetime = Field(description="Task creation time")
    completed_at: datetime | None = Field(default=None, description="Task completion time")


class MemoryResponse(BaseModel):
    """Memory entry response."""

    id: str = Field(description="Memory ID")
    content: str = Field(description="Memory content")
    memory_type: str = Field(description="Type of memory (fact, task, preference, etc.)")
    importance: float = Field(description="Importance score 0.0 to 1.0")
    tags: list[str] = Field(default_factory=list, description="Tags for categorization")
    created_at: datetime = Field(description="Creation timestamp")


class SkillResponse(BaseModel):
    """Skill definition response."""

    id: str = Field(description="Skill ID")
    name: str = Field(description="Skill name")
    description: str = Field(description="Skill description")
    triggers: list[str] = Field(default_factory=list, description="Keyword triggers")
    steps: int = Field(description="Number of steps in the skill")


class AgentResponse(BaseModel):
    """Agent configuration response."""

    id: str = Field(description="Agent ID")
    name: str = Field(description="Agent display name")
    description: str = Field(description="Agent description")
    icon: str = Field(description="Agent icon emoji")
    model: str = Field(description="LLM model being used")
    temperature: float = Field(description="Temperature setting for generation")


class ConfigResponse(BaseModel):
    """Configuration response."""

    app_name: str = Field(description="Application name")
    debug: bool = Field(description="Debug mode enabled")
    default_model: str = Field(description="Default LLM model")
    max_context_tokens: int = Field(description="Maximum context tokens")
    max_response_tokens: int = Field(description="Maximum response tokens")
