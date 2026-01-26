# Autonomous Development Team

MaratOS includes an autonomous development team feature that transforms single-request agent interactions into a fully autonomous development workflow. The system can work for hours on complex projects with iterative feedback loops, quality gates, and git integration.

## Overview

```
User Prompt
    │
    ▼
┌─────────────────┐
│  Orchestrator   │ ◄── Controls entire workflow
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Architect     │ ◄── Creates task breakdown with dependencies
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────┐
│         Execution Loop              │
│  ┌──────┐  ┌──────┐  ┌──────────┐  │
│  │Coder │→ │Tester│→ │ Reviewer │  │
│  └───┬──┘  └───┬──┘  └────┬─────┘  │
│      │         │          │        │
│      └─────────┴──────────┘        │
│         Feedback Loop              │
│      (Fix → Retest → Re-review)    │
└────────────────┬───────────────────┘
                 │
                 ▼
┌─────────────────┐
│  Git + Finalize │ ◄── Commit, push, create PR
└─────────────────┘
```

## Quick Start

1. Navigate to the **Autonomous** page in the sidebar
2. Fill in:
   - **Project Name**: A descriptive name for your project
   - **Prompt**: Detailed description of what you want built
   - **Options**: Auto-commit, push to remote, create PR
3. Click **Start Autonomous Development**
4. Watch as the AI team plans, implements, tests, and delivers

## Architecture

### Backend Components

#### Data Models (`backend/app/autonomous/models.py`)

##### ProjectPlan
The main project container that tracks the entire autonomous development session.

```python
@dataclass
class ProjectPlan:
    id: str                          # Unique project ID
    name: str                        # Project name
    original_prompt: str             # User's original request
    workspace_path: str              # Directory for file operations
    status: ProjectStatus            # Current project status
    config: ProjectConfig            # Project configuration
    tasks: list[ProjectTask]         # All tasks in the project
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    paused_at: datetime | None
    total_iterations: int            # Total agent iterations run
    branch_name: str | None          # Git branch name
    pr_url: str | None               # Pull request URL if created
    error: str | None                # Error message if failed
```

##### ProjectStatus
```python
class ProjectStatus(str, Enum):
    PLANNING = "planning"        # Architect is creating task breakdown
    IN_PROGRESS = "in_progress"  # Tasks are being executed
    BLOCKED = "blocked"          # Waiting on dependencies
    PAUSED = "paused"            # User paused execution
    COMPLETED = "completed"      # All tasks finished successfully
    FAILED = "failed"            # Project failed (max retries exceeded)
    CANCELLED = "cancelled"      # User cancelled the project
```

##### ProjectTask
Individual task within a project.

```python
@dataclass
class ProjectTask:
    id: str                              # Unique task ID
    title: str                           # Task title
    description: str                     # Detailed task description
    agent_type: str                      # Agent to run: coder, tester, reviewer, docs, devops
    status: AutonomousTaskStatus         # Current task status
    depends_on: list[str]                # Task IDs this depends on
    quality_gates: list[QualityGate]     # Quality checks required
    iterations: list[TaskIteration]      # History of all attempts
    max_attempts: int = 3                # Max retry attempts
    priority: int = 0                    # Execution priority (higher = first)
    target_files: list[str]              # Files this task works on
    final_commit_sha: str | None         # Git commit if completed
    error: str | None                    # Error message if failed
```

##### AutonomousTaskStatus
```python
class AutonomousTaskStatus(str, Enum):
    PENDING = "pending"          # Waiting to start
    BLOCKED = "blocked"          # Waiting on dependencies
    READY = "ready"              # Dependencies met, ready to run
    IN_PROGRESS = "in_progress"  # Agent is working
    TESTING = "testing"          # Running tests quality gate
    REVIEWING = "reviewing"      # Running code review quality gate
    FIXING = "fixing"            # Agent is fixing issues
    COMPLETED = "completed"      # All quality gates passed
    FAILED = "failed"            # Max attempts exceeded
    SKIPPED = "skipped"          # Skipped due to dependency failure
```

##### QualityGate
Quality checks that must pass before task completion.

```python
@dataclass
class QualityGate:
    type: QualityGateType    # Type of quality check
    required: bool = True    # Whether gate must pass
    passed: bool = False     # Whether gate passed
    error: str | None        # Error message if failed
    checked_at: datetime | None
```

##### QualityGateType
```python
class QualityGateType(str, Enum):
    TESTS_PASS = "tests_pass"           # Run tests via tester agent
    REVIEW_APPROVED = "review_approved"  # Code review via reviewer agent
    LINT_CLEAN = "lint_clean"           # Run linter (ruff, eslint)
    TYPE_CHECK = "type_check"           # Run type checker (mypy, tsc)
    BUILD_SUCCESS = "build_success"     # Run build command
```

##### TaskIteration
Record of a single attempt at completing a task.

```python
@dataclass
class TaskIteration:
    attempt: int                         # Attempt number (1, 2, 3...)
    started_at: datetime
    completed_at: datetime | None
    success: bool                        # Whether this attempt succeeded
    agent_response: str                  # Agent's output
    quality_results: dict[str, Any]      # Results from each quality gate
    feedback: str | None                 # Feedback for next attempt
    files_modified: list[str]            # Files changed in this attempt
    commit_sha: str | None               # Commit SHA if committed
```

##### ProjectConfig
Configuration options for a project.

```python
@dataclass
class ProjectConfig:
    auto_commit: bool = True             # Commit after each task
    push_to_remote: bool = False         # Push to remote on completion
    create_pr: bool = False              # Create pull request
    pr_base_branch: str = "main"         # Base branch for PR
    max_runtime_hours: float = 8.0       # Maximum execution time
    max_total_iterations: int = 50       # Max agent iterations
    parallel_tasks: int = 3              # Max concurrent tasks
```

---

#### Orchestrator Engine (`backend/app/autonomous/orchestrator.py`)

The orchestrator is the main execution engine that coordinates the entire autonomous development process.

##### Execution Flow

```python
async def start(self) -> AsyncIterator[OrchestratorEvent]:
    # Phase 1: Planning
    yield event(PROJECT_STARTED)
    yield event(PLANNING_STARTED)
    async for event in self._run_planning():
        yield event
    yield event(PLANNING_COMPLETED)

    # Phase 2: Execution Loop
    while not complete and not timeout:
        ready_tasks = project.get_ready_tasks()
        async for event in self._run_tasks_parallel(ready_tasks):
            yield event

    # Phase 3: Finalization
    if push_to_remote:
        await git.push()
    if create_pr:
        await git.create_pull_request()

    yield event(PROJECT_COMPLETED)
```

##### Planning Phase

The architect agent analyzes the prompt and creates a structured task breakdown:

```python
async def _run_planning(self):
    prompt = f"""
    Analyze this development request and create a detailed task breakdown.

    ## Request
    {project.original_prompt}

    ## Output Format
    Return as JSON array:
    [
      {{
        "title": "Task title",
        "description": "Detailed description",
        "agent_type": "coder",
        "quality_gates": ["tests_pass"],
        "depends_on": [],
        "target_files": ["src/main.py"]
      }}
    ]
    """
    response = await architect.chat(prompt)
    tasks = parse_task_list(response)
```

##### Task Execution with Feedback Loop

```python
async def _run_task_with_feedback(self, task):
    for attempt in range(task.max_attempts):
        # Run the agent
        response = await self._run_agent(task.agent_type, prompt)

        # Check quality gates
        all_passed = True
        for gate in task.quality_gates:
            passed, error = await self._check_quality_gate(task, gate)
            if not passed:
                all_passed = False
                # Generate fix feedback
                task.feedback = generate_fix_feedback(gate, error)
                break

        if all_passed:
            if auto_commit:
                await self._commit_task(task)
            task.status = COMPLETED
            return

        # Retry with feedback
        task.status = FIXING

    # Max attempts exceeded
    task.status = FAILED
```

##### Quality Gate Checks

| Gate Type | Implementation |
|-----------|----------------|
| `tests_pass` | Runs tester agent to execute tests |
| `review_approved` | Runs reviewer agent for code review |
| `lint_clean` | Executes `ruff` (Python) or `eslint` (JS/TS) |
| `type_check` | Executes `mypy` (Python) or `tsc` (TypeScript) |
| `build_success` | Tries common build commands (npm, yarn, make) |

##### Event Types

```python
class EventType(str, Enum):
    PROJECT_STARTED = "project_started"
    PLANNING_STARTED = "planning_started"
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
```

---

#### Project Manager (`backend/app/autonomous/project_manager.py`)

Registry for tracking active projects.

```python
class ProjectManager:
    async def create_project(name, prompt, workspace_path, config) -> ProjectPlan
    def get(project_id) -> ProjectPlan | None
    def list_projects(status, limit) -> list[ProjectPlan]
    def get_active_projects() -> list[ProjectPlan]
    async def pause_project(project_id) -> bool
    async def resume_project(project_id) -> bool
    async def cancel_project(project_id) -> bool
    def get_stats() -> dict

# Global instance
project_manager = ProjectManager()
```

---

#### Git Operations (`backend/app/autonomous/git_ops.py`)

Async git operations for project management.

```python
class GitOperations:
    def __init__(self, workdir: str | Path)

    # Repository management
    async def is_git_repo() -> bool
    async def init() -> GitResult

    # Branch operations
    async def get_current_branch() -> str | None
    async def create_branch(branch_name) -> GitResult
    async def checkout(branch_name) -> GitResult

    # Changes
    async def status() -> dict  # modified, added, deleted, untracked
    async def add(*files) -> GitResult
    async def commit(message, allow_empty) -> GitResult
    async def diff(file, staged) -> str

    # Remote operations
    async def push(remote, branch, set_upstream) -> GitResult
    async def has_remote(remote) -> bool
    async def create_pull_request(title, body, base, head) -> dict

    # Utilities
    async def get_last_commit_sha() -> str | None
    async def get_changed_files(since_commit) -> list[str]
    async def log(count, oneline) -> list[dict]
```

---

#### API Endpoints (`backend/app/api/autonomous.py`)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/autonomous/start` | Start new project (SSE stream) |
| `GET` | `/api/autonomous/projects` | List all projects |
| `GET` | `/api/autonomous/projects/{id}` | Get project with tasks |
| `POST` | `/api/autonomous/projects/{id}/pause` | Pause execution |
| `POST` | `/api/autonomous/projects/{id}/resume` | Resume execution |
| `POST` | `/api/autonomous/projects/{id}/cancel` | Cancel project |
| `POST` | `/api/autonomous/projects/{id}/tasks/{tid}/retry` | Retry failed task |
| `GET` | `/api/autonomous/stats` | Get system statistics |

##### Start Project Request

```typescript
interface StartProjectRequest {
  name: string                    // Project name
  prompt: string                  // What to build
  workspace_path?: string         // Custom workspace (optional)
  auto_commit?: boolean           // Commit after each task (default: true)
  push_to_remote?: boolean        // Push on completion (default: false)
  create_pr?: boolean             // Create PR (default: false)
  pr_base_branch?: string         // PR base branch (default: "main")
  max_runtime_hours?: number      // Max runtime (default: 8)
  max_total_iterations?: number   // Max iterations (default: 50)
  parallel_tasks?: number         // Max concurrent tasks (default: 3)
}
```

##### SSE Event Stream

The `/api/autonomous/start` endpoint returns a Server-Sent Events stream:

```
data: {"type": "project_started", "project_id": "abc123", ...}

data: {"type": "planning_started", ...}

data: {"type": "task_created", "data": {"task_id": "t1", "task": {...}}}

data: {"type": "task_started", "data": {"task_id": "t1", "title": "...", "attempt": 1}}

data: {"type": "quality_gate_check", "data": {"task_id": "t1", "gate_type": "tests_pass"}}

data: {"type": "quality_gate_passed", "data": {"task_id": "t1", "gate_type": "tests_pass"}}

data: {"type": "git_commit", "data": {"task_id": "t1", "sha": "abc1234", "message": "..."}}

data: {"type": "project_completed", "data": {"tasks_completed": 5, "pr_url": "..."}}

data: [DONE]
```

---

#### Database Models (`backend/app/database.py`)

```python
class AutonomousProject(Base):
    __tablename__ = "autonomous_projects"

    id: str                    # Primary key
    name: str
    original_prompt: str
    workspace_path: str
    status: str
    config: JSON
    branch_name: str | None
    pr_url: str | None
    error: str | None
    total_iterations: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    paused_at: datetime | None


class AutonomousTask(Base):
    __tablename__ = "autonomous_tasks"

    id: str                    # Primary key
    project_id: str            # Foreign key to project
    title: str
    description: str
    agent_type: str
    status: str
    depends_on: JSON           # List of task IDs
    quality_gates: JSON        # List of QualityGate dicts
    iterations: JSON           # List of TaskIteration dicts
    target_files: JSON
    max_attempts: int
    priority: int
    final_commit_sha: str | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
```

---

### Frontend Components

#### Zustand Store (`frontend/src/stores/autonomous.ts`)

```typescript
interface AutonomousStore {
  // Current project state
  currentProject: AutonomousProject | null
  tasks: AutonomousTask[]
  events: AutonomousEvent[]

  // UI state
  isStreaming: boolean
  isPlanning: boolean
  error: string | null
  abortController: AbortController | null

  // Projects list
  projects: AutonomousProject[]

  // Actions
  setCurrentProject: (project) => void
  updateProject: (updates) => void
  setTasks: (tasks) => void
  updateTask: (taskId, updates) => void
  addTask: (task) => void
  addEvent: (event) => void
  clearEvents: () => void
  setStreaming: (streaming) => void
  setPlanning: (planning) => void
  setError: (error) => void
  stopProject: () => void
  reset: () => void
}
```

---

#### AutonomousProgress Component

Displays overall project progress with controls.

**Features:**
- Project name and workspace path
- Status badge (planning, in progress, completed, etc.)
- Progress bar with percentage
- Stats grid: completed, failed, pending tasks, total iterations
- Git info: branch name, PR link
- Control buttons: pause, resume, cancel
- Collapsible original prompt

**Props:**
```typescript
interface AutonomousProgressProps {
  project: AutonomousProject
  onPause?: () => void
  onResume?: () => void
  onCancel?: () => void
}
```

---

#### TaskCard Component

Displays individual task with status and quality gates.

**Features:**
- Status badge with icon (pending, in_progress, testing, reviewing, fixing, completed, failed)
- Agent type indicator (coder, tester, reviewer, docs, devops)
- Attempt counter
- Task title and description
- Quality gate indicators (passed/failed)
- Target files list
- Error display for failed tasks
- Commit SHA for completed tasks
- Retry button for failed tasks
- Dependencies list

**Props:**
```typescript
interface TaskCardProps {
  task: AutonomousTask
  onRetry?: (taskId: string) => void
}
```

---

#### EventLog Component

Live event stream display.

**Features:**
- Auto-scroll to newest events
- Color-coded event types
- Event icons
- Timestamp display
- Human-readable event messages
- Keeps last 100 events

**Props:**
```typescript
interface EventLogProps {
  events: AutonomousEvent[]
  maxHeight?: string
}
```

---

#### AutonomousPage

Main page component that ties everything together.

**Features:**
- Project creation form:
  - Name input
  - Prompt textarea
  - Workspace path (optional)
  - Max runtime hours
  - Checkboxes: auto-commit, push to remote, create PR
  - PR base branch input
- Project view:
  - AutonomousProgress component
  - Planning indicator during architect phase
  - Tasks grouped by status (active, ready, waiting, completed, failed)
  - Event log sidebar
- Real-time updates via SSE
- Error display
- New project button

---

## API Types (`frontend/src/lib/api.ts`)

### Request/Response Types

```typescript
interface StartProjectRequest {
  name: string
  prompt: string
  workspace_path?: string
  auto_commit?: boolean
  push_to_remote?: boolean
  create_pr?: boolean
  pr_base_branch?: string
  max_runtime_hours?: number
  max_total_iterations?: number
  parallel_tasks?: number
}

interface AutonomousProject {
  id: string
  name: string
  original_prompt: string
  workspace_path: string
  status: string
  progress: number
  tasks_completed: number
  tasks_failed: number
  tasks_pending: number
  total_iterations: number
  branch_name?: string
  pr_url?: string
  error?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

interface AutonomousTask {
  id: string
  title: string
  description: string
  agent_type: string
  status: string
  depends_on: string[]
  quality_gates: QualityGate[]
  current_attempt: number
  max_attempts: number
  priority: number
  target_files: string[]
  final_commit_sha?: string
  error?: string
  created_at: string
  started_at?: string
  completed_at?: string
}

interface AutonomousEvent {
  type: string
  project_id: string
  data: Record<string, unknown>
  timestamp: string
}
```

### API Functions

```typescript
// List all projects
fetchAutonomousProjects(): Promise<AutonomousProject[]>

// Get project details with tasks
fetchAutonomousProject(id: string): Promise<{
  project: AutonomousProject
  tasks: AutonomousTask[]
}>

// Start new project (returns SSE stream)
streamAutonomousProject(
  request: StartProjectRequest,
  signal?: AbortSignal
): AsyncGenerator<AutonomousEvent>

// Control actions
pauseAutonomousProject(id: string): Promise<void>
resumeAutonomousProject(id: string): Promise<void>
cancelAutonomousProject(id: string): Promise<void>
retryAutonomousTask(projectId: string, taskId: string): Promise<void>

// Statistics
fetchAutonomousStats(): Promise<{
  total_projects: number
  active_projects: number
  running_orchestrators: number
  by_status: Record<string, number>
}>
```

---

## Example Workflow

### User Request
> "Build a REST API for a todo app with authentication"

### Planning Phase
The architect agent creates this task breakdown:

| # | Task | Agent | Dependencies | Quality Gates |
|---|------|-------|--------------|---------------|
| 1 | Setup project structure | coder | - | - |
| 2 | Implement User model | coder | 1 | lint_clean |
| 3 | Add auth endpoints | coder | 2 | tests_pass |
| 4 | Implement Todo model | coder | 1 | lint_clean |
| 5 | Add todo CRUD endpoints | coder | 3, 4 | tests_pass |
| 6 | Write integration tests | tester | 5 | tests_pass |
| 7 | Code review | reviewer | 5 | review_approved |
| 8 | Generate API documentation | docs | 6, 7 | - |

### Execution

1. **Task 1** starts → completes → commit `feat: initial structure`
2. **Tasks 2, 4** run in parallel (both depend only on task 1)
3. **Task 3** waits for task 2 → runs → lint fails → fixes → lint passes
4. **Task 5** waits for tasks 3, 4 → runs → tests fail → fixes → tests pass
5. **Task 6** runs tests → all pass
6. **Task 7** reviews code → requests changes → coder fixes → approved
7. **Task 8** generates documentation

### Finalization

- All commits pushed to `auto/abc123-todo-api` branch
- PR created: "Auto: Todo API with Authentication"

---

## Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `MARATOS_WORKSPACE` | Default workspace directory | `~/maratos-workspace` |

### Project Defaults

| Setting | Default | Description |
|---------|---------|-------------|
| `auto_commit` | `true` | Commit after each task completion |
| `push_to_remote` | `false` | Push to remote on project completion |
| `create_pr` | `false` | Create pull request |
| `pr_base_branch` | `main` | Base branch for PR |
| `max_runtime_hours` | `8.0` | Maximum project runtime |
| `max_total_iterations` | `50` | Maximum agent iterations |
| `parallel_tasks` | `3` | Maximum concurrent tasks |
| `max_attempts` (per task) | `3` | Maximum retries per task |

---

## File Structure

```
backend/app/autonomous/
├── __init__.py              # Module exports
├── models.py                # Data models (ProjectPlan, ProjectTask, etc.)
├── orchestrator.py          # Main execution engine
├── project_manager.py       # Project registry
└── git_ops.py               # Git operations

backend/app/api/
└── autonomous.py            # API endpoints

backend/app/database.py      # Added AutonomousProject, AutonomousTask models

frontend/src/
├── stores/
│   └── autonomous.ts        # Zustand store
├── components/autonomous/
│   ├── index.ts             # Component exports
│   ├── AutonomousProgress.tsx
│   ├── TaskCard.tsx
│   └── EventLog.tsx
├── pages/
│   └── AutonomousPage.tsx   # Main page
├── lib/
│   └── api.ts               # Added autonomous API functions
└── App.tsx                  # Added /autonomous route

frontend/src/components/
└── Layout.tsx               # Added Autonomous nav link
```

---

## Troubleshooting

### Project stuck in "blocked" status
- Check if there are failed dependencies
- Use the retry button on failed tasks
- Check the event log for error details

### Quality gates always failing
- Ensure required tools are installed (ruff, eslint, mypy, tsc)
- Check if tests are properly configured in the workspace
- Review the feedback in task iterations

### Git operations failing
- Ensure workspace is a git repository
- Check if `gh` CLI is installed for PR creation
- Verify remote is configured correctly

### Project timeout
- Increase `max_runtime_hours` in project config
- Reduce task complexity in the prompt
- Check for infinite loops in quality gate failures
