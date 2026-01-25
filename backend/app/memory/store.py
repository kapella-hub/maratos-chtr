"""Memory storage with semantic search for MaratOS."""

import json
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import numpy as np

# Optional: use sentence-transformers for embeddings
try:
    from sentence_transformers import SentenceTransformer
    EMBEDDINGS_AVAILABLE = True
except ImportError:
    EMBEDDINGS_AVAILABLE = False


@dataclass
class MemoryEntry:
    """A single memory entry."""
    
    id: str
    content: str
    memory_type: str  # conversation, fact, decision, code, task
    timestamp: datetime
    
    # Metadata
    session_id: str | None = None
    agent_id: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    
    # For semantic search
    embedding: list[float] | None = None
    
    # Importance for retention (0-1, higher = more important)
    importance: float = 0.5
    
    # Access tracking
    access_count: int = 0
    last_accessed: datetime | None = None
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "content": self.content,
            "memory_type": self.memory_type,
            "timestamp": self.timestamp.isoformat(),
            "session_id": self.session_id,
            "agent_id": self.agent_id,
            "tags": self.tags,
            "metadata": self.metadata,
            "importance": self.importance,
            "access_count": self.access_count,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> "MemoryEntry":
        return cls(
            id=data["id"],
            content=data["content"],
            memory_type=data.get("memory_type", "fact"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            session_id=data.get("session_id"),
            agent_id=data.get("agent_id"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
            embedding=data.get("embedding"),
            importance=data.get("importance", 0.5),
            access_count=data.get("access_count", 0),
        )


class MemoryStore:
    """Persistent memory store with semantic search."""
    
    def __init__(self, storage_path: Path) -> None:
        self.storage_path = storage_path
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self._memories: dict[str, MemoryEntry] = {}
        self._embeddings: dict[str, np.ndarray] = {}
        self._model: Any = None
        
        # Load existing memories
        self._load()
    
    def _get_model(self):
        """Get or initialize the embedding model."""
        if self._model is None and EMBEDDINGS_AVAILABLE:
            self._model = SentenceTransformer('all-MiniLM-L6-v2')
        return self._model
    
    def _compute_embedding(self, text: str) -> list[float] | None:
        """Compute embedding for text."""
        model = self._get_model()
        if model is None:
            return None
        return model.encode(text).tolist()
    
    def _generate_id(self, content: str) -> str:
        """Generate a unique ID for content."""
        hash_input = f"{content}{datetime.now().isoformat()}"
        return hashlib.sha256(hash_input.encode()).hexdigest()[:16]
    
    def add(
        self,
        content: str,
        memory_type: str = "fact",
        session_id: str | None = None,
        agent_id: str | None = None,
        tags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
        importance: float = 0.5,
    ) -> MemoryEntry:
        """Add a new memory."""
        entry = MemoryEntry(
            id=self._generate_id(content),
            content=content,
            memory_type=memory_type,
            timestamp=datetime.now(),
            session_id=session_id,
            agent_id=agent_id,
            tags=tags or [],
            metadata=metadata or {},
            importance=importance,
            embedding=self._compute_embedding(content),
        )
        
        self._memories[entry.id] = entry
        if entry.embedding:
            self._embeddings[entry.id] = np.array(entry.embedding)
        
        self._save_entry(entry)
        return entry
    
    def get(self, memory_id: str) -> MemoryEntry | None:
        """Get a memory by ID."""
        entry = self._memories.get(memory_id)
        if entry:
            entry.access_count += 1
            entry.last_accessed = datetime.now()
        return entry
    
    def search(
        self,
        query: str,
        limit: int = 10,
        memory_types: list[str] | None = None,
        tags: list[str] | None = None,
        min_importance: float = 0.0,
    ) -> list[MemoryEntry]:
        """Semantic search for relevant memories."""
        results = []
        
        # Filter by type, tags, importance first
        candidates = []
        for entry in self._memories.values():
            if memory_types and entry.memory_type not in memory_types:
                continue
            if tags and not any(t in entry.tags for t in tags):
                continue
            if entry.importance < min_importance:
                continue
            candidates.append(entry)
        
        # If we have embeddings, do semantic search
        query_embedding = self._compute_embedding(query)
        if query_embedding is not None:
            query_vec = np.array(query_embedding)
            
            scored = []
            for entry in candidates:
                if entry.id in self._embeddings:
                    # Cosine similarity
                    entry_vec = self._embeddings[entry.id]
                    similarity = np.dot(query_vec, entry_vec) / (
                        np.linalg.norm(query_vec) * np.linalg.norm(entry_vec)
                    )
                    scored.append((entry, similarity))
            
            # Sort by similarity
            scored.sort(key=lambda x: x[1], reverse=True)
            results = [entry for entry, _ in scored[:limit]]
        else:
            # Fallback to keyword search
            query_lower = query.lower()
            scored = []
            for entry in candidates:
                if query_lower in entry.content.lower():
                    scored.append((entry, 1.0))
                elif any(query_lower in tag.lower() for tag in entry.tags):
                    scored.append((entry, 0.5))
            
            scored.sort(key=lambda x: x[1], reverse=True)
            results = [entry for entry, _ in scored[:limit]]
        
        # Update access stats
        for entry in results:
            entry.access_count += 1
            entry.last_accessed = datetime.now()
        
        return results
    
    def get_recent(
        self,
        limit: int = 20,
        session_id: str | None = None,
    ) -> list[MemoryEntry]:
        """Get most recent memories."""
        entries = list(self._memories.values())
        
        if session_id:
            entries = [e for e in entries if e.session_id == session_id]
        
        entries.sort(key=lambda e: e.timestamp, reverse=True)
        return entries[:limit]
    
    def get_important(
        self,
        limit: int = 20,
        min_importance: float = 0.7,
    ) -> list[MemoryEntry]:
        """Get most important memories."""
        entries = [e for e in self._memories.values() if e.importance >= min_importance]
        entries.sort(key=lambda e: e.importance, reverse=True)
        return entries[:limit]
    
    def delete(self, memory_id: str) -> bool:
        """Delete a memory."""
        if memory_id in self._memories:
            del self._memories[memory_id]
            self._embeddings.pop(memory_id, None)
            
            # Delete file
            file_path = self.storage_path / f"{memory_id}.json"
            if file_path.exists():
                file_path.unlink()
            
            return True
        return False
    
    def update_importance(self, memory_id: str, importance: float) -> bool:
        """Update a memory's importance."""
        if memory_id in self._memories:
            self._memories[memory_id].importance = max(0.0, min(1.0, importance))
            self._save_entry(self._memories[memory_id])
            return True
        return False
    
    def compact(self, keep_top_n: int = 1000, min_importance: float = 0.3) -> int:
        """Remove old, low-importance memories to save space.
        
        Returns number of memories removed.
        """
        if len(self._memories) <= keep_top_n:
            return 0
        
        # Score memories by importance + recency + access
        now = datetime.now()
        scored = []
        for entry in self._memories.values():
            age_days = (now - entry.timestamp).days
            recency_score = max(0, 1 - (age_days / 365))  # Decay over a year
            access_score = min(1, entry.access_count / 10)  # Cap at 10 accesses
            
            total_score = (
                entry.importance * 0.5 +
                recency_score * 0.3 +
                access_score * 0.2
            )
            scored.append((entry.id, total_score))
        
        # Sort by score
        scored.sort(key=lambda x: x[1], reverse=True)
        
        # Remove lowest scoring memories
        to_remove = scored[keep_top_n:]
        removed = 0
        for memory_id, score in to_remove:
            if score < min_importance:
                self.delete(memory_id)
                removed += 1
        
        return removed
    
    def _save_entry(self, entry: MemoryEntry) -> None:
        """Save a single entry to disk."""
        file_path = self.storage_path / f"{entry.id}.json"
        with open(file_path, "w") as f:
            json.dump(entry.to_dict(), f)
    
    def _load(self) -> None:
        """Load all memories from disk."""
        for file_path in self.storage_path.glob("*.json"):
            try:
                with open(file_path) as f:
                    data = json.load(f)
                entry = MemoryEntry.from_dict(data)
                self._memories[entry.id] = entry
                if entry.embedding:
                    self._embeddings[entry.id] = np.array(entry.embedding)
            except Exception as e:
                print(f"Failed to load memory {file_path}: {e}")
    
    def stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        return {
            "total_memories": len(self._memories),
            "by_type": self._count_by_type(),
            "embeddings_available": EMBEDDINGS_AVAILABLE,
            "storage_path": str(self.storage_path),
        }
    
    def _count_by_type(self) -> dict[str, int]:
        """Count memories by type."""
        counts: dict[str, int] = {}
        for entry in self._memories.values():
            counts[entry.memory_type] = counts.get(entry.memory_type, 0) + 1
        return counts
