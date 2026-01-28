"""Task Graph - DAG representation and execution ordering.

This module implements a directed acyclic graph (DAG) for task dependencies,
providing topological ordering, parallel execution grouping, and cycle detection.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Iterator

from app.autonomous.planner_schema import ExecutionPlan, PlannedTask


class TaskNodeStatus(str, Enum):
    """Status of a task node in the graph."""
    PENDING = "pending"          # Not yet ready to execute
    READY = "ready"              # All dependencies met, can execute
    RUNNING = "running"          # Currently executing
    VERIFYING = "verifying"      # Running verification/acceptance checks
    COMPLETED = "completed"      # Successfully finished
    FAILED = "failed"            # Failed execution
    SKIPPED = "skipped"          # Skipped due to dependency failure
    BLOCKED = "blocked"          # Blocked by failed dependency


@dataclass
class TaskNode:
    """A node in the task execution graph."""
    task: PlannedTask
    status: TaskNodeStatus = TaskNodeStatus.PENDING
    result: Any = None
    error: str | None = None
    logs: list[str] = field(default_factory=list)
    artifacts: dict[str, Any] = field(default_factory=dict)

    # Timing
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Execution tracking
    attempt: int = 0
    verification_results: dict[str, bool] = field(default_factory=dict)

    @property
    def task_id(self) -> str:
        return self.task.id

    @property
    def is_terminal(self) -> bool:
        """Check if task has reached a terminal state."""
        return self.status in (
            TaskNodeStatus.COMPLETED,
            TaskNodeStatus.FAILED,
            TaskNodeStatus.SKIPPED,
        )

    @property
    def can_execute(self) -> bool:
        """Check if task can be executed."""
        return self.status == TaskNodeStatus.READY

    @property
    def duration_ms(self) -> float | None:
        """Get execution duration in milliseconds."""
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds() * 1000
        return None

    def log(self, message: str) -> None:
        """Add a log entry."""
        timestamp = datetime.utcnow().isoformat()
        self.logs.append(f"[{timestamp}] {message}")

    def add_artifact(self, name: str, value: Any) -> None:
        """Add an output artifact."""
        self.artifacts[name] = value


class TaskGraph:
    """Directed Acyclic Graph for task execution.

    Manages task dependencies, determines execution order,
    and tracks overall execution state.
    """

    def __init__(self, plan: ExecutionPlan):
        """Initialize the graph from an execution plan."""
        self.plan = plan
        self.nodes: dict[str, TaskNode] = {}
        self._adjacency: dict[str, set[str]] = defaultdict(set)  # task -> dependents
        self._reverse: dict[str, set[str]] = defaultdict(set)    # task -> dependencies

        self._build_graph()

    def _build_graph(self) -> None:
        """Build the graph structure from the plan."""
        # Create nodes
        for task in self.plan.tasks:
            self.nodes[task.id] = TaskNode(task=task)

        # Build adjacency lists
        for task in self.plan.tasks:
            for dep_id in task.depends_on:
                self._adjacency[dep_id].add(task.id)
                self._reverse[task.id].add(dep_id)

        # Validate no cycles
        if self._has_cycle():
            raise ValueError("Task graph contains a cycle - invalid DAG")

        # Initialize ready status for root tasks
        self._update_ready_status()

    def _has_cycle(self) -> bool:
        """Detect cycles using DFS."""
        WHITE, GRAY, BLACK = 0, 1, 2
        color = {task_id: WHITE for task_id in self.nodes}

        def dfs(node: str) -> bool:
            color[node] = GRAY
            for neighbor in self._adjacency[node]:
                if color[neighbor] == GRAY:
                    return True  # Back edge found - cycle
                if color[neighbor] == WHITE and dfs(neighbor):
                    return True
            color[node] = BLACK
            return False

        for node in self.nodes:
            if color[node] == WHITE:
                if dfs(node):
                    return True
        return False

    def _update_ready_status(self) -> None:
        """Update READY status for all pending tasks whose deps are met."""
        for task_id, node in self.nodes.items():
            if node.status == TaskNodeStatus.PENDING:
                deps = self._reverse[task_id]
                if not deps:
                    # No dependencies - ready immediately
                    node.status = TaskNodeStatus.READY
                elif all(self.nodes[d].status == TaskNodeStatus.COMPLETED for d in deps):
                    # All dependencies completed
                    node.status = TaskNodeStatus.READY

    def get_node(self, task_id: str) -> TaskNode | None:
        """Get a task node by ID."""
        return self.nodes.get(task_id)

    def get_ready_tasks(self) -> list[TaskNode]:
        """Get all tasks that are ready to execute."""
        return [n for n in self.nodes.values() if n.status == TaskNodeStatus.READY]

    def get_running_tasks(self) -> list[TaskNode]:
        """Get all currently running tasks."""
        return [n for n in self.nodes.values() if n.status == TaskNodeStatus.RUNNING]

    def get_completed_tasks(self) -> list[TaskNode]:
        """Get all completed tasks."""
        return [n for n in self.nodes.values() if n.status == TaskNodeStatus.COMPLETED]

    def get_failed_tasks(self) -> list[TaskNode]:
        """Get all failed tasks."""
        return [n for n in self.nodes.values() if n.status == TaskNodeStatus.FAILED]

    def mark_running(self, task_id: str) -> None:
        """Mark a task as running."""
        node = self.nodes[task_id]
        if node.status != TaskNodeStatus.READY:
            raise ValueError(f"Cannot start task {task_id}: status is {node.status}")
        node.status = TaskNodeStatus.RUNNING
        node.started_at = datetime.utcnow()
        node.attempt += 1
        node.log(f"Started execution (attempt {node.attempt})")

    def mark_verifying(self, task_id: str) -> None:
        """Mark a task as verifying."""
        node = self.nodes[task_id]
        node.status = TaskNodeStatus.VERIFYING
        node.log("Starting verification")

    def mark_completed(self, task_id: str, result: Any = None) -> None:
        """Mark a task as completed and update dependents."""
        node = self.nodes[task_id]
        node.status = TaskNodeStatus.COMPLETED
        node.completed_at = datetime.utcnow()
        node.result = result
        node.log(f"Completed successfully (duration: {node.duration_ms:.0f}ms)")

        # Update dependent tasks
        self._update_ready_status()

    def mark_failed(self, task_id: str, error: str) -> None:
        """Mark a task as failed and block dependents."""
        node = self.nodes[task_id]
        node.status = TaskNodeStatus.FAILED
        node.completed_at = datetime.utcnow()
        node.error = error
        node.log(f"Failed: {error}")

        # Block all dependents
        self._block_dependents(task_id)

    def _block_dependents(self, task_id: str) -> None:
        """Recursively block all tasks that depend on a failed task."""
        for dependent_id in self._adjacency[task_id]:
            node = self.nodes[dependent_id]
            if node.status in (TaskNodeStatus.PENDING, TaskNodeStatus.READY):
                node.status = TaskNodeStatus.BLOCKED
                node.error = f"Blocked by failed dependency: {task_id}"
                node.log(f"Blocked due to failure of {task_id}")
                self._block_dependents(dependent_id)

    def mark_skipped(self, task_id: str, reason: str) -> None:
        """Mark a task as skipped."""
        node = self.nodes[task_id]
        node.status = TaskNodeStatus.SKIPPED
        node.error = reason
        node.log(f"Skipped: {reason}")

    def can_retry(self, task_id: str) -> bool:
        """Check if a task can be retried."""
        node = self.nodes[task_id]
        return (
            node.status == TaskNodeStatus.FAILED
            and node.attempt < node.task.max_attempts
        )

    def retry_task(self, task_id: str) -> None:
        """Reset a failed task for retry."""
        node = self.nodes[task_id]
        if not self.can_retry(task_id):
            raise ValueError(f"Cannot retry task {task_id}")
        node.status = TaskNodeStatus.READY
        node.error = None
        node.log(f"Reset for retry (will be attempt {node.attempt + 1})")

    def topological_order(self) -> Iterator[str]:
        """Yield task IDs in topological order (Kahn's algorithm)."""
        in_degree = {t: len(self._reverse[t]) for t in self.nodes}
        queue = [t for t, d in in_degree.items() if d == 0]

        while queue:
            task_id = queue.pop(0)
            yield task_id

            for dependent in self._adjacency[task_id]:
                in_degree[dependent] -= 1
                if in_degree[dependent] == 0:
                    queue.append(dependent)

    def execution_levels(self) -> list[list[str]]:
        """Get tasks grouped by execution level (parallelizable groups).

        Tasks at the same level have no dependencies on each other
        and can be executed in parallel.
        """
        levels: list[list[str]] = []
        remaining = set(self.nodes.keys())
        completed = set()

        while remaining:
            # Find all tasks whose dependencies are all in completed
            current_level = []
            for task_id in remaining:
                deps = self._reverse[task_id]
                if deps <= completed:
                    current_level.append(task_id)

            if not current_level:
                raise ValueError("Cycle detected - cannot determine execution levels")

            levels.append(current_level)
            completed.update(current_level)
            remaining -= set(current_level)

        return levels

    def get_dependencies(self, task_id: str) -> set[str]:
        """Get direct dependencies of a task."""
        return self._reverse[task_id].copy()

    def get_dependents(self, task_id: str) -> set[str]:
        """Get tasks that directly depend on this task."""
        return self._adjacency[task_id].copy()

    def get_input_artifacts(self, task_id: str) -> dict[str, Any]:
        """Collect artifacts from dependencies as inputs for a task."""
        artifacts = {}
        for dep_id in self._reverse[task_id]:
            dep_node = self.nodes[dep_id]
            if dep_node.artifacts:
                artifacts[dep_id] = dep_node.artifacts
        return artifacts

    @property
    def is_complete(self) -> bool:
        """Check if all tasks have reached terminal state."""
        return all(n.is_terminal for n in self.nodes.values())

    @property
    def has_failures(self) -> bool:
        """Check if any tasks failed."""
        return any(n.status == TaskNodeStatus.FAILED for n in self.nodes.values())

    @property
    def progress(self) -> float:
        """Calculate overall progress (0-1)."""
        if not self.nodes:
            return 1.0
        completed = sum(1 for n in self.nodes.values() if n.is_terminal)
        return completed / len(self.nodes)

    def get_status_summary(self) -> dict[str, int]:
        """Get count of tasks in each status."""
        summary: dict[str, int] = defaultdict(int)
        for node in self.nodes.values():
            summary[node.status.value] += 1
        return dict(summary)

    def to_dict(self) -> dict:
        """Serialize graph state for persistence/resume."""
        return {
            "plan_id": self.plan.plan_id,
            "nodes": {
                task_id: {
                    "status": node.status.value,
                    "result": node.result,
                    "error": node.error,
                    "logs": node.logs,
                    "artifacts": node.artifacts,
                    "started_at": node.started_at.isoformat() if node.started_at else None,
                    "completed_at": node.completed_at.isoformat() if node.completed_at else None,
                    "attempt": node.attempt,
                    "verification_results": node.verification_results,
                }
                for task_id, node in self.nodes.items()
            },
            "progress": self.progress,
            "is_complete": self.is_complete,
            "status_summary": self.get_status_summary(),
        }

    def restore_state(self, state: dict) -> None:
        """Restore graph state from serialized form."""
        for task_id, node_state in state.get("nodes", {}).items():
            if task_id in self.nodes:
                node = self.nodes[task_id]
                node.status = TaskNodeStatus(node_state["status"])
                node.result = node_state.get("result")
                node.error = node_state.get("error")
                node.logs = node_state.get("logs", [])
                node.artifacts = node_state.get("artifacts", {})
                node.attempt = node_state.get("attempt", 0)
                node.verification_results = node_state.get("verification_results", {})

                if node_state.get("started_at"):
                    node.started_at = datetime.fromisoformat(node_state["started_at"])
                if node_state.get("completed_at"):
                    node.completed_at = datetime.fromisoformat(node_state["completed_at"])

        # Re-evaluate ready status
        self._update_ready_status()
