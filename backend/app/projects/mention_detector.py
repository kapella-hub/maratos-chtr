"""Project mention detection in user messages.

Detects when users reference configured projects by name in their messages
and returns matching project names for automatic context injection.
"""

import logging
import re
from dataclasses import dataclass

from app.projects import project_registry

logger = logging.getLogger(__name__)


@dataclass
class MentionResult:
    """Result of project mention detection."""
    detected: bool
    project_names: list[str]  # All detected project names
    primary_project: str | None  # The primary project (longest match or first)
    multiple_detected: bool  # True if more than one project was mentioned


def detect_project_mentions(message: str) -> MentionResult:
    """Detect project names mentioned in a message.

    Uses word-boundary matching to avoid false positives from substrings.
    Prefers longer matches when project names overlap.

    Args:
        message: The user's message to scan

    Returns:
        MentionResult with detected projects and primary selection
    """
    projects = project_registry.list_all()
    if not projects:
        return MentionResult(
            detected=False,
            project_names=[],
            primary_project=None,
            multiple_detected=False,
        )

    # Build list of (name, pattern) sorted by name length descending
    # Longer names first to prefer "my-app-api" over "my-app"
    project_patterns = []
    for p in projects:
        # Escape special regex chars in project name
        escaped_name = re.escape(p.name)
        # Build word-boundary pattern
        # Allow common delimiters: word boundary, quotes, backticks
        pattern = re.compile(
            rf'(?:^|[\s\'""`({{\[])({escaped_name})(?:[\s\'""`)}}\].,!?]|$)',
            re.IGNORECASE
        )
        project_patterns.append((p.name, len(p.name), pattern))

    # Sort by name length descending (prefer longer matches)
    project_patterns.sort(key=lambda x: -x[1])

    detected_names = []
    detected_positions = []  # Track positions to avoid overlapping matches

    for name, name_len, pattern in project_patterns:
        for match in pattern.finditer(message):
            start, end = match.span(1)  # Position of the captured group

            # Check if this position overlaps with an already detected project
            overlaps = False
            for pos_start, pos_end in detected_positions:
                if not (end <= pos_start or start >= pos_end):
                    overlaps = True
                    break

            if not overlaps:
                detected_names.append(name)
                detected_positions.append((start, end))
                logger.debug(f"Detected project mention: '{name}' at position {start}-{end}")

    if not detected_names:
        return MentionResult(
            detected=False,
            project_names=[],
            primary_project=None,
            multiple_detected=False,
        )

    # Primary project is the first detected (which is the longest due to sorting)
    # Actually, let's prefer the first mentioned in the message
    # Sort detected by position
    if len(detected_names) > 1:
        # Re-sort by position in message
        position_order = sorted(
            range(len(detected_names)),
            key=lambda i: detected_positions[i][0]
        )
        detected_names_ordered = [detected_names[i] for i in position_order]
    else:
        detected_names_ordered = detected_names

    return MentionResult(
        detected=True,
        project_names=detected_names_ordered,
        primary_project=detected_names_ordered[0],
        multiple_detected=len(detected_names_ordered) > 1,
    )


def get_project_context_for_session(
    session_active_project: str | None,
    message: str,
    explicit_project: str | None = None,
) -> tuple[str | None, str | None, bool]:
    """Determine which project context to use for a session.

    Uses hybrid RAG: always includes core docs + retrieves relevant docs based on query.

    Priority:
    1. Explicit project from /project command
    2. Session's active project

    Args:
        session_active_project: The session's currently set active project
        message: The user's message (used for semantic doc retrieval)
        explicit_project: Project set explicitly via /project command

    Returns:
        Tuple of (project_name, project_context, is_auto_detected)
    """
    from app.projects import project_registry, load_context_pack
    from app.projects.docs_store import get_docs_for_context, docs_exist

    def _build_context_with_rag(project_name: str, project) -> str:
        """Build project context with RAG-based doc retrieval."""
        # Get base context (from context pack or basic info)
        base_context = project.get_context()

        # If project has docs, do RAG retrieval based on user's message
        if docs_exist(project_name):
            # Get docs using hybrid approach: core + semantically relevant
            docs_context = get_docs_for_context(
                project_name,
                query=message,  # Use user's message for semantic search
                max_relevant_docs=5,
            )
            if docs_context:
                # Append docs to base context
                base_context = f"{base_context}\n\n{docs_context}"

        return base_context

    # Priority 1: Explicit /project command
    if explicit_project:
        project = project_registry.get(explicit_project)
        if project:
            context = _build_context_with_rag(explicit_project, project)
            return explicit_project, context, False
        return None, None, False

    # Priority 2: Session's active project
    if session_active_project:
        project = project_registry.get(session_active_project)
        if project:
            context = _build_context_with_rag(session_active_project, project)
            return session_active_project, context, False
        # Project no longer exists, clear it
        logger.warning(f"Session's active project '{session_active_project}' no longer exists")

    # Auto-detection from message disabled - users select projects explicitly
    # in the chat UI instead of relying on mention detection
    return None, None, False
