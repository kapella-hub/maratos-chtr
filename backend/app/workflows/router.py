"""Workflow Router - Determines if a message should trigger the delivery loop.

This module implements robust detection of coding tasks using:
1. Explicit commands (/code, /fix, /refactor, etc.)
2. Keyword-based classification with confidence scoring
3. Optional LLM classifier for ambiguous cases

The goal is LOW FALSE POSITIVES - we'd rather ask a clarifying question
than incorrectly trigger the workflow.
"""

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class RouterConfig:
    """Configuration for the workflow router."""

    # Master switch
    enabled: bool = True

    # Confidence thresholds (0.0 - 1.0)
    auto_trigger_threshold: float = 0.8  # Above this: auto-trigger workflow
    clarify_threshold: float = 0.5       # Between clarify and auto: ask user
    # Below clarify_threshold: don't trigger, handle normally

    # LLM classifier settings
    use_llm_classifier: bool = False  # Enable LLM for ambiguous cases
    llm_classifier_timeout: float = 5.0  # Seconds

    # Explicit command prefixes (always trigger if matched)
    explicit_commands: tuple[str, ...] = (
        "/code", "/implement", "/fix", "/refactor",
        "/feature", "/bug", "/test", "/endpoint",
    )


# Global config instance
router_config = RouterConfig()


def update_router_config(**kwargs) -> None:
    """Update router configuration."""
    for key, value in kwargs.items():
        if hasattr(router_config, key):
            setattr(router_config, key, value)


# =============================================================================
# Classification Result
# =============================================================================

class TaskType(str, Enum):
    """Types of tasks detected."""
    CODING = "coding"           # Implementation, bug fix, refactor
    TESTING = "testing"         # Write/run tests
    DOCUMENTATION = "documentation"  # Write docs
    DEVOPS = "devops"          # CI/CD, deployment
    EXPLANATION = "explanation"  # Explain, describe, help understand
    QUESTION = "question"       # General question
    UNKNOWN = "unknown"         # Cannot determine


@dataclass
class ClassificationResult:
    """Result of message classification."""
    task_type: TaskType
    confidence: float  # 0.0 - 1.0
    should_trigger_workflow: bool
    needs_clarification: bool
    clarification_question: str | None = None
    matched_keywords: list[str] = field(default_factory=list)
    matched_command: str | None = None
    reasoning: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type.value,
            "confidence": self.confidence,
            "should_trigger_workflow": self.should_trigger_workflow,
            "needs_clarification": self.needs_clarification,
            "clarification_question": self.clarification_question,
            "matched_keywords": self.matched_keywords,
            "matched_command": self.matched_command,
            "reasoning": self.reasoning,
        }


# =============================================================================
# Keyword Definitions
# =============================================================================

# Strong indicators of coding tasks (high confidence)
STRONG_CODING_KEYWORDS = {
    # Implementation verbs
    "implement": 0.9,
    "create a function": 0.9,
    "create a class": 0.9,
    "create an endpoint": 0.9,
    "create an api": 0.9,
    "add a function": 0.9,
    "add a method": 0.9,
    "add an endpoint": 0.9,
    "write code": 0.9,
    "write a function": 0.9,
    "write a class": 0.9,
    "build a": 0.85,
    "develop a": 0.85,

    # Bug fixing
    "fix the bug": 0.95,
    "fix this bug": 0.95,
    "fix the error": 0.9,
    "fix this error": 0.9,
    "debug": 0.8,
    "resolve the issue": 0.85,

    # Refactoring
    "refactor": 0.9,
    "restructure": 0.85,
    "rewrite": 0.8,
    "optimize the code": 0.85,
    "clean up the code": 0.8,

    # Feature work
    "add feature": 0.9,
    "new feature": 0.85,
    "implement feature": 0.95,

    # Specific code elements
    "add authentication": 0.9,
    "add validation": 0.85,
    "add error handling": 0.85,
    "add logging": 0.8,
    "add caching": 0.85,
    "add pagination": 0.85,
}

# Regex patterns for compound phrases (pattern -> confidence)
# These match phrases with words in between like "add X endpoint" or "create X component"
STRONG_CODING_PATTERNS = [
    (r'\badd\s+(?:\w+\s+)*endpoint\b', 0.9),
    (r'\badd\s+(?:\w+\s+)*validation\b', 0.9),
    (r'\bcreate\s+(?:\w+\s+)*component\b', 0.9),
    (r'\bcreate\s+(?:\w+\s+)*endpoint\b', 0.9),
    (r'\bcreate\s+(?:\w+\s+)*function\b', 0.9),
    (r'\bcreate\s+(?:\w+\s+)*class\b', 0.9),
    (r'\bfix\s+(?:\w+\s+)*error\b', 0.9),
    (r'\bfix\s+(?:\w+\s+)*bug\b', 0.95),
    (r'\bwrite\s+(?:\w+\s+)*test', 0.95),
    (r'\badd\s+(?:\w+\s+)*test', 0.9),
]

# Medium confidence keywords (need more context)
MEDIUM_CODING_KEYWORDS = {
    "add": 0.5,
    "create": 0.5,
    "make": 0.4,
    "change": 0.5,
    "modify": 0.6,
    "update": 0.5,
    "fix": 0.6,
    "improve": 0.5,
    "enhance": 0.5,
    "extend": 0.6,
    "integrate": 0.6,
    "connect": 0.5,
    "setup": 0.5,
    "configure": 0.5,
}

# Context keywords that boost confidence when combined with medium keywords
CODING_CONTEXT_KEYWORDS = {
    "function", "method", "class", "module", "component",
    "api", "endpoint", "route", "handler", "controller",
    "service", "model", "schema", "database", "table",
    "frontend", "backend", "ui", "interface", "button",
    "form", "page", "view", "template", "hook",
    "test", "spec", "unit test", "integration test",
    "file", "code", "script", "logic", "algorithm",
}

# Strong indicators of NON-coding tasks (reduce confidence)
NON_CODING_KEYWORDS = {
    "explain": 0.9,
    "what is": 0.9,
    "what are": 0.9,
    "how does": 0.85,
    "how do": 0.8,
    "how can you": 0.9,  # Questions about capabilities
    "how you can": 0.9,  # Alternative word order
    "how can i": 0.85,
    "how i can": 0.85,   # Alternative word order
    "how could": 0.85,
    "how would": 0.85,
    "how should": 0.85,
    "what would": 0.85,
    "what could": 0.85,
    "why does": 0.9,
    "why is": 0.9,
    "describe": 0.85,
    "tell me about": 0.9,
    "help me understand": 0.95,
    "can you explain": 0.9,
    "difference between": 0.9,
    "compare": 0.8,
    "list": 0.7,
    "show me": 0.6,
    "what's the": 0.8,
    "see how": 0.8,      # Exploratory questions
    "?": 0.3,  # Questions generally reduce confidence
}

# Testing-specific keywords
TESTING_KEYWORDS = {
    "write tests": 0.95,
    "add tests": 0.9,
    "create tests": 0.9,
    "test coverage": 0.85,
    "unit tests": 0.9,
    "integration tests": 0.9,
    "run tests": 0.7,  # Lower - might just be running, not writing
}

# DevOps keywords
DEVOPS_KEYWORDS = {
    "deploy": 0.85,
    "deployment": 0.8,
    "docker": 0.8,
    "kubernetes": 0.85,
    "ci/cd": 0.9,
    "pipeline": 0.75,
    "github actions": 0.85,
    "terraform": 0.85,
}


# =============================================================================
# Smart Intent Detection
# =============================================================================

# Question words that indicate interrogative intent
QUESTION_STARTERS = (
    "what", "why", "how", "when", "where", "who", "which",
    "is", "are", "can", "could", "would", "should", "do", "does",
    "have", "has", "will", "did", "was", "were",
)

# Strong imperative verbs (high confidence - clear coding intent)
STRONG_IMPERATIVE_VERBS = (
    "create", "build", "implement", "write", "develop",
    "fix", "repair", "resolve", "debug", "patch",
    "refactor", "rewrite",
)

# Weaker imperative verbs (need context for high confidence)
WEAK_IMPERATIVE_VERBS = (
    "add", "make", "update", "modify", "change", "edit",
    "delete", "remove", "drop",
    "setup", "configure", "install", "deploy",
    "test", "run", "execute", "check",
)


def _is_question(message: str) -> tuple[bool, str]:
    """Detect if message is a question based on structure.

    Returns (is_question, reason).
    """
    msg = message.strip()
    msg_lower = msg.lower()

    # Ends with question mark - strong signal
    if msg.endswith("?"):
        return True, "ends with ?"

    # Starts with question word
    first_word = msg_lower.split()[0] if msg_lower.split() else ""
    if first_word in QUESTION_STARTERS:
        return True, f"starts with '{first_word}'"

    # Contains question patterns mid-sentence
    question_patterns = [
        r"\bwhat\s+(?:is|are|does|do|can|could|would|should)\b",
        r"\bhow\s+(?:to|do|does|can|could|would|should|is|are)\b",
        r"\bwhy\s+(?:is|are|does|do|did|would|should)\b",
        r"\bcan\s+(?:you|i|we)\s+(?:explain|describe|tell|show|help)",
        r"\bcould\s+you\s+(?:explain|describe|tell|show|help)",
        r"\bis\s+(?:it|this|there)\s+(?:possible|a way)",
    ]
    for pattern in question_patterns:
        if re.search(pattern, msg_lower):
            return True, f"matches question pattern"

    return False, ""


def _is_imperative(message: str) -> tuple[bool, str, float]:
    """Detect if message is an imperative command.

    Returns (is_imperative, matched_verb, confidence).
    Strong verbs get high confidence, weak verbs get lower confidence.
    """
    msg_lower = message.lower().strip()
    words = msg_lower.split()

    if not words:
        return False, "", 0.0

    first_word = words[0]

    # Direct imperative: starts with strong action verb
    if first_word in STRONG_IMPERATIVE_VERBS:
        return True, first_word, 0.9

    # Direct imperative: starts with weak verb (needs context)
    if first_word in WEAK_IMPERATIVE_VERBS:
        # Check if there's coding context
        has_context = any(ctx in msg_lower for ctx in CODING_CONTEXT_KEYWORDS)
        confidence = 0.75 if has_context else 0.5
        return True, first_word, confidence

    # "Please" + verb
    if first_word == "please" and len(words) > 1:
        verb = words[1]
        if verb in STRONG_IMPERATIVE_VERBS:
            return True, verb, 0.85
        if verb in WEAK_IMPERATIVE_VERBS:
            has_context = any(ctx in msg_lower for ctx in CODING_CONTEXT_KEYWORDS)
            return True, verb, 0.7 if has_context else 0.45

    # "I want/need you to" + verb
    want_patterns = [
        r"^i\s+(?:want|need|would like)\s+(?:you\s+)?to\s+(\w+)",
        r"^(?:can|could|would)\s+you\s+(?:please\s+)?(\w+)",
    ]
    for pattern in want_patterns:
        match = re.match(pattern, msg_lower)
        if match:
            verb = match.group(1)
            if verb in STRONG_IMPERATIVE_VERBS:
                return True, verb, 0.8
            if verb in WEAK_IMPERATIVE_VERBS:
                return True, verb, 0.6

    return False, "", 0.0


# =============================================================================
# Keyword-based Classifier
# =============================================================================

def classify_by_keywords(message: str) -> ClassificationResult:
    """Classify message using smart intent detection + keyword matching.

    Priority:
    1. Explicit commands (/code, /fix, etc.)
    2. Question detection (structural)
    3. Imperative detection (structural)
    4. Keyword matching (fallback)
    """
    message_lower = message.lower().strip()
    matched_keywords = []
    task_type = TaskType.UNKNOWN
    base_confidence = 0.0

    # 1. Check for explicit commands first
    for cmd in router_config.explicit_commands:
        if message_lower.startswith(cmd):
            return ClassificationResult(
                task_type=TaskType.CODING,
                confidence=1.0,
                should_trigger_workflow=True,
                needs_clarification=False,
                matched_command=cmd,
                reasoning=f"Explicit command: {cmd}",
            )

    # 2. Smart question detection - check structure first
    is_question, question_reason = _is_question(message)
    if is_question:
        # Determine if it's an explanation request or general question
        is_explanation = any(word in message_lower for word in ("explain", "describe", "understand", "tell me"))
        return ClassificationResult(
            task_type=TaskType.EXPLANATION if is_explanation else TaskType.QUESTION,
            confidence=0.9,
            should_trigger_workflow=False,
            needs_clarification=False,
            matched_keywords=[question_reason],
            reasoning=f"Question detected: {question_reason}",
        )

    # 3. Check non-coding indicators (for non-question exploratory statements)
    for keyword, weight in NON_CODING_KEYWORDS.items():
        if keyword in message_lower:
            is_explanation = any(x in keyword for x in ("explain", "describe", "understand"))
            return ClassificationResult(
                task_type=TaskType.EXPLANATION if is_explanation else TaskType.QUESTION,
                confidence=weight,
                should_trigger_workflow=False,
                needs_clarification=False,
                matched_keywords=[keyword],
                reasoning=f"Non-coding indicator: {keyword}",
            )

    # 4. Check for specialized keywords first (testing, devops)
    # Check for testing keywords
    for keyword, weight in TESTING_KEYWORDS.items():
        if keyword in message_lower:
            matched_keywords.append(keyword)
            if weight > base_confidence:
                base_confidence = weight
                task_type = TaskType.TESTING

    # Check for devops keywords
    for keyword, weight in DEVOPS_KEYWORDS.items():
        if keyword in message_lower:
            matched_keywords.append(keyword)
            if weight > base_confidence:
                base_confidence = weight
                task_type = TaskType.DEVOPS

    # 5. Check for imperative commands - boost confidence for clear commands
    # Only if not already classified as testing/devops
    is_imperative, imperative_verb, imperative_confidence = _is_imperative(message)
    if is_imperative and task_type not in (TaskType.TESTING, TaskType.DEVOPS):
        matched_keywords.append(f"imperative:{imperative_verb}")
        base_confidence = max(base_confidence, imperative_confidence)
        task_type = TaskType.CODING

    # Check for strong coding keywords
    for keyword, weight in STRONG_CODING_KEYWORDS.items():
        if keyword in message_lower:
            matched_keywords.append(keyword)
            if weight > base_confidence:
                base_confidence = weight
                task_type = TaskType.CODING

    # Check for strong coding patterns (regex-based)
    for pattern, weight in STRONG_CODING_PATTERNS:
        if re.search(pattern, message_lower):
            matched_keywords.append(f"pattern:{pattern[:20]}...")
            if weight > base_confidence:
                base_confidence = weight
                task_type = TaskType.CODING

    # Check for medium keywords with context boost
    if base_confidence < 0.7:
        for keyword, weight in MEDIUM_CODING_KEYWORDS.items():
            if re.search(rf'\b{keyword}\b', message_lower):
                # Check for context boost
                context_matches = sum(1 for ctx in CODING_CONTEXT_KEYWORDS if ctx in message_lower)
                boosted_weight = min(weight + (context_matches * 0.1), 0.9)

                if boosted_weight > base_confidence:
                    matched_keywords.append(keyword)
                    base_confidence = boosted_weight
                    task_type = TaskType.CODING

    # Determine if we should trigger
    should_trigger = base_confidence >= router_config.auto_trigger_threshold
    needs_clarification = (
        router_config.clarify_threshold <= base_confidence < router_config.auto_trigger_threshold
    )

    # Generate clarification question if needed
    clarification_question = None
    if needs_clarification:
        if task_type == TaskType.CODING:
            clarification_question = (
                "This looks like a coding task. Should I implement this using the "
                "coder → tester → devops workflow? (yes/no)"
            )
        elif task_type == TaskType.TESTING:
            clarification_question = (
                "Should I write and run tests for this? The workflow will validate "
                "the implementation. (yes/no)"
            )
        else:
            clarification_question = (
                "I'm not sure if this requires code changes. Should I start "
                "the coding workflow? (yes/no)"
            )

    return ClassificationResult(
        task_type=task_type if base_confidence > 0.3 else TaskType.UNKNOWN,
        confidence=base_confidence,
        should_trigger_workflow=should_trigger and task_type in (TaskType.CODING, TaskType.TESTING, TaskType.DEVOPS),
        needs_clarification=needs_clarification,
        clarification_question=clarification_question,
        matched_keywords=matched_keywords,
        reasoning=f"Keyword match: {', '.join(matched_keywords)}" if matched_keywords else "No strong matches",
    )


# =============================================================================
# LLM-based Classifier (Optional)
# =============================================================================

LLM_CLASSIFIER_PROMPT = """Classify this user message. Is it a coding task that requires implementation?

MESSAGE: {message}

Respond with ONLY valid JSON (no markdown, no explanation):
{{"is_coding_task": true/false, "confidence": 0.0-1.0, "task_type": "coding|testing|documentation|devops|explanation|question", "reasoning": "brief explanation"}}

Rules:
- is_coding_task = true ONLY if user wants code written/modified
- confidence = how sure you are (0.0-1.0)
- Asking questions, explaining, describing = NOT coding tasks
- "Fix the bug" = coding task
- "Why is there a bug" = NOT coding task (explanation)
"""


async def classify_by_llm(message: str) -> ClassificationResult | None:
    """Use LLM to classify ambiguous messages.

    Returns None if LLM classification fails or times out.
    """
    if not router_config.use_llm_classifier:
        return None

    try:
        import asyncio
        import json
        from app.llm import kiro_provider

        if not await kiro_provider.is_available():
            logger.warning("LLM classifier: kiro-cli not available")
            return None

        prompt = LLM_CLASSIFIER_PROMPT.format(message=message[:500])

        # Get response with timeout
        response = ""
        try:
            async with asyncio.timeout(router_config.llm_classifier_timeout):
                response = await kiro_provider.generate_short_response(
                    prompt=prompt,
                    max_length=200,
                )
        except asyncio.TimeoutError:
            logger.warning("LLM classifier timed out")
            return None

        if not response:
            return None

        # Parse JSON response
        # Try to extract JSON if wrapped in markdown
        json_str = response
        if "```" in json_str:
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', json_str, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
        elif "{" in json_str:
            # Find JSON object
            start = json_str.find("{")
            end = json_str.rfind("}") + 1
            if start >= 0 and end > start:
                json_str = json_str[start:end]

        data = json.loads(json_str)

        is_coding = data.get("is_coding_task", False)
        confidence = float(data.get("confidence", 0.5))
        task_type_str = data.get("task_type", "unknown")
        reasoning = data.get("reasoning", "")

        # Map task type
        task_type_map = {
            "coding": TaskType.CODING,
            "testing": TaskType.TESTING,
            "documentation": TaskType.DOCUMENTATION,
            "devops": TaskType.DEVOPS,
            "explanation": TaskType.EXPLANATION,
            "question": TaskType.QUESTION,
        }
        task_type = task_type_map.get(task_type_str, TaskType.UNKNOWN)

        should_trigger = is_coding and confidence >= router_config.auto_trigger_threshold
        needs_clarification = (
            is_coding and
            router_config.clarify_threshold <= confidence < router_config.auto_trigger_threshold
        )

        return ClassificationResult(
            task_type=task_type,
            confidence=confidence,
            should_trigger_workflow=should_trigger,
            needs_clarification=needs_clarification,
            clarification_question="Should I start the coding workflow for this? (yes/no)" if needs_clarification else None,
            reasoning=f"LLM: {reasoning}",
        )

    except json.JSONDecodeError as e:
        logger.warning(f"LLM classifier: invalid JSON response: {e}")
        return None
    except Exception as e:
        logger.warning(f"LLM classifier error: {e}")
        return None


# =============================================================================
# Main Router Function
# =============================================================================

async def classify_message(message: str) -> ClassificationResult:
    """Classify a message to determine if it should trigger the delivery workflow.

    This is the main entry point for message classification.

    Args:
        message: The user's message

    Returns:
        ClassificationResult with trigger decision and confidence
    """
    if not router_config.enabled:
        return ClassificationResult(
            task_type=TaskType.UNKNOWN,
            confidence=0.0,
            should_trigger_workflow=False,
            needs_clarification=False,
            reasoning="Workflow router disabled",
        )

    # First try keyword classification
    keyword_result = classify_by_keywords(message)

    # If high confidence or explicit command, return immediately
    if keyword_result.confidence >= router_config.auto_trigger_threshold:
        logger.info(f"Router: High confidence ({keyword_result.confidence:.2f}) - triggering workflow")
        return keyword_result

    # If clearly not a coding task, return immediately
    if keyword_result.task_type in (TaskType.EXPLANATION, TaskType.QUESTION):
        logger.info(f"Router: Non-coding task detected ({keyword_result.task_type.value})")
        return keyword_result

    # For ambiguous cases, optionally use LLM classifier
    if router_config.use_llm_classifier and keyword_result.confidence < router_config.auto_trigger_threshold:
        llm_result = await classify_by_llm(message)
        if llm_result:
            # Use LLM result if it's more confident
            if llm_result.confidence > keyword_result.confidence:
                logger.info(f"Router: Using LLM classification ({llm_result.confidence:.2f})")
                return llm_result

    # Return keyword result (may need clarification)
    return keyword_result


def classify_message_sync(message: str) -> ClassificationResult:
    """Synchronous wrapper for classify_message (skips LLM)."""
    if not router_config.enabled:
        return ClassificationResult(
            task_type=TaskType.UNKNOWN,
            confidence=0.0,
            should_trigger_workflow=False,
            needs_clarification=False,
            reasoning="Workflow router disabled",
        )

    return classify_by_keywords(message)


# =============================================================================
# User Response Handlers
# =============================================================================

def handle_clarification_response(response: str) -> bool:
    """Handle user's response to clarification question.

    Args:
        response: User's response (yes/no/etc.)

    Returns:
        True if user confirmed workflow should run
    """
    response_lower = response.lower().strip()

    yes_responses = {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "go", "proceed", "do it"}
    no_responses = {"no", "n", "nope", "nah", "cancel", "stop", "don't", "dont"}

    if response_lower in yes_responses:
        return True
    if response_lower in no_responses:
        return False

    # Default to yes for coding-related confirmations
    if any(word in response_lower for word in ["code", "implement", "fix", "build"]):
        return True

    # Default to no for ambiguous responses
    return False


# =============================================================================
# Convenience Functions
# =============================================================================

def is_explicit_command(message: str) -> tuple[bool, str | None]:
    """Check if message starts with an explicit workflow command.

    Returns:
        Tuple of (is_command, command_name)
    """
    message_lower = message.lower().strip()
    for cmd in router_config.explicit_commands:
        if message_lower.startswith(cmd):
            return True, cmd
    return False, None


def should_trigger_workflow(message: str) -> bool:
    """Quick synchronous check if message should trigger workflow.

    Use this for simple checks. For full classification with LLM,
    use classify_message() instead.
    """
    result = classify_message_sync(message)
    return result.should_trigger_workflow
