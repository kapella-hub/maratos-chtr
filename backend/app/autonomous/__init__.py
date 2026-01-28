"""Autonomous development team module.

This module provides functionality for autonomous multi-agent projects that can
run for extended periods, with quality gates, feedback loops, and git integration.

The unified orchestration engine powers both:
- Inline "project mode" within chat sessions
- Autonomous API-driven project runs
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

# Unified orchestration engine
from app.autonomous.engine import (
    OrchestrationEngine,
    RunState,
    RunConfig,
    RunContext,
    EngineEvent,
    EngineEventType,
    get_engine,
)

# Planner schema and task graph
from app.autonomous.planner_schema import (
    ExecutionPlan,
    PlannedTask,
    AcceptanceCriterion,
    TaskInput,
    TaskOutput,
    PlanMetadata,
)
from app.autonomous.task_graph import (
    TaskGraph,
    TaskNode,
    TaskNodeStatus,
)

# Inline orchestration
from app.autonomous.inline_orchestrator import (
    InlineOrchestrator,
    InlineEvent,
    get_inline_orchestrator,
    handle_project_action,
)
from app.autonomous.inline_project import (
    InlineProject,
    InlineProjectStatus,
    get_inline_project,
    create_inline_project,
)

# Detection
from app.autonomous.detection import (
    ProjectDetector,
    DetectionResult,
    project_detector,
    enable_project_detection,
)

# Persistence repositories
from app.autonomous.repositories import (
    RunRepository,
    TaskRepository,
    ArtifactRepository,
    LogRepository,
)

# Persistent engine
from app.autonomous.persistent_engine import (
    PersistentOrchestrationEngine,
    get_persistent_engine,
    get_run_by_session,
    get_run_tasks,
    get_tool_audit_trail,
)

__all__ = [
    # Legacy autonomous models
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
    # Unified engine
    "OrchestrationEngine",
    "RunState",
    "RunConfig",
    "RunContext",
    "EngineEvent",
    "EngineEventType",
    "get_engine",
    # Planner schema
    "ExecutionPlan",
    "PlannedTask",
    "AcceptanceCriterion",
    "TaskInput",
    "TaskOutput",
    "PlanMetadata",
    # Task graph
    "TaskGraph",
    "TaskNode",
    "TaskNodeStatus",
    # Inline orchestration
    "InlineOrchestrator",
    "InlineEvent",
    "get_inline_orchestrator",
    "handle_project_action",
    "InlineProject",
    "InlineProjectStatus",
    "get_inline_project",
    "create_inline_project",
    # Detection
    "ProjectDetector",
    "DetectionResult",
    "project_detector",
    "enable_project_detection",
    # Persistence repositories
    "RunRepository",
    "TaskRepository",
    "ArtifactRepository",
    "LogRepository",
    # Persistent engine
    "PersistentOrchestrationEngine",
    "get_persistent_engine",
    "get_run_by_session",
    "get_run_tasks",
    "get_tool_audit_trail",
]
