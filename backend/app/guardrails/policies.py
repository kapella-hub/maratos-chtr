"""Agent and tool policy definitions.

Defines per-agent policies for:
- Allowed tools
- Filesystem access (read/write paths)
- Budget limits
- Diff approval requirements
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BudgetPolicy:
    """Budget limits for an agent execution session."""

    # Tool loop limits
    max_tool_loops_per_message: int = 6  # Max iterations in tool loop
    max_tool_calls_per_message: int = 20  # Max total tool calls per message
    max_tool_calls_per_session: int = 100  # Max total tool calls per session

    # Spawned task limits
    max_spawned_tasks_per_run: int = 10  # Max subagent spawns per orchestrator run
    max_nested_spawn_depth: int = 3  # Max depth of nested agent spawns

    # Shell execution limits
    max_shell_time_seconds: float = 120.0  # Max time per shell command
    max_shell_calls_per_message: int = 10  # Max shell invocations per message
    max_total_shell_time_per_session: float = 600.0  # 10 min total shell time

    # Memory limits
    max_output_size_bytes: int = 1_000_000  # 1MB max output per tool call


@dataclass
class FilesystemPolicy:
    """Filesystem access policy for an agent."""

    # Read access
    read_paths: list[str] = field(default_factory=lambda: ["*"])
    read_allowed: bool = True

    # Write access
    write_paths: list[str] = field(default_factory=list)
    write_allowed: bool = False

    # Workspace enforcement
    workspace_only: bool = True
    workspace_path: str = "~/maratos-workspace"

    def can_read(self, path: str) -> bool:
        """Check if reading a path is allowed."""
        if not self.read_allowed:
            return False
        if "*" in self.read_paths:
            return True
        return self._path_matches(path, self.read_paths)

    def can_write(self, path: str) -> bool:
        """Check if writing to a path is allowed."""
        if not self.write_allowed:
            return False
        if not self.write_paths:
            return False

        # Expand workspace path
        expanded_path = Path(path).expanduser().resolve()
        workspace_expanded = Path(self.workspace_path).expanduser().resolve()

        # Check workspace enforcement
        if self.workspace_only:
            try:
                expanded_path.relative_to(workspace_expanded)
                return True
            except ValueError:
                pass

        return self._path_matches(path, self.write_paths)

    def _path_matches(self, path: str, allowed_paths: list[str]) -> bool:
        """Check if path matches any of the allowed paths."""
        expanded = Path(path).expanduser().resolve()

        for allowed in allowed_paths:
            if allowed == "*":
                return True

            allowed_expanded = Path(allowed).expanduser().resolve()
            try:
                expanded.relative_to(allowed_expanded)
                return True
            except ValueError:
                continue

        return False


@dataclass
class DiffApprovalPolicy:
    """Policy for diff-first mode approval requirements."""

    enabled: bool = False

    # Actions requiring approval
    require_approval_for_writes: bool = True
    require_approval_for_deletes: bool = True
    require_approval_for_shell: bool = False

    # Paths requiring approval (even if writes allowed)
    protected_paths: list[str] = field(default_factory=lambda: [
        "*.py",  # Python source
        "*.js", "*.ts",  # JavaScript/TypeScript
        "*.yaml", "*.yml",  # Config files
        "*.json",  # JSON configs
        "Dockerfile*",
        "*.sql",
    ])

    # Approval timeout
    approval_timeout_seconds: float = 300.0  # 5 minutes

    def requires_approval(self, action: str, path: str | None = None) -> bool:
        """Check if an action requires approval."""
        if not self.enabled:
            return False

        if action == "write" and self.require_approval_for_writes:
            if path and self._is_protected_path(path):
                return True
        elif action == "delete" and self.require_approval_for_deletes:
            return True
        elif action == "shell" and self.require_approval_for_shell:
            return True

        return False

    def _is_protected_path(self, path: str) -> bool:
        """Check if path matches protected patterns."""
        from fnmatch import fnmatch
        filename = Path(path).name

        for pattern in self.protected_paths:
            if fnmatch(filename, pattern):
                return True
        return False


@dataclass
class AgentPolicy:
    """Complete policy for an agent type."""

    agent_id: str
    description: str

    # Tool access
    allowed_tools: list[str] = field(default_factory=list)

    # Filesystem policy
    filesystem: FilesystemPolicy = field(default_factory=FilesystemPolicy)

    # Budget policy
    budget: BudgetPolicy = field(default_factory=BudgetPolicy)

    # Diff approval policy
    diff_approval: DiffApprovalPolicy = field(default_factory=DiffApprovalPolicy)

    # Notes for system prompt
    notes: str = ""

    def is_tool_allowed(self, tool_id: str) -> bool:
        """Check if a tool is allowed for this agent."""
        return tool_id in self.allowed_tools

    def to_prompt_section(self) -> str:
        """Generate policy section for system prompt."""
        allowed_list = ", ".join(self.allowed_tools)
        read_paths = ", ".join(self.filesystem.read_paths) if self.filesystem.read_paths else "None"
        write_paths = ", ".join(self.filesystem.write_paths) if self.filesystem.write_paths else "None (read-only)"

        sections = [
            "## TOOL POLICY",
            "",
            f"**Allowed Tools:** {allowed_list}",
            f"**Read Access:** {read_paths}",
            f"**Write Access:** {write_paths}",
        ]

        if self.notes:
            sections.append(f"**Notes:** {self.notes}")

        sections.extend([
            "",
            "## BUDGET LIMITS",
            "",
            f"- Max tool loops per message: {self.budget.max_tool_loops_per_message}",
            f"- Max shell time per command: {self.budget.max_shell_time_seconds}s",
            f"- Max spawned tasks: {self.budget.max_spawned_tasks_per_run}",
        ])

        if self.diff_approval.enabled:
            sections.extend([
                "",
                "## DIFF-FIRST MODE",
                "",
                "High-impact actions (writes, deletes) will produce diffs for approval before execution.",
            ])

        sections.extend([
            "",
            "IMPORTANT: Attempting to use tools not in your allowed list will fail.",
            "Write operations outside allowed paths will be blocked.",
        ])

        return "\n".join(sections)


# Agent policy definitions
AGENT_POLICIES: dict[str, AgentPolicy] = {
    "mo": AgentPolicy(
        agent_id="mo",
        description="Primary orchestrator - delegates to specialists",
        allowed_tools=["routing", "filesystem", "shell", "web_search", "web_fetch", "kiro", "sessions", "canvas"],
        filesystem=FilesystemPolicy(
            read_paths=["*"],
            write_paths=["/Projects", "~/maratos-workspace"],
            write_allowed=True,
            workspace_only=False,
        ),
        budget=BudgetPolicy(
            max_tool_loops_per_message=6,
            max_spawned_tasks_per_run=15,
            max_shell_time_seconds=120.0,
        ),
        diff_approval=DiffApprovalPolicy(enabled=False),
        notes="Orchestrator - delegates heavy implementation to specialists",
    ),

    "architect": AgentPolicy(
        agent_id="architect",
        description="Plans and designs - spawns coders for implementation",
        allowed_tools=["filesystem", "shell", "kiro"],
        filesystem=FilesystemPolicy(
            read_paths=["*"],
            write_paths=["~/maratos-workspace"],
            write_allowed=True,
            workspace_only=True,
        ),
        budget=BudgetPolicy(
            max_tool_loops_per_message=6,
            max_spawned_tasks_per_run=5,
            max_shell_time_seconds=60.0,
        ),
        diff_approval=DiffApprovalPolicy(enabled=False),
        notes="Plans and designs - spawns coders for implementation",
    ),

    "coder": AgentPolicy(
        agent_id="coder",
        description="Pure implementation - reads existing code, writes new code",
        allowed_tools=["filesystem", "shell", "kiro"],
        filesystem=FilesystemPolicy(
            read_paths=["*"],
            write_paths=["/Projects", "~/maratos-workspace"],
            write_allowed=True,
            workspace_only=False,
        ),
        budget=BudgetPolicy(
            max_tool_loops_per_message=8,
            max_spawned_tasks_per_run=0,  # Coder doesn't spawn
            max_shell_time_seconds=180.0,  # Allow longer for builds
        ),
        diff_approval=DiffApprovalPolicy(enabled=False),
        notes="Pure implementation - reads existing code, writes new code",
    ),

    "reviewer": AgentPolicy(
        agent_id="reviewer",
        description="Code review - reads and analyzes, does not modify",
        allowed_tools=["filesystem", "shell", "kiro"],
        filesystem=FilesystemPolicy(
            read_paths=["*"],
            write_paths=[],  # READ-ONLY
            write_allowed=False,
            workspace_only=True,
        ),
        budget=BudgetPolicy(
            max_tool_loops_per_message=6,
            max_spawned_tasks_per_run=0,
            max_shell_time_seconds=60.0,
            max_shell_calls_per_message=5,  # Limited shell for reviews
        ),
        diff_approval=DiffApprovalPolicy(enabled=False),
        notes="Code review - reads and analyzes, does NOT modify files",
    ),

    "tester": AgentPolicy(
        agent_id="tester",
        description="Test writer - must copy to workspace before writing",
        allowed_tools=["filesystem", "shell", "kiro"],
        filesystem=FilesystemPolicy(
            read_paths=["*"],
            write_paths=["~/maratos-workspace"],
            write_allowed=True,
            workspace_only=True,
        ),
        budget=BudgetPolicy(
            max_tool_loops_per_message=10,  # Tests may need more iterations
            max_spawned_tasks_per_run=0,
            max_shell_time_seconds=300.0,  # Tests can take longer
            max_shell_calls_per_message=15,
        ),
        diff_approval=DiffApprovalPolicy(enabled=False),
        notes="Must copy to workspace before writing tests",
    ),

    "docs": AgentPolicy(
        agent_id="docs",
        description="Documentation writer - can write docs directly",
        allowed_tools=["filesystem", "shell", "kiro"],
        filesystem=FilesystemPolicy(
            read_paths=["*"],
            write_paths=["/Projects", "~/maratos-workspace"],
            write_allowed=True,
            workspace_only=False,
        ),
        budget=BudgetPolicy(
            max_tool_loops_per_message=6,
            max_spawned_tasks_per_run=0,
            max_shell_time_seconds=30.0,
        ),
        diff_approval=DiffApprovalPolicy(enabled=False),
        notes="Documentation writer - can write docs directly",
    ),

    "devops": AgentPolicy(
        agent_id="devops",
        description="Infrastructure - writes config files, Dockerfiles, CI/CD",
        allowed_tools=["filesystem", "shell", "kiro"],
        filesystem=FilesystemPolicy(
            read_paths=["*"],
            write_paths=["/Projects", "~/maratos-workspace"],
            write_allowed=True,
            workspace_only=False,
        ),
        budget=BudgetPolicy(
            max_tool_loops_per_message=8,
            max_spawned_tasks_per_run=0,
            max_shell_time_seconds=300.0,  # Docker builds can take time
            max_shell_calls_per_message=20,
        ),
        diff_approval=DiffApprovalPolicy(
            enabled=True,  # DevOps changes are sensitive
            require_approval_for_writes=True,
            require_approval_for_shell=True,
            protected_paths=["Dockerfile*", "*.yaml", "*.yml", ".github/*"],
        ),
        notes="Infrastructure - writes config files, Dockerfiles, CI/CD. Changes require approval.",
    ),
}


def get_agent_policy(agent_id: str) -> AgentPolicy:
    """Get the policy for an agent, defaulting to coder if unknown."""
    return AGENT_POLICIES.get(agent_id, AGENT_POLICIES["coder"])
