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
    auto_trigger_threshold: float = 0.65  # Above this: auto-trigger workflow
    clarify_threshold: float = 0.4        # Between clarify and auto: ask user
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
# NOTE: Only include phrases with explicit coding context.
# Generic phrases like "build a" are handled by smart imperative detection.
STRONG_CODING_KEYWORDS = {
    # Implementation with explicit code context
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
    "build an api": 0.9,
    "build a component": 0.9,
    "build an endpoint": 0.9,
    "create an app": 0.85,
    "create a new app": 0.85,
    "build an app": 0.85,
    "scaffold a": 0.85,

    # UI/UX improvements
    "improve the ui": 0.85,
    "improve the ux": 0.85,
    "improve ui": 0.85,
    "improve ux": 0.85,
    "update the ui": 0.85,
    "redesign the": 0.85,
    "modernize the": 0.85,
    "make it look": 0.8,
    "style the": 0.8,
    "add styling": 0.85,

    # Bug fixing
    "fix the bug": 0.95,
    "fix this bug": 0.95,
    "fix the error": 0.9,
    "fix this error": 0.9,
    "debug": 0.8,
    "resolve the issue": 0.85,

    # Refactoring
    "refactor": 0.9,
    "restructure the code": 0.85,
    "rewrite the code": 0.85,
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
    (r'\bdevelop\s+something\b', 0.85),
    (r'\bsurpri[sz]e\s+me\b', 0.85),
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
    "improve": 0.6,
    "enhance": 0.6,
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
    "frontend", "backend", "ui", "ux", "interface", "button", "design", "layout", "styling",
    "form", "page", "view", "template", "hook",
    "test", "spec", "unit test", "integration test",
    "file", "code", "script", "logic", "algorithm",
    "app", "application", "project", "tool", "cli", "program", "system",
    "strategy", "strategies", "backtest", "analysis", # Added for finance/trading context
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
    "dockerfile": 0.85,
    "container": 0.85,
    "containerize": 0.9,
    "kubernetes": 0.85,
    "k8s": 0.85,
    "ci/cd": 0.9,
    "pipeline": 0.75,
    "github actions": 0.85,
    "terraform": 0.85,
    "spin up": 0.8,
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

# Code-specific imperative verbs (high confidence without context needed)
CODE_SPECIFIC_VERBS = (
    "implement", "refactor", "rewrite", "debug", "patch",
    "fix",  # "fix" almost always means code in dev context
)

# General imperative verbs (need coding context for high confidence)
GENERAL_IMPERATIVE_VERBS = (
    "create", "build", "write", "develop", "make",
    "repair", "resolve",
)

# Weaker imperative verbs (need context for high confidence)
WEAK_IMPERATIVE_VERBS = (
    "add", "make", "update", "modify", "change", "edit",
    "delete", "remove", "drop",
    "setup", "configure", "install",
    "test", "check",
)

# Operations verbs - indicate running/deploying rather than coding
OPERATIONS_VERBS = (
    "deploy", "run", "start", "launch", "spin", "host", "serve",
    "execute", "boot", "restart", "stop", "scale",
)

# Infrastructure/operations context - indicates devops domain
OPERATIONS_CONTEXT = {
    "container", "docker", "dockerfile", "image",
    "kubernetes", "k8s", "pod", "cluster", "node",
    "server", "vm", "instance", "cloud",
    "aws", "gcp", "azure", "heroku", "vercel", "netlify",
    "ci", "cd", "pipeline", "workflow", "action",
    "environment", "production", "staging", "dev",
    "port", "localhost", "nginx", "apache",
}

# Phrases that indicate "make it run" intent
OPERATIONS_PHRASES = [
    r"\bspin\s+(?:it\s+)?up\b",
    r"\bget\s+(?:it\s+)?running\b",
    r"\bmake\s+(?:it\s+)?live\b",
    r"\bput\s+(?:it\s+)?(?:in(?:to)?|on)\s+(?:a\s+)?(?:container|docker|server|cloud)\b",
    r"\brun\s+(?:it\s+)?(?:in|on|with)\b",
    r"\bstart\s+(?:it\s+)?(?:up|in|on)\b",
    r"\blaunch\s+(?:it|this|the)\b",
    r"\bhost\s+(?:it|this)\b",
    r"\bserve\s+(?:it|this)\b",
    r"\bdeploy\s+(?:it|this|to)\b",
    r"\bcontainerize\b",
    r"\bdockerize\b",
]


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


def _has_coding_context(message: str) -> bool:
    """Check if message contains coding-related context words.

    Uses word boundary matching to avoid false positives like 'ui' in 'build'.
    """
    msg_lower = message.lower()
    for ctx in CODING_CONTEXT_KEYWORDS:
        # Use word boundary regex for accurate matching
        if re.search(rf'\b{re.escape(ctx)}\b', msg_lower):
            return True
    return False


def _is_imperative(message: str) -> tuple[bool, str, float]:
    """Detect if message is an imperative coding command.

    Returns (is_imperative, matched_verb, confidence).

    Code-specific verbs (implement, refactor, debug) get high confidence.
    General verbs (create, build, write) need coding context for high confidence.
    """
    msg_lower = message.lower().strip()
    words = msg_lower.split()

    if not words:
        return False, "", 0.0

    first_word = words[0]
    has_coding_context = _has_coding_context(message)

    # Code-specific verbs: high confidence even without explicit context
    if first_word in CODE_SPECIFIC_VERBS:
        return True, first_word, 0.9

    # General imperative verbs: need coding context for high confidence
    if first_word in GENERAL_IMPERATIVE_VERBS:
        if has_coding_context:
            return True, first_word, 0.85
        else:
            # Low confidence without coding context - might not be a coding task
            return True, first_word, 0.4

    # Weak imperative verbs (add, update, etc.)
    if first_word in WEAK_IMPERATIVE_VERBS:
        confidence = 0.75 if has_coding_context else 0.5
        return True, first_word, confidence

    # "Please" + verb
    if first_word == "please" and len(words) > 1:
        verb = words[1]
        if verb in CODE_SPECIFIC_VERBS:
            return True, verb, 0.85
        if verb in GENERAL_IMPERATIVE_VERBS:
            return True, verb, 0.8 if has_coding_context else 0.35
        if verb in WEAK_IMPERATIVE_VERBS:
            return True, verb, 0.7 if has_coding_context else 0.45

    # "I want/need you to" + verb
    want_patterns = [
        r"^i\s+(?:want|need|would like)\s+(?:you\s+)?to\s+(\w+)",
        r"^(?:can|could|would)\s+you\s+(?:please\s+)?(\w+)",
    ]
    for pattern in want_patterns:
        match = re.match(pattern, msg_lower)
        if match:
            verb = match.group(1)
            if verb in CODE_SPECIFIC_VERBS:
                return True, verb, 0.8
            if verb in GENERAL_IMPERATIVE_VERBS:
                return True, verb, 0.75 if has_coding_context else 0.35
            if verb in WEAK_IMPERATIVE_VERBS:
                return True, verb, 0.6

    return False, "", 0.0


def _is_operations_task(message: str) -> tuple[bool, str, float]:
    """Detect if message is about operations/devops (running, deploying, infrastructure).

    Returns (is_operations, reason, confidence).

    This detects intent to:
    - Run/start/launch something (not write code for it)
    - Deploy or containerize
    - Work with infrastructure
    """
    msg_lower = message.lower().strip()
    words = msg_lower.split()

    if not words:
        return False, "", 0.0

    # Check for operations phrases first (highest signal)
    for pattern in OPERATIONS_PHRASES:
        if re.search(pattern, msg_lower):
            return True, f"matches operations phrase", 0.9

    first_word = words[0]

    # Starts with operations verb
    if first_word in OPERATIONS_VERBS:
        # Check for infrastructure context
        has_ops_context = any(ctx in msg_lower for ctx in OPERATIONS_CONTEXT)
        if has_ops_context:
            return True, f"operations verb '{first_word}' + context", 0.9
        # Even without explicit context, "deploy", "spin", "host" are strong signals
        if first_word in ("deploy", "spin", "host", "serve", "launch"):
            return True, f"strong operations verb '{first_word}'", 0.85
        # "run" alone is ambiguous (could mean run tests)
        return True, f"operations verb '{first_word}'", 0.6

    # Check for "please" + operations verb
    if first_word == "please" and len(words) > 1:
        verb = words[1]
        if verb in OPERATIONS_VERBS:
            has_ops_context = any(ctx in msg_lower for ctx in OPERATIONS_CONTEXT)
            return True, f"please + operations verb '{verb}'", 0.85 if has_ops_context else 0.7

    # Check for infrastructure context with any action
    has_ops_context = any(ctx in msg_lower for ctx in OPERATIONS_CONTEXT)
    if has_ops_context:
        # Look for action verbs that combined with ops context = devops task
        action_verbs = ("put", "get", "make", "set", "use", "add", "create")
        if first_word in action_verbs:
            return True, f"action verb + operations context", 0.75

    # "I want/need" + operations verb
    want_patterns = [
        r"(?:want|need|would like)\s+(?:to\s+)?(?:you\s+)?(?:to\s+)?(\w+)",
    ]
    for pattern in want_patterns:
        match = re.search(pattern, msg_lower)
        if match:
            verb = match.group(1)
            if verb in OPERATIONS_VERBS:
                return True, f"want/need + operations verb '{verb}'", 0.8

    return False, "", 0.0


# =============================================================================
# Keyword-based Classifier
# =============================================================================

def classify_by_keywords(message: str) -> ClassificationResult:
    """Classify message using smart intent detection + keyword matching.

    Priority:
    1. Explicit commands (/code, /fix, etc.)
    2. Question detection (structural)
    3. Non-coding indicators
    4. Operations/DevOps detection (structural)
    5. Testing detection
    6. Imperative coding detection (structural)
    7. Keyword matching (fallback)
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

    # 4. Smart operations/devops detection (structural)
    is_ops, ops_reason, ops_confidence = _is_operations_task(message)
    if is_ops and ops_confidence >= 0.7:
        matched_keywords.append(f"operations:{ops_reason}")
        return ClassificationResult(
            task_type=TaskType.DEVOPS,
            confidence=ops_confidence,
            should_trigger_workflow=ops_confidence >= router_config.auto_trigger_threshold,
            needs_clarification=router_config.clarify_threshold <= ops_confidence < router_config.auto_trigger_threshold,
            clarification_question="This looks like a deployment/infrastructure task. Should I use the devops workflow? (yes/no)" if router_config.clarify_threshold <= ops_confidence < router_config.auto_trigger_threshold else None,
            matched_keywords=matched_keywords,
            reasoning=f"Operations task: {ops_reason}",
        )

    # 5. Check for testing keywords
    for keyword, weight in TESTING_KEYWORDS.items():
        if keyword in message_lower:
            matched_keywords.append(keyword)
            if weight > base_confidence:
                base_confidence = weight
                task_type = TaskType.TESTING

    # 6. Check for imperative commands - boost confidence for clear coding commands
    # Only if not already classified as testing
    is_imperative, imperative_verb, imperative_confidence = _is_imperative(message)
    if is_imperative and task_type != TaskType.TESTING:
        matched_keywords.append(f"imperative:{imperative_verb}")
        base_confidence = max(base_confidence, imperative_confidence)
        if task_type == TaskType.UNKNOWN:
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
                # Check for context boost (use word boundary matching)
                context_matches = sum(
                    1 for ctx in CODING_CONTEXT_KEYWORDS
                    if re.search(rf'\b{re.escape(ctx)}\b', message_lower)
                )
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
                "🚀 **Coding Task Detected**\n\n"
                "Shall I spin up the autonomous **Thinking Workflow**?\n\n"
                "**Pipeline:**\n"
                "1. 👨‍💻 **Coder**: Implement changes\n"
                "2. 🧪 **Tester**: Verify logic\n"
                "3. 🚢 **DevOps**: Operations check\n\n"
                "*(Reply 'yes' to proceed)*"
            )
        elif task_type == TaskType.TESTING:
            clarification_question = (
                "🧪 **Testing Task Detected**\n\n"
                "Shall I run the **Verification Workflow**?\n\n"
                "**Scope:**\n"
                "1. Generate test cases\n"
                "2. Execute test suite\n"
                "3. Report coverage\n\n"
                "*(Reply 'yes' to proceed)*"
            )
        else:
            clarification_question = (
                "❓ **Ambiguous Request**\n\n"
                "I'm detecting potential code changes but confidence is low.\n"
                "Should I force-start the **Coding Workflow**?\n\n"
                "*(Reply 'yes' to proceed)*"
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


def classify_message_sync(message: str, session_id: str | None = None) -> ClassificationResult:
    """Synchronous wrapper for classify_message (skips LLM).

    If session_id is provided, uses session context to enhance classification.
    """
    if not router_config.enabled:
        return ClassificationResult(
            task_type=TaskType.UNKNOWN,
            confidence=0.0,
            should_trigger_workflow=False,
            needs_clarification=False,
            reasoning="Workflow router disabled",
        )

    # Get base classification
    result = classify_by_keywords(message)

    # Enhance with session context if available
    if session_id:
        result = _enhance_with_context(result, message, session_id)

    return result


def _enhance_with_context(
    result: ClassificationResult,
    message: str,
    session_id: str,
) -> ClassificationResult:
    """Enhance classification result using session context.

    This enables smart follow-ups like:
    - "deploy it" after coding → knows what to deploy
    - "add tests" after coding → knows what to test
    - "spin it up" after creating app → knows what to run
    """
    state = get_session_state(session_id)

    # No context to use
    if not state.last_task:
        return result

    msg_lower = message.lower().strip()

    # Detect pronoun references that indicate follow-up
    pronoun_patterns = [
        r"\b(it|this|that|these|those)\b",
        r"\b(the app|the code|the feature|the changes)\b",
        r"\bnow\s+\w+",  # "now deploy", "now test"
    ]
    has_reference = any(re.search(p, msg_lower) for p in pronoun_patterns)

    if not has_reference:
        return result

    # Check for follow-up actions that should inherit context
    follow_up_actions = {
        # Testing follow-ups
        ("test", "run tests", "add tests", "write tests"): TaskType.TESTING,
        # DevOps follow-ups
        ("deploy", "spin up", "containerize", "dockerize", "run it", "start it", "launch"): TaskType.DEVOPS,
        # Documentation follow-ups
        ("document", "add docs", "write docs", "readme"): TaskType.DOCUMENTATION,
        # More coding
        ("refactor", "improve", "optimize", "fix", "update"): TaskType.CODING,
    }

    for keywords, follow_up_type in follow_up_actions.items():
        if any(kw in msg_lower for kw in keywords):
            # This is a follow-up action referencing previous work
            # Context makes intent clear - use high confidence
            context_confidence = 0.85

            return ClassificationResult(
                task_type=follow_up_type,
                confidence=context_confidence,
                should_trigger_workflow=True,  # Context makes it clear
                needs_clarification=False,
                matched_keywords=result.matched_keywords + ["context:follow_up"],
                reasoning=f"Follow-up to: {state.last_task[:50]}",
            )

    return result


def get_task_with_context(message: str, session_id: str) -> str:
    """Expand a message with session context for better agent understanding.

    Transforms vague follow-ups into specific tasks:
    - "deploy it" → "deploy the backtest app (files: backend/app/main.py, ...)"
    - "add tests" → "add tests for the market data feature (components: MarketDataFetcher)"
    """
    state = get_session_state(session_id)

    if not state.last_task:
        return message

    msg_lower = message.lower().strip()

    # Check if message has vague references
    vague_refs = ["it", "this", "that", "the app", "the code", "the feature"]
    has_vague_ref = any(ref in msg_lower for ref in vague_refs)

    if not has_vague_ref:
        return message

    # Build context suffix
    context_parts = []
    if state.last_task:
        context_parts.append(f"Previous task: {state.last_task}")
    if state.last_result_summary:
        context_parts.append(f"What was done: {state.last_result_summary}")
    if state.files_touched:
        context_parts.append(f"Files: {', '.join(state.files_touched[:5])}")
    if state.components_created:
        context_parts.append(f"Components: {', '.join(state.components_created[:5])}")
    if state.project_path:
        context_parts.append(f"Project path: {state.project_path}")

    if context_parts:
        context_str = " | ".join(context_parts)
        return f"{message}\n\n[Context from previous workflow: {context_str}]"

    return message


# =============================================================================
# Session State Tracking (Task Continuity)
# =============================================================================

from dataclasses import dataclass as _dataclass, field as _field
from datetime import datetime as _datetime
from typing import Dict, List, Optional


@_dataclass
class SessionState:
    """Tracks workflow context for a session to enable smart follow-ups."""

    # What was just done
    last_task: Optional[str] = None  # "add real market data"
    last_task_type: Optional[TaskType] = None
    last_result_summary: Optional[str] = None  # "Created backtest.py with yfinance integration"

    # What was created/modified
    files_touched: List[str] = _field(default_factory=list)
    components_created: List[str] = _field(default_factory=list)  # ["BacktestEngine", "MarketDataFetcher"]

    # Context for follow-ups
    project_path: Optional[str] = None  # Working directory
    tech_stack: List[str] = _field(default_factory=list)  # ["fastapi", "yfinance", "pandas"]

    # Suggestions made but not yet acted on
    pending_suggestions: List[str] = _field(default_factory=list)

    # Timestamps
    last_updated: _datetime = _field(default_factory=_datetime.now)

    def update_from_workflow(
        self,
        task: str,
        task_type: TaskType,
        result_summary: str | None = None,
        files: list[str] | None = None,
        components: list[str] | None = None,
        project_path: str | None = None,
    ) -> None:
        """Update state after a workflow completes."""
        self.last_task = task
        self.last_task_type = task_type
        self.last_result_summary = result_summary
        self.last_updated = _datetime.now()

        if files:
            # Keep last 20 files, most recent first
            self.files_touched = files[:10] + [f for f in self.files_touched if f not in files][:10]
        if components:
            self.components_created = components[:10] + [c for c in self.components_created if c not in components][:10]
        if project_path:
            self.project_path = project_path

    def add_suggestion(self, suggestion: str) -> None:
        """Track a suggestion made by an agent."""
        if suggestion not in self.pending_suggestions:
            self.pending_suggestions.append(suggestion)
            # Keep last 5
            self.pending_suggestions = self.pending_suggestions[-5:]

    def clear_suggestion(self, suggestion: str) -> None:
        """Remove a suggestion when acted upon."""
        self.pending_suggestions = [s for s in self.pending_suggestions if s != suggestion]

    def get_context_summary(self) -> str:
        """Get a summary of recent context for agents."""
        parts = []
        if self.last_task:
            parts.append(f"Last task: {self.last_task}")
        if self.last_result_summary:
            parts.append(f"Result: {self.last_result_summary}")
        if self.files_touched:
            parts.append(f"Files: {', '.join(self.files_touched[:5])}")
        if self.components_created:
            parts.append(f"Components: {', '.join(self.components_created[:5])}")
        if self.project_path:
            parts.append(f"Project: {self.project_path}")
        return " | ".join(parts) if parts else ""


# In-memory store for session state
_session_states: Dict[str, SessionState] = {}

# How long state is valid (30 minutes)
SESSION_STATE_TIMEOUT_SECONDS = 1800


def get_session_state(session_id: str) -> SessionState:
    """Get or create session state."""
    if session_id not in _session_states:
        _session_states[session_id] = SessionState()

    state = _session_states[session_id]

    # Check if expired
    elapsed = (_datetime.now() - state.last_updated).total_seconds()
    if elapsed > SESSION_STATE_TIMEOUT_SECONDS:
        # Reset stale state
        _session_states[session_id] = SessionState()
        return _session_states[session_id]

    return state


def update_session_state(
    session_id: str,
    task: str,
    task_type: TaskType,
    result_summary: str | None = None,
    files: list[str] | None = None,
    components: list[str] | None = None,
    project_path: str | None = None,
) -> None:
    """Update session state after workflow completion."""
    state = get_session_state(session_id)
    state.update_from_workflow(
        task=task,
        task_type=task_type,
        result_summary=result_summary,
        files=files,
        components=components,
        project_path=project_path,
    )
    logger.debug(f"Updated session state for {session_id[:8]}: {state.get_context_summary()[:100]}")


# =============================================================================
# Pending Clarification Tracking
# =============================================================================


@_dataclass
class PendingClarification:
    """Tracks a pending workflow clarification for a session."""
    original_task: str
    task_type: TaskType
    confidence: float
    asked_at: _datetime
    matched_keywords: list[str]


# In-memory store for pending clarifications (session_id -> PendingClarification)
# In production, this would be persisted to the database
_pending_clarifications: Dict[str, PendingClarification] = {}

# How long a clarification is valid (5 minutes)
CLARIFICATION_TIMEOUT_SECONDS = 300


def store_pending_clarification(
    session_id: str,
    original_task: str,
    classification: ClassificationResult,
) -> None:
    """Store a pending clarification for a session."""
    _pending_clarifications[session_id] = PendingClarification(
        original_task=original_task,
        task_type=classification.task_type,
        confidence=classification.confidence,
        asked_at=_datetime.now(),
        matched_keywords=classification.matched_keywords,
    )
    logger.debug(f"Stored pending clarification for session {session_id[:8]}")


def get_pending_clarification(session_id: str) -> PendingClarification | None:
    """Get pending clarification for a session, if any and not expired."""
    pending = _pending_clarifications.get(session_id)
    if not pending:
        return None

    # Check if expired
    elapsed = (_datetime.now() - pending.asked_at).total_seconds()
    if elapsed > CLARIFICATION_TIMEOUT_SECONDS:
        del _pending_clarifications[session_id]
        logger.debug(f"Clarification for session {session_id[:8]} expired")
        return None

    return pending


def clear_pending_clarification(session_id: str) -> None:
    """Clear pending clarification for a session."""
    if session_id in _pending_clarifications:
        del _pending_clarifications[session_id]
        logger.debug(f"Cleared pending clarification for session {session_id[:8]}")


# =============================================================================
# User Response Handlers
# =============================================================================

# Affirmative responses
YES_RESPONSES = {"yes", "y", "yeah", "yep", "sure", "ok", "okay", "go", "proceed", "do it", "yes please", "let's go", "lets go"}
NO_RESPONSES = {"no", "n", "nope", "nah", "cancel", "stop", "don't", "dont", "nevermind", "never mind", "skip"}


def handle_clarification_response(response: str) -> bool:
    """Handle user's response to clarification question.

    Args:
        response: User's response (yes/no/etc.)

    Returns:
        True if user confirmed workflow should run
    """
    response_lower = response.lower().strip()

    if response_lower in YES_RESPONSES:
        return True
    if response_lower in NO_RESPONSES:
        return False

    # Default to yes for coding-related confirmations
    if any(word in response_lower for word in ["code", "implement", "fix", "build"]):
        return True

    # Default to no for ambiguous responses
    return False


@_dataclass
class FollowUpResult:
    """Result of analyzing a follow-up message after clarification."""
    should_trigger_workflow: bool
    task_to_execute: str  # Either original task or new/refined task
    is_affirmative: bool  # True if user said "yes"
    is_negative: bool     # True if user said "no"
    is_new_task: bool     # True if this is a new coding command
    is_refinement: bool   # True if this refines the original task
    reasoning: str


def analyze_clarification_followup(
    session_id: str,
    message: str,
) -> FollowUpResult | None:
    """Analyze a message that comes after a clarification was asked.

    This is the "smarter" handler that:
    1. Recognizes affirmative responses → triggers with original task
    2. Recognizes negative responses → lets MO handle normally
    3. Recognizes new imperative commands → re-classifies and triggers if appropriate
    4. Recognizes task refinements → merges with original and triggers

    Returns None if no pending clarification for this session.
    """
    pending = get_pending_clarification(session_id)
    if not pending:
        return None

    message_lower = message.lower().strip()

    # Check for affirmative response
    if message_lower in YES_RESPONSES:
        clear_pending_clarification(session_id)
        return FollowUpResult(
            should_trigger_workflow=True,
            task_to_execute=pending.original_task,
            is_affirmative=True,
            is_negative=False,
            is_new_task=False,
            is_refinement=False,
            reasoning="User confirmed with affirmative response",
        )

    # Check for negative response
    if message_lower in NO_RESPONSES:
        clear_pending_clarification(session_id)
        return FollowUpResult(
            should_trigger_workflow=False,
            task_to_execute=message,
            is_affirmative=False,
            is_negative=True,
            is_new_task=False,
            is_refinement=False,
            reasoning="User declined with negative response",
        )

    # Check if this is a new imperative command that should trigger workflow
    is_imperative, verb, confidence = _is_imperative(message)
    if is_imperative and confidence >= 0.7:
        # This is a new strong command - classify it
        new_classification = classify_by_keywords(message)
        if new_classification.should_trigger_workflow:
            clear_pending_clarification(session_id)
            return FollowUpResult(
                should_trigger_workflow=True,
                task_to_execute=message,  # Use the new task
                is_affirmative=False,
                is_negative=False,
                is_new_task=True,
                is_refinement=False,
                reasoning=f"New imperative command detected (verb: {verb}, confidence: {confidence:.2f})",
            )

    # Check if this looks like a refinement of the original task
    # Refinements typically add context without negating the original
    refinement_indicators = [
        "also", "and also", "but also",
        "with", "using", "for",
        "include", "add", "make sure",
        "specifically", "particularly",
    ]
    is_refinement = any(ind in message_lower for ind in refinement_indicators)

    # Or if it continues the thought (short additions)
    word_count = len(message.split())
    if word_count < 15 and not is_refinement:
        # Could be a refinement or short confirmation
        # Check if it has coding context
        if _has_coding_context(message):
            is_refinement = True

    if is_refinement:
        # Merge the refinement with the original task
        merged_task = f"{pending.original_task}. Additional requirements: {message}"
        clear_pending_clarification(session_id)
        return FollowUpResult(
            should_trigger_workflow=True,
            task_to_execute=merged_task,
            is_affirmative=False,
            is_negative=False,
            is_new_task=False,
            is_refinement=True,
            reasoning="Message appears to refine the original task",
        )

    # Check if it's a question - don't trigger, let MO handle
    is_question, _ = _is_question(message)
    if is_question:
        clear_pending_clarification(session_id)
        return FollowUpResult(
            should_trigger_workflow=False,
            task_to_execute=message,
            is_affirmative=False,
            is_negative=False,
            is_new_task=False,
            is_refinement=False,
            reasoning="Follow-up is a question, letting MO handle",
        )

    # Default: unclear response, let MO handle but keep clarification pending
    # (user might still respond)
    return FollowUpResult(
        should_trigger_workflow=False,
        task_to_execute=message,
        is_affirmative=False,
        is_negative=False,
        is_new_task=False,
        is_refinement=False,
        reasoning="Unclear follow-up, passing to MO",
    )


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
