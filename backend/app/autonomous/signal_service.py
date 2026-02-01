
import re
from typing import List, Optional
from pydantic import BaseModel
from enum import Enum

class SignalType(Enum):
    TODO = "todo"
    ERROR = "error"
    DECISION = "decision"
    WARNING = "warning"
    INFO = "info"

class Signal(BaseModel):
    type: SignalType
    content: str
    source: str  # "log", "agent_output", "user_input"
    confidence: float
    context: Optional[str] = None

class SignalService:
    """
    Extracts actionable signals from unstructured text.
    """
    
    PATTERNS = {
        SignalType.TODO: [
            r"TODO:?\s*(.*)",
            r"\[ \] (.*)",
            r"ACTION ITEM:?\s*(.*)"
        ],
        SignalType.ERROR: [
            r"Error:?\s*(.*)",
            r"Exception:?\s*(.*)",
            r"Failed to (.*)",
        ],
        SignalType.DECISION: [
            r"DECISION:?\s*(.*)",
            r"Selected approach:?\s*(.*)",
            r".*decided to (.*)",
        ],
        SignalType.WARNING: [
            r"Warning:?\s*(.*)",
            r"WARNING:?\s*(.*)",
        ]
    }

    @classmethod
    def extract_signals(cls, text: str, source: str = "text") -> List[Signal]:
        signals = []
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            for signal_type, patterns in cls.PATTERNS.items():
                for pattern in patterns:
                    match = re.search(pattern, line, re.IGNORECASE)
                    if match:
                        content = match.group(1).strip()
                        if content:
                            signals.append(Signal(
                                type=signal_type,
                                content=content,
                                source=source,
                                confidence=0.8, # Regex match is fairly high confidence
                                context=line
                            ))
                        break # Stop after first match per line to avoid dupes on same line
        
        return signals
