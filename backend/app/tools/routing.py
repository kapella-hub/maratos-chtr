"""Routing Tool - Forces explicit reasoning before agent delegation."""

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from app.tools.base import Tool, ToolParameter, ToolResult


class TaskType(str, Enum):
    """Types of tasks MO can handle."""
    DIRECT = "direct"  # MO handles directly
    ARCHITECT = "architect"  # Needs planning/analysis first
    CODER = "coder"  # Direct implementation
    REVIEWER = "reviewer"  # Code review
    TESTER = "tester"  # Test generation
    DOCS = "docs"  # Documentation
    DEVOPS = "devops"  # Infrastructure


class ContentType(str, Enum):
    """What the user is asking for."""
    CODE_IMPLEMENTATION = "code_implementation"  # Actual source files
    TEXT_CONTENT = "text_content"  # Prompts, docs, explanations
    INFORMATION = "information"  # Questions, advice
    ANALYSIS = "analysis"  # Review, suggestions
    DIAGRAM = "diagram"  # Visual/mermaid diagrams
    COMMAND = "command"  # Shell commands to run


@dataclass
class RoutingDecision:
    """Structured routing decision."""
    task_type: TaskType
    content_type: ContentType
    reasoning: str
    confidence: float  # 0.0 - 1.0
    user_intent: str  # One-line summary of what user wants
    warnings: list[str] = field(default_factory=list)


# Keywords that suggest different content types
CODE_IMPL_SIGNALS = [
    r'\b(implement|build|add|fix|modify|update|refactor)\b.*\b(function|class|component|feature|endpoint|api|module)\b',
    r'\b(in|to|for)\s+[\w/]+\.(py|ts|tsx|js|jsx|go|rs|java|cpp|c|rb|swift)\b',
    r'\bcreate\s+(a\s+)?new\s+(file|component|module|class)\b',
    r'\bwrite\s+(the\s+)?(code|implementation)\b',
]

TEXT_CONTENT_SIGNALS = [
    r'\b(write|create|generate|make|give)\s+(me\s+)?(a\s+)?(prompt|template|instruction|guide|spec|plan|outline|description|example)\b',
    r'\b(document|explain|describe)\s+(how|what|why)\b',
    r'\bwrite\s+(up|out)\b',
    r'\bcreate\s+a\s+prompt\b',
    r'\bprompt\s+for\b',
]

QUESTION_SIGNALS = [
    r'^(what|how|why|when|where|can|could|should|is|are|do|does|will|would)\b',
    r'\?$',
    r'\b(explain|tell me|help me understand)\b',
]

ANALYSIS_SIGNALS = [
    r'\b(review|analyze|check|audit|suggest|recommend|improve)\b',
    r'\b(what do you think|any suggestions|how can i make)\b',
    r'\blook at\b.*\b(code|file|implementation)\b',
]


def analyze_intent(message: str) -> tuple[ContentType, list[str], float]:
    """Analyze message to determine content type and confidence."""
    message_lower = message.lower()
    signals_found = []
    scores = {
        ContentType.CODE_IMPLEMENTATION: 0,
        ContentType.TEXT_CONTENT: 0,
        ContentType.INFORMATION: 0,
        ContentType.ANALYSIS: 0,
    }

    # Check for text content signals (highest priority for disambiguation)
    for pattern in TEXT_CONTENT_SIGNALS:
        if re.search(pattern, message_lower):
            signals_found.append(f"text_content: matched '{pattern}'")
            scores[ContentType.TEXT_CONTENT] += 2  # Higher weight

    # Check for code implementation signals
    for pattern in CODE_IMPL_SIGNALS:
        if re.search(pattern, message_lower):
            signals_found.append(f"code_impl: matched '{pattern}'")
            scores[ContentType.CODE_IMPLEMENTATION] += 1

    # Check for question signals
    for pattern in QUESTION_SIGNALS:
        if re.search(pattern, message_lower):
            signals_found.append(f"question: matched '{pattern}'")
            scores[ContentType.INFORMATION] += 1

    # Check for analysis signals
    for pattern in ANALYSIS_SIGNALS:
        if re.search(pattern, message_lower):
            signals_found.append(f"analysis: matched '{pattern}'")
            scores[ContentType.ANALYSIS] += 1

    # Determine primary content type
    max_score = max(scores.values())
    if max_score == 0:
        return ContentType.INFORMATION, signals_found, 0.5

    # Find the type with highest score
    for content_type, score in scores.items():
        if score == max_score:
            confidence = min(0.9, 0.5 + (score * 0.15))
            return content_type, signals_found, confidence

    return ContentType.INFORMATION, signals_found, 0.5


def validate_routing(
    task_type: str,
    content_type: str,
    reasoning: str,
    user_intent: str,
    confidence: float,
    original_message: str,
) -> dict[str, Any]:
    """Validate a routing decision and provide feedback."""
    warnings = []
    feedback_parts = []

    # Parse task type
    try:
        task = TaskType(task_type.lower())
    except ValueError:
        return {
            "valid": False,
            "feedback": f"Invalid task_type '{task_type}'. Must be one of: {[t.value for t in TaskType]}",
            "suggested_type": None,
            "proceed": False,
        }

    # Parse content type
    try:
        content = ContentType(content_type.lower())
    except ValueError:
        return {
            "valid": False,
            "feedback": f"Invalid content_type '{content_type}'. Must be one of: {[c.value for c in ContentType]}",
            "suggested_type": None,
            "proceed": False,
        }

    # Analyze the original message
    detected_content, signals, detected_confidence = analyze_intent(original_message)

    suggested_type = None
    mismatch_detected = False

    # Rule 1: Text content should be handled directly
    if content == ContentType.TEXT_CONTENT and task != TaskType.DIRECT:
        warnings.append(
            "Content type is 'text_content' (prompts, docs, explanations) - this should be handled DIRECTLY, not by an agent."
        )
        suggested_type = TaskType.DIRECT
        mismatch_detected = True

    # Rule 2: Questions/information should be handled directly
    if content == ContentType.INFORMATION and task != TaskType.DIRECT:
        warnings.append(
            "Content type is 'information' (questions, advice) - this should be answered DIRECTLY."
        )
        suggested_type = TaskType.DIRECT
        mismatch_detected = True

    # Rule 3: If we detected text_content but MO classified differently
    if detected_content == ContentType.TEXT_CONTENT and content != ContentType.TEXT_CONTENT:
        warnings.append(
            f"⚠️ MISMATCH: Message appears to request TEXT content (prompt/template/docs) "
            f"but you classified it as '{content.value}'. Signals: {[s for s in signals if 'text_content' in s]}"
        )
        if task != TaskType.DIRECT:
            suggested_type = TaskType.DIRECT
            mismatch_detected = True

    # Rule 4: Analysis without code changes should usually be direct
    if content == ContentType.ANALYSIS and task not in [TaskType.DIRECT, TaskType.REVIEWER]:
        warnings.append(
            "Analysis/review tasks are typically handled directly or by the reviewer agent."
        )

    # Rule 5: Low confidence should trigger reconsideration
    if confidence < 0.6:
        warnings.append(
            f"Low confidence ({confidence:.0%}). Consider if you fully understand what the user wants."
        )

    # Build decision record
    decision = RoutingDecision(
        task_type=task,
        content_type=content,
        reasoning=reasoning,
        confidence=confidence,
        user_intent=user_intent,
        warnings=warnings,
    )

    # Determine if we should block or warn
    should_block = mismatch_detected and detected_confidence > 0.7

    if should_block:
        feedback_parts.append(
            f"🛑 ROUTING BLOCKED: Strong mismatch detected between your classification and message analysis."
        )
        feedback_parts.append(f"You chose: task_type='{task.value}', content_type='{content.value}'")
        feedback_parts.append(f"Analysis suggests: content is likely '{detected_content.value}' (confidence: {detected_confidence:.0%})")
        feedback_parts.append(f"Recommendation: Use task_type='{suggested_type.value if suggested_type else 'direct'}' instead.")
    elif warnings:
        feedback_parts.append("⚠️ WARNINGS:")
        for w in warnings:
            feedback_parts.append(f"  • {w}")

    return {
        "valid": not should_block,
        "decision": {
            "task_type": decision.task_type.value,
            "content_type": decision.content_type.value,
            "reasoning": decision.reasoning,
            "confidence": decision.confidence,
            "user_intent": decision.user_intent,
            "warnings": decision.warnings,
        },
        "feedback": "\n".join(feedback_parts) if feedback_parts else None,
        "suggested_type": suggested_type.value if suggested_type else None,
        "detected_content": detected_content.value,
        "detected_confidence": detected_confidence,
        "detected_signals": signals,
        "proceed": not should_block,
    }


@dataclass
class RoutingTool(Tool):
    """Tool that forces explicit routing decisions before action."""

    id: str = "routing"
    name: str = "Decide Routing"
    description: str = """MANDATORY: Call this tool FIRST before responding to ANY user request.

This tool validates your routing decision against the user's actual intent.
It will BLOCK incorrect routing (e.g., sending text generation tasks to coder).

Call this BEFORE:
- Spawning any agent ([SPAWN:...])
- Responding directly
- Taking any action

If the tool returns proceed=false, you MUST reconsider and call again with corrected values."""

    parameters: list[ToolParameter] = field(default_factory=lambda: [
        ToolParameter(
            name="original_message",
            type="string",
            description="Copy the user's EXACT message here verbatim. This is used to validate your routing decision.",
        ),
        ToolParameter(
            name="task_type",
            type="string",
            description="How to handle: 'direct' (MO responds), or agent name (architect/coder/reviewer/tester/docs/devops)",
            enum=["direct", "architect", "coder", "reviewer", "tester", "docs", "devops"],
        ),
        ToolParameter(
            name="content_type",
            type="string",
            description="What user wants: 'text_content' (prompts/docs/explanations), 'code_implementation' (actual source files), 'information' (questions), 'analysis' (review/suggestions), 'diagram', 'command'",
            enum=["code_implementation", "text_content", "information", "analysis", "diagram", "command"],
        ),
        ToolParameter(
            name="reasoning",
            type="string",
            description="WHY you chose this routing. Be specific about what the user is asking for.",
        ),
        ToolParameter(
            name="user_intent",
            type="string",
            description="One sentence: What does the user want to RECEIVE? (e.g., 'A prompt template for code reviews')",
        ),
        ToolParameter(
            name="confidence",
            type="number",
            description="How confident are you? (0.0-1.0)",
        ),
    ])

    # This will be set by the agent before execution
    _original_message: str = ""

    def set_context(self, original_message: str) -> None:
        """Set the original user message for validation."""
        self._original_message = original_message

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute routing validation."""
        original_message = kwargs.get("original_message", "")
        task_type = kwargs.get("task_type", "direct")
        content_type = kwargs.get("content_type", "information")
        reasoning = kwargs.get("reasoning", "")
        user_intent = kwargs.get("user_intent", "")
        confidence = kwargs.get("confidence", 0.5)

        # Use passed original_message, fallback to stored context
        message_to_validate = original_message or self._original_message

        result = validate_routing(
            task_type=task_type,
            content_type=content_type,
            reasoning=reasoning,
            user_intent=user_intent,
            confidence=confidence,
            original_message=message_to_validate,
        )

        # Format response
        lines = [
            "## Routing Decision",
            f"- **Task Type:** {result['decision']['task_type']}",
            f"- **Content Type:** {result['decision']['content_type']}",
            f"- **User Intent:** {result['decision']['user_intent']}",
            f"- **Your Confidence:** {result['decision']['confidence']:.0%}",
            "",
            "## Analysis",
            f"- **Detected Content Type:** {result['detected_content']}",
            f"- **Detection Confidence:** {result['detected_confidence']:.0%}",
        ]

        if result["detected_signals"]:
            lines.append(f"- **Signals Found:** {len(result['detected_signals'])}")

        if result["feedback"]:
            lines.append("")
            lines.append(result["feedback"])

        lines.append("")
        if result["proceed"]:
            lines.append(f"✅ **PROCEED** with task_type='{result['decision']['task_type']}'")
        else:
            lines.append(f"❌ **BLOCKED** - Reconsider routing. Suggested: '{result['suggested_type']}'")

        return ToolResult(
            success=result["proceed"],
            output="\n".join(lines),
            data=result,
        )


# Register the tool
from app.tools.base import registry
registry.register(RoutingTool())
