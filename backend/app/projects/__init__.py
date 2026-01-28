"""Project profiles for context loading."""

from app.projects.registry import project_registry, Project, ProjectRegistry
from app.projects.analyzer import analyze_project, ProjectAnalysis
from app.projects.context_pack import (
    ContextPack,
    ProjectManifest,
    ModuleMapping,
    Entrypoint,
    generate_context_pack,
    save_context_pack,
    load_context_pack,
    context_pack_exists,
    context_pack_is_stale,
    extract_readme_summary,
    generate_file_tree,
)
from app.projects.docs_store import (
    ProjectDoc,
    create_doc,
    get_doc,
    list_docs,
    update_doc,
    delete_doc,
    get_all_docs,
    get_docs_for_context,
    docs_exist,
)

__all__ = [
    # Registry
    "project_registry",
    "Project",
    "ProjectRegistry",
    # Analyzer
    "analyze_project",
    "ProjectAnalysis",
    # Context Pack
    "ContextPack",
    "ProjectManifest",
    "ModuleMapping",
    "Entrypoint",
    "generate_context_pack",
    "save_context_pack",
    "load_context_pack",
    "context_pack_exists",
    "context_pack_is_stale",
    "extract_readme_summary",
    "generate_file_tree",
    # Docs Store
    "ProjectDoc",
    "create_doc",
    "get_doc",
    "list_docs",
    "update_doc",
    "delete_doc",
    "get_all_docs",
    "get_docs_for_context",
    "docs_exist",
]
