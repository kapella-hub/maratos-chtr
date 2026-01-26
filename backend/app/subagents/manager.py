"""Subagent manager for spawning and tracking background tasks."""

import asyncio
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Subagent task status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class SubagentTask:
    """A background task run by a subagent."""
    
    id: str
    name: str
    description: str
    agent_id: str
    
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0  # 0-1
    
    # Timing
    created_at: datetime = field(default_factory=datetime.now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    
    # Results
    result: Any = None
    error: str | None = None
    logs: list[str] = field(default_factory=list)
    
    # Parent task for nested subagents
    parent_id: str | None = None
    
    # Callback when complete
    callback_session: str | None = None  # Session to notify
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "agent_id": self.agent_id,
            "status": self.status.value,
            "progress": self.progress,
            "created_at": self.created_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "result": self.result,
            "error": self.error,
            "logs": self.logs[-20:],  # Last 20 logs
        }
    
    def log(self, message: str) -> None:
        """Add a log entry."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.logs.append(f"[{timestamp}] {message}")
        logger.info(f"[{self.id}] {message}")


class SubagentManager:
    """Manages subagent tasks."""
    
    def __init__(self) -> None:
        self._tasks: dict[str, SubagentTask] = {}
        self._running: dict[str, asyncio.Task] = {}
    
    async def spawn(
        self,
        name: str,
        description: str,
        agent_id: str,
        work_fn: Callable[["SubagentTask"], Coroutine[Any, Any, Any]],
        parent_id: str | None = None,
        callback_session: str | None = None,
    ) -> SubagentTask:
        """Spawn a new subagent task.
        
        Args:
            name: Task name
            description: What the task does
            agent_id: Which agent runs this
            work_fn: Async function that does the work (receives task for logging/progress)
            parent_id: Parent task ID if nested
            callback_session: Session to notify when complete
        
        Returns:
            The created SubagentTask
        """
        task = SubagentTask(
            id=str(uuid.uuid4())[:8],
            name=name,
            description=description,
            agent_id=agent_id,
            parent_id=parent_id,
            callback_session=callback_session,
        )
        
        self._tasks[task.id] = task
        
        # Start the task in background
        async_task = asyncio.create_task(self._run_task(task, work_fn))
        self._running[task.id] = async_task
        
        logger.info(f"Spawned subagent task: {task.id} - {name}")
        return task
    
    async def _run_task(
        self,
        task: SubagentTask,
        work_fn: Callable[[SubagentTask], Coroutine[Any, Any, Any]],
    ) -> None:
        """Run a task and handle completion/errors."""
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.now()
        task.log(f"Started: {task.description}")
        
        try:
            result = await work_fn(task)
            task.result = result
            task.status = TaskStatus.COMPLETED
            task.progress = 1.0
            task.log("Completed successfully")
            
        except asyncio.CancelledError:
            task.status = TaskStatus.CANCELLED
            task.log("Cancelled")
            
        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error = str(e)
            task.log(f"Failed: {e}")
            logger.error(f"Subagent task {task.id} failed: {e}")
        
        finally:
            task.completed_at = datetime.now()
            self._running.pop(task.id, None)
            
            # TODO: Notify callback session if set
            if task.callback_session:
                logger.info(f"Task {task.id} complete, should notify session {task.callback_session}")
    
    def get(self, task_id: str) -> SubagentTask | None:
        """Get a task by ID."""
        return self._tasks.get(task_id)
    
    def list_tasks(
        self,
        status: TaskStatus | None = None,
        agent_id: str | None = None,
        limit: int = 50,
    ) -> list[SubagentTask]:
        """List tasks with optional filters."""
        tasks = list(self._tasks.values())
        
        if status:
            tasks = [t for t in tasks if t.status == status]
        if agent_id:
            tasks = [t for t in tasks if t.agent_id == agent_id]
        
        # Sort by created time, newest first
        tasks.sort(key=lambda t: t.created_at, reverse=True)
        
        return tasks[:limit]
    
    async def cancel(self, task_id: str) -> bool:
        """Cancel a running task."""
        if task_id in self._running:
            self._running[task_id].cancel()
            return True
        return False

    async def cancel_all(self) -> int:
        """Cancel all running tasks. Returns number of tasks cancelled."""
        cancelled = 0
        for task_id in list(self._running.keys()):
            self._running[task_id].cancel()
            cancelled += 1
        return cancelled

    def get_running_count(self) -> int:
        """Get number of currently running tasks."""
        return len(self._running)
    
    def cleanup_old(self, max_age_hours: int = 24) -> int:
        """Remove old completed tasks."""
        now = datetime.now()
        to_remove = []
        
        for task_id, task in self._tasks.items():
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED):
                if task.completed_at:
                    age_hours = (now - task.completed_at).total_seconds() / 3600
                    if age_hours > max_age_hours:
                        to_remove.append(task_id)
        
        for task_id in to_remove:
            del self._tasks[task_id]
        
        return len(to_remove)


# Global subagent manager
subagent_manager = SubagentManager()
