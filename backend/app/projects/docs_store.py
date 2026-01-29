"""Project documentation store with RAG support.

Manages per-project documentation snippets stored as markdown files
with a JSON index for metadata. Supports semantic search via embeddings
for retrieving relevant docs based on query.

Hybrid approach:
- "Core" docs are always included in context
- Other docs are retrieved based on semantic similarity to the query
"""

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

# Optional: use sentence-transformers for embeddings
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False
    logger.info("sentence-transformers not installed, semantic search disabled for docs")

# Singleton model instance
_embedding_model = None


def _get_embedding_model():
    """Get or initialize the embedding model."""
    global _embedding_model
    if _embedding_model is None and EMBEDDINGS_AVAILABLE:
        _embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    return _embedding_model


def _compute_embedding(text: str) -> list[float] | None:
    """Compute embedding for text."""
    model = _get_embedding_model()
    if model is None:
        return None
    try:
        embedding = model.encode(text, normalize_embeddings=True)
        return embedding.tolist()
    except Exception as e:
        logger.warning(f"Failed to compute embedding: {e}")
        return None


def _cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a = np.array(vec1)
    b = np.array(vec2)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


@dataclass
class ProjectDoc:
    """A documentation snippet for a project."""
    id: str
    title: str
    content: str
    tags: list[str] = field(default_factory=list)
    is_core: bool = False  # Core docs are always included in context
    created_at: str = ""
    updated_at: str = ""
    embedding: list[float] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "content": self.content,
            "tags": self.tags,
            "is_core": self.is_core,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def to_index_entry(self) -> dict[str, Any]:
        """Return metadata for index (without full content)."""
        return {
            "id": self.id,
            "title": self.title,
            "tags": self.tags,
            "is_core": self.is_core,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "content_length": len(self.content),
            "has_embedding": self.embedding is not None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectDoc":
        return cls(
            id=data.get("id", ""),
            title=data.get("title", ""),
            content=data.get("content", ""),
            tags=data.get("tags", []),
            is_core=data.get("is_core", False),
            created_at=data.get("created_at", ""),
            updated_at=data.get("updated_at", ""),
            embedding=data.get("embedding"),
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


def _get_embedding_path(project_name: str, doc_id: str) -> Path:
    """Get the file path for a doc's embedding."""
    return get_project_docs_dir(project_name) / f"{doc_id}.emb.json"


def _load_embedding(project_name: str, doc_id: str) -> list[float] | None:
    """Load embedding for a doc."""
    emb_path = _get_embedding_path(project_name, doc_id)
    if not emb_path.exists():
        return None
    try:
        with open(emb_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None


def _save_embedding(project_name: str, doc_id: str, embedding: list[float]) -> None:
    """Save embedding for a doc."""
    emb_path = _get_embedding_path(project_name, doc_id)
    with open(emb_path, "w") as f:
        json.dump(embedding, f)


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
        embedding = _load_embedding(project_name, doc_id)
        return ProjectDoc(
            id=doc_id,
            title=entry.get("title", ""),
            content=content,
            tags=entry.get("tags", []),
            is_core=entry.get("is_core", False),
            created_at=entry.get("created_at", ""),
            updated_at=entry.get("updated_at", ""),
            embedding=embedding,
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


def create_doc(
    project_name: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    is_core: bool = False,
) -> ProjectDoc:
    """Create a new doc for a project.

    Args:
        project_name: Name of the project
        title: Doc title
        content: Markdown content
        tags: Optional tags for categorization
        is_core: If True, doc is always included in context (not just when relevant)

    Returns the created doc with generated ID.
    """
    doc_id = str(uuid.uuid4())[:8]
    now = datetime.utcnow().isoformat()

    # Compute embedding for semantic search
    embedding = _compute_embedding(f"{title}\n\n{content}")

    doc = ProjectDoc(
        id=doc_id,
        title=title,
        content=content,
        tags=tags or [],
        is_core=is_core,
        created_at=now,
        updated_at=now,
        embedding=embedding,
    )

    # Write content file
    docs_dir = get_project_docs_dir(project_name)
    docs_dir.mkdir(parents=True, exist_ok=True)

    doc_path = _get_doc_path(project_name, doc_id)
    doc_path.write_text(content, encoding="utf-8")

    # Save embedding if computed
    if embedding:
        _save_embedding(project_name, doc_id, embedding)

    # Update index
    index = _load_index(project_name)
    index[doc_id] = doc.to_index_entry()
    _save_index(project_name, index)

    logger.info(f"Created doc {doc_id} for project {project_name} (core={is_core}, has_embedding={embedding is not None})")
    return doc


def update_doc(
    project_name: str,
    doc_id: str,
    title: str | None = None,
    content: str | None = None,
    tags: list[str] | None = None,
    is_core: bool | None = None,
) -> ProjectDoc | None:
    """Update an existing doc.

    Only updates provided fields. Returns updated doc or None if not found.
    Recomputes embedding if title or content changes.
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
    new_is_core = is_core if is_core is not None else entry.get("is_core", False)
    now = datetime.utcnow().isoformat()

    # Recompute embedding if title or content changed
    needs_new_embedding = title is not None or content is not None
    embedding = None
    if needs_new_embedding:
        embedding = _compute_embedding(f"{new_title}\n\n{new_content}")
    else:
        embedding = _load_embedding(project_name, doc_id)

    doc = ProjectDoc(
        id=doc_id,
        title=new_title,
        content=new_content,
        tags=new_tags,
        is_core=new_is_core,
        created_at=entry.get("created_at", now),
        updated_at=now,
        embedding=embedding,
    )

    # Write content if changed
    if content is not None:
        doc_path.write_text(new_content, encoding="utf-8")

    # Save new embedding if recomputed
    if needs_new_embedding and embedding:
        _save_embedding(project_name, doc_id, embedding)

    # Update index
    index[doc_id] = doc.to_index_entry()
    _save_index(project_name, index)

    logger.info(f"Updated doc {doc_id} for project {project_name} (core={new_is_core})")
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

    # Delete content file
    doc_path = _get_doc_path(project_name, doc_id)
    if doc_path.exists():
        doc_path.unlink()

    # Delete embedding file
    emb_path = _get_embedding_path(project_name, doc_id)
    if emb_path.exists():
        emb_path.unlink()

    logger.info(f"Deleted doc {doc_id} for project {project_name}")
    return True


def search_docs(
    project_name: str,
    query: str,
    top_k: int = 5,
    min_similarity: float = 0.3,
) -> list[tuple[ProjectDoc, float]]:
    """Search docs by semantic similarity.

    Args:
        project_name: Name of the project
        query: Search query
        top_k: Maximum number of results
        min_similarity: Minimum cosine similarity threshold

    Returns:
        List of (doc, similarity_score) tuples, sorted by score descending
    """
    docs = get_all_docs(project_name)
    if not docs:
        return []

    query_embedding = _compute_embedding(query)
    if query_embedding is None:
        # No embeddings available, return empty (core docs will still be included)
        logger.debug("Embeddings not available, skipping semantic search")
        return []

    results = []
    for doc in docs:
        if doc.embedding is None:
            continue
        similarity = _cosine_similarity(query_embedding, doc.embedding)
        if similarity >= min_similarity:
            results.append((doc, similarity))

    # Sort by similarity descending
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


def get_docs_for_context(
    project_name: str,
    query: str | None = None,
    max_chars_per_doc: int = 15000,
    max_relevant_docs: int = 5,
) -> str:
    """Get docs formatted for context injection using hybrid RAG.

    Hybrid approach:
    1. Always includes docs marked as "core"
    2. If query provided, retrieves top-k semantically similar docs
    3. Falls back to all docs if no embeddings available

    Args:
        project_name: Name of the project
        query: Optional query for semantic search
        max_chars_per_doc: Maximum characters per doc (truncates if longer)
        max_relevant_docs: Maximum number of relevant docs to retrieve

    Returns:
        Markdown formatted section with doc titles and content
    """
    all_docs = get_all_docs(project_name)
    if not all_docs:
        return ""

    # Separate core docs (always included) from others
    core_docs = [d for d in all_docs if d.is_core]
    other_docs = [d for d in all_docs if not d.is_core]

    # Get relevant docs via semantic search if query provided
    relevant_docs: list[ProjectDoc] = []
    if query and other_docs and EMBEDDINGS_AVAILABLE:
        search_results = search_docs(project_name, query, top_k=max_relevant_docs)
        # Filter out core docs from search results (they're already included)
        core_ids = {d.id for d in core_docs}
        relevant_docs = [doc for doc, score in search_results if doc.id not in core_ids]
        logger.debug(f"Found {len(relevant_docs)} relevant docs for query")
    elif not EMBEDDINGS_AVAILABLE and other_docs:
        # No embeddings, include all docs (up to limit)
        relevant_docs = other_docs[:max_relevant_docs]

    # Combine: core docs first, then relevant docs
    docs_to_include = core_docs + relevant_docs

    if not docs_to_include:
        return ""

    lines = ["## Project Documentation", ""]

    # Core docs section
    if core_docs:
        lines.append("### Core Documentation")
        lines.append("*Always-included project knowledge*")
        lines.append("")
        for doc in core_docs:
            lines.append(f"#### {doc.title}")
            if doc.tags:
                lines.append(f"*Tags: {', '.join(doc.tags)}*")
            lines.append("")
            content = doc.content.strip()
            if len(content) > max_chars_per_doc:
                content = content[:max_chars_per_doc - 3] + "..."
            lines.append(content)
            lines.append("")

    # Relevant docs section
    if relevant_docs:
        lines.append("### Related Documentation")
        lines.append("*Retrieved based on current context*")
        lines.append("")
        for doc in relevant_docs:
            lines.append(f"#### {doc.title}")
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


def get_embeddings_status() -> dict[str, Any]:
    """Get status of embeddings support."""
    return {
        "available": EMBEDDINGS_AVAILABLE,
        "model": "all-MiniLM-L6-v2" if EMBEDDINGS_AVAILABLE else None,
    }
