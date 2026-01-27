"""Thinking module for structured AI reasoning.

This module provides:
- Structured thinking models (ThinkingStep, ThinkingBlock, ThinkingSession)
- ThinkingManager for handling thinking operations
- AdaptiveThinkingManager for context-aware level selection
- ThinkingTemplates for task-specific reasoning patterns
- ThinkingMetrics for tracking and analysis
"""

from app.thinking.models import (
    ThinkingLevel,
    ThinkingStepType,
    ThinkingStep,
    ThinkingBlock,
    ThinkingSession,
)
from app.thinking.manager import ThinkingManager
from app.thinking.templates import ThinkingTemplates, get_template
from app.thinking.adaptive import AdaptiveThinkingManager
from app.thinking.metrics import ThinkingMetrics

__all__ = [
    "ThinkingLevel",
    "ThinkingStepType",
    "ThinkingStep",
    "ThinkingBlock",
    "ThinkingSession",
    "ThinkingManager",
    "ThinkingTemplates",
    "get_template",
    "AdaptiveThinkingManager",
    "ThinkingMetrics",
]
