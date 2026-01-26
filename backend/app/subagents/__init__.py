"""Subagent system for MaratOS - spawn background tasks."""

from app.subagents.manager import SubagentManager, SubagentTask, TaskStatus
from app.subagents.runner import SubagentRunner
from app.subagents.metrics import TaskMetricsManager, task_metrics
from app.subagents.recovery import (
    FailureContext,
    FailureLogger,
    FailureType,
    RecoveryAction,
    RecoveryConfig,
    RecoveryStrategy,
    failure_logger,
    default_recovery_config,
)

__all__ = [
    # Manager
    "SubagentManager",
    "SubagentTask",
    "TaskStatus",
    # Runner
    "SubagentRunner",
    # Metrics
    "TaskMetricsManager",
    "task_metrics",
    # Recovery
    "FailureContext",
    "FailureLogger",
    "FailureType",
    "RecoveryAction",
    "RecoveryConfig",
    "RecoveryStrategy",
    "failure_logger",
    "default_recovery_config",
]
