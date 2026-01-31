"""Handoff system defines structured context passing between agents."""

import json
from datetime import datetime
from uuid import uuid4
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict

@dataclass
class HandoffArtifact:
    """An artifact included in the handoff."""
    type: str  # 'code', 'link', 'file', 'image'
    path: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None

@dataclass
class HandoffContext:
    """Contextual information for the handoff."""
    task_description: str
    files_modified: List[str] = field(default_factory=list)
    key_decisions: List[str] = field(default_factory=list)
    pending_items: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Handoff:
    """A structured handoff between agents."""
    from_agent: str
    to_agent: str
    context: HandoffContext
    id: str = field(default_factory=lambda: str(uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    artifacts: List[HandoffArtifact] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=2)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Handoff':
        """Create from dictionary."""
        context_data = data.get('context', {})
        context = HandoffContext(**context_data)
        
        artifacts_data = data.get('artifacts', [])
        artifacts = [HandoffArtifact(**a) for a in artifacts_data]
        
        return cls(
            id=data.get('id', str(uuid4())),
            from_agent=data['from_agent'],
            to_agent=data['to_agent'],
            timestamp=data.get('timestamp', datetime.utcnow().isoformat()),
            context=context,
            artifacts=artifacts
        )

class HandoffManager:
    """Manages creation and storage of handoffs."""
    
    def __init__(self, storage_path: str = "backend/data/handoffs"):
        self.storage_path = storage_path
        # Ensure storage exists (in real impl)

    def create_handoff(
        self,
        from_agent: str,
        to_agent: str,
        task_description: str,
        files_modified: List[str] = None,
        key_decisions: List[str] = None
    ) -> Handoff:
        """Create a new handoff."""
        context = HandoffContext(
            task_description=task_description,
            files_modified=files_modified or [],
            key_decisions=key_decisions or []
        )
        return Handoff(
            from_agent=from_agent,
            to_agent=to_agent,
            context=context
        )
    
    def serialize(self, handoff: Handoff) -> str:
        return handoff.to_json()

    def deserialize(self, json_str: str) -> Handoff:
        return Handoff.from_dict(json.loads(json_str))
