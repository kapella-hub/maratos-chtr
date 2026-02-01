"""Orchestrator engine for autonomous development projects."""

import asyncio
import json
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncIterator

from app.autonomous.models import (
    ProjectPlan,
    ProjectTask,
    ProjectConfig,
    ProjectStatus,
    AutonomousTaskStatus,
    QualityGate,
    QualityGateType,
    TaskIteration,
)
from app.autonomous.git_ops import GitOperations
from app.autonomous.model_selector import (
    model_selector,
    get_model_config_for_task,
    ModelTier,
)
from app.autonomous.repositories import (
    RunRepository,
    TaskRepository,
    LogRepository,
    ArtifactRepository,
)

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Orchestrator event types."""
    PROJECT_STARTED = "project_started"
    PLANNING_STARTED = "planning_started"
    MODEL_SELECTED = "model_selected"
    TASK_CREATED = "task_created"
    PLANNING_COMPLETED = "planning_completed"
    TASK_STARTED = "task_started"
    TASK_PROGRESS = "task_progress"
    TASK_AGENT_OUTPUT = "task_agent_output"
    QUALITY_GATE_CHECK = "quality_gate_check"
    QUALITY_GATE_PASSED = "quality_gate_passed"
    QUALITY_GATE_FAILED = "quality_gate_failed"
    TASK_FIXING = "task_fixing"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    GIT_COMMIT = "git_commit"
    GIT_PUSH = "git_push"
    GIT_PR_CREATED = "git_pr_created"
    PAUSED = "paused"
    RESUMED = "resumed"
    TIMEOUT = "timeout"
    PROJECT_COMPLETED = "project_completed"
    PROJECT_FAILED = "project_failed"
    ERROR = "error"


@dataclass
class OrchestratorEvent:
    """An event emitted by the orchestrator."""
    type: EventType
    project_id: str
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.value,
            "project_id": self.project_id,
            "data": self.data,
            "timestamp": self.timestamp.isoformat(),
        }

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        return f"data: {json.dumps(self.to_dict())}\n\n"


class Orchestrator:
    """Main orchestration engine for autonomous development."""

    def __init__(self, project: ProjectPlan) -> None:
        self.project = project
        self.git = GitOperations(project.workspace_path)
        self._paused = False
        self._cancelled = False
        self._start_time: datetime | None = None

    @classmethod
    async def load(cls, run_id: str) -> "Orchestrator | None":
        """Load an orchestrator from a persisted run."""
        # Load run
        run = await RunRepository.get(run_id)
        if not run:
            return None
            
        # Load tasks
        db_tasks = await TaskRepository.get_by_run(run_id)
        
        # Reconstruct tasks
        tasks = []
        for t in db_tasks:
            task = ProjectTask(
                id=t.id,
                title=t.title,
                description=t.description,
                agent_type=t.agent_id, # Remapped from agent_id
                status=AutonomousTaskStatus(t.status),
                depends_on=t.depends_on or [],
                target_files=t.target_files or [],
                priority=t.priority,
            )
            # Restore verification results
            if t.verification_results:
                task.iterations.append(TaskIteration(
                    attempt=t.attempt,
                    started_at=t.started_at or datetime.now(),
                    completed_at=t.completed_at,
                    success=t.status == "completed",
                    agent_response=t.result or "",
                    quality_results=t.verification_results
                ))
            tasks.append(task)
            
        # Reconstruct Plan
        plan = ProjectPlan(
            id=run.id,
            name=f"Run {run.id[:8]}", # Name might be lost if not stored
            original_prompt=run.original_prompt,
            workspace_path=run.workspace_path or "/tmp",
            status=ProjectStatus.IN_PROGRESS if run.state != "done" else ProjectStatus.COMPLETED,
            tasks=tasks,
            config=ProjectConfig.from_dict(run.config_json or {})
        )
        
        return cls(plan)

    async def start(self) -> AsyncIterator[OrchestratorEvent]:
        """Start the autonomous development process."""
        self._start_time = datetime.now()
        self.project.started_at = self._start_time
        self.project.status = ProjectStatus.PLANNING

        yield self._event(EventType.PROJECT_STARTED)

        # Persistence: Create run record
        try:
            await RunRepository.create(
                run_id=self.project.id,
                original_prompt=self.project.original_prompt,
                workspace_path=self.project.workspace_path,
                config=self.project.config.to_dict(),
            )
        except Exception as e:
            logger.error(f"Failed to persist run creation: {e}")

        try:
            # Phase 1: Planning
            yield self._event(EventType.PLANNING_STARTED)
            async for event in self._run_planning():
                yield event

            if self._cancelled:
                return

            yield self._event(EventType.PLANNING_COMPLETED, {
                "task_count": len(self.project.tasks),
            })

            # Initialize git if needed
            if not await self.git.is_git_repo():
                await self.git.init()

            # Create feature branch if configured
            if self.project.config.auto_commit:
                branch_name = f"auto/{self.project.id}-{self._sanitize_branch_name(self.project.name)}"
                await self.git.create_branch(branch_name)
                self.project.branch_name = branch_name

            # Phase 2: Execution loop
            self.project.status = ProjectStatus.IN_PROGRESS
            async for event in self._run_execution_loop():
                yield event

            if self._cancelled:
                return

            # Phase 3: Finalization
            async for event in self._run_finalization():
                yield event

            # Mark complete
            self.project.status = ProjectStatus.COMPLETED
            self.project.completed_at = datetime.now()
            yield self._event(EventType.PROJECT_COMPLETED, {
                "pr_url": self.project.pr_url,
            })

            # Persistence: Mark run completed
            await RunRepository.update_state("done")

        except asyncio.CancelledError:
            self._cancelled = True
            self.project.status = ProjectStatus.CANCELLED
            logger.info(f"Project {self.project.id} cancelled")
            
            # Persistence: Mark cancelled
            await RunRepository.update_state(self.project.id, "cancelled")

        except Exception as e:
            logger.error(f"Orchestrator error: {e}", exc_info=True)
            self.project.status = ProjectStatus.FAILED
            self.project.error = str(e)
            self.project.completed_at = datetime.now()
            yield self._event(EventType.PROJECT_FAILED, {"error": str(e)})

            # Persistence: Mark failed
            await RunRepository.update_state(
                self.project.id, 
                "failed", 
                error=str(e)
            )

    async def _run_planning(self) -> AsyncIterator[OrchestratorEvent]:
        """Run the planning phase using the architect agent."""
        from app.agents import agent_registry
        from app.agents.base import Message

        architect = agent_registry.get("architect")
        if not architect:
            raise ValueError("Architect agent not found")

        # Build planning prompt
        planning_prompt = f"""Analyze this development request and create a detailed task breakdown.

## Request
{self.project.original_prompt}

## Workspace
{self.project.workspace_path}

## Instructions
1. Break down the work into discrete tasks
2. Identify dependencies between tasks
3. For each task, specify:
   - A clear title
   - A detailed description of what needs to be done
   - The agent type that should handle it (coder, tester, reviewer, docs, devops)
   - Any quality gates needed (tests_pass, review_approved, lint_clean)
   - Dependencies on other tasks (by task number)
   - Files that will be created or modified

## Output Format
Return your analysis as a JSON array of tasks:
```json
[
  {{
    "title": "Task title",
    "description": "Detailed description",
    "agent_type": "coder",
    "quality_gates": ["tests_pass"],
    "depends_on": [],
    "target_files": ["src/main.py"]
  }},
  ...
]
```

Be thorough but practical. Include testing and documentation tasks. Number dependencies by their position in the array (0-indexed).
"""

        messages = [Message(role="user", content=planning_prompt)]

        # Get the most capable model for planning (critical phase)
        planning_model = model_selector.models[ModelTier.TIER_1_ADVANCED]
        logger.info(f"Planning with model: {planning_model.model_id}")

        # Emit model selection event
        yield self._event(EventType.MODEL_SELECTED, {
            "phase": "planning",
            "model": planning_model.model_id,
            "reason": "Architecture planning requires advanced reasoning",
        })

        # Run architect with advanced model
        response_text = ""
        async for chunk in architect.chat(
            messages,
            {"workspace": self.project.workspace_path},
            model_override=planning_model.model_id,
            temperature_override=planning_model.temperature,
            max_tokens_override=planning_model.max_tokens,
        ):
            response_text += chunk

        # Parse tasks from response
        tasks = self._parse_task_list(response_text)

        for task in tasks:
            self.project.tasks.append(task)
            yield self._event(EventType.TASK_CREATED, {
                "task_id": task.id,
                "task": task.to_dict(),
            })

        # Persistence: Save created tasks
        try:
            task_dicts = []
            for t in tasks:
                 d = t.to_dict()
                 d["run_id"] = self.project.id
                 d["agent_id"] = t.agent_type # Map type to ID for now
                 task_dicts.append(d)
            
            await TaskRepository.create_many(task_dicts)
            
            # Update state to execution
            await RunRepository.update_state(self.project.id, "planning_complete")
            
        except Exception as e:
            logger.error(f"Failed to persist tasks: {e}")

    def _parse_task_list(self, response: str) -> list[ProjectTask]:
        """Parse task list from architect response."""
        tasks = []

        # Try to find JSON in the response
        json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
        if not json_match:
            # Try without code fence
            json_match = re.search(r'\[\s*\{[\s\S]*\}\s*\]', response)

        if json_match:
            try:
                json_str = json_match.group(1) if '```' in response else json_match.group(0)
                task_data = json.loads(json_str)

                for i, data in enumerate(task_data):
                    task_id = str(uuid.uuid4())[:8]

                    # Parse quality gates
                    quality_gates = []
                    for gate_type in data.get("quality_gates", []):
                        try:
                            gate = QualityGate(type=QualityGateType(gate_type))
                            quality_gates.append(gate)
                        except ValueError:
                            logger.warning(f"Unknown quality gate type: {gate_type}")

                    # Parse dependencies (convert indices to task IDs)
                    depends_on = []
                    for dep in data.get("depends_on", []):
                        if isinstance(dep, int) and dep < len(tasks):
                            depends_on.append(tasks[dep].id)
                        elif isinstance(dep, str):
                            # Might be a task ID or index string
                            try:
                                dep_idx = int(dep)
                                if dep_idx < len(tasks):
                                    depends_on.append(tasks[dep_idx].id)
                            except ValueError:
                                depends_on.append(dep)

                    task = ProjectTask(
                        id=task_id,
                        title=data.get("title", f"Task {i + 1}"),
                        description=data.get("description", ""),
                        agent_type=data.get("agent_type", "coder"),
                        quality_gates=quality_gates,
                        depends_on=depends_on,
                        target_files=data.get("target_files", []),
                        priority=len(task_data) - i,  # Earlier tasks have higher priority
                    )
                    tasks.append(task)

            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse task JSON: {e}")

        # If no tasks found, create a default task
        if not tasks:
            tasks.append(ProjectTask(
                id=str(uuid.uuid4())[:8],
                title="Implement request",
                description=self.project.original_prompt,
                agent_type="coder",
            ))

        return tasks

    async def _run_execution_loop(self) -> AsyncIterator[OrchestratorEvent]:
        """Run the main execution loop."""
        while not self._is_complete() and not self._is_timeout():
            if self._cancelled:
                return

            # Handle pause
            while self._paused:
                yield self._event(EventType.PAUSED)
                await asyncio.sleep(1)
                if self._cancelled:
                    return
                if not self._paused:
                    yield self._event(EventType.RESUMED)

            # Get ready tasks
            ready_tasks = self.project.get_ready_tasks()
            if not ready_tasks:
                # Check if blocked
                if self._has_pending_tasks():
                    self.project.status = ProjectStatus.BLOCKED
                    await asyncio.sleep(2)  # Wait before rechecking
                    continue
                else:
                    # All done
                    break

            # Run ready tasks (up to max parallel)
            max_parallel = self.project.config.parallel_tasks
            tasks_to_run = ready_tasks[:max_parallel]

            # Run tasks concurrently
            async for event in self._run_tasks_parallel(tasks_to_run):
                yield event

    async def _run_tasks_parallel(self, tasks: list[ProjectTask]) -> AsyncIterator[OrchestratorEvent]:
        """Run multiple tasks in parallel."""
        if len(tasks) == 1:
            async for event in self._run_task_with_feedback(tasks[0]):
                yield event
        else:
            # Create queues for each task
            queues: list[asyncio.Queue[OrchestratorEvent | None]] = [
                asyncio.Queue() for _ in tasks
            ]

            async def run_and_queue(task: ProjectTask, queue: asyncio.Queue):
                try:
                    async for event in self._run_task_with_feedback(task):
                        await queue.put(event)
                except Exception as e:
                    await queue.put(self._event(EventType.ERROR, {
                        "task_id": task.id,
                        "error": str(e),
                    }))
                finally:
                    await queue.put(None)  # Signal done

            # Start all tasks
            runners = [
                asyncio.create_task(run_and_queue(task, queue))
                for task, queue in zip(tasks, queues)
            ]

            # Yield events from all queues until all done
            active = set(range(len(queues)))
            while active:
                for i in list(active):
                    try:
                        event = queues[i].get_nowait()
                        if event is None:
                            active.discard(i)
                        else:
                            yield event
                    except asyncio.QueueEmpty:
                        pass
                await asyncio.sleep(0.1)

            # Wait for all runners to complete
            await asyncio.gather(*runners, return_exceptions=True)

    async def _run_task_with_feedback(self, task: ProjectTask) -> AsyncIterator[OrchestratorEvent]:
        """Run a task with feedback loop for quality gates."""
        task.status = AutonomousTaskStatus.IN_PROGRESS
        task.started_at = datetime.now()

        # Persistence: Task started
        await TaskRepository.update_status(task.id, "running")

        # Get model info for this task
        gate_types = [g.type.value for g in task.quality_gates]
        task_model = get_model_config_for_task(
            agent_type=task.agent_type,
            task_description=task.description,
            quality_gates=gate_types,
        )

        yield self._event(EventType.TASK_STARTED, {
            "task_id": task.id,
            "title": task.title,
            "agent_type": task.agent_type,
            "attempt": task.current_attempt + 1,
            "model": task_model.model_id,
        })

        yield self._event(EventType.MODEL_SELECTED, {
            "task_id": task.id,
            "model": task_model.model_id,
            "reason": f"{task.agent_type} agent for: {task.title[:50]}",
        })

        for attempt in range(task.max_attempts):
            self.project.total_iterations += 1

            # Check max iterations
            if self.project.total_iterations > self.project.config.max_total_iterations:
                task.status = AutonomousTaskStatus.FAILED
                task.error = "Max total iterations exceeded"
                
                # Persistence: Task failed (global limit)
                await TaskRepository.update_status(task.id, "failed", error=task.error)
                
                yield self._event(EventType.TASK_FAILED, {
                    "task_id": task.id,
                    "reason": task.error,
                })
                return

            iteration = TaskIteration(
                attempt=attempt + 1,
                started_at=datetime.now(),
            )

            # Build prompt with any feedback from previous iteration
            prompt = self._build_task_prompt(task, iteration)

            # Run the agent
            yield self._event(EventType.TASK_PROGRESS, {
                "task_id": task.id,
                "progress": 0.1,
                "stage": "running_agent",
            })

            try:
                # Extract quality gate types for model selection
                gate_types = [g.type.value for g in task.quality_gates]

                agent_response = await self._run_agent(
                    agent_type=task.agent_type,
                    prompt=prompt,
                    task_description=task.description,
                    quality_gates=gate_types,
                )
                iteration.agent_response = agent_response

                yield self._event(EventType.TASK_AGENT_OUTPUT, {
                    "task_id": task.id,
                    "output": agent_response[:2000],  # Truncate for SSE
                })

            except Exception as e:
                iteration.feedback = f"Agent error: {e}"
                task.iterations.append(iteration)
                logger.error(f"Agent error for task {task.id}: {e}")
                continue

            yield self._event(EventType.TASK_PROGRESS, {
                "task_id": task.id,
                "progress": 0.5,
                "stage": "checking_quality_gates",
            })

            # Check quality gates
            all_gates_passed = True
            for gate in task.quality_gates:
                task.status = self._get_status_for_gate(gate.type)
                yield self._event(EventType.QUALITY_GATE_CHECK, {
                    "task_id": task.id,
                    "gate_type": gate.type.value,
                })

                passed, error = await self._check_quality_gate(task, gate, agent_response)
                gate.passed = passed
                gate.error = error
                gate.checked_at = datetime.now()

                if passed:
                    yield self._event(EventType.QUALITY_GATE_PASSED, {
                        "task_id": task.id,
                        "gate_type": gate.type.value,
                    })
                else:
                    all_gates_passed = False
                    yield self._event(EventType.QUALITY_GATE_FAILED, {
                        "task_id": task.id,
                        "gate_type": gate.type.value,
                        "error": error,
                    })
                    iteration.feedback = self._generate_fix_feedback(gate, error)
                    iteration.quality_results[gate.type.value] = {
                        "passed": False,
                        "error": error,
                    }
                    break  # Stop checking other gates

                iteration.quality_results[gate.type.value] = {"passed": True}

            iteration.completed_at = datetime.now()
            iteration.success = all_gates_passed
            task.iterations.append(iteration)

            if all_gates_passed:
                # All gates passed - commit if configured
                if self.project.config.auto_commit:
                    commit_result = await self._commit_task(task)
                    if commit_result:
                        iteration.commit_sha = commit_result
                        task.final_commit_sha = commit_result
                        yield self._event(EventType.GIT_COMMIT, {
                            "task_id": task.id,
                            "sha": commit_result,
                            "message": f"feat: {task.title}",
                        })


                task.status = AutonomousTaskStatus.COMPLETED
                task.completed_at = datetime.now()
                
                # Persistence: Task completed
                await TaskRepository.update_result(
                    task.id, 
                    result=iteration.agent_response,
                    verification_results=iteration.quality_results
                )
                await TaskRepository.update_status(task.id, "completed")
                
                yield self._event(EventType.TASK_COMPLETED, {
                    "task_id": task.id,
                    "iterations": task.current_attempt,
                    "commit_sha": task.final_commit_sha,
                })
                return

            else:
                # Need to fix - continue loop
                task.status = AutonomousTaskStatus.FIXING
                yield self._event(EventType.TASK_FIXING, {
                    "task_id": task.id,
                    "attempt": attempt + 1,
                    "feedback": iteration.feedback[:500],
                })

        # Max attempts reached
        task.status = AutonomousTaskStatus.FAILED
        task.error = f"Failed after {task.max_attempts} attempts"
        task.completed_at = datetime.now()

        # Persistence: Task failed (max attempts)
        await TaskRepository.update_status(
            task.id, 
            "failed", 
            error=task.error
        )

        yield self._event(EventType.TASK_FAILED, {
            "task_id": task.id,
            "reason": task.error,
            "attempts": task.max_attempts,
        })

    def _build_task_prompt(self, task: ProjectTask, iteration: TaskIteration) -> str:
        """Build the prompt for a task agent."""
        prompt = f"""## Task
{task.title}

## Description
{task.description}

## Workspace
{self.project.workspace_path}

## Target Files
{', '.join(task.target_files) if task.target_files else 'Determine appropriate files'}
"""

        # Add feedback from previous iteration
        if task.iterations:
            last_iteration = task.iterations[-1]
            if last_iteration.feedback:
                prompt += f"""

## Previous Attempt Feedback
The previous attempt failed quality checks. Here's what needs to be fixed:
{last_iteration.feedback}

Please address these issues in your implementation.
"""

        prompt += """

## Instructions
1. Implement the task according to the description
2. Ensure code is clean and follows best practices
3. Include appropriate error handling
4. Add comments where helpful

Proceed with the implementation.
"""
        return prompt

    async def _run_agent(
        self,
        agent_type: str,
        prompt: str,
        task_description: str | None = None,
        quality_gates: list[str] | None = None,
    ) -> str:
        """Run an agent and collect its response with auto model selection.

        Args:
            agent_type: Type of agent to run
            prompt: The prompt to send
            task_description: Optional task description for model selection
            quality_gates: Optional quality gates for model selection

        Returns:
            Agent's response text
        """
        from app.agents import agent_registry
        from app.agents.base import Message

        agent = agent_registry.get(agent_type)
        if not agent:
            raise ValueError(f"Agent not found: {agent_type}")

        # Get optimal model for this task
        model_config = get_model_config_for_task(
            agent_type=agent_type,
            task_description=task_description,
            quality_gates=quality_gates,
        )

        logger.info(
            f"Running {agent_type} with model {model_config.model_id} "
            f"(task: {task_description[:50] if task_description else 'N/A'}...)"
        )

        messages = [Message(role="user", content=prompt)]
        context = {"workspace": self.project.workspace_path}

        response_text = ""
        async for chunk in agent.chat(
            messages,
            context,
            model_override=model_config.model_id,
            temperature_override=model_config.temperature,
            max_tokens_override=model_config.max_tokens,
        ):
            # Filter out thinking markers
            if chunk.startswith("__THINKING"):
                continue
            response_text += chunk

        return response_text

    async def _check_quality_gate(
        self,
        task: ProjectTask,
        gate: QualityGate,
        agent_response: str,
    ) -> tuple[bool, str | None]:
        """Check a quality gate. Returns (passed, error_message)."""
        try:
            if gate.type == QualityGateType.TESTS_PASS:
                return await self._run_tests(task)

            elif gate.type == QualityGateType.REVIEW_APPROVED:
                return await self._run_review(task, agent_response)

            elif gate.type == QualityGateType.LINT_CLEAN:
                return await self._run_lint(task)

            elif gate.type == QualityGateType.TYPE_CHECK:
                return await self._run_type_check(task)

            elif gate.type == QualityGateType.BUILD_SUCCESS:
                return await self._run_build(task)

            else:
                return True, None  # Unknown gate type, skip

        except Exception as e:
            logger.error(f"Quality gate check failed: {e}")
            return False, str(e)

    async def _run_tests(self, task: ProjectTask) -> tuple[bool, str | None]:
        """Run tests using the tester agent."""
        from app.agents import agent_registry
        from app.agents.base import Message

        tester = agent_registry.get("tester")
        if not tester:
            # No tester agent, skip
            return True, None

        prompt = f"""Run tests for the following files/functionality:
{', '.join(task.target_files) if task.target_files else 'All relevant tests'}

Workspace: {self.project.workspace_path}

Report any test failures with details.
"""
        messages = [Message(role="user", content=prompt)]

        # Get model for testing (balanced tier)
        test_model = get_model_config_for_task(
            agent_type="tester",
            task_description=f"Run tests for: {task.title}",
            quality_gates=["tests_pass"],
        )

        response = ""
        async for chunk in tester.chat(
            messages,
            {"workspace": self.project.workspace_path},
            model_override=test_model.model_id,
            temperature_override=test_model.temperature,
        ):
            if not chunk.startswith("__THINKING"):
                response += chunk

        # Parse test result from response
        if any(x in response.lower() for x in ["all tests pass", "tests passed", "0 failed", "success"]):
            return True, None
        elif any(x in response.lower() for x in ["failed", "error", "failure"]):
            return False, response[:4000]
        else:
            # Ambiguous, assume passed
            return True, None

    async def _run_review(self, task: ProjectTask, agent_response: str) -> tuple[bool, str | None]:
        """Run code review using the reviewer agent."""
        from app.agents import agent_registry
        from app.agents.base import Message

        reviewer = agent_registry.get("reviewer")
        if not reviewer:
            return True, None

        prompt = f"""Review this code implementation:

## Task
{task.title}

## Implementation
{agent_response[:5000]}

## Files
{', '.join(task.target_files) if task.target_files else 'See implementation'}

Provide a verdict: APPROVED or CHANGES_REQUESTED with specific feedback.
"""
        messages = [Message(role="user", content=prompt)]

        # Get model for review (balanced tier - needs good understanding)
        review_model = get_model_config_for_task(
            agent_type="reviewer",
            task_description=f"Review: {task.title}",
            quality_gates=["review_approved"],
        )

        response = ""
        async for chunk in reviewer.chat(
            messages,
            {"workspace": self.project.workspace_path},
            model_override=review_model.model_id,
            temperature_override=review_model.temperature,
        ):
            if not chunk.startswith("__THINKING"):
                response += chunk

        # Parse review result
        if "approved" in response.lower() and "changes_requested" not in response.lower():
            return True, None
        else:
            return False, response[:1000]

    async def _run_lint(self, task: ProjectTask) -> tuple[bool, str | None]:
        """Run linter on task files."""
        import subprocess

        # Try common linters based on file types
        files = task.target_files
        if not files:
            return True, None

        # Check file extensions
        py_files = [f for f in files if f.endswith(".py")]
        js_ts_files = [f for f in files if f.endswith((".js", ".ts", ".tsx", ".jsx"))]

        errors = []

        if py_files:
            try:
                result = subprocess.run(
                    ["ruff", "check"] + py_files,
                    cwd=self.project.workspace_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    errors.append(result.stdout + result.stderr)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        if js_ts_files:
            try:
                result = subprocess.run(
                    ["eslint"] + js_ts_files,
                    cwd=self.project.workspace_path,
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if result.returncode != 0:
                    errors.append(result.stdout + result.stderr)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        if errors:
            return False, "\n".join(errors)[:1000]
        return True, None

    async def _run_type_check(self, task: ProjectTask) -> tuple[bool, str | None]:
        """Run type checker on task files."""
        import subprocess

        files = task.target_files
        py_files = [f for f in files if f.endswith(".py")]
        ts_files = [f for f in files if f.endswith((".ts", ".tsx"))]

        errors = []

        if py_files:
            try:
                result = subprocess.run(
                    ["mypy"] + py_files,
                    cwd=self.project.workspace_path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    errors.append(result.stdout + result.stderr)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        if ts_files:
            try:
                result = subprocess.run(
                    ["npx", "tsc", "--noEmit"],
                    cwd=self.project.workspace_path,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if result.returncode != 0:
                    errors.append(result.stdout + result.stderr)
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

        if errors:
            return False, "\n".join(errors)[:4000]
        return True, None
        return True, None

    async def _run_build(self, task: ProjectTask) -> tuple[bool, str | None]:
        """Run build command."""
        import subprocess

        # Try common build commands
        build_commands = [
            ["npm", "run", "build"],
            ["yarn", "build"],
            ["make"],
            ["python", "setup.py", "build"],
        ]

        for cmd in build_commands:
            try:
                result = subprocess.run(
                    cmd,
                    cwd=self.project.workspace_path,
                    capture_output=True,
                    text=True,
                    timeout=300,
                )
                if result.returncode == 0:
                    return True, None
                # If command exists but failed, report error
                if "not found" not in (result.stderr + result.stdout).lower():
                    return False, (result.stdout + result.stderr)[:4000]
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue

        # No build command found, skip
        return True, None

    def _generate_fix_feedback(self, gate: QualityGate, error: str | None) -> str:
        """Generate feedback for fixing a failed quality gate."""
        if gate.type == QualityGateType.TESTS_PASS:
            return f"""Tests failed. Please fix the following issues:

{error}

Make sure to:
1. Fix any failing tests
2. Update tests if behavior changed intentionally
3. Add missing test cases
"""

        elif gate.type == QualityGateType.REVIEW_APPROVED:
            return f"""Code review requested changes:

{error}

Please address the reviewer's feedback and update your implementation.
"""

        elif gate.type == QualityGateType.LINT_CLEAN:
            return f"""Linter errors found:

{error}

Please fix the linting issues and ensure code style compliance.
"""

        elif gate.type == QualityGateType.TYPE_CHECK:
            return f"""Type checking errors:

{error}

Please fix the type errors and ensure proper type annotations.
"""

        elif gate.type == QualityGateType.BUILD_SUCCESS:
            return f"""Build failed:

{error}

Please fix the build errors.
"""

        return f"Quality check failed: {error}"

    def _get_status_for_gate(self, gate_type: QualityGateType) -> AutonomousTaskStatus:
        """Get task status for a quality gate check."""
        if gate_type == QualityGateType.TESTS_PASS:
            return AutonomousTaskStatus.TESTING
        elif gate_type == QualityGateType.REVIEW_APPROVED:
            return AutonomousTaskStatus.REVIEWING
        return AutonomousTaskStatus.IN_PROGRESS

    async def _commit_task(self, task: ProjectTask) -> str | None:
        """Commit task changes."""
        # Stage all changes
        status = await self.git.status()
        if not status.get("has_changes"):
            return None

        await self.git.add()

        # Create commit message
        message = f"feat: {task.title}\n\nTask ID: {task.id}\nAgent: {task.agent_type}"

        result = await self.git.commit(message)
        if result.success:
            return await self.git.get_last_commit_sha()
        return None

    async def _run_finalization(self) -> AsyncIterator[OrchestratorEvent]:
        """Run finalization phase (push, PR)."""
        if self.project.config.push_to_remote:
            if await self.git.has_remote():
                result = await self.git.push(
                    branch=self.project.branch_name,
                    set_upstream=True,
                )
                if result.success:
                    yield self._event(EventType.GIT_PUSH, {
                        "branch": self.project.branch_name,
                    })

        if self.project.config.create_pr and self.project.branch_name:
            pr_result = await self.git.create_pull_request(
                title=f"[Auto] {self.project.name}",
                body=self._generate_pr_body(),
                base=self.project.config.pr_base_branch,
                head=self.project.branch_name,
            )
            if pr_result.get("success"):
                self.project.pr_url = pr_result.get("url")
                yield self._event(EventType.GIT_PR_CREATED, {
                    "url": self.project.pr_url,
                    "number": pr_result.get("number"),
                })

    def _generate_pr_body(self) -> str:
        """Generate pull request body."""
        completed = [t for t in self.project.tasks if t.status == AutonomousTaskStatus.COMPLETED]
        failed = [t for t in self.project.tasks if t.status == AutonomousTaskStatus.FAILED]

        body = f"""## Summary
Auto-generated PR for: {self.project.name}

### Original Request
{self.project.original_prompt[:500]}

### Tasks Completed ({len(completed)})
"""
        for task in completed:
            body += f"- [x] {task.title}"
            if task.final_commit_sha:
                body += f" ({task.final_commit_sha})"
            body += "\n"

        if failed:
            body += f"\n### Tasks Failed ({len(failed)})\n"
            for task in failed:
                body += f"- [ ] {task.title}: {task.error or 'Unknown error'}\n"

        body += f"""
### Statistics
- Total iterations: {self.project.total_iterations}
- Tasks completed: {self.project.tasks_completed}/{len(self.project.tasks)}

---
Generated by MaratOS Autonomous Development Team
"""
        return body

    def _is_complete(self) -> bool:
        """Check if project execution is complete."""
        return all(t.is_terminal for t in self.project.tasks)

    def _is_timeout(self) -> bool:
        """Check if max runtime exceeded."""
        if not self._start_time:
            return False
        elapsed_hours = (datetime.now() - self._start_time).total_seconds() / 3600
        return elapsed_hours >= self.project.config.max_runtime_hours

    def _has_pending_tasks(self) -> bool:
        """Check if there are pending (non-terminal) tasks."""
        return any(not t.is_terminal for t in self.project.tasks)

    def _event(self, event_type: EventType, data: dict[str, Any] | None = None) -> OrchestratorEvent:
        """Create an orchestrator event."""
        return OrchestratorEvent(
            type=event_type,
            project_id=self.project.id,
            data=data or {},
        )

    def _sanitize_branch_name(self, name: str) -> str:
        """Sanitize a string for use as a git branch name."""
        # Replace spaces and special chars with dashes
        sanitized = re.sub(r'[^a-zA-Z0-9-]', '-', name.lower())
        # Remove consecutive dashes
        sanitized = re.sub(r'-+', '-', sanitized)
        # Trim dashes from ends
        return sanitized.strip('-')[:30]

    def pause(self) -> None:
        """Pause execution."""
        self._paused = True

    def resume(self) -> None:
        """Resume execution."""
        self._paused = False

    def cancel(self) -> None:
        """Cancel execution."""
        self._cancelled = True
