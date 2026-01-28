"""Project documentation store.

Manages per-project documentation snippets stored as markdown files
with a JSON index for metadata.
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ProjectDoc:
    """A documentation snippet for a project."""
    id: str
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_index_entry(self) -> dict[str, Any]:
        """Return metadata for index (without full content)."""
        return {
            "id": self.id,
            "title": self.title,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "content_length": len(self.content),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectDoc":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            tags=data.get("tags", []),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
        )


def get_project_docs_dir(project_name: str) -> Path:
    """Get the docs directory for a project."""
    return Path.home() / ".maratos" / "projects" / project_name / "docs"


def get_docs_index_path(project_name: str) -> Path:
    """Get the index.json path for a project's docs."""
    return get_project_docs_dir(project_name) / "index.json"


def _load_index(project_name: str) -> dict[str, dict[str, Any]]:
    """Load the docs index for a project."""
    index_path = get_docs_index_path(project_name)
    if not index_path.exists():
        return {}

    try:
        with open(index_path) as f:
            data = json.load(f)
            return data.get("docs", {})
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load docs index for {project_name}: {e}")
        return {}


def _save_index(project_name: str, index: dict[str, dict[str, Any]]) -> None:
    """Save the docs index for a project."""
    docs_dir = get_project_docs_dir(project_name)
    docs_dir.mkdir(parents=True, exist_ok=True)

    index_path = get_docs_index_path(project_name)
    with open(index_path, "w") as f:
        json.dump({"docs": index, "updated_at": datetime.utcnow().isoformat()}, f, indent=2)


def _get_doc_path(project_name: str, doc_id: str) -> Path:
    """Get the file path for a doc."""
    return get_project_docs_dir(project_name) / f"{doc_id}.md"


def list_docs(project_name: str) -> list[dict[str, Any]]:
    """List all docs for a project (metadata only).

    Returns list of index entries sorted by updated_at descending.
    """
    index = _load_index(project_name)
    docs = list(index.values())
    docs.sort(key=lambda d: d.get("updated_at", ""), reverse=True)
    return docs


def get_doc(project_name: str, doc_id: str) -> ProjectDoc | None:
    """Get a single doc by ID with full content."""
    index = _load_index(project_name)
    if doc_id not in index:
        return None

    doc_path = _get_doc_path(project_name, doc_id)
    if not doc_path.exists():
        logger.warning(f"Doc file missing for {project_name}/{doc_id}")
        return None

    try:
        content = doc_path.read_text(encoding="utf-8")
        entry = index[doc_id]
        return ProjectDoc(
            id=doc_id,
            title=entry.get("title", ""),
            content=content,
            tags=entry.get("tags", []),
            created_at=entry.get("created_at", ""),
            updated_at=entry.get("updated_at", ""),
        )
    except IOError as e:
        logger.error(f"Failed to read doc {project_name}/{doc_id}: {e}")
        return None


def get_all_docs(project_name: str) -> list[ProjectDoc]:
    """Get all docs for a project with full content."""
    index = _load_index(project_name)
    docs = []

    for doc_id in index:
        doc = get_doc(project_name, doc_id)
        if doc:
            docs.append(doc)

    docs.sort(key=lambda d: d.updated_at, reverse=True)
    return docs


def create_doc(project_name: str, title: str, content: str, tags: list[str] | None = None) -> ProjectDoc:
    """Create a new doc for a project.

    Returns the created doc with generated ID.
    """
    doc_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()

    doc = ProjectDoc(
        id=doc_id,
        title=title,
        content=content,
        tags=tags or [],
        created_at=now,
        updated_at=now,
    )

    # Write content file
    docs_dir = get_project_docs_dir(project_name)
    docs_dir.mkdir(parents=True, exist_ok=True)

    doc_path = _get_doc_path(project_name, doc_id)
    doc_path.write_text(content, encoding="utf-8")

    # Update index
    index = _load_index(project_name)
    index[doc_id] = doc.to_index_entry()
    _save_index(project_name, index)

    logger.info(f"Created doc {doc_id} for project {project_name}")
    return doc


def update_doc(
    project_name: str,
    doc_id: str,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
) -> ProjectDoc | None:
    """Update an existing doc.

    Only updates provided fields. Returns updated doc or None if not found.
    """
    index = _load_index(project_name)
    if doc_id not in index:
        return None

    doc_path = _get_doc_path(project_name, doc_id)
    if not doc_path.exists():
        return None

    # Load current values
    entry = index[doc_id]
    current_content = doc_path.read_text(encoding="utf-8")

    # Apply updates
    new_title = title if title is not None else entry.get("title", "")
    new_content = content if content is not None else current_content
    new_tags = tags if tags is not None else entry.get("tags", [])
    now = datetime.utcnow().isoformat()

    doc = ProjectDoc(
        id=doc_id,
        title=new_title,
        content=new_content,
        tags=new_tags,
        created_at=entry.get("created_at", now),
        updated_at=now,
    )

    # Write content if changed
    if content is not None:
        doc_path.write_text(new_content, encoding="utf-8")

    # Update index
    index[doc_id] = doc.to_index_entry()
    _save_index(project_name, index)

    logger.info(f"Updated doc {doc_id} for project {project_name}")
    return doc


def delete_doc(project_name: str, doc_id: str) -> bool:
    """Delete a doc.

    Returns True if deleted, False if not found.
    """
    index = _load_index(project_name)
    if doc_id not in index:
        return False

    # Remove from index
    del index[doc_id]
    _save_index(project_name, index)

    # Delete file
    doc_path = _get_doc_path(project_name, doc_id)
    if doc_path.exists():
        doc_path.unlink()

    logger.info(f"Deleted doc {doc_id} for project {project_name}")
    return True


def get_docs_for_context(project_name: str, max_chars_per_doc: int = 2000) -> str:
    """Get docs formatted for context injection.

    Returns markdown formatted section with doc titles and content.
    Content is truncated if longer than max_chars_per_doc.
    """
    docs = get_all_docs(project_name)
    if not docs:
        return ""

    lines = ["## Developer Docs", ""]

    for doc in docs:
        lines.append(f"### {doc.title}")
        if doc.tags:
            lines.append(f"*Tags: {', '.join(doc.tags)}*")
        lines.append("")

        content = doc.content.strip()
        if len(content) > max_chars_per_doc:
            content = content[:max_chars_per_doc - 3] + "..."

        lines.append(content)
        lines.append("")

    return "\n".join(lines)


def docs_exist(project_name: str) -> bool:
    """Check if any docs exist for a project."""
    index = _load_index(project_name)
    return len(index) > 0
