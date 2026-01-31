
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

@dataclass
class ThinkingLesson:
    """A lesson learned from a critique."""
    id: str
    context: str
    critique: str
    tags: List[str] = field(default_factory=list)
    project_id: str | None = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "context": self.context,
            "critique": self.critique,
            "tags": self.tags,
            "project_id": self.project_id,
            "created_at": self.created_at,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ThinkingLesson":
        return cls(
            id=data["id"],
            context=data["context"],
            critique=data["critique"],
            tags=data.get("tags", []),
            project_id=data.get("project_id"),
            created_at=data.get("created_at", datetime.utcnow().isoformat()),
            metadata=data.get("metadata", {}),
        )

class ThinkingMemory:
    """Persistent storage for thinking lessons.
    
    Supports project-scoped isolation and tag-based retrieval.
    """
    
    def __init__(self, data_path: str = "backend/data/thinking_lessons.json"):
        self.data_path = Path(data_path)
        self.lessons: List[ThinkingLesson] = []
        self._load_lessons()

    def _load_lessons(self) -> None:
        """Load lessons from disk."""
        if not self.data_path.exists():
            return
            
        try:
            with open(self.data_path, "r") as f:
                data = json.load(f)
                self.lessons = [ThinkingLesson.from_dict(d) for d in data]
        except Exception as e:
            logger.error(f"Failed to load thinking lessons: {e}")

    async def save_lesson(
        self, 
        context: str, 
        critique: str, 
        tags: List[str] | None = None,
        project_id: str | None = None,
        metadata: Dict[str, Any] | None = None
    ) -> None:
        """Save a new lesson asynchronously."""
        from uuid import uuid4
        import asyncio
        
        lesson = ThinkingLesson(
            id=str(uuid4())[:8],
            context=context,
            critique=critique,
            tags=tags or [],
            project_id=project_id,
            metadata=metadata or {}
        )
        self.lessons.append(lesson)
        
        # Non-blocking flush
        await self._flush()

    async def _flush(self) -> None:
        """Write lessons to disk asynchronously."""
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._flush_sync)
        except Exception as e:
            logger.error(f"Failed to save thinking lessons: {e}")

    def _flush_sync(self) -> None:
        """Synchronous flush for executor."""
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.data_path, "w") as f:
                json.dump([l.to_dict() for l in self.lessons], f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save thinking lessons (sync): {e}")

    def search_lessons(
        self, 
        query: str, 
        project_id: str | None = None,
        limit: int = 3
    ) -> List[ThinkingLesson]:
        """Search for relevant lessons based on keyword overlap and project scope."""
        import re
        
        def tokenize(text: str) -> set[str]:
            return set(re.findall(r'\w+', text.lower()))

        query_words = tokenize(query)
        
        scored_lessons = []
        for lesson in self.lessons:
            # Filter by project_id if provided (strict scoping)
            if project_id and lesson.project_id and lesson.project_id != project_id:
                continue
                
            # Score based on overlap with context + tags
            # Tags give a boost match
            score = 0
            
            # Context match
            context_words = tokenize(lesson.context)
            score += len(query_words.intersection(context_words))
            
            # Tag match (boosted)
            for tag in lesson.tags:
                if tag.lower() in query_words:
                    score += 5
            
            if score > 0:
                scored_lessons.append((score, lesson))
        
        # Sort by score descending
        scored_lessons.sort(key=lambda x: x[0], reverse=True)
        return [l for _, l in scored_lessons[:limit]]

_memory: ThinkingMemory | None = None
_project_memories: Dict[str, ThinkingMemory] = {}

def get_thinking_memory(project_root: str | None = None) -> ThinkingMemory:
    """Get memory instance.
    
    If project_root is provided, returns project-specific memory (.maratos/knowledge.json).
    Otherwise returns global memory.
    """
    global _memory, _project_memories
    
    if project_root:
        if project_root in _project_memories:
            return _project_memories[project_root]
            
        path = Path(project_root) / ".maratos" / "knowledge.json"
        instance = ThinkingMemory(data_path=str(path))
        _project_memories[project_root] = instance
        return instance

    if _memory is None:
        _memory = ThinkingMemory()
    return _memory

