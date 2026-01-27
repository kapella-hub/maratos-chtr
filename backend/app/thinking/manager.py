"""ThinkingManager - Core class for handling thinking operations.

Manages thinking sessions, blocks, and steps. Provides methods for
parsing thinking content and generating structured output.
"""

import json
import re
import time
from typing import Any, AsyncIterator
from uuid import uuid4

from app.thinking.models import (
    ThinkingLevel,
    ThinkingStepType,
    ThinkingStep,
    ThinkingBlock,
    ThinkingSession,
)


class ThinkingManager:
    """Manages thinking operations for AI responses.

    Handles:
    - Creating and managing thinking sessions
    - Parsing thinking content from various formats
    - Generating structured thinking output
    - Converting between formats (XML tags <-> JSON)
    """

    # Patterns for parsing legacy XML-style thinking tags
    THINKING_START_PATTERN = re.compile(r"<thinking>|<analysis>|\[THINKING\]", re.IGNORECASE)
    THINKING_END_PATTERN = re.compile(r"</thinking>|</analysis>|\[/THINKING\]", re.IGNORECASE)

    # Pattern for parsing step markers within thinking blocks
    STEP_PATTERN = re.compile(
        r"\[(?P<type>ANALYSIS|EVALUATION|DECISION|VALIDATION|RISK|IMPLEMENTATION|CRITIQUE)\]"
        r"(?P<content>.*?)(?=\[(?:ANALYSIS|EVALUATION|DECISION|VALIDATION|RISK|IMPLEMENTATION|CRITIQUE)\]|$)",
        re.IGNORECASE | re.DOTALL
    )

    def __init__(self, default_level: ThinkingLevel = ThinkingLevel.MEDIUM):
        """Initialize the thinking manager.

        Args:
            default_level: Default thinking level when not specified
        """
        self.default_level = default_level
        self._active_sessions: dict[str, ThinkingSession] = {}

    def create_session(
        self,
        message_id: str,
        level: ThinkingLevel | None = None,
        complexity_score: float = 0.5,
    ) -> ThinkingSession:
        """Create a new thinking session for a message.

        Args:
            message_id: ID of the message this session is for
            level: Thinking level to use (or default)
            complexity_score: Estimated complexity of the task (0.0-1.0)

        Returns:
            New ThinkingSession
        """
        session = ThinkingSession(
            message_id=message_id,
            original_level=level or self.default_level,
            complexity_score=complexity_score,
        )
        self._active_sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> ThinkingSession | None:
        """Get an active thinking session by ID."""
        return self._active_sessions.get(session_id)

    def close_session(self, session_id: str) -> ThinkingSession | None:
        """Close and return a thinking session."""
        return self._active_sessions.pop(session_id, None)

    def start_block(
        self,
        session: ThinkingSession,
        template: str | None = None,
    ) -> ThinkingBlock:
        """Start a new thinking block within a session.

        Args:
            session: The thinking session
            template: Optional template name for this block

        Returns:
            New ThinkingBlock
        """
        block = ThinkingBlock(
            level=session.effective_level,
            template=template,
        )
        session.add_block(block)
        return block

    def add_step(
        self,
        block: ThinkingBlock,
        step_type: ThinkingStepType,
        content: str,
        duration_ms: int = 0,
        tokens: int = 0,
    ) -> ThinkingStep:
        """Add a step to a thinking block.

        Args:
            block: The thinking block
            step_type: Type of thinking step
            content: Content of the step
            duration_ms: Time taken for this step
            tokens: Tokens used for this step

        Returns:
            New ThinkingStep
        """
        step = ThinkingStep(
            type=step_type,
            content=content,
            duration_ms=duration_ms,
            tokens=tokens,
        )
        block.add_step(step)
        return step

    def complete_block(self, block: ThinkingBlock) -> None:
        """Mark a thinking block as complete."""
        block.complete()

    def parse_legacy_content(self, content: str) -> list[ThinkingStep]:
        """Parse legacy XML-style thinking content into steps.

        Args:
            content: Raw thinking content (may contain XML tags)

        Returns:
            List of ThinkingStep objects
        """
        steps = []

        # Try to parse step markers first
        step_matches = list(self.STEP_PATTERN.finditer(content))

        if step_matches:
            for match in step_matches:
                step_type_str = match.group("type").upper()
                step_content = match.group("content").strip()

                # Map to ThinkingStepType
                type_map = {
                    "ANALYSIS": ThinkingStepType.ANALYSIS,
                    "EVALUATION": ThinkingStepType.EVALUATION,
                    "DECISION": ThinkingStepType.DECISION,
                    "VALIDATION": ThinkingStepType.VALIDATION,
                    "RISK": ThinkingStepType.RISK_ASSESSMENT,
                    "IMPLEMENTATION": ThinkingStepType.IMPLEMENTATION,
                    "CRITIQUE": ThinkingStepType.CRITIQUE,
                }
                step_type = type_map.get(step_type_str, ThinkingStepType.ANALYSIS)

                if step_content:
                    steps.append(ThinkingStep(type=step_type, content=step_content))
        else:
            # No step markers - treat entire content as single analysis step
            clean_content = self.THINKING_START_PATTERN.sub("", content)
            clean_content = self.THINKING_END_PATTERN.sub("", clean_content).strip()

            if clean_content:
                steps.append(ThinkingStep(
                    type=ThinkingStepType.ANALYSIS,
                    content=clean_content,
                ))

        return steps

    def extract_thinking_from_stream(
        self,
        content: str,
    ) -> tuple[str, str | None]:
        """Extract thinking content from a streamed response.

        Args:
            content: Raw content that may contain thinking tags

        Returns:
            Tuple of (clean_content, thinking_content or None)
        """
        thinking_content = None

        # Check for thinking tags
        start_match = self.THINKING_START_PATTERN.search(content)
        end_match = self.THINKING_END_PATTERN.search(content)

        if start_match and end_match and end_match.start() > start_match.end():
            # Complete thinking block found
            thinking_content = content[start_match.end():end_match.start()].strip()
            clean_content = (
                content[:start_match.start()] +
                content[end_match.end():]
            ).strip()
            return clean_content, thinking_content
        elif start_match and not end_match:
            # Thinking block started but not ended
            thinking_content = content[start_match.end():].strip()
            clean_content = content[:start_match.start()].strip()
            return clean_content, thinking_content

        return content, None

    def generate_thinking_prompt(
        self,
        level: ThinkingLevel,
        template: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Generate a thinking prompt for the given level and template.

        Args:
            level: Thinking level to use
            template: Optional template name
            context: Optional context for the prompt

        Returns:
            Thinking prompt string
        """
        if level == ThinkingLevel.OFF:
            return ""

        base_prompts = {
            ThinkingLevel.MINIMAL: (
                "Before responding, briefly consider: Is this request clear? "
                "Any obvious issues?"
            ),
            ThinkingLevel.LOW: (
                "Before responding, analyze the request:\n"
                "1. What is being asked?\n"
                "2. What are the key requirements?\n"
            ),
            ThinkingLevel.MEDIUM: (
                "Before responding, think through this systematically:\n"
                "[ANALYSIS] Break down the problem\n"
                "[EVALUATION] Consider approaches\n"
                "[DECISION] Choose the best approach\n"
            ),
            ThinkingLevel.HIGH: (
                "Before responding, perform deep analysis:\n"
                "[ANALYSIS] Break down the problem completely\n"
                "[EVALUATION] Consider multiple approaches with pros/cons\n"
                "[RISK] Identify potential issues and edge cases\n"
                "[DECISION] Select and justify the best approach\n"
                "[VALIDATION] Verify the decision is sound\n"
            ),
            ThinkingLevel.MAX: (
                "Before responding, perform exhaustive analysis:\n"
                "[ANALYSIS] Comprehensively break down all aspects\n"
                "[EVALUATION] Evaluate all possible approaches\n"
                "[RISK] Thoroughly assess risks and edge cases\n"
                "[DECISION] Make a well-justified decision\n"
                "[IMPLEMENTATION] Plan the execution\n"
                "[VALIDATION] Verify completeness and correctness\n"
                "[CRITIQUE] Self-review and identify weaknesses\n"
            ),
        }

        prompt = base_prompts.get(level, base_prompts[ThinkingLevel.MEDIUM])

        # Add template-specific guidance if provided
        if template:
            from app.thinking.templates import get_template
            template_obj = get_template(template)
            if template_obj:
                prompt += f"\n\nFocus areas for {template}:\n"
                prompt += "\n".join(f"- {focus}" for focus in template_obj.focus_areas)

        return prompt

    async def stream_thinking_events(
        self,
        session: ThinkingSession,
        content_stream: AsyncIterator[str],
    ) -> AsyncIterator[dict[str, Any]]:
        """Process a content stream and yield thinking events.

        Args:
            session: The thinking session
            content_stream: Async iterator of content chunks

        Yields:
            Dict events for SSE streaming
        """
        in_thinking = False
        thinking_buffer = ""
        current_block: ThinkingBlock | None = None
        start_time = time.time()

        async for chunk in content_stream:
            # Check for thinking markers
            if "__THINKING_START__" in chunk or self.THINKING_START_PATTERN.search(chunk):
                in_thinking = True
                current_block = self.start_block(session)
                yield {
                    "type": "thinking_start",
                    "block_id": current_block.id,
                    "level": session.effective_level.value,
                }
                # Remove marker from chunk
                chunk = chunk.replace("__THINKING_START__", "")
                chunk = self.THINKING_START_PATTERN.sub("", chunk)

            if "__THINKING_END__" in chunk or self.THINKING_END_PATTERN.search(chunk):
                in_thinking = False
                # Remove marker from chunk
                chunk = chunk.replace("__THINKING_END__", "")
                chunk = self.THINKING_END_PATTERN.sub("", chunk)

                if current_block and thinking_buffer:
                    # Parse accumulated thinking content
                    steps = self.parse_legacy_content(thinking_buffer)
                    duration_ms = int((time.time() - start_time) * 1000)

                    for step in steps:
                        step.duration_ms = duration_ms // max(len(steps), 1)
                        current_block.add_step(step)

                    self.complete_block(current_block)

                    yield {
                        "type": "thinking_complete",
                        "block": current_block.to_dict(),
                    }

                thinking_buffer = ""
                current_block = None
                start_time = time.time()

            if in_thinking:
                thinking_buffer += chunk
                # Yield incremental thinking update
                if current_block:
                    yield {
                        "type": "thinking_progress",
                        "block_id": current_block.id,
                        "content": chunk,
                    }
            else:
                # Regular content
                if chunk.strip():
                    yield {
                        "type": "content",
                        "data": chunk,
                    }

    def to_json(self, session: ThinkingSession) -> str:
        """Convert a thinking session to JSON string."""
        return json.dumps(session.to_dict(), indent=2)

    def from_json(self, json_str: str) -> ThinkingSession:
        """Create a thinking session from JSON string."""
        data = json.loads(json_str)
        return ThinkingSession.from_dict(data)


# Global instance for convenience
_default_manager: ThinkingManager | None = None


def get_thinking_manager() -> ThinkingManager:
    """Get the global thinking manager instance."""
    global _default_manager
    if _default_manager is None:
        _default_manager = ThinkingManager()
    return _default_manager
