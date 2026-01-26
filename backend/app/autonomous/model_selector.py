"""Automatic model selection for autonomous development tasks.

Selects the most appropriate model based on:
- Agent type (architect, coder, reviewer, tester, docs, devops)
- Task complexity (inferred from description or explicit)
- Quality gate requirements
"""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.config import settings


class ModelTier(str, Enum):
    """Model capability tiers."""
    TIER_1_ADVANCED = "tier_1"    # Most capable - complex reasoning, architecture
    TIER_2_BALANCED = "tier_2"   # Balanced - general coding, review
    TIER_3_FAST = "tier_3"       # Fast/cheap - documentation, simple tasks


@dataclass
class ModelConfig:
    """Configuration for a model tier."""
    model_id: str
    description: str
    max_tokens: int = 8192
    temperature: float = 0.7


# Default model configurations for each tier
# These can be customized via environment or settings
DEFAULT_MODELS = {
    ModelTier.TIER_1_ADVANCED: ModelConfig(
        model_id="claude-opus-4",
        description="Most capable - complex architecture, critical decisions",
        max_tokens=8192,
        temperature=0.7,
    ),
    ModelTier.TIER_2_BALANCED: ModelConfig(
        model_id="claude-sonnet-4",
        description="Balanced - coding, review, testing",
        max_tokens=8192,
        temperature=0.7,
    ),
    ModelTier.TIER_3_FAST: ModelConfig(
        model_id="claude-3-5-haiku-latest",
        description="Fast - documentation, simple fixes",
        max_tokens=4096,
        temperature=0.5,
    ),
}


# Agent type to default tier mapping
AGENT_DEFAULT_TIERS = {
    "architect": ModelTier.TIER_1_ADVANCED,   # Architecture requires deep reasoning
    "coder": ModelTier.TIER_2_BALANCED,       # Coding is balanced
    "reviewer": ModelTier.TIER_2_BALANCED,    # Review needs good understanding
    "tester": ModelTier.TIER_2_BALANCED,      # Testing needs precision
    "docs": ModelTier.TIER_3_FAST,            # Documentation is simpler
    "devops": ModelTier.TIER_2_BALANCED,      # DevOps needs reliability
    "mo": ModelTier.TIER_2_BALANCED,          # Orchestrator uses balanced
}


# Keywords that indicate task complexity
COMPLEXITY_KEYWORDS = {
    "high": [
        "architect", "design", "security", "authentication", "authorization",
        "database schema", "api design", "refactor", "optimize", "performance",
        "concurrency", "async", "distributed", "microservice", "integration",
        "migration", "critical", "complex", "algorithm", "data structure",
    ],
    "medium": [
        "implement", "create", "build", "add", "update", "modify", "fix",
        "test", "review", "validate", "endpoint", "component", "service",
        "handler", "controller", "model", "query", "function", "class",
    ],
    "low": [
        "document", "readme", "comment", "docstring", "changelog", "typo",
        "format", "lint", "style", "rename", "move", "copy", "simple",
        "basic", "trivial", "minor", "cleanup", "organize",
    ],
}


class ModelSelector:
    """Selects appropriate models for autonomous tasks."""

    def __init__(self, custom_models: dict[ModelTier, ModelConfig] | None = None) -> None:
        """Initialize with optional custom model configurations."""
        self.models = DEFAULT_MODELS.copy()
        if custom_models:
            self.models.update(custom_models)

    def get_model_for_agent(
        self,
        agent_type: str,
        task_description: str | None = None,
        quality_gates: list[str] | None = None,
        force_tier: ModelTier | None = None,
    ) -> ModelConfig:
        """Get the appropriate model for an agent and task.

        Args:
            agent_type: The type of agent (coder, tester, etc.)
            task_description: Optional task description for complexity analysis
            quality_gates: Optional list of quality gates (affects tier selection)
            force_tier: Optional tier override

        Returns:
            ModelConfig for the selected model
        """
        if force_tier:
            return self.models[force_tier]

        # Start with agent default tier
        tier = AGENT_DEFAULT_TIERS.get(agent_type, ModelTier.TIER_2_BALANCED)

        # Adjust based on task complexity if description provided
        if task_description:
            complexity = self._analyze_complexity(task_description)

            if complexity == "high" and tier != ModelTier.TIER_1_ADVANCED:
                tier = ModelTier.TIER_1_ADVANCED
            elif complexity == "low" and tier == ModelTier.TIER_2_BALANCED:
                # Only downgrade balanced tier, not advanced
                tier = ModelTier.TIER_3_FAST

        # Upgrade tier if critical quality gates present
        if quality_gates:
            critical_gates = {"tests_pass", "review_approved", "type_check"}
            if any(gate in critical_gates for gate in quality_gates):
                if tier == ModelTier.TIER_3_FAST:
                    tier = ModelTier.TIER_2_BALANCED

        return self.models[tier]

    def _analyze_complexity(self, description: str) -> str:
        """Analyze task description to determine complexity.

        Returns: "high", "medium", or "low"
        """
        description_lower = description.lower()

        # Count keyword matches for each level
        high_count = sum(1 for kw in COMPLEXITY_KEYWORDS["high"] if kw in description_lower)
        low_count = sum(1 for kw in COMPLEXITY_KEYWORDS["low"] if kw in description_lower)

        # Check for explicit complexity indicators
        if any(x in description_lower for x in ["complex", "critical", "security", "architecture"]):
            return "high"

        if any(x in description_lower for x in ["simple", "trivial", "basic", "minor"]):
            return "low"

        # Use keyword counts
        if high_count >= 2:
            return "high"
        if low_count >= 2 and high_count == 0:
            return "low"

        return "medium"

    def get_tier_for_phase(self, phase: str) -> ModelTier:
        """Get recommended tier for a project phase.

        Args:
            phase: Project phase (planning, implementation, testing, documentation)

        Returns:
            Recommended ModelTier
        """
        phase_tiers = {
            "planning": ModelTier.TIER_1_ADVANCED,      # Planning needs best reasoning
            "implementation": ModelTier.TIER_2_BALANCED,  # Coding is balanced
            "testing": ModelTier.TIER_2_BALANCED,        # Testing needs reliability
            "review": ModelTier.TIER_2_BALANCED,         # Review needs understanding
            "documentation": ModelTier.TIER_3_FAST,      # Docs are simpler
            "finalization": ModelTier.TIER_3_FAST,       # Final steps are routine
        }
        return phase_tiers.get(phase, ModelTier.TIER_2_BALANCED)

    def estimate_cost_savings(
        self,
        task_count: int,
        avg_tokens_per_task: int = 2000,
    ) -> dict[str, Any]:
        """Estimate cost savings from tiered model selection vs using top tier for all.

        This is an approximation based on typical pricing ratios.
        """
        # Approximate cost ratios (tier 1 = 1.0)
        cost_ratios = {
            ModelTier.TIER_1_ADVANCED: 1.0,
            ModelTier.TIER_2_BALANCED: 0.2,   # ~5x cheaper
            ModelTier.TIER_3_FAST: 0.04,      # ~25x cheaper
        }

        # Typical task distribution
        tier_distribution = {
            ModelTier.TIER_1_ADVANCED: 0.15,  # 15% need top tier
            ModelTier.TIER_2_BALANCED: 0.60,  # 60% balanced
            ModelTier.TIER_3_FAST: 0.25,      # 25% can use fast
        }

        all_top_tier_cost = task_count * avg_tokens_per_task * cost_ratios[ModelTier.TIER_1_ADVANCED]

        tiered_cost = sum(
            task_count * pct * avg_tokens_per_task * cost_ratios[tier]
            for tier, pct in tier_distribution.items()
        )

        savings_pct = (1 - tiered_cost / all_top_tier_cost) * 100

        return {
            "all_top_tier_relative_cost": all_top_tier_cost,
            "tiered_relative_cost": tiered_cost,
            "savings_percent": round(savings_pct, 1),
            "tier_distribution": {t.value: f"{p*100:.0f}%" for t, p in tier_distribution.items()},
        }


# Global model selector instance
model_selector = ModelSelector()


def get_model_for_task(
    agent_type: str,
    task_description: str | None = None,
    quality_gates: list[str] | None = None,
) -> str:
    """Convenience function to get model ID for a task.

    Args:
        agent_type: Type of agent
        task_description: Optional task description
        quality_gates: Optional quality gates

    Returns:
        Model ID string
    """
    config = model_selector.get_model_for_agent(
        agent_type=agent_type,
        task_description=task_description,
        quality_gates=quality_gates,
    )
    return config.model_id


def get_model_config_for_task(
    agent_type: str,
    task_description: str | None = None,
    quality_gates: list[str] | None = None,
) -> ModelConfig:
    """Get full model config for a task.

    Args:
        agent_type: Type of agent
        task_description: Optional task description
        quality_gates: Optional quality gates

    Returns:
        ModelConfig with model_id, max_tokens, temperature
    """
    return model_selector.get_model_for_agent(
        agent_type=agent_type,
        task_description=task_description,
        quality_gates=quality_gates,
    )
