"""Automatic model selection for autonomous development tasks.

Selects the most appropriate model based on:
- Agent type (architect, coder, reviewer, tester, docs, devops)
- Task complexity (inferred from description or explicit)
- Quality gate requirements

Models are dynamically discovered from kiro-cli to ensure compatibility.
"""

import logging
import re
import subprocess
from dataclasses import dataclass
from enum import Enum
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)


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
    credit_multiplier: float = 1.0  # Cost relative to base


# Kiro-cli model names and their credit multipliers
# Based on: Auto (1x), claude-sonnet-4.5 (1.3x), claude-sonnet-4 (1.3x),
#           claude-haiku-4.5 (0.4x), claude-opus-4.5 (2.2x)
KIRO_MODEL_CREDITS = {
    "Auto": 1.0,
    "claude-opus-4.5": 2.2,
    "claude-sonnet-4.5": 1.3,
    "claude-sonnet-4": 1.3,
    "claude-haiku-4.5": 0.4,
}


def discover_available_models() -> list[str]:
    """Discover available models by querying kiro-cli.

    Executes `kiro-cli chat --model invalid "test"` and parses the error
    message to extract available model names. This ensures future compatibility
    when new models are added.

    Returns:
        List of available model names
    """
    try:
        # Run kiro-cli with an invalid model to get the error with available models
        result = subprocess.run(
            ["kiro-cli", "chat", "--model", "__invalid_model__", "test"],
            capture_output=True,
            text=True,
            timeout=10,
        )

        # Parse the error message for available models
        # Expected format: "error: Model '__invalid_model__' does not exist. Available models: Auto, claude-sonnet-4.5, ..."
        output = result.stderr or result.stdout

        # Look for "Available models:" in the output
        match = re.search(r"Available models?:\s*(.+?)(?:\n|$)", output, re.IGNORECASE)
        if match:
            models_str = match.group(1).strip()
            # Split by comma and clean up
            models = [m.strip() for m in models_str.split(",") if m.strip()]
            logger.info(f"Discovered kiro-cli models: {models}")
            return models

        logger.warning(f"Could not parse models from kiro-cli output: {output}")
        return []

    except FileNotFoundError:
        logger.warning("kiro-cli not found in PATH, using default models")
        return []
    except subprocess.TimeoutExpired:
        logger.warning("kiro-cli timed out, using default models")
        return []
    except Exception as e:
        logger.warning(f"Error discovering models from kiro-cli: {e}")
        return []


def _get_available_models() -> list[str]:
    """Get available models, with caching."""
    if not hasattr(_get_available_models, "_cache"):
        discovered = discover_available_models()
        # Use discovered models or fall back to known defaults
        _get_available_models._cache = discovered if discovered else list(KIRO_MODEL_CREDITS.keys())
    return _get_available_models._cache


def _select_best_model(preference_order: list[str]) -> str:
    """Select the best available model from a preference order.

    Args:
        preference_order: List of model names in order of preference

    Returns:
        The first available model, or "Auto" as fallback
    """
    available = _get_available_models()

    for model in preference_order:
        if model in available:
            return model

    # Fallback to Auto if available
    if "Auto" in available:
        return "Auto"

    # Last resort: return first available
    return available[0] if available else "claude-sonnet-4"


# Default model configurations for each tier
# Using kiro-cli model names with dynamic selection
DEFAULT_MODELS = {
    ModelTier.TIER_1_ADVANCED: ModelConfig(
        model_id=_select_best_model(["claude-opus-4.5"]),
        description="Most capable - complex architecture, critical decisions (2.2x credits)",
        max_tokens=8192,
        temperature=0.7,
        credit_multiplier=2.2,
    ),
    ModelTier.TIER_2_BALANCED: ModelConfig(
        model_id=_select_best_model(["claude-sonnet-4.5", "claude-sonnet-4"]),
        description="Balanced - coding, review, testing (1.3x credits)",
        max_tokens=8192,
        temperature=0.7,
        credit_multiplier=1.3,
    ),
    ModelTier.TIER_3_FAST: ModelConfig(
        model_id=_select_best_model(["claude-haiku-4.5"]),
        description="Fast - documentation, simple fixes (0.4x credits)",
        max_tokens=4096,
        temperature=0.5,
        credit_multiplier=0.4,
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

        # Apply user preference from settings
        user_model = settings.default_model
        if user_model and user_model != "claude-sonnet-4":  # Don't override if it's the default
            # kiro-cli uses short model names directly
            clean_model = user_model.split("/")[-1] if "/" in user_model else user_model
            
            # Update Balanced Tier (the workhorse) to use user's choice
            # We assume the user picked a model they want to use for development
            self.models[ModelTier.TIER_2_BALANCED].model_id = clean_model
            self.models[ModelTier.TIER_2_BALANCED].description += " (User Selected)"
            
            # If user picked an Opus model, upgrade Tier 1 as well just in case
            if "opus" in clean_model.lower():
                 self.models[ModelTier.TIER_1_ADVANCED].model_id = clean_model
                 self.models[ModelTier.TIER_1_ADVANCED].description += " (User Selected)"

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

        Uses actual kiro-cli credit multipliers:
        - opus-4.5: 2.2x credits
        - sonnet-4.5/4: 1.3x credits
        - haiku-4.5: 0.4x credits
        """
        # Get actual credit multipliers from model configs
        cost_ratios = {
            tier: config.credit_multiplier
            for tier, config in self.models.items()
        }

        # Typical task distribution
        tier_distribution = {
            ModelTier.TIER_1_ADVANCED: 0.15,  # 15% need top tier (architecture, critical)
            ModelTier.TIER_2_BALANCED: 0.60,  # 60% balanced (coding, testing, review)
            ModelTier.TIER_3_FAST: 0.25,      # 25% can use fast (docs, simple fixes)
        }

        # Cost if using top tier (opus) for everything
        all_top_tier_cost = task_count * avg_tokens_per_task * cost_ratios[ModelTier.TIER_1_ADVANCED]

        # Cost with tiered selection
        tiered_cost = sum(
            task_count * pct * avg_tokens_per_task * cost_ratios[tier]
            for tier, pct in tier_distribution.items()
        )

        savings_pct = (1 - tiered_cost / all_top_tier_cost) * 100

        return {
            "all_top_tier_relative_cost": round(all_top_tier_cost, 2),
            "tiered_relative_cost": round(tiered_cost, 2),
            "savings_percent": round(savings_pct, 1),
            "tier_distribution": {t.value: f"{p*100:.0f}%" for t, p in tier_distribution.items()},
            "models_used": {
                t.value: f"{self.models[t].model_id} ({self.models[t].credit_multiplier}x)"
                for t in ModelTier
            },
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


def refresh_available_models() -> list[str]:
    """Force refresh the available models cache by re-querying kiro-cli.

    Returns:
        Updated list of available model names
    """
    if hasattr(_get_available_models, "_cache"):
        delattr(_get_available_models, "_cache")
    return _get_available_models()


def get_available_models_info() -> dict[str, Any]:
    """Get information about available models and current tier assignments.

    Returns:
        Dict with available models, tier assignments, and credit info
    """
    available = _get_available_models()

    return {
        "available_models": available,
        "tier_assignments": {
            tier.value: {
                "model": config.model_id,
                "description": config.description,
                "credit_multiplier": config.credit_multiplier,
                "max_tokens": config.max_tokens,
                "temperature": config.temperature,
            }
            for tier, config in model_selector.models.items()
        },
        "known_credits": KIRO_MODEL_CREDITS,
    }
