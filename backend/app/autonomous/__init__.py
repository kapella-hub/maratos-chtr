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
from app.autonomous.model_selector import (
    ModelSelector,
    ModelTier,
    ModelConfig,
    model_selector,
    get_model_for_task,
    get_model_config_for_task,
    discover_available_models,
    refresh_available_models,
    get_available_models_info,
)

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
    "ModelSelector",
    "ModelTier",
    "ModelConfig",
    "model_selector",
    "get_model_for_task",
    "get_model_config_for_task",
    "discover_available_models",
    "refresh_available_models",
    "get_available_models_info",
]
