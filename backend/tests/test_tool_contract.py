"""Tests for tool contract presence in agent prompts."""

import pytest

from app.agents.architect import ArchitectAgent
from app.agents.coder import CoderAgent
from app.agents.devops import DevOpsAgent
from app.agents.docs import DocsAgent
from app.agents.mo import MOAgent
from app.agents.reviewer import ReviewerAgent
from app.agents.tester import TesterAgent
from app.agents.tool_contract import TOOL_CALL_CONTRACT, TOOL_POLICIES


class TestToolContractInPrompts:
    """Verify all agents include the tool call contract in their prompts."""

    @pytest.fixture
    def agents(self):
        """Create instances of all agents."""
        return {
            "mo": MOAgent(),
            "architect": ArchitectAgent(),
            "coder": CoderAgent(),
            "reviewer": ReviewerAgent(),
            "tester": TesterAgent(),
            "docs": DocsAgent(),
            "devops": DevOpsAgent(),
        }

    def test_all_agents_have_tool_execution_contract(self, agents):
        """Every agent prompt must include the TOOL EXECUTION CONTRACT section."""
        for agent_id, agent in agents.items():
            prompt, _ = agent.get_system_prompt()
            assert "## TOOL EXECUTION CONTRACT" in prompt, (
                f"Agent '{agent_id}' is missing TOOL EXECUTION CONTRACT section"
            )

    def test_all_agents_have_tool_call_format(self, agents):
        """Every agent prompt must include the canonical tool_call format."""
        for agent_id, agent in agents.items():
            prompt, _ = agent.get_system_prompt()
            assert '<tool_call>{"tool":' in prompt or "<tool_call>{" in prompt, (
                f"Agent '{agent_id}' is missing <tool_call> format examples"
            )

    def test_all_agents_have_tool_policy(self, agents):
        """Every agent prompt must include a TOOL POLICY section."""
        for agent_id, agent in agents.items():
            prompt, _ = agent.get_system_prompt()
            assert "## TOOL POLICY" in prompt, (
                f"Agent '{agent_id}' is missing TOOL POLICY section"
            )

    def test_all_agents_have_allowed_tools_listed(self, agents):
        """Every agent prompt must list allowed tools."""
        for agent_id, agent in agents.items():
            prompt, _ = agent.get_system_prompt()
            assert "**Allowed Tools:**" in prompt, (
                f"Agent '{agent_id}' is missing Allowed Tools list"
            )

    def test_no_pseudo_syntax_in_prompts(self, agents):
        """Prompts should not contain old pseudo-syntax like 'filesystem action='."""
        # Patterns that indicate old pseudo-syntax
        old_patterns = [
            "filesystem action=read",
            "filesystem action=write",
            "filesystem action=list",
            "shell command=",
            "sessions action=list limit=",  # old format without JSON
        ]

        for agent_id, agent in agents.items():
            prompt, _ = agent.get_system_prompt()
            for pattern in old_patterns:
                # Allow patterns inside <tool_call> JSON (proper format)
                # Disallow patterns outside tool_call blocks (pseudo-syntax)
                lines = prompt.split("\n")
                for line in lines:
                    if pattern in line and "<tool_call>" not in line:
                        # Could be inside a code block showing examples - check context
                        # Allow if inside proper tool_call examples
                        if '{"tool":' not in line and '"args":' not in line:
                            pytest.fail(
                                f"Agent '{agent_id}' uses old pseudo-syntax: '{pattern}'\n"
                                f"Line: {line.strip()}"
                            )


class TestToolPoliciesConfiguration:
    """Verify tool policies are configured correctly."""

    def test_all_standard_agents_have_policies(self):
        """All standard agent types should have defined policies."""
        required_agents = ["mo", "architect", "coder", "reviewer", "tester", "docs", "devops"]
        for agent_type in required_agents:
            assert agent_type in TOOL_POLICIES, (
                f"Missing policy for agent type '{agent_type}'"
            )

    def test_reviewer_is_read_only(self):
        """Reviewer agent should have no write paths (read-only for reviews)."""
        policy = TOOL_POLICIES["reviewer"]
        assert policy["write_paths"] == [], (
            "Reviewer should be read-only (empty write_paths)"
        )

    def test_tester_requires_workspace(self):
        """Tester should only write to workspace."""
        policy = TOOL_POLICIES["tester"]
        assert "~/maratos-workspace" in policy["write_paths"], (
            "Tester should write to ~/maratos-workspace"
        )

    def test_mo_has_routing_tool(self):
        """MO should have access to routing tool."""
        policy = TOOL_POLICIES["mo"]
        assert "routing" in policy["allowed"], (
            "MO should have routing tool access"
        )

    def test_all_policies_have_required_fields(self):
        """Each policy must have allowed, read_paths, write_paths, notes."""
        required_fields = ["allowed", "read_paths", "write_paths", "notes"]
        for agent_type, policy in TOOL_POLICIES.items():
            for field in required_fields:
                assert field in policy, (
                    f"Policy for '{agent_type}' missing required field '{field}'"
                )


class TestToolCallExamples:
    """Verify tool call examples in the contract are valid."""

    def test_contract_has_filesystem_examples(self):
        """Contract should include filesystem tool examples."""
        assert '"tool": "filesystem"' in TOOL_CALL_CONTRACT
        assert '"action": "read"' in TOOL_CALL_CONTRACT
        assert '"action": "write"' in TOOL_CALL_CONTRACT

    def test_contract_has_shell_example(self):
        """Contract should include shell tool example."""
        assert '"tool": "shell"' in TOOL_CALL_CONTRACT
        assert '"command":' in TOOL_CALL_CONTRACT

    def test_contract_has_kiro_examples(self):
        """Contract should include kiro tool examples."""
        assert '"tool": "kiro"' in TOOL_CALL_CONTRACT
        assert '"action": "architect"' in TOOL_CALL_CONTRACT or '"action": "validate"' in TOOL_CALL_CONTRACT

    def test_contract_has_web_examples(self):
        """Contract should include web tool examples."""
        assert '"tool": "web_search"' in TOOL_CALL_CONTRACT
        assert '"tool": "web_fetch"' in TOOL_CALL_CONTRACT
