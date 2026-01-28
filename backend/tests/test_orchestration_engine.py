"""Tests for the unified orchestration engine.

Tests cover:
- Planner schema validation and JSON parsing
- DAG execution ordering
- SSE event ordering
- State machine transitions
- Resume capability hooks
"""

import asyncio
import json
import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

from app.autonomous.planner_schema import (
    ExecutionPlan,
    PlannedTask,
    AcceptanceCriterion,
    TaskInput,
    TaskOutput,
    PlanMetadata,
    TaskPriority,
    EXAMPLE_PLAN,
    get_plan_json_schema,
)
from app.autonomous.task_graph import (
    TaskGraph,
    TaskNode,
    TaskNodeStatus,
)
from app.autonomous.engine import (
    OrchestrationEngine,
    RunState,
    RunConfig,
    RunContext,
    EngineEvent,
    EngineEventType,
    STATE_TRANSITIONS,
)
from app.autonomous.detection import (
    ProjectDetector,
    DetectionResult,
)


# =============================================================================
# Planner Schema Tests
# =============================================================================

class TestPlannerSchema:
    """Tests for planner schema validation and JSON parsing."""

    def test_parse_valid_plan(self):
        """Valid plan JSON should parse successfully."""
        plan = ExecutionPlan.model_validate(EXAMPLE_PLAN)

        assert plan.plan_id == "plan-20260127-001"
        assert plan.version == "1.0"
        assert len(plan.tasks) == 3
        assert plan.summary == "Implement JWT-based authentication with login/register endpoints"

    def test_parse_minimal_plan(self):
        """Minimal valid plan should parse."""
        minimal = {
            "plan_id": "plan-001",
            "original_prompt": "Test prompt",
            "summary": "Test plan",
            "tasks": [
                {
                    "id": "task-001",
                    "title": "Test task",
                    "description": "Do something",
                    "agent_id": "coder",
                }
            ],
        }
        plan = ExecutionPlan.model_validate(minimal)

        assert plan.plan_id == "plan-001"
        assert len(plan.tasks) == 1
        assert plan.tasks[0].agent_id == "coder"

    def test_reject_empty_tasks(self):
        """Plan with no tasks should be rejected."""
        invalid = {
            "plan_id": "plan-001",
            "original_prompt": "Test",
            "summary": "Test",
            "tasks": [],
        }
        with pytest.raises(ValueError):
            ExecutionPlan.model_validate(invalid)

    def test_reject_invalid_agent_id(self):
        """Task with invalid agent_id should be rejected."""
        invalid = {
            "plan_id": "plan-001",
            "original_prompt": "Test",
            "summary": "Test",
            "tasks": [
                {
                    "id": "task-001",
                    "title": "Test",
                    "description": "Test",
                    "agent_id": "invalid_agent",
                }
            ],
        }
        with pytest.raises(ValueError, match="Unknown agent_id"):
            ExecutionPlan.model_validate(invalid)

    def test_reject_unknown_dependency(self):
        """Task depending on unknown task should be rejected."""
        invalid = {
            "plan_id": "plan-001",
            "original_prompt": "Test",
            "summary": "Test",
            "tasks": [
                {
                    "id": "task-001",
                    "title": "Test",
                    "description": "Test",
                    "agent_id": "coder",
                    "depends_on": ["task-999"],  # Doesn't exist
                }
            ],
        }
        with pytest.raises(ValueError, match="depends on unknown task"):
            ExecutionPlan.model_validate(invalid)

    def test_reject_self_dependency(self):
        """Task depending on itself should be rejected."""
        invalid_task = {
            "id": "task-001",
            "title": "Test",
            "description": "Test",
            "agent_id": "coder",
            "depends_on": ["task-001"],
        }
        with pytest.raises(ValueError, match="cannot depend on itself"):
            PlannedTask.model_validate(invalid_task)

    def test_parse_task_with_acceptance_criteria(self):
        """Task with acceptance criteria should parse."""
        task_data = {
            "id": "task-001",
            "title": "Test",
            "description": "Test",
            "agent_id": "coder",
            "acceptance": [
                {
                    "id": "ac-001",
                    "description": "Tests pass",
                    "verification_type": "test",
                    "command": "pytest tests/",
                    "required": True,
                },
                {
                    "id": "ac-002",
                    "description": "Code reviewed",
                    "verification_type": "manual",
                    "required": False,
                },
            ],
        }
        task = PlannedTask.model_validate(task_data)

        assert len(task.acceptance) == 2
        assert task.acceptance[0].verification_type == "test"
        assert task.acceptance[0].command == "pytest tests/"
        assert task.acceptance[1].required is False

    def test_get_root_tasks(self):
        """get_root_tasks should return tasks with no dependencies."""
        plan = ExecutionPlan.model_validate(EXAMPLE_PLAN)
        roots = plan.get_root_tasks()

        assert len(roots) == 1
        assert roots[0].id == "task-001"

    def test_get_dependents(self):
        """get_dependents should return tasks that depend on given task."""
        plan = ExecutionPlan.model_validate(EXAMPLE_PLAN)
        dependents = plan.get_dependents("task-001")

        assert len(dependents) == 1
        assert dependents[0].id == "task-002"

    def test_json_schema_export(self):
        """JSON schema should be exportable."""
        schema = get_plan_json_schema()

        assert "properties" in schema
        assert "tasks" in schema["properties"]
        assert "plan_id" in schema["properties"]


# =============================================================================
# Task Graph Tests
# =============================================================================

class TestTaskGraph:
    """Tests for DAG execution ordering."""

    def test_build_graph_from_plan(self):
        """Graph should build correctly from execution plan."""
        plan = ExecutionPlan.model_validate(EXAMPLE_PLAN)
        graph = TaskGraph(plan)

        assert len(graph.nodes) == 3
        assert "task-001" in graph.nodes
        assert "task-002" in graph.nodes
        assert "task-003" in graph.nodes

    def test_detect_cycle(self):
        """Graph should detect cycles."""
        cyclic_plan = {
            "plan_id": "plan-001",
            "original_prompt": "Test",
            "summary": "Test",
            "tasks": [
                {"id": "a", "title": "A", "description": "A", "agent_id": "coder", "depends_on": ["c"]},
                {"id": "b", "title": "B", "description": "B", "agent_id": "coder", "depends_on": ["a"]},
                {"id": "c", "title": "C", "description": "C", "agent_id": "coder", "depends_on": ["b"]},
            ],
        }
        plan = ExecutionPlan.model_validate(cyclic_plan)

        with pytest.raises(ValueError, match="cycle"):
            TaskGraph(plan)

    def test_topological_order(self):
        """Topological order should respect dependencies."""
        plan = ExecutionPlan.model_validate(EXAMPLE_PLAN)
        graph = TaskGraph(plan)

        order = list(graph.topological_order())

        # task-001 must come before task-002
        assert order.index("task-001") < order.index("task-002")
        # task-002 must come before task-003
        assert order.index("task-002") < order.index("task-003")

    def test_execution_levels(self):
        """Execution levels should group parallelizable tasks."""
        # Create a plan with parallel tasks
        parallel_plan = {
            "plan_id": "plan-001",
            "original_prompt": "Test",
            "summary": "Test",
            "tasks": [
                {"id": "root", "title": "Root", "description": "Root task", "agent_id": "architect"},
                {"id": "a", "title": "A", "description": "A", "agent_id": "coder", "depends_on": ["root"]},
                {"id": "b", "title": "B", "description": "B", "agent_id": "coder", "depends_on": ["root"]},
                {"id": "c", "title": "C", "description": "C", "agent_id": "coder", "depends_on": ["root"]},
                {"id": "final", "title": "Final", "description": "Final", "agent_id": "tester", "depends_on": ["a", "b", "c"]},
            ],
        }
        plan = ExecutionPlan.model_validate(parallel_plan)
        graph = TaskGraph(plan)

        levels = graph.execution_levels()

        assert len(levels) == 3
        assert levels[0] == ["root"]  # First level: root
        assert set(levels[1]) == {"a", "b", "c"}  # Second level: parallel tasks
        assert levels[2] == ["final"]  # Third level: final

    def test_ready_tasks_initialization(self):
        """Root tasks should be READY initially."""
        plan = ExecutionPlan.model_validate(EXAMPLE_PLAN)
        graph = TaskGraph(plan)

        ready = graph.get_ready_tasks()

        assert len(ready) == 1
        assert ready[0].task_id == "task-001"

    def test_mark_running(self):
        """mark_running should update status and timing."""
        plan = ExecutionPlan.model_validate(EXAMPLE_PLAN)
        graph = TaskGraph(plan)

        graph.mark_running("task-001")
        node = graph.get_node("task-001")

        assert node.status == TaskNodeStatus.RUNNING
        assert node.started_at is not None
        assert node.attempt == 1

    def test_mark_completed_updates_dependents(self):
        """Completing a task should make dependents ready."""
        plan = ExecutionPlan.model_validate(EXAMPLE_PLAN)
        graph = TaskGraph(plan)

        # Initially only root is ready
        assert len(graph.get_ready_tasks()) == 1

        # Run and complete root
        graph.mark_running("task-001")
        graph.mark_completed("task-001", {"result": "done"})

        # Now task-002 should be ready
        ready = graph.get_ready_tasks()
        assert len(ready) == 1
        assert ready[0].task_id == "task-002"

    def test_mark_failed_blocks_dependents(self):
        """Failing a task should block all dependents."""
        plan = ExecutionPlan.model_validate(EXAMPLE_PLAN)
        graph = TaskGraph(plan)

        graph.mark_running("task-001")
        graph.mark_failed("task-001", "Test failure")

        # task-002 should be blocked
        node_002 = graph.get_node("task-002")
        assert node_002.status == TaskNodeStatus.BLOCKED

        # task-003 should also be blocked (transitive)
        node_003 = graph.get_node("task-003")
        assert node_003.status == TaskNodeStatus.BLOCKED

    def test_retry_task(self):
        """Failed task should be retryable if under max attempts."""
        plan = ExecutionPlan.model_validate(EXAMPLE_PLAN)
        graph = TaskGraph(plan)

        graph.mark_running("task-001")
        graph.mark_failed("task-001", "First failure")

        assert graph.can_retry("task-001")

        graph.retry_task("task-001")
        node = graph.get_node("task-001")

        assert node.status == TaskNodeStatus.READY
        assert node.error is None

    def test_progress_calculation(self):
        """Progress should reflect completed tasks."""
        plan = ExecutionPlan.model_validate(EXAMPLE_PLAN)
        graph = TaskGraph(plan)

        assert graph.progress == 0.0

        # Complete first task
        graph.mark_running("task-001")
        graph.mark_completed("task-001")

        assert graph.progress == pytest.approx(1 / 3, rel=0.01)

    def test_serialization_roundtrip(self):
        """Graph state should survive serialization/deserialization."""
        plan = ExecutionPlan.model_validate(EXAMPLE_PLAN)
        graph = TaskGraph(plan)

        # Make some progress
        graph.mark_running("task-001")
        graph.mark_completed("task-001", {"result": "done"})

        # Serialize
        state = graph.to_dict()

        # Create new graph and restore
        new_graph = TaskGraph(plan)
        new_graph.restore_state(state)

        assert new_graph.get_node("task-001").status == TaskNodeStatus.COMPLETED
        assert new_graph.progress == graph.progress


# =============================================================================
# State Machine Tests
# =============================================================================

class TestStateMachine:
    """Tests for state machine transitions."""

    def test_valid_transitions(self):
        """Valid state transitions should succeed."""
        ctx = RunContext(run_id="test-001", config=RunConfig())

        # INTAKE -> PLAN
        assert ctx.can_transition_to(RunState.PLAN)
        ctx.transition_to(RunState.PLAN)
        assert ctx.state == RunState.PLAN

        # PLAN -> TASK_GRAPH
        assert ctx.can_transition_to(RunState.TASK_GRAPH)
        ctx.transition_to(RunState.TASK_GRAPH)
        assert ctx.state == RunState.TASK_GRAPH

    def test_invalid_transitions(self):
        """Invalid state transitions should raise."""
        ctx = RunContext(run_id="test-001", config=RunConfig())

        # INTAKE -> EXECUTE (skipping PLAN) should fail
        assert not ctx.can_transition_to(RunState.EXECUTE)

        with pytest.raises(ValueError, match="Invalid state transition"):
            ctx.transition_to(RunState.EXECUTE)

    def test_terminal_states_have_no_transitions(self):
        """Terminal states should have no valid transitions."""
        assert len(STATE_TRANSITIONS[RunState.DONE]) == 0
        assert len(STATE_TRANSITIONS[RunState.FAILED]) == 0
        assert len(STATE_TRANSITIONS[RunState.CANCELLED]) == 0

    def test_pause_resume_flow(self):
        """Pause and resume should work correctly."""
        ctx = RunContext(run_id="test-001", config=RunConfig())

        # Get to EXECUTE state
        ctx.transition_to(RunState.PLAN)
        ctx.transition_to(RunState.TASK_GRAPH)
        ctx.transition_to(RunState.EXECUTE)

        # Pause
        ctx.resume_state = ctx.state
        ctx.transition_to(RunState.PAUSED)
        assert ctx.state == RunState.PAUSED

        # Resume
        ctx.state = ctx.resume_state  # Simulated resume
        assert ctx.state == RunState.EXECUTE

    def test_on_state_change_callback(self):
        """State change callback should be called."""
        changes = []

        def on_change(old: RunState, new: RunState):
            changes.append((old, new))

        config = RunConfig(on_state_change=on_change)
        ctx = RunContext(run_id="test-001", config=config)

        ctx.transition_to(RunState.PLAN)
        ctx.transition_to(RunState.TASK_GRAPH)

        assert len(changes) == 2
        assert changes[0] == (RunState.INTAKE, RunState.PLAN)
        assert changes[1] == (RunState.PLAN, RunState.TASK_GRAPH)


# =============================================================================
# SSE Event Tests
# =============================================================================

class TestSSEEvents:
    """Tests for SSE event ordering and formatting."""

    def test_event_to_sse_format(self):
        """Events should format as valid SSE."""
        event = EngineEvent(
            type=EngineEventType.TASK_STARTED,
            run_id="run-001",
            data={"task_id": "task-001", "agent_id": "coder"},
        )

        sse = event.to_sse()

        assert sse.startswith("data: ")
        assert sse.endswith("\n\n")

        # Parse JSON
        json_str = sse.replace("data: ", "").strip()
        data = json.loads(json_str)

        assert data["type"] == "task_started"
        assert data["run_id"] == "run-001"
        assert data["task_id"] == "task-001"

    def test_event_to_dict(self):
        """Events should convert to dict correctly."""
        event = EngineEvent(
            type=EngineEventType.RUN_STATE,
            run_id="run-001",
            data={"state": "execute"},
        )

        d = event.to_dict()

        assert d["type"] == "run_state"
        assert d["run_id"] == "run-001"
        assert d["data"]["state"] == "execute"
        assert "timestamp" in d

    @pytest.mark.asyncio
    async def test_event_ordering_basic_flow(self):
        """Events should follow expected ordering in basic flow."""
        events = []

        # Mock the engine components
        with patch('app.autonomous.engine.DefaultPlanner') as MockPlanner, \
             patch('app.autonomous.engine.DefaultExecutor') as MockExecutor, \
             patch('app.autonomous.engine.DefaultVerifier') as MockVerifier:

            # Setup mock planner
            mock_planner = MagicMock()
            async def mock_create_plan(ctx):
                plan_data = {
                    "plan_id": "test-plan",
                    "original_prompt": ctx.original_prompt,
                    "summary": "Test plan",
                    "tasks": [
                        {"id": "t1", "title": "Task 1", "description": "Desc", "agent_id": "coder"}
                    ],
                }
                plan = ExecutionPlan.model_validate(plan_data)
                yield EngineEvent(
                    type=EngineEventType.PLANNING_COMPLETED,
                    run_id=ctx.run_id,
                    data={"plan": plan},
                )
            mock_planner.create_plan = mock_create_plan
            MockPlanner.return_value = mock_planner

            # Setup mock executor
            mock_executor = MagicMock()
            async def mock_execute(ctx, node, inputs, on_progress, on_output):
                on_progress(0.5)
                on_output("Working...")
                return {"success": True, "response": "Done"}
            mock_executor.execute_task = mock_execute
            MockExecutor.return_value = mock_executor

            # Setup mock verifier
            mock_verifier = MagicMock()
            async def mock_verify(ctx):
                yield EngineEvent(
                    type=EngineEventType.VERIFICATION_COMPLETED,
                    run_id=ctx.run_id,
                    data={"passed": True},
                )
            mock_verifier.verify = mock_verify
            MockVerifier.return_value = mock_verifier

            # Run engine
            engine = OrchestrationEngine()
            async for event in engine.run("Test prompt"):
                events.append(event.type)

        # Verify event ordering
        assert EngineEventType.RUN_STATE in events  # Should have state events
        assert events[0] == EngineEventType.RUN_STATE  # First event is state change

        # Check that certain events appear in order
        state_events = [e for e in events if e == EngineEventType.RUN_STATE]
        assert len(state_events) >= 3  # intake, plan, etc.


# =============================================================================
# Resume Capability Tests
# =============================================================================

class TestResumeCapability:
    """Tests for run persistence and resume hooks."""

    def test_context_serialization(self):
        """Run context should serialize for persistence."""
        plan_data = {
            "plan_id": "test-plan",
            "original_prompt": "Test",
            "summary": "Test",
            "tasks": [{"id": "t1", "title": "T1", "description": "D", "agent_id": "coder"}],
        }
        plan = ExecutionPlan.model_validate(plan_data)

        ctx = RunContext(
            run_id="run-001",
            config=RunConfig(),
            state=RunState.EXECUTE,
            original_prompt="Test prompt",
            workspace_path="/test/path",
        )
        ctx.plan = plan
        ctx.graph = TaskGraph(plan)
        ctx.graph.mark_running("t1")

        # Serialize
        state = ctx.to_dict()

        assert state["run_id"] == "run-001"
        assert state["state"] == "execute"
        assert state["plan"] is not None
        assert state["graph_state"] is not None

    def test_context_deserialization(self):
        """Run context should deserialize from saved state."""
        saved_state = {
            "run_id": "run-001",
            "state": "execute",
            "original_prompt": "Test prompt",
            "workspace_path": "/test/path",
            "started_at": "2026-01-27T10:00:00",
            "completed_at": None,
            "error": None,
            "error_details": None,
            "paused_at": None,
            "resume_state": None,
            "plan": {
                "plan_id": "test-plan",
                "version": "1.0",
                "original_prompt": "Test",
                "summary": "Test",
                "tasks": [{"id": "t1", "title": "T1", "description": "D", "agent_id": "coder"}],
            },
            "graph_state": {
                "nodes": {
                    "t1": {
                        "status": "running",
                        "result": None,
                        "error": None,
                        "logs": [],
                        "artifacts": {},
                        "started_at": "2026-01-27T10:01:00",
                        "completed_at": None,
                        "attempt": 1,
                        "verification_results": {},
                    }
                }
            },
        }

        ctx = RunContext.from_dict(saved_state)

        assert ctx.run_id == "run-001"
        assert ctx.state == RunState.EXECUTE
        assert ctx.plan is not None
        assert ctx.graph is not None
        assert ctx.graph.get_node("t1").status == TaskNodeStatus.RUNNING


# =============================================================================
# Project Detection Tests
# =============================================================================

class TestProjectDetection:
    """Tests for project mode detection."""

    def test_detect_explicit_project_trigger(self):
        """Explicit 'start a project' should trigger."""
        detector = ProjectDetector(enabled=True, threshold=0.75)

        result = detector.detect("Start a project to build a todo app")

        assert result.should_project is True
        assert result.confidence >= 0.75

    def test_detect_project_prefix(self):
        """'Project:' prefix should trigger."""
        detector = ProjectDetector(enabled=True, threshold=0.75)

        result = detector.detect("Project: implement user authentication system")

        assert result.should_project is True

    def test_no_trigger_for_questions(self):
        """Questions should not trigger project mode."""
        detector = ProjectDetector(enabled=True, threshold=0.75)

        result = detector.detect("What is the best way to implement auth?")

        assert result.should_project is False
        assert "question" in result.reason.lower() or result.confidence < 0.75

    def test_no_trigger_for_simple_tasks(self):
        """Simple tasks should not trigger project mode."""
        detector = ProjectDetector(enabled=True, threshold=0.75)

        result = detector.detect("Just a quick fix for the typo")

        assert result.should_project is False

    def test_disabled_detection(self):
        """Disabled detector should always return False."""
        detector = ProjectDetector(enabled=False)

        result = detector.detect("Start a project to build an app")

        assert result.should_project is False
        assert "disabled" in result.reason.lower()

    def test_extract_project_name(self):
        """Should extract project name from message."""
        detector = ProjectDetector(enabled=True)

        result = detector.detect("Build a todo app")

        assert result.suggested_name == "todo"

    def test_extract_workspace_path(self):
        """Should extract workspace path if mentioned."""
        detector = ProjectDetector(enabled=True)

        result = detector.detect("Create an app in /Users/dev/myproject")

        assert result.workspace_hint == "/Users/dev/myproject"
