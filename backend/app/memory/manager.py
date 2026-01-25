"""Memory manager for agents."""

import logging
from pathlib import Path
from typing import Any

from app.memory.store import MemoryStore, MemoryEntry

logger = logging.getLogger(__name__)


class MemoryManager:
    """Manages memory for agents - provides context and stores learnings."""
    
    def __init__(self, storage_path: Path | None = None) -> None:
        if storage_path is None:
            storage_path = Path.home() / ".maratos" / "memory"
        
        self.store = MemoryStore(storage_path)
    
    async def remember(
        self,
        content: str,
        memory_type: str = "fact",
        session_id: str | None = None,
        agent_id: str | None = None,
        tags: list[str] | None = None,
        importance: float = 0.5,
    ) -> MemoryEntry:
        """Store a new memory.
        
        Memory types:
        - conversation: Chat messages worth remembering
        - fact: Learned facts about user/system
        - decision: Decisions made and why
        - code: Code patterns, solutions, learnings
        - task: Completed tasks and outcomes
        """
        entry = self.store.add(
            content=content,
            memory_type=memory_type,
            session_id=session_id,
            agent_id=agent_id,
            tags=tags,
            importance=importance,
        )
        logger.info(f"Stored memory: {entry.id} ({memory_type})")
        return entry
    
    async def recall(
        self,
        query: str,
        limit: int = 5,
        memory_types: list[str] | None = None,
    ) -> list[MemoryEntry]:
        """Recall relevant memories for a query."""
        memories = self.store.search(
            query=query,
            limit=limit,
            memory_types=memory_types,
        )
        logger.debug(f"Recalled {len(memories)} memories for: {query[:50]}...")
        return memories
    
    async def get_context(
        self,
        query: str,
        session_id: str | None = None,
        max_tokens: int = 2000,
    ) -> str:
        """Get relevant memory context to add to prompts.
        
        Returns formatted string of relevant memories.
        """
        parts = []
        char_count = 0
        char_limit = max_tokens * 4  # Rough estimate
        
        # Get relevant memories via semantic search
        relevant = await self.recall(query, limit=10)
        
        if relevant:
            parts.append("## Relevant Memories")
            for entry in relevant:
                if char_count > char_limit:
                    break
                
                memory_text = f"- [{entry.memory_type}] {entry.content}"
                if entry.tags:
                    memory_text += f" (tags: {', '.join(entry.tags)})"
                
                parts.append(memory_text)
                char_count += len(memory_text)
        
        # Get recent session memories if applicable
        if session_id:
            recent = self.store.get_recent(limit=5, session_id=session_id)
            if recent:
                parts.append("\n## Recent in Session")
                for entry in recent:
                    if char_count > char_limit:
                        break
                    memory_text = f"- {entry.content}"
                    parts.append(memory_text)
                    char_count += len(memory_text)
        
        # Get important facts
        important = self.store.get_important(limit=5, min_importance=0.8)
        important_new = [e for e in important if e not in relevant]
        if important_new:
            parts.append("\n## Important Facts")
            for entry in important_new[:3]:
                if char_count > char_limit:
                    break
                memory_text = f"- {entry.content}"
                parts.append(memory_text)
                char_count += len(memory_text)
        
        return "\n".join(parts) if parts else ""
    
    async def extract_and_store(
        self,
        conversation: list[dict],
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> list[MemoryEntry]:
        """Extract important information from a conversation and store it.
        
        Called after conversations to learn from them.
        """
        stored = []
        
        for msg in conversation:
            role = msg.get("role", "")
            content = msg.get("content", "")
            
            # Skip short messages
            if len(content) < 50:
                continue
            
            # Detect decisions
            decision_keywords = ["decided", "decision", "chose", "will use", "going with"]
            if any(kw in content.lower() for kw in decision_keywords):
                entry = await self.remember(
                    content=content[:500],
                    memory_type="decision",
                    session_id=session_id,
                    agent_id=agent_id,
                    importance=0.7,
                )
                stored.append(entry)
            
            # Detect facts/preferences
            fact_keywords = ["always", "never", "prefer", "likes", "uses", "works at", "lives in"]
            if any(kw in content.lower() for kw in fact_keywords):
                entry = await self.remember(
                    content=content[:500],
                    memory_type="fact",
                    session_id=session_id,
                    agent_id=agent_id,
                    importance=0.6,
                )
                stored.append(entry)
            
            # Detect code/technical learnings
            if "```" in content or "function" in content or "class " in content:
                entry = await self.remember(
                    content=content[:1000],
                    memory_type="code",
                    session_id=session_id,
                    agent_id=agent_id,
                    importance=0.5,
                )
                stored.append(entry)
        
        return stored
    
    def compact(self, keep_top_n: int = 1000) -> int:
        """Compact memory to save space."""
        return self.store.compact(keep_top_n=keep_top_n)
    
    def stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        return self.store.stats()


# Global memory manager
memory_manager = MemoryManager()
