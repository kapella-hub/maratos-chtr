"""Data models for autonomous development team."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class ProjectStatus(str, Enum):
    """Project execution status."""
    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AutonomousTaskStatus(str, Enum):
    """Task execution status with feedback loop states."""
    PENDING = "pending"
    BLOCKED = "blocked"          # Waiting on dependencies
    READY = "ready"              # Dependencies met, ready to start
    IN_PROGRESS = "in_progress"  # Agent is working
    TESTING = "testing"          # Running quality gate: tests
    REVIEWING = "reviewing"      # Running quality gate: code review
    FIXING = "fixing"            # Agent is fixing issues from quality gate
    COMPLETED = "completed"      # All quality gates passed
    FAILED = "failed"            # Max attempts exceeded
    SKIPPED = "skipped"          # Skipped due to dependency failure


class QualityGateType(str, Enum):
    """Types of quality gates."""
    TESTS_PASS = "tests_pass"
    REVIEW_APPROVED = "review_approved"
    LINT_CLEAN = "lint_clean"
    TYPE_CHECK = "type_check"
    BUILD_SUCCESS = "build_success"


@dataclass
class QualityGate:
    """A quality gate that must pass before task completion."""

    type: QualityGateType
    required: bool = True
    passed: bool = False
    error: str | None = None
    checked_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "required": self.required,
            "passed": self.passed,
            "error": self.error,
            "checked_at": self.checked_at.isoformat() if self.checked_at else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QualityGate":
        return cls(
            type=QualityGateType(data["type"]),
            required=data.get("required", True),
            passed=data.get("passed", False),
            error=data.get("error"),
            checked_at=datetime.fromisoformat(data["checked_at"]) if data.get("checked_at") else None,
        )


@dataclass
class TaskIteration:
    """Record of a single attempt at completing a task."""

    attempt: int
    started_at: datetime
    completed_at: datetime | None = None
    success: bool = False
    agent_response: str = ""
    quality_results: dict[str, Any] = field(default_factory=dict)
    feedback: str | None = None  # Feedback for the next iteration
    files_modified: list[str] = field(default_factory=list)
    commit_sha: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempt": self.attempt,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "success": self.success,
            "agent_response": self.agent_response[:1000],  # Truncate for storage
            "quality_results": self.quality_results,
            "feedback": self.feedback,
            "files_modified": self.files_modified,
            "commit_sha": self.commit_sha,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskIteration":
        return cls(
            attempt=data["attempt"],
            started_at=datetime.fromisoformat(data["started_at"]),
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            success=data.get("success", False),
            agent_response=data.get("agent_response", ""),
            quality_results=data.get("quality_results", {}),
            feedback=data.get("feedback"),
            files_modified=data.get("files_modified", []),
            commit_sha=data.get("commit_sha"),
        )


@dataclass
class ProjectTask:
    """A task within an autonomous project."""

    id: str
    title: str
    description: str
    agent_type: str  # coder, tester, reviewer, docs, devops, architect

    status: AutonomousTaskStatus = AutonomousTaskStatus.PENDING
    depends_on: list[str] = field(default_factory=list)  # Task IDs
    quality_gates: list[QualityGate] = field(default_factory=list)
    iterations: list[TaskIteration] = field(default_factory=list)

    max_attempts: int = 3
    priority: int = 0  # Higher = more important

    # Files this task will work on (for targeted reviews/tests)
    target_files: list[str] = field(default_factory=list)

    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Result
    final_commit_sha: str | None = None
    error: str | None = None

    @property
    def current_attempt(self) -> int:
        return len(self.iterations)

    @property
    def is_terminal(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status in (
            AutonomousTaskStatus.COMPLETED,
            AutonomousTaskStatus.FAILED,
            AutonomousTaskStatus.SKIPPED,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "agent_type": self.agent_type,
            "status": self.status.value,
            "depends_on": self.depends_on,
            "quality_gates": [g.to_dict() for g in self.quality_gates],
            "iterations": [i.to_dict() for i in self.iterations],
            "max_attempts": self.max_attempts,
            "priority": self.priority,
            "target_files": self.target_files,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "final_commit_sha": self.final_commit_sha,
            "error": self.error,
            "current_attempt": self.current_attempt,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectTask":
        return cls(
            id=data["id"],
            title=data["title"],
            description=data["description"],
            agent_type=data["agent_type"],
            status=AutonomousTaskStatus(data.get("status", "pending")),
            depends_on=data.get("depends_on", []),
            quality_gates=[QualityGate.from_dict(g) for g in data.get("quality_gates", [])],
            iterations=[TaskIteration.from_dict(i) for i in data.get("iterations", [])],
            max_attempts=data.get("max_attempts", 3),
            priority=data.get("priority", 0),
            target_files=data.get("target_files", []),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            final_commit_sha=data.get("final_commit_sha"),
            error=data.get("error"),
        )


@dataclass
class ProjectConfig:
    """Configuration for an autonomous project."""

    auto_commit: bool = True
    push_to_remote: bool = False
    create_pr: bool = False
    pr_base_branch: str = "main"
    max_runtime_hours: float = 8.0
    max_total_iterations: int = 50
    parallel_tasks: int = 3  # Max concurrent tasks

    def to_dict(self) -> dict[str, Any]:
        return {
            "auto_commit": self.auto_commit,
            "push_to_remote": self.push_to_remote,
            "create_pr": self.create_pr,
            "pr_base_branch": self.pr_base_branch,
            "max_runtime_hours": self.max_runtime_hours,
            "max_total_iterations": self.max_total_iterations,
            "parallel_tasks": self.parallel_tasks,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectConfig":
        return cls(
            auto_commit=data.get("auto_commit", True),
            push_to_remote=data.get("push_to_remote", False),
            create_pr=data.get("create_pr", False),
            pr_base_branch=data.get("pr_base_branch", "main"),
            max_runtime_hours=data.get("max_runtime_hours", 8.0),
            max_total_iterations=data.get("max_total_iterations", 50),
            parallel_tasks=data.get("parallel_tasks", 3),
        )


@dataclass
class ProjectPlan:
    """An autonomous development project."""

    id: str
    name: str
    original_prompt: str
    workspace_path: str

    status: ProjectStatus = ProjectStatus.PLANNING
    config: ProjectConfig = field(default_factory=ProjectConfig)
    tasks: list[ProjectTask] = field(default_factory=list)

    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    paused_at: datetime | None = None

    # Progress tracking
    total_iterations: int = 0

    # Git integration
    branch_name: str | None = None
    pr_url: str | None = None

    # Error state
    error: str | None = None

    @property
    def tasks_completed(self) -> int:
        return len([t for t in self.tasks if t.status == AutonomousTaskStatus.COMPLETED])

    @property
    def tasks_failed(self) -> int:
        return len([t for t in self.tasks if t.status == AutonomousTaskStatus.FAILED])

    @property
    def tasks_pending(self) -> int:
        return len([t for t in self.tasks if not t.is_terminal])

    @property
    def progress(self) -> float:
        if not self.tasks:
            return 0.0
        completed = self.tasks_completed
        total = len(self.tasks)
        return completed / total if total > 0 else 0.0

    def get_task(self, task_id: str) -> ProjectTask | None:
        """Get a task by ID."""
        for task in self.tasks:
            if task.id == task_id:
                return task
        return None

    def get_ready_tasks(self) -> list[ProjectTask]:
        """Get tasks that are ready to execute (dependencies met)."""
        ready = []
        completed_ids = {t.id for t in self.tasks if t.status == AutonomousTaskStatus.COMPLETED}

        for task in self.tasks:
            if task.status in (AutonomousTaskStatus.PENDING, AutonomousTaskStatus.READY):
                # Check if all dependencies are completed
                deps_met = all(dep_id in completed_ids for dep_id in task.depends_on)
                if deps_met:
                    task.status = AutonomousTaskStatus.READY
                    ready.append(task)

        # Sort by priority (higher first)
        ready.sort(key=lambda t: t.priority, reverse=True)
        return ready

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "original_prompt": self.original_prompt,
            "workspace_path": self.workspace_path,
            "status": self.status.value,
            "config": self.config.to_dict(),
            "tasks": [t.to_dict() for t in self.tasks],
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "paused_at": self.paused_at.isoformat() if self.paused_at else None,
            "total_iterations": self.total_iterations,
            "branch_name": self.branch_name,
            "pr_url": self.pr_url,
            "error": self.error,
            "progress": self.progress,
            "tasks_completed": self.tasks_completed,
            "tasks_failed": self.tasks_failed,
            "tasks_pending": self.tasks_pending,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectPlan":
        return cls(
            id=data["id"],
            name=data["name"],
            original_prompt=data["original_prompt"],
            workspace_path=data["workspace_path"],
            status=ProjectStatus(data.get("status", "planning")),
            config=ProjectConfig.from_dict(data.get("config", {})),
            tasks=[ProjectTask.from_dict(t) for t in data.get("tasks", [])],
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            completed_at=datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None,
            paused_at=datetime.fromisoformat(data["paused_at"]) if data.get("paused_at") else None,
            total_iterations=data.get("total_iterations", 0),
            branch_name=data.get("branch_name"),
            pr_url=data.get("pr_url"),
            error=data.get("error"),
        )
