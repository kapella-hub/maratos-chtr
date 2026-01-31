"""Pydantic models for port-snitch."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ServiceType(str, Enum):
    """Known service types for port detection."""
    HTTP = "http"
    HTTPS = "https"
    SSH = "ssh"
    DATABASE = "database"
    CACHE = "cache"
    MESSAGE_QUEUE = "message_queue"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    """Risk hint levels for ports."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    UNKNOWN = "unknown"


class Label(BaseModel):
    """Key-value label for tagging entries."""
    key: str
    value: str


class PortEntry(BaseModel):
    """A single port binding entry."""
    port: int = Field(ge=1, le=65535)
    protocol: str = Field(pattern=r"^(tcp|udp)$")
    process: str
    pid: int = Field(ge=0)
    user: str
    bind_address: str
    detected_type: ServiceType = ServiceType.UNKNOWN
    label: Label | None = None
    risk_hint: RiskLevel = RiskLevel.UNKNOWN


class Snapshot(BaseModel):
    """A named snapshot of port entries at a point in time."""
    name: str
    timestamp: datetime = Field(default_factory=datetime.now)
    entries: list[PortEntry] = Field(default_factory=list)
