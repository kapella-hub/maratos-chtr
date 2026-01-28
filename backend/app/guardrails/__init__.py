"""Enterprise guardrails for tool execution and agent safety.

Provides:
- Tool allowlists per agent
- Filesystem jail enforcement
- Budget controls (tool loops, spawned tasks, shell time)
- Audit logging to database
- Diff-first mode for high-impact actions
- Unified configuration via environment variables
"""

from app.guardrails.policies import (
    AgentPolicy,
    BudgetPolicy,
    FilesystemPolicy,
    DiffApprovalPolicy,
    AGENT_POLICIES,
    get_agent_policy,
)
from app.guardrails.budgets import (
    BudgetTracker,
    BudgetExceededError,
    BudgetType,
)
from app.guardrails.diff_approval import (
    DiffApprovalManager,
    PendingApproval,
    ApprovalStatus,
    diff_approval_manager,
)
from app.guardrails.audit_repository import AuditRepository
from app.guardrails.enforcer import (
    GuardrailsEnforcer,
    EnforcementContext,
    EnforcementResult,
)
from app.guardrails.approval_executor import (
    ApprovalExecutor,
    ApprovalExecutionError,
    approval_executor,
    execute_with_approval,
)
from app.guardrails.config import (
    GuardrailsSettings,
    get_guardrails_settings,
    reset_guardrails_settings,
    get_budget_limits,
    get_diff_approval_config,
    get_audit_retention_config,
    get_agent_tool_allowlist,
    get_config_summary,
    validate_guardrails_config,
    BudgetLimits,
    DiffApprovalConfig,
    AuditRetentionConfig,
)

__all__ = [
    # Policies
    "AgentPolicy",
    "BudgetPolicy",
    "FilesystemPolicy",
    "DiffApprovalPolicy",
    "AGENT_POLICIES",
    "get_agent_policy",
    # Budgets
    "BudgetTracker",
    "BudgetExceededError",
    "BudgetType",
    # Diff approval
    "DiffApprovalManager",
    "PendingApproval",
    "ApprovalStatus",
    "diff_approval_manager",
    # Audit
    "AuditRepository",
    # Enforcer
    "GuardrailsEnforcer",
    "EnforcementContext",
    "EnforcementResult",
    # Approval Executor
    "ApprovalExecutor",
    "ApprovalExecutionError",
    "approval_executor",
    "execute_with_approval",
    # Configuration
    "GuardrailsSettings",
    "get_guardrails_settings",
    "reset_guardrails_settings",
    "get_budget_limits",
    "get_diff_approval_config",
    "get_audit_retention_config",
    "get_agent_tool_allowlist",
    "get_config_summary",
    "validate_guardrails_config",
    "BudgetLimits",
    "DiffApprovalConfig",
    "AuditRetentionConfig",
]
