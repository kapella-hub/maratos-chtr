"""Tests for project documentation store and API."""

import json
from pathlib import Path

import pytest

from app.projects.docs_store import (
    ProjectDoc,
    create_doc,
    delete_doc,
    docs_exist,
    get_all_docs,
    get_doc,
    get_docs_for_context,
    get_project_docs_dir,
    list_docs,
    update_doc,
)


@pytest.fixture
def docs_dir(tmp_path: Path, monkeypatch):
    """Set up temporary docs directory."""
    storage_dir = tmp_path / "projects"
    monkeypatch.setattr(
        "app.projects.docs_store.get_project_docs_dir",
        lambda name: storage_dir / name / "docs"
    )
    return storage_dir


class TestProjectDoc:
    """Tests for ProjectDoc dataclass."""

    def test_to_dict(self):
        doc = ProjectDoc(
            id="abc123",
            title="Test Doc",
            content="Test content",
            tags=["api", "guide"],
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-02T00:00:00",
        )
        data = doc.to_dict()
        assert data["id"] == "abc123"
        assert data["title"] == "Test Doc"
        assert data["content"] == "Test content"
        assert data["tags"] == ["api", "guide"]

    def test_to_index_entry(self):
        doc = ProjectDoc(
            id="abc123",
            title="Test Doc",
            content="A" * 100,
            tags=["api"],
            created_at="2024-01-01T00:00:00",
            updated_at="2024-01-02T00:00:00",
        )
        entry = doc.to_index_entry()
        assert entry["id"] == "abc123"
        assert entry["title"] == "Test Doc"
        assert "content" not in entry
        assert entry["content_length"] == 100

    def test_from_dict(self):
        data = {
            "id": "abc123",
            "title": "Test Doc",
            "content": "Test content",
            "tags": ["api"],
            "created_at": "2024-01-01T00:00:00",
            "updated_at": "2024-01-02T00:00:00",
        }
        doc = ProjectDoc.from_dict(data)
        assert doc.id == "abc123"
        assert doc.title == "Test Doc"


class TestDocsStore:
    """Tests for docs store functions."""

    def test_create_doc(self, docs_dir: Path):
        doc = create_doc("myproject", "API Guide", "How to use the API", ["api"])

        assert doc.id
        assert doc.title == "API Guide"
        assert doc.content == "How to use the API"
        assert doc.tags == ["api"]
        assert doc.created_at
        assert doc.updated_at

        # Verify file was created
        doc_path = docs_dir / "myproject" / "docs" / f"{doc.id}.md"
        assert doc_path.exists()
        assert doc_path.read_text() == "How to use the API"

        # Verify index was updated
        index_path = docs_dir / "myproject" / "docs" / "index.json"
        assert index_path.exists()
        index = json.loads(index_path.read_text())
        assert doc.id in index["docs"]

    def test_list_docs(self, docs_dir: Path):
        # Create multiple docs
        doc1 = create_doc("myproject", "Doc 1", "Content 1")
        doc2 = create_doc("myproject", "Doc 2", "Content 2")
        doc3 = create_doc("myproject", "Doc 3", "Content 3")

        docs = list_docs("myproject")
        assert len(docs) == 3

        # Should be sorted by updated_at descending
        titles = [d["title"] for d in docs]
        assert "Doc 1" in titles
        assert "Doc 2" in titles
        assert "Doc 3" in titles

    def test_list_docs_empty_project(self, docs_dir: Path):
        docs = list_docs("nonexistent")
        assert docs == []

    def test_get_doc(self, docs_dir: Path):
        created = create_doc("myproject", "Test", "Content")

        doc = get_doc("myproject", created.id)
        assert doc is not None
        assert doc.id == created.id
        assert doc.title == "Test"
        assert doc.content == "Content"

    def test_get_doc_not_found(self, docs_dir: Path):
        doc = get_doc("myproject", "nonexistent")
        assert doc is None

    def test_get_all_docs(self, docs_dir: Path):
        create_doc("myproject", "Doc 1", "Content 1")
        create_doc("myproject", "Doc 2", "Content 2")

        docs = get_all_docs("myproject")
        assert len(docs) == 2
        assert all(isinstance(d, ProjectDoc) for d in docs)
        assert all(d.content for d in docs)

    def test_update_doc_title(self, docs_dir: Path):
        created = create_doc("myproject", "Old Title", "Content")

        updated = update_doc("myproject", created.id, title="New Title")
        assert updated is not None
        assert updated.title == "New Title"
        assert updated.content == "Content"  # Unchanged

    def test_update_doc_content(self, docs_dir: Path):
        created = create_doc("myproject", "Title", "Old Content")

        updated = update_doc("myproject", created.id, content="New Content")
        assert updated is not None
        assert updated.title == "Title"  # Unchanged
        assert updated.content == "New Content"

        # Verify file was updated
        doc_path = docs_dir / "myproject" / "docs" / f"{created.id}.md"
        assert doc_path.read_text() == "New Content"

    def test_update_doc_tags(self, docs_dir: Path):
        created = create_doc("myproject", "Title", "Content", ["old"])

        updated = update_doc("myproject", created.id, tags=["new", "tags"])
        assert updated is not None
        assert updated.tags == ["new", "tags"]

    def test_update_doc_not_found(self, docs_dir: Path):
        updated = update_doc("myproject", "nonexistent", title="New")
        assert updated is None

    def test_delete_doc(self, docs_dir: Path):
        created = create_doc("myproject", "Title", "Content")

        result = delete_doc("myproject", created.id)
        assert result is True

        # Verify file was deleted
        doc_path = docs_dir / "myproject" / "docs" / f"{created.id}.md"
        assert not doc_path.exists()

        # Verify removed from index
        docs = list_docs("myproject")
        assert len(docs) == 0

    def test_delete_doc_not_found(self, docs_dir: Path):
        result = delete_doc("myproject", "nonexistent")
        assert result is False

    def test_docs_exist(self, docs_dir: Path):
        assert not docs_exist("myproject")

        create_doc("myproject", "Title", "Content")
        assert docs_exist("myproject")

    def test_get_docs_for_context_empty(self, docs_dir: Path):
        context = get_docs_for_context("myproject")
        assert context == ""

    def test_get_docs_for_context(self, docs_dir: Path):
        create_doc("myproject", "API Guide", "How to use the API\n\nMore details here.", ["api"])
        create_doc("myproject", "Setup", "Installation instructions", ["setup", "install"])

        context = get_docs_for_context("myproject")
        assert "## Developer Docs" in context
        assert "### API Guide" in context
        assert "### Setup" in context
        assert "How to use the API" in context
        assert "*Tags: api*" in context

    def test_get_docs_for_context_truncation(self, docs_dir: Path):
        long_content = "A" * 5000
        create_doc("myproject", "Long Doc", long_content)

        context = get_docs_for_context("myproject", max_chars_per_doc=100)
        assert "..." in context
        assert len(context) < 5000


class TestDocsContextPackIntegration:
    """Tests for docs integration with context pack."""

    def test_context_pack_includes_docs(self, tmp_path: Path, monkeypatch):
        # Set up project
        project_dir = tmp_path / "testproject"
        project_dir.mkdir()
        (project_dir / "pyproject.toml").write_text('[project]\nname = "test"\n')
        (project_dir / "src").mkdir()

        # Set up docs storage
        storage_dir = tmp_path / "storage"
        monkeypatch.setattr(
            "app.projects.docs_store.get_project_docs_dir",
            lambda name: storage_dir / name / "docs"
        )

        # Create a doc
        create_doc("testproject", "Architecture Notes", "This is how the system works.")

        # Generate context pack with project_name
        from app.projects.context_pack import generate_context_pack

        pack = generate_context_pack(project_dir, project_name="testproject")

        assert pack.developer_docs
        assert "Developer Docs" in pack.developer_docs
        assert "Architecture Notes" in pack.developer_docs

    def test_compact_context_includes_docs(self, tmp_path: Path, monkeypatch):
        # Set up project
        project_dir = tmp_path / "testproject"
        project_dir.mkdir()
        (project_dir / "pyproject.toml").write_text('[project]\nname = "test"\n')

        # Set up docs storage
        storage_dir = tmp_path / "storage"
        monkeypatch.setattr(
            "app.projects.docs_store.get_project_docs_dir",
            lambda name: storage_dir / name / "docs"
        )

        # Create a doc
        create_doc("testproject", "Important Notes", "Remember this!")

        # Generate context pack and get compact context
        from app.projects.context_pack import generate_context_pack

        pack = generate_context_pack(project_dir, project_name="testproject")
        context = pack.get_compact_context()

        assert "Developer Docs" in context
        assert "Important Notes" in context
        assert "Remember this!" in context
