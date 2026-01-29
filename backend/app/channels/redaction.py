"""Message redaction hooks for sensitive content filtering.

Provides configurable redaction patterns for PII, credentials, and other
sensitive data before message persistence.
"""

import logging
import re
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class RedactionPattern:
    """A pattern for redacting sensitive content."""

    name: str
    pattern: re.Pattern
    replacement: str
    enabled: bool = True


# Default redaction patterns
DEFAULT_PATTERNS: list[RedactionPattern] = [
    # Credit card numbers (basic pattern)
    RedactionPattern(
        name="credit_card",
        pattern=re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"),
        replacement="[REDACTED-CC]",
    ),
    # Social Security Numbers
    RedactionPattern(
        name="ssn",
        pattern=re.compile(r"\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b"),
        replacement="[REDACTED-SSN]",
    ),
    # Email addresses (optional, disabled by default)
    RedactionPattern(
        name="email",
        pattern=re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b"),
        replacement="[REDACTED-EMAIL]",
        enabled=False,  # Disabled by default as emails are often needed
    ),
    # API keys (common patterns)
    RedactionPattern(
        name="api_key",
        pattern=re.compile(
            r"\b(?:sk|pk|api|key|token|secret|password|auth)[-_](?:[a-zA-Z0-9_-]+)\b",
            re.IGNORECASE,
        ),
        replacement="[REDACTED-KEY]",
    ),
    # Bearer tokens
    RedactionPattern(
        name="bearer_token",
        pattern=re.compile(r"Bearer\s+[A-Za-z0-9\-_=]+\.?[A-Za-z0-9\-_=]*\.?[A-Za-z0-9\-_=]*"),
        replacement="Bearer [REDACTED-TOKEN]",
    ),
    # AWS keys
    RedactionPattern(
        name="aws_key",
        pattern=re.compile(r"(?:AKIA|ASIA)[A-Z0-9]{16}"),
        replacement="[REDACTED-AWS-KEY]",
    ),
    # Private keys (PEM format)
    RedactionPattern(
        name="private_key",
        pattern=re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"
        ),
        replacement="[REDACTED-PRIVATE-KEY]",
    ),
]

# Global pattern registry
_patterns: list[RedactionPattern] = DEFAULT_PATTERNS.copy()
_pre_hooks: list[Callable[[str], tuple[str, bool]]] = []
_post_hooks: list[Callable[[str], str]] = []


def register_pattern(pattern: RedactionPattern) -> None:
    """Register a new redaction pattern.

    Args:
        pattern: RedactionPattern to add
    """
    _patterns.append(pattern)
    logger.info(f"Registered redaction pattern: {pattern.name}")


def enable_pattern(name: str) -> bool:
    """Enable a redaction pattern by name.

    Args:
        name: Pattern name

    Returns:
        True if pattern was found and enabled
    """
    for p in _patterns:
        if p.name == name:
            p.enabled = True
            return True
    return False


def disable_pattern(name: str) -> bool:
    """Disable a redaction pattern by name.

    Args:
        name: Pattern name

    Returns:
        True if pattern was found and disabled
    """
    for p in _patterns:
        if p.name == name:
            p.enabled = False
            return True
    return False


def register_pre_hook(hook: Callable[[str], tuple[str, bool]]) -> None:
    """Register a pre-persist redaction hook.

    Hook receives the message text and returns (modified_text, was_modified).

    Args:
        hook: Function that processes text before persistence
    """
    _pre_hooks.append(hook)


def register_post_hook(hook: Callable[[str], str]) -> None:
    """Register a post-retrieve redaction hook.

    Hook receives the message text and returns modified text.
    Used for additional masking when displaying to certain contexts.

    Args:
        hook: Function that processes text after retrieval
    """
    _post_hooks.append(hook)


def apply_patterns(text: str) -> tuple[str, bool]:
    """Apply all enabled redaction patterns to text.

    Args:
        text: Input text to redact

    Returns:
        Tuple of (redacted_text, was_redacted)
    """
    was_redacted = False

    for pattern in _patterns:
        if not pattern.enabled:
            continue

        if pattern.pattern.search(text):
            text = pattern.pattern.sub(pattern.replacement, text)
            was_redacted = True
            logger.debug(f"Applied redaction pattern: {pattern.name}")

    return text, was_redacted


def apply_redaction_hooks(text: str) -> tuple[str, bool]:
    """Apply all redaction hooks and patterns to text.

    This is the main entry point for pre-persist redaction.

    Args:
        text: Input text to redact

    Returns:
        Tuple of (redacted_text, was_redacted)
    """
    was_redacted = False

    # Apply pattern-based redaction first
    text, patterns_applied = apply_patterns(text)
    was_redacted = was_redacted or patterns_applied

    # Apply custom pre-hooks
    for hook in _pre_hooks:
        try:
            text, hook_applied = hook(text)
            was_redacted = was_redacted or hook_applied
        except Exception as e:
            logger.error(f"Pre-hook error: {e}")

    return text, was_redacted


def apply_post_hooks(text: str) -> str:
    """Apply post-retrieve hooks to text.

    Used for additional masking when displaying in certain contexts.

    Args:
        text: Input text

    Returns:
        Processed text
    """
    for hook in _post_hooks:
        try:
            text = hook(text)
        except Exception as e:
            logger.error(f"Post-hook error: {e}")

    return text


def clear_hooks() -> None:
    """Clear all custom hooks (for testing)."""
    _pre_hooks.clear()
    _post_hooks.clear()


def reset_patterns() -> None:
    """Reset patterns to defaults (for testing)."""
    global _patterns
    _patterns = DEFAULT_PATTERNS.copy()
