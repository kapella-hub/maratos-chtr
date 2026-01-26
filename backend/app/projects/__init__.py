"""Project profiles for context loading."""

from app.projects.registry import project_registry, Project
from app.projects.analyzer import analyze_project, ProjectAnalysis

__all__ = ["project_registry", "Project", "analyze_project", "ProjectAnalysis"]
