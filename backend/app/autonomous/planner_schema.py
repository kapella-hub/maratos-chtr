"""Planner Schema - Pydantic models for structured planner output.

This module defines the canonical schema for orchestration plans,
enabling validation and deterministic execution.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class TaskPriority(str, Enum):
    """Task priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class AcceptanceCriterion(BaseModel):
    """A single acceptance criterion for a task."""
    id: str = Field(..., description="Unique identifier for this criterion")
    description: str = Field(..., description="What needs to be true for acceptance")
    verification_type: str = Field(
        default="manual",
        description="How to verify: 'test', 'lint', 'typecheck', 'build', 'manual', 'review'"
    )
    command: str | None = Field(
        default=None,
        description="Command to run for automated verification"
    )
    required: bool = Field(default=True, description="Whether this criterion is required")


class TaskInput(BaseModel):
    """Input specification for a task."""
    name: str = Field(..., description="Input name/identifier")
    description: str = Field(..., description="What this input provides")
    source: str | None = Field(
        default=None,
        description="Where this comes from: 'user', 'task:<task_id>', 'context'"
    )
    required: bool = Field(default=True)
    default_value: Any = Field(default=None, description="Default if not provided")


class TaskOutput(BaseModel):
    """Output specification for a task."""
    name: str = Field(..., description="Output name/identifier")
    description: str = Field(..., description="What this output provides")
    type: str = Field(
        default="artifact",
        description="Output type: 'artifact', 'file', 'data', 'status'"
    )


class PlannedTask(BaseModel):
    """A single task in the execution plan."""
    id: str = Field(..., description="Unique task identifier (e.g., 'task-001')")
    title: str = Field(..., max_length=200, description="Short task title")
    description: str = Field(..., description="Detailed task description with context")
    agent_id: str = Field(..., description="Agent to execute: architect, coder, reviewer, tester, docs, devops")

    # Dependencies
    depends_on: list[str] = Field(
        default_factory=list,
        description="List of task IDs this depends on"
    )

    # Inputs and outputs for DAG data flow
    inputs: list[TaskInput] = Field(
        default_factory=list,
        description="Required inputs for this task"
    )
    outputs: list[TaskOutput] = Field(
        default_factory=list,
        description="Expected outputs from this task"
    )

    # Acceptance criteria
    acceptance: list[AcceptanceCriterion] = Field(
        default_factory=list,
        description="Criteria for task completion"
    )

    # Optional skill binding
    skill_id: str | None = Field(
        default=None,
        description="Skill ID to execute instead of free-form agent"
    )

    # Execution hints
    priority: TaskPriority = Field(default=TaskPriority.MEDIUM)
    estimated_complexity: str = Field(
        default="medium",
        description="Complexity hint: 'trivial', 'simple', 'medium', 'complex', 'epic'"
    )
    target_files: list[str] = Field(
        default_factory=list,
        description="Files this task will likely modify"
    )

    # Retry configuration
    max_attempts: int = Field(default=3, ge=1, le=10)

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id(cls, v: str) -> str:
        """Validate agent ID is a known agent type."""
        valid_agents = {"architect", "coder", "reviewer", "tester", "docs", "devops", "mo"}
        if v not in valid_agents:
            raise ValueError(f"Unknown agent_id: {v}. Must be one of {valid_agents}")
        return v

    @field_validator("depends_on")
    @classmethod
    def validate_no_self_dependency(cls, v: list[str], info) -> list[str]:
        """Ensure task doesn't depend on itself."""
        task_id = info.data.get("id")
        if task_id and task_id in v:
            raise ValueError(f"Task cannot depend on itself: {task_id}")
        return v


class PlanMetadata(BaseModel):
    """Metadata about the plan itself."""
    planner_model: str = Field(..., description="Model used for planning")
    planning_duration_ms: float | None = Field(default=None)
    confidence_score: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Planner's confidence in this plan"
    )
    alternative_approaches: list[str] = Field(
        default_factory=list,
        description="Other approaches considered"
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="Assumptions made during planning"
    )
    risks: list[str] = Field(
        default_factory=list,
        description="Identified risks or concerns"
    )


class ExecutionPlan(BaseModel):
    """Complete execution plan from the planner.

    This is the canonical output format that the orchestration engine
    validates and executes.
    """
    # Plan identification
    plan_id: str = Field(..., description="Unique plan identifier")
    version: str = Field(default="1.0", description="Plan schema version")

    # Source
    original_prompt: str = Field(..., description="Original user request")
    workspace_path: str | None = Field(default=None, description="Target workspace")

    # Plan content
    summary: str = Field(..., description="Brief summary of what this plan accomplishes")
    tasks: list[PlannedTask] = Field(..., min_length=1, description="Ordered list of tasks")

    # Configuration
    parallel_execution: bool = Field(
        default=True,
        description="Whether independent tasks can run in parallel"
    )
    fail_fast: bool = Field(
        default=False,
        description="Stop all tasks on first failure"
    )
    verification_mode: str = Field(
        default="per_task",
        description="When to verify: 'per_task', 'end_only', 'continuous'"
    )

    # Metadata
    metadata: PlanMetadata | None = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    @field_validator("tasks")
    @classmethod
    def validate_task_dependencies(cls, tasks: list[PlannedTask]) -> list[PlannedTask]:
        """Validate all task dependencies reference existing tasks."""
        task_ids = {t.id for t in tasks}
        for task in tasks:
            for dep in task.depends_on:
                if dep not in task_ids:
                    raise ValueError(
                        f"Task '{task.id}' depends on unknown task '{dep}'. "
                        f"Available tasks: {task_ids}"
                    )
        return tasks

    def get_task(self, task_id: str) -> PlannedTask | None:
        """Get a task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_root_tasks(self) -> list[PlannedTask]:
        """Get tasks with no dependencies (entry points)."""
        return [t for t in self.tasks if not t.depends_on]

    def get_dependents(self, task_id: str) -> list[PlannedTask]:
        """Get tasks that depend on the given task."""
        return [t for t in self.tasks if task_id in t.depends_on]


# JSON Schema export for external validation
def get_plan_json_schema() -> dict:
    """Get JSON Schema for the execution plan."""
    return ExecutionPlan.model_json_schema()


# Example plan for testing/documentation
EXAMPLE_PLAN = {
    "plan_id": "plan-20260127-001",
    "version": "1.0",
    "original_prompt": "Add user authentication to the app",
    "workspace_path": "/Users/dev/myproject",
    "summary": "Implement JWT-based authentication with login/register endpoints",
    "tasks": [
        {
            "id": "task-001",
            "title": "Design authentication architecture",
            "description": "Design the auth system including JWT tokens, session management, and API structure",
            "agent_id": "architect",
            "depends_on": [],
            "inputs": [
                {"name": "requirements", "description": "User auth requirements", "source": "user"}
            ],
            "outputs": [
                {"name": "design_doc", "description": "Architecture design", "type": "artifact"}
            ],
            "acceptance": [
                {"id": "ac-001", "description": "Design document created", "verification_type": "manual"}
            ],
            "priority": "high",
            "estimated_complexity": "medium"
        },
        {
            "id": "task-002",
            "title": "Implement auth models and utilities",
            "description": "Create User model, password hashing, JWT utilities",
            "agent_id": "coder",
            "depends_on": ["task-001"],
            "inputs": [
                {"name": "design", "description": "Auth design from architect", "source": "task:task-001"}
            ],
            "outputs": [
                {"name": "auth_code", "description": "Auth implementation", "type": "file"}
            ],
            "acceptance": [
                {"id": "ac-002", "description": "Tests pass", "verification_type": "test", "command": "pytest tests/test_auth.py"}
            ],
            "target_files": ["src/auth/models.py", "src/auth/utils.py"],
            "priority": "high"
        },
        {
            "id": "task-003",
            "title": "Write auth tests",
            "description": "Create comprehensive tests for authentication",
            "agent_id": "tester",
            "depends_on": ["task-002"],
            "acceptance": [
                {"id": "ac-003", "description": "80%+ coverage", "verification_type": "test"}
            ],
            "priority": "medium"
        }
    ],
    "parallel_execution": True,
    "verification_mode": "per_task",
    "metadata": {
        "planner_model": "claude-sonnet-4-20250514",
        "confidence_score": 0.85,
        "assumptions": ["Using existing database", "JWT is preferred over sessions"],
        "risks": ["Token refresh logic complexity"]
    }
}
