"""Autonomous development team module.

This module provides functionality for autonomous multi-agent projects that can
run for extended periods, with quality gates, feedback loops, and git integration.
"""

from app.autonomous.models import (
    ProjectPlan,
    ProjectTask,
    QualityGate,
    TaskIteration,
    ProjectStatus,
    AutonomousTaskStatus,
    QualityGateType,
)
from app.autonomous.orchestrator import Orchestrator, OrchestratorEvent
from app.autonomous.project_manager import project_manager
from app.autonomous.git_ops import GitOperations

__all__ = [
    "ProjectPlan",
    "ProjectTask",
    "QualityGate",
    "TaskIteration",
    "ProjectStatus",
    "AutonomousTaskStatus",
    "QualityGateType",
    "Orchestrator",
    "OrchestratorEvent",
    "project_manager",
    "GitOperations",
]
