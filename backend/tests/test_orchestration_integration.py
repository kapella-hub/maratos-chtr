"""Integration tests for agent orchestration.

Tests the full spawn → execute → report back flow.
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

from app.subagents.manager import SubagentManager, SubagentTask, TaskStatus, GoalStatus
from app.subagents.runner import SubagentRunner, parse_goals, parse_goal_completions


class TestSpawnExecuteReportFlow:
    """Test the complete spawn → execute → report back flow."""

    @pytest.fixture
    def manager(self):
        """Create a fresh SubagentManager."""
        return SubagentManager()

    @pytest.mark.asyncio
    async def test_basic_spawn_execute_complete(self, manager):
        """Test basic task spawning, execution, and completion."""
        completed = asyncio.Event()
        result_data = {"test": "result"}

        async def work_fn(task: SubagentTask):
            task.log("Starting work")
            task.progress = 0.5
            await asyncio.sleep(0.01)
            task.progress = 0.9
            completed.set()
            return result_data

        task = await manager.spawn(
            name="Test Task",
            description="A test task",
            agent_id="coder",
            work_fn=work_fn,
            max_attempts=1,
            timeout_seconds=10.0,
        )

        assert task.agent_id == "coder"

        # Wait for task to start (status changes from PENDING to RUNNING)
        for _ in range(50):
            await asyncio.sleep(0.01)
            if task.status != TaskStatus.PENDING:
                break

        # Should be running or already completed
        assert task.status in (TaskStatus.RUNNING, TaskStatus.COMPLETED)

        # Wait for completion
        await asyncio.wait_for(completed.wait(), timeout=5.0)
        await asyncio.sleep(0.1)  # Let task finish

        # Verify completion
        assert task.status == TaskStatus.COMPLETED
        assert task.result == result_data
        assert task.progress == 1.0

    @pytest.mark.asyncio
    async def test_task_with_goals(self, manager):
        """Test task execution with sub-goals."""
        completed = asyncio.Event()

        async def work_fn(task: SubagentTask):
            # Add goals
            task.add_goal(1, "Initialize project")
            task.add_goal(2, "Write code")
            task.add_goal(3, "Run tests")

            # Complete goals
            task.start_goal(1)
            await asyncio.sleep(0.01)
            task.complete_goal(1)

            task.start_goal(2)
            await asyncio.sleep(0.01)
            task.complete_goal(2)

            task.start_goal(3)
            await asyncio.sleep(0.01)
            task.complete_goal(3)

            completed.set()
            return {"goals_completed": 3}

        task = await manager.spawn(
            name="Task with Goals",
            description="Task with multiple goals",
            agent_id="coder",
            work_fn=work_fn,
        )

        await asyncio.wait_for(completed.wait(), timeout=5.0)
        await asyncio.sleep(0.1)

        assert task.status == TaskStatus.COMPLETED
        assert len(task.goals) == 3
        assert all(g.status == GoalStatus.COMPLETED for g in task.goals)

    @pytest.mark.asyncio
    async def test_task_with_checkpoints(self, manager):
        """Test task with checkpoint tracking."""
        completed = asyncio.Event()

        async def work_fn(task: SubagentTask):
            task.add_checkpoint("setup", "Project setup complete")
            await asyncio.sleep(0.01)
            task.add_checkpoint("code", "Code written")
            await asyncio.sleep(0.01)
            task.add_checkpoint("test", "Tests passed")
            completed.set()
            return {"checkpoints": 3}

        task = await manager.spawn(
            name="Task with Checkpoints",
            description="Task with checkpoints",
            agent_id="coder",
            work_fn=work_fn,
        )

        await asyncio.wait_for(completed.wait(), timeout=5.0)
        await asyncio.sleep(0.1)

        assert len(task.checkpoints) == 3
        assert task.checkpoints[0].name == "setup"
        assert task.checkpoints[2].name == "test"

    @pytest.mark.asyncio
    async def test_task_failure_and_retry(self, manager):
        """Test task failure with retry attempts."""
        attempt_count = 0

        async def work_fn(task: SubagentTask):
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 2:
                raise Exception("Simulated failure")
            return {"success": True}

        task = await manager.spawn(
            name="Retry Task",
            description="Task that fails first",
            agent_id="coder",
            work_fn=work_fn,
            max_attempts=3,
            timeout_seconds=5.0,
        )

        # Wait for task completion
        for _ in range(50):
            await asyncio.sleep(0.1)
            if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                break

        assert task.status == TaskStatus.COMPLETED
        assert attempt_count == 2

    @pytest.mark.asyncio
    async def test_task_timeout(self, manager):
        """Test task timeout handling."""
        async def slow_work_fn(task: SubagentTask):
            await asyncio.sleep(10)  # Will timeout
            return {"never": "reached"}

        task = await manager.spawn(
            name="Slow Task",
            description="Task that times out",
            agent_id="coder",
            work_fn=slow_work_fn,
            max_attempts=1,
            timeout_seconds=0.1,  # Very short timeout
        )

        # Wait for timeout
        for _ in range(30):
            await asyncio.sleep(0.1)
            if task.status in (TaskStatus.TIMED_OUT, TaskStatus.FAILED):
                break

        assert task.status in (TaskStatus.TIMED_OUT, TaskStatus.FAILED)


class TestParallelAgentExecution:
    """Test parallel execution of multiple agents."""

    @pytest.fixture
    def manager(self):
        return SubagentManager()

    @pytest.mark.asyncio
    async def test_parallel_task_execution(self, manager):
        """Test that multiple tasks run in parallel."""
        start_times = {}
        end_times = {}

        async def make_work_fn(task_name: str):
            async def work_fn(task: SubagentTask):
                start_times[task_name] = datetime.now()
                await asyncio.sleep(0.1)
                end_times[task_name] = datetime.now()
                return {"task": task_name}
            return work_fn

        # Spawn multiple tasks
        tasks = []
        for i, agent in enumerate(["coder", "reviewer", "tester"]):
            task = await manager.spawn(
                name=f"Task {i}",
                description=f"Parallel task {i}",
                agent_id=agent,
                work_fn=await make_work_fn(agent),
            )
            tasks.append(task)

        # Wait for all to complete
        for _ in range(50):
            await asyncio.sleep(0.1)
            if all(t.status == TaskStatus.COMPLETED for t in tasks):
                break

        # Verify all completed
        assert all(t.status == TaskStatus.COMPLETED for t in tasks)

        # Verify they ran in parallel (start times should be close)
        starts = list(start_times.values())
        if len(starts) >= 2:
            time_diff = (max(starts) - min(starts)).total_seconds()
            assert time_diff < 0.5, "Tasks should start nearly simultaneously"

    @pytest.mark.asyncio
    async def test_running_count_tracking(self, manager):
        """Test that running task count is tracked correctly."""
        blockers = []

        async def blocking_work(task: SubagentTask):
            event = asyncio.Event()
            blockers.append(event)
            await event.wait()
            return {}

        # Spawn 3 tasks
        for i in range(3):
            await manager.spawn(
                name=f"Blocking {i}",
                description="Blocks until released",
                agent_id="coder",
                work_fn=blocking_work,
            )

        await asyncio.sleep(0.1)
        assert manager.get_running_count() == 3

        # Release one
        blockers[0].set()
        await asyncio.sleep(0.1)
        assert manager.get_running_count() == 2

        # Release rest
        for b in blockers[1:]:
            b.set()
        await asyncio.sleep(0.1)
        assert manager.get_running_count() == 0


class TestSequentialDependentTasks:
    """Test sequential task execution with dependencies."""

    @pytest.fixture
    def runner(self):
        return SubagentRunner()

    @pytest.mark.asyncio
    async def test_sequential_task_chain(self):
        """Test that tasks can be chained sequentially."""
        execution_order = []

        manager = SubagentManager()

        async def task_a(task: SubagentTask):
            execution_order.append("A")
            await asyncio.sleep(0.05)
            return {"step": "A"}

        async def task_b(task: SubagentTask):
            execution_order.append("B")
            await asyncio.sleep(0.05)
            return {"step": "B"}

        async def task_c(task: SubagentTask):
            execution_order.append("C")
            return {"step": "C"}

        # Helper to wait for task completion
        async def wait_for_completion(task, timeout=5.0):
            for _ in range(int(timeout / 0.05)):
                await asyncio.sleep(0.05)
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    break

        # Run sequentially
        t1 = await manager.spawn("Task A", "First", "coder", task_a)
        await wait_for_completion(t1)

        t2 = await manager.spawn("Task B", "Second", "reviewer", task_b)
        await wait_for_completion(t2)

        t3 = await manager.spawn("Task C", "Third", "tester", task_c)
        await wait_for_completion(t3)

        assert execution_order == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_task_result_passed_to_next(self):
        """Test that task results can be used by subsequent tasks."""
        manager = SubagentManager()
        shared_context = {}

        async def producer(task: SubagentTask):
            result = {"produced_value": 42}
            shared_context["producer_result"] = result
            return result

        async def consumer(task: SubagentTask):
            producer_result = shared_context.get("producer_result", {})
            return {"consumed": producer_result.get("produced_value", 0) * 2}

        # Helper to wait for task completion
        async def wait_for_completion(task, timeout=5.0):
            for _ in range(int(timeout / 0.05)):
                await asyncio.sleep(0.05)
                if task.status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    break

        t1 = await manager.spawn("Producer", "Produces value", "coder", producer)
        await wait_for_completion(t1)

        assert t1.status == TaskStatus.COMPLETED
        assert t1.result == {"produced_value": 42}

        t2 = await manager.spawn("Consumer", "Consumes value", "reviewer", consumer)
        await wait_for_completion(t2)

        assert t2.status == TaskStatus.COMPLETED
        assert t2.result == {"consumed": 84}


class TestGoalParsing:
    """Test goal marker parsing from agent responses."""

    def test_parse_single_goal(self):
        """Test parsing a single goal marker."""
        text = "[GOAL:1] Initialize the project structure"
        task = SubagentTask(
            id="test", name="Test", description="Test", agent_id="coder"
        )

        parse_goals(text, task)

        assert len(task.goals) == 1
        assert task.goals[0].id == 1
        assert "Initialize" in task.goals[0].description

    def test_parse_multiple_goals(self):
        """Test parsing multiple goal markers."""
        text = """
        [GOAL:1] Setup environment
        Working on setup...
        [GOAL:2] Write implementation
        Implementing...
        [GOAL:3] Add tests
        """
        task = SubagentTask(
            id="test", name="Test", description="Test", agent_id="coder"
        )

        parse_goals(text, task)

        assert len(task.goals) == 3
        assert task.goals[0].id == 1
        assert task.goals[1].id == 2
        assert task.goals[2].id == 3

    def test_parse_goal_completions(self):
        """Test parsing goal completion markers."""
        text = "[GOAL_DONE:1][GOAL_DONE:2]"
        task = SubagentTask(
            id="test", name="Test", description="Test", agent_id="coder"
        )
        task.add_goal(1, "Goal 1")
        task.add_goal(2, "Goal 2")
        task.add_goal(3, "Goal 3")

        parse_goal_completions(text, task)

        assert task.goals[0].status == GoalStatus.COMPLETED
        assert task.goals[1].status == GoalStatus.COMPLETED
        assert task.goals[2].status == GoalStatus.PENDING


class TestMockedAgentExecution:
    """Test agent execution with mocked responses."""

    @pytest.mark.asyncio
    async def test_mocked_coder_response(self):
        """Test with mocked coder agent response."""
        manager = SubagentManager()

        mock_response = """
        [GOAL:1] Analyze requirements
        Analyzing the task requirements...
        [GOAL_DONE:1]

        [GOAL:2] Write implementation
        ```python
        def hello():
            print("Hello, World!")
        ```
        [GOAL_DONE:2]

        [CHECKPOINT:code_written] Implementation complete

        [GOAL:3] Verify code
        Code verified successfully.
        [GOAL_DONE:3]
        """

        async def mocked_work(task: SubagentTask):
            # Simulate streaming response
            for chunk in mock_response.split("\n"):
                task.response_so_far += chunk + "\n"
                await asyncio.sleep(0.01)

            # Parse the final response
            parse_goals(task.response_so_far, task)
            parse_goal_completions(task.response_so_far, task)

            return {"response": task.response_so_far}

        task = await manager.spawn(
            name="Mocked Coder",
            description="Write hello world",
            agent_id="coder",
            work_fn=mocked_work,
        )

        # Wait for completion
        for _ in range(50):
            await asyncio.sleep(0.1)
            if task.status == TaskStatus.COMPLETED:
                break

        assert task.status == TaskStatus.COMPLETED
        assert len(task.goals) == 3
        completed_goals = sum(1 for g in task.goals if g.status == GoalStatus.COMPLETED)
        assert completed_goals == 3

    @pytest.mark.asyncio
    async def test_mocked_reviewer_response(self):
        """Test with mocked reviewer agent response."""
        manager = SubagentManager()

        mock_response = """
        [GOAL:1] Review code structure
        Code structure looks good.
        [GOAL_DONE:1]

        [GOAL:2] Check for security issues
        No security issues found.
        [GOAL_DONE:2]

        [CHECKPOINT:review_complete] Code review finished

        Summary: Code approved with no issues.
        """

        async def mocked_work(task: SubagentTask):
            task.response_so_far = mock_response
            parse_goals(mock_response, task)
            parse_goal_completions(mock_response, task)
            return {"approved": True}

        task = await manager.spawn(
            name="Mocked Reviewer",
            description="Review code",
            agent_id="reviewer",
            work_fn=mocked_work,
        )

        for _ in range(50):
            await asyncio.sleep(0.1)
            if task.status == TaskStatus.COMPLETED:
                break

        assert task.status == TaskStatus.COMPLETED
        assert task.result["approved"] is True


class TestTaskCancellation:
    """Test task cancellation scenarios."""

    @pytest.mark.asyncio
    async def test_cancel_running_task(self):
        """Test cancelling a running task."""
        manager = SubagentManager()

        async def long_running(task: SubagentTask):
            for i in range(100):
                await asyncio.sleep(0.1)
                task.progress = i / 100
            return {}

        task = await manager.spawn(
            name="Long Running",
            description="Takes a long time",
            agent_id="coder",
            work_fn=long_running,
        )

        await asyncio.sleep(0.2)
        assert task.status == TaskStatus.RUNNING

        # Cancel the task
        cancelled = await manager.cancel(task.id)
        assert cancelled is True

        await asyncio.sleep(0.2)
        assert task.status == TaskStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_all_tasks(self):
        """Test cancelling all running tasks."""
        manager = SubagentManager()

        async def work_fn(task: SubagentTask):
            await asyncio.sleep(10)
            return {}

        # Spawn multiple tasks
        for i in range(3):
            await manager.spawn(f"Task {i}", f"Description {i}", "coder", work_fn)

        await asyncio.sleep(0.1)
        assert manager.get_running_count() == 3

        cancelled = await manager.cancel_all()
        assert cancelled == 3

        await asyncio.sleep(0.2)
        assert manager.get_running_count() == 0
