"""Tests for project mention detection."""

import pytest

from app.projects.mention_detector import (
    MentionResult,
    detect_project_mentions,
    get_project_context_for_session,
)


class MockProject:
    """Mock project for testing."""

    def __init__(self, name: str, context: str = "mock context"):
        self.name = name
        self._context = context

    def get_context(self) -> str:
        return self._context


@pytest.fixture
def mock_registry(monkeypatch):
    """Set up mock project registry."""
    projects = [
        MockProject("myapp", "MyApp context"),
        MockProject("myapp-api", "MyApp API context"),
        MockProject("backend", "Backend context"),
    ]
    project_map = {p.name: p for p in projects}

    monkeypatch.setattr(
        "app.projects.mention_detector.project_registry.list_all",
        lambda: projects,
    )
    monkeypatch.setattr(
        "app.projects.mention_detector.project_registry.get",
        lambda name: project_map.get(name),
    )

    # Also patch the imports used in get_project_context_for_session
    monkeypatch.setattr(
        "app.projects.project_registry.get",
        lambda name: project_map.get(name),
    )

    return projects


class TestMentionResult:
    """Tests for MentionResult dataclass."""

    def test_no_detection(self):
        result = MentionResult(
            detected=False,
            project_names=[],
            primary_project=None,
            multiple_detected=False,
        )
        assert not result.detected
        assert result.project_names == []
        assert result.primary_project is None
        assert not result.multiple_detected

    def test_single_detection(self):
        result = MentionResult(
            detected=True,
            project_names=["myapp"],
            primary_project="myapp",
            multiple_detected=False,
        )
        assert result.detected
        assert result.project_names == ["myapp"]
        assert result.primary_project == "myapp"
        assert not result.multiple_detected

    def test_multiple_detection(self):
        result = MentionResult(
            detected=True,
            project_names=["myapp", "backend"],
            primary_project="myapp",
            multiple_detected=True,
        )
        assert result.detected
        assert len(result.project_names) == 2
        assert result.primary_project == "myapp"
        assert result.multiple_detected


class TestDetectProjectMentions:
    """Tests for detect_project_mentions function."""

    def test_no_projects_configured(self, monkeypatch):
        """No detection when no projects configured."""
        monkeypatch.setattr(
            "app.projects.mention_detector.project_registry.list_all",
            lambda: [],
        )

        result = detect_project_mentions("Can you help with myapp?")
        assert not result.detected
        assert result.project_names == []

    def test_simple_mention(self, mock_registry):
        """Detect simple project name mention."""
        result = detect_project_mentions("Can you help with myapp?")
        assert result.detected
        assert "myapp" in result.project_names
        assert result.primary_project == "myapp"

    def test_mention_with_quotes(self, mock_registry):
        """Detect project name in quotes."""
        result = detect_project_mentions('Work on the "backend" project')
        assert result.detected
        assert "backend" in result.project_names

    def test_mention_with_backticks(self, mock_registry):
        """Detect project name in backticks."""
        result = detect_project_mentions("Check the `myapp` codebase")
        assert result.detected
        assert "myapp" in result.project_names

    def test_case_insensitive(self, mock_registry):
        """Detection is case-insensitive."""
        result = detect_project_mentions("Review MYAPP code")
        assert result.detected
        # The result should contain the canonical name from the project
        assert result.primary_project is not None

    def test_prefer_longer_match(self, mock_registry):
        """Prefer longer project names over shorter overlapping ones."""
        result = detect_project_mentions("Fix bug in myapp-api")
        assert result.detected
        # Should detect myapp-api, not just myapp
        assert "myapp-api" in result.project_names
        # myapp should NOT be in results since it's a substring
        assert "myapp" not in result.project_names

    def test_multiple_projects(self, mock_registry):
        """Detect multiple different projects."""
        result = detect_project_mentions("Compare myapp and backend")
        assert result.detected
        assert result.multiple_detected
        assert "myapp" in result.project_names
        assert "backend" in result.project_names

    def test_no_false_positive_substring(self, mock_registry):
        """Don't match project names as substrings of other words."""
        result = detect_project_mentions("The myapplication is great")
        # "myapp" should not match "myapplication"
        assert not result.detected or "myapp" not in result.project_names

    def test_word_boundary_start(self, mock_registry):
        """Match at start of message."""
        result = detect_project_mentions("myapp needs fixing")
        assert result.detected
        assert "myapp" in result.project_names

    def test_word_boundary_end(self, mock_registry):
        """Match at end of message."""
        result = detect_project_mentions("Please fix myapp")
        assert result.detected
        assert "myapp" in result.project_names

    def test_with_punctuation(self, mock_registry):
        """Match followed by punctuation."""
        result = detect_project_mentions("Is myapp, the main project, working?")
        assert result.detected
        assert "myapp" in result.project_names

    def test_first_mentioned_is_primary(self, mock_registry):
        """First mentioned project becomes primary."""
        result = detect_project_mentions("Compare backend to myapp")
        assert result.detected
        assert result.primary_project == "backend"


class TestGetProjectContextForSession:
    """Tests for get_project_context_for_session function."""

    def test_no_context_available(self, mock_registry):
        """Returns None when no project context available."""
        name, context, auto = get_project_context_for_session(
            session_active_project=None,
            message="Hello world",
            explicit_project=None,
        )
        assert name is None
        assert context is None
        assert auto is False

    def test_explicit_project_priority(self, mock_registry):
        """Explicit project takes highest priority."""
        name, context, auto = get_project_context_for_session(
            session_active_project="backend",
            message="Hello myapp",
            explicit_project="myapp-api",
        )
        assert name == "myapp-api"
        assert context == "MyApp API context"
        assert auto is False

    def test_session_active_priority(self, mock_registry):
        """Session active project takes priority over message detection."""
        name, context, auto = get_project_context_for_session(
            session_active_project="backend",
            message="Hello myapp",  # mentions different project
            explicit_project=None,
        )
        assert name == "backend"
        assert context == "Backend context"
        assert auto is False

    def test_auto_detect_from_message(self, mock_registry):
        """Auto-detect project from message when no other context."""
        name, context, auto = get_project_context_for_session(
            session_active_project=None,
            message="Can you help with myapp?",
            explicit_project=None,
        )
        assert name == "myapp"
        assert context == "MyApp context"
        assert auto is True

    def test_invalid_explicit_project(self, mock_registry):
        """Returns None for invalid explicit project."""
        name, context, auto = get_project_context_for_session(
            session_active_project=None,
            message="Hello",
            explicit_project="nonexistent",
        )
        assert name is None
        assert context is None
        assert auto is False

    def test_stale_session_project(self, mock_registry):
        """Handles session with deleted project gracefully."""
        name, context, auto = get_project_context_for_session(
            session_active_project="deleted-project",
            message="Hello myapp",
            explicit_project=None,
        )
        # Should fall through to auto-detect since session project doesn't exist
        assert name == "myapp"
        assert context == "MyApp context"
        assert auto is True
