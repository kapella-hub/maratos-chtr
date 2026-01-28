"""Integration tests for orchestration persistence.

Tests the full workflow: create run -> add tasks -> update status -> verify persisted.
Uses a file-based SQLite database to simulate restarts.
"""

import asyncio
import os
import pytest
import tempfile
import uuid
from pathlib import Path

# Set up test database BEFORE importing app modules
_tmpdir = tempfile.mkdtemp()
_db_path = Path(_tmpdir) / "test_persistence.db"
os.environ["MARATOS_DATABASE_URL"] = f"sqlite+aiosqlite:///{_db_path}"

# Now import app modules (after env var is set)
# This ensures the database module uses our test DB
from app.database import init_db, engine, Base

# Flag to track if DB is initialized
_db_initialized = False


def _ensure_db():
    """Synchronously ensure DB is initialized."""
    global _db_initialized
    if not _db_initialized:
        asyncio.get_event_loop().run_until_complete(init_db())
        _db_initialized = True


@pytest.fixture(scope="module")
def event_loop():
    """Create event loop for module scope."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    _ensure_db()  # Initialize DB when loop is created
    yield loop

    # Cleanup
    loop.run_until_complete(engine.dispose())
    loop.close()

    import shutil
    shutil.rmtree(_tmpdir, ignore_errors=True)


class TestPersistenceWorkflow:
    """Test the full persistence workflow."""

    @pytest.mark.asyncio
    async def test_create_run_persists(self, event_loop):
        """Create a run and verify it persists."""
        from app.autonomous.repositories import RunRepository

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        run = await RunRepository.create(
            run_id=run_id,
            original_prompt="Build a todo app with React",
            workspace_path="/tmp/test-workspace",
            session_id="test-session-123",
            mode="inline",
        )

        assert run.id == run_id
        assert run.original_prompt == "Build a todo app with React"
        assert run.state == "intake"

        # Verify we can retrieve it
        retrieved = await RunRepository.get(run_id)
        assert retrieved is not None
        assert retrieved.id == run_id
        assert retrieved.original_prompt == "Build a todo app with React"

    @pytest.mark.asyncio
    async def test_add_tasks_persists(self, event_loop):
        """Add tasks to a run and verify persistence."""
        from app.autonomous.repositories import RunRepository, TaskRepository

        # Create run
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        await RunRepository.create(
            run_id=run_id,
            original_prompt="Test prompt",
        )

        # Add tasks
        task1 = await TaskRepository.create(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            run_id=run_id,
            title="Design API schema",
            description="Create OpenAPI schema for todo endpoints",
            agent_id="architect",
        )

        task2 = await TaskRepository.create(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            run_id=run_id,
            title="Implement endpoints",
            description="Build CRUD endpoints",
            agent_id="coder",
            depends_on=[task1.id],
        )

        # Verify tasks persist
        tasks = await TaskRepository.get_by_run(run_id)
        assert len(tasks) == 2
        assert tasks[0].title == "Design API schema"
        assert tasks[1].depends_on == [task1.id]

    @pytest.mark.asyncio
    async def test_update_status_persists(self, event_loop):
        """Update task status and verify persistence."""
        from app.autonomous.repositories import RunRepository, TaskRepository

        # Create run and task
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        await RunRepository.create(run_id=run_id, original_prompt="Test")
        await TaskRepository.create(
            task_id=task_id,
            run_id=run_id,
            title="Test task",
            description="Test description",
            agent_id="coder",
        )

        # Update status
        await TaskRepository.update_status(task_id, "running")

        task = await TaskRepository.get(task_id)
        assert task.status == "running"
        assert task.started_at is not None

        # Complete the task
        await TaskRepository.update_status(task_id, "completed")
        await TaskRepository.update_result(task_id, "Task completed successfully")

        task = await TaskRepository.get(task_id)
        assert task.status == "completed"
        assert task.result == "Task completed successfully"
        assert task.completed_at is not None

    @pytest.mark.asyncio
    async def test_run_state_transitions(self, event_loop):
        """Test run state machine transitions persist."""
        from app.autonomous.repositories import RunRepository

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        await RunRepository.create(run_id=run_id, original_prompt="Test")

        # Transition through states
        states = ["plan", "task_graph", "execute", "verify", "done"]
        for state in states:
            await RunRepository.update_state(run_id, state)
            run = await RunRepository.get(run_id)
            assert run.state == state

    @pytest.mark.asyncio
    async def test_logs_persist(self, event_loop):
        """Test task logs persist."""
        from app.autonomous.repositories import RunRepository, TaskRepository, LogRepository

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        await RunRepository.create(run_id=run_id, original_prompt="Test")
        await TaskRepository.create(
            task_id=task_id,
            run_id=run_id,
            title="Test task",
            description="Test",
            agent_id="coder",
        )

        # Add logs
        await LogRepository.create(
            task_id=task_id,
            run_id=run_id,
            message="Starting task execution",
            level="info",
        )

        await LogRepository.create(
            task_id=task_id,
            run_id=run_id,
            message="Calling filesystem tool",
            level="debug",
            tool_name="filesystem",
            tool_input={"action": "read", "path": "/test"},
            tool_output="file contents",
            tool_duration_ms=50.5,
        )

        # Verify logs persist
        logs = await LogRepository.get_by_task(task_id)
        assert len(logs) == 2
        assert logs[0].message == "Starting task execution"

        # Verify audit trail
        audit = await LogRepository.get_tool_audit_trail(run_id)
        assert len(audit) == 1
        assert audit[0].tool_name == "filesystem"
        assert audit[0].tool_duration_ms == 50.5

    @pytest.mark.asyncio
    async def test_artifacts_persist(self, event_loop):
        """Test artifacts persist."""
        from app.autonomous.repositories import (
            RunRepository,
            TaskRepository,
            ArtifactRepository,
        )

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        await RunRepository.create(run_id=run_id, original_prompt="Test")
        await TaskRepository.create(
            task_id=task_id,
            run_id=run_id,
            title="Test task",
            description="Test",
            agent_id="coder",
        )

        # Create artifact
        artifact = await ArtifactRepository.create(
            task_id=task_id,
            run_id=run_id,
            name="api_schema.json",
            artifact_type="file",
            path="/workspace/api_schema.json",
            producer_agent="architect",
        )

        assert artifact.name == "api_schema.json"

        # Verify persistence
        artifacts = await ArtifactRepository.get_by_task(task_id)
        assert len(artifacts) == 1
        assert artifacts[0].artifact_type == "file"
        assert artifacts[0].producer_agent == "architect"

    @pytest.mark.asyncio
    async def test_full_state_serialization(self, event_loop):
        """Test full state can be serialized for resume."""
        from app.autonomous.repositories import RunRepository

        run_id = f"run-{uuid.uuid4().hex[:12]}"

        # Create run with plan
        await RunRepository.create(run_id=run_id, original_prompt="Build app")
        await RunRepository.update_plan(run_id, {
            "name": "Build App",
            "tasks": [
                {"id": "t1", "title": "Design", "agent_id": "architect"},
                {"id": "t2", "title": "Build", "agent_id": "coder", "depends_on": ["t1"]},
            ]
        })

        # Save graph state
        await RunRepository.update_graph_state(run_id, {
            "nodes": {"t1": {"status": "completed"}, "t2": {"status": "running"}},
            "completed": ["t1"],
        })

        # Pause
        await RunRepository.update_state(run_id, "paused")
        await RunRepository.set_resume_state(run_id, "execute")

        # Get full state
        state = await RunRepository.get_full_state(run_id)

        assert state is not None
        assert state["state"] == "paused"
        assert state["resume_state"] == "execute"
        assert state["plan"]["name"] == "Build App"
        assert len(state["plan"]["tasks"]) == 2
        assert state["graph_state"]["completed"] == ["t1"]


class TestSimulatedRestart:
    """Test that data survives simulated server restart."""

    @pytest.mark.asyncio
    async def test_data_survives_new_session(self, event_loop):
        """Data should be retrievable after creating new repository instances."""
        from app.autonomous.repositories import RunRepository, TaskRepository

        # Create data in "first session"
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        task_id = f"task-{uuid.uuid4().hex[:8]}"

        await RunRepository.create(
            run_id=run_id,
            original_prompt="Persistent test",
            workspace_path="/test",
            mode="autonomous",
        )
        await TaskRepository.create(
            task_id=task_id,
            run_id=run_id,
            title="Persistent task",
            description="Should survive restart",
            agent_id="coder",
        )
        await TaskRepository.update_status(task_id, "completed")

        # Query with fresh call (simulates restart)
        run = await RunRepository.get(run_id)
        assert run is not None
        assert run.original_prompt == "Persistent test"
        assert run.mode == "autonomous"

        tasks = await TaskRepository.get_by_run(run_id)
        assert len(tasks) == 1
        assert tasks[0].status == "completed"

    @pytest.mark.asyncio
    async def test_interrupted_runs_query(self, event_loop):
        """Query for interrupted runs should work."""
        from app.autonomous.repositories import RunRepository

        # Create an "interrupted" run (in execute state)
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        await RunRepository.create(run_id=run_id, original_prompt="Interrupted run")
        await RunRepository.update_state(run_id, "execute")

        # Query active runs
        active = await RunRepository.list_active()
        assert any(r.id == run_id for r in active)

        # The run should be in execute state
        run = await RunRepository.get(run_id)
        assert run.state == "execute"


class TestTaskSummary:
    """Test task summary aggregation."""

    @pytest.mark.asyncio
    async def test_task_summary(self, event_loop):
        """Task summary should correctly aggregate statuses."""
        from app.autonomous.repositories import RunRepository, TaskRepository

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        await RunRepository.create(run_id=run_id, original_prompt="Test")

        # Create tasks with different statuses
        for i, status in enumerate(["completed", "completed", "running", "pending", "failed"]):
            task_id = f"task-{uuid.uuid4().hex[:8]}"
            await TaskRepository.create(
                task_id=task_id,
                run_id=run_id,
                title=f"Task {i}",
                description="Test",
                agent_id="coder",
            )
            if status != "pending":
                await TaskRepository.update_status(task_id, status)

        summary = await TaskRepository.get_task_summary(run_id)

        assert summary["total"] == 5
        assert summary["completed"] == 2
        assert summary["running"] == 1
        assert summary["pending"] == 1
        assert summary["failed"] == 1


class TestProjectManagerDBBacked:
    """Test the DB-backed ProjectManager."""

    @pytest.mark.asyncio
    async def test_project_manager_create_and_get(self, event_loop):
        """ProjectManager should persist to DB."""
        from app.autonomous.project_manager import ProjectManager
        from app.autonomous.models import ProjectConfig

        pm = ProjectManager()

        # Create project
        project = await pm.create_project(
            name="Test Project",
            prompt="Build a test application",
            workspace_path="/tmp/test",
            config=ProjectConfig(),
        )

        assert project.id is not None

        # Get project (should read from DB)
        retrieved = await pm.get(project.id)
        assert retrieved is not None
        assert retrieved.original_prompt == "Build a test application"

    @pytest.mark.asyncio
    async def test_project_manager_tasks(self, event_loop):
        """ProjectManager should return tasks from DB."""
        from app.autonomous.project_manager import ProjectManager
        from app.autonomous.repositories import TaskRepository

        pm = ProjectManager()

        project = await pm.create_project(
            name="Task Test",
            prompt="Build something",
            workspace_path="/tmp/test",
        )

        run_id = f"run-{project.id}"

        # Add tasks directly via repository
        await TaskRepository.create(
            task_id=f"task-{uuid.uuid4().hex[:8]}",
            run_id=run_id,
            title="First task",
            description="Do something",
            agent_id="coder",
        )

        # Get tasks via project manager
        tasks = await pm.get_project_tasks(project.id)
        assert len(tasks) == 1
        assert tasks[0]["title"] == "First task"
