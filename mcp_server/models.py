from enum import Enum
from typing import Optional, List, Dict
from pydantic import BaseModel, Field

# Import existing evidence models
from mcp_server.evidence import (
    WorkloadState,
    PodState,
    EventItem,
    RevisionInfo,
    HealthResult,
    EvidenceSnapshot
)

class TicketSeverity(str, Enum):
    critical = "critical"
    high = "high"
    medium = "medium"
    low = "low"
    info = "info"

class TicketStatus(str, Enum):
    open = "open"
    investigating = "investigating"
    pending_approval = "pending_approval"
    approved = "approved"
    executing = "executing"
    resolved = "resolved"
    blocked = "blocked"
    closed = "closed"

class Ticket(BaseModel):
    id: str
    title: str
    status: TicketStatus
    severity: TicketSeverity
    namespace: str
    deployment: str
    service: str
    created_at: str
    updated_at: str
    signals: List[str] = Field(default_factory=list)
    related_ticket_ids: List[str] = Field(default_factory=list)
    diagnosis: Optional[Dict] = None
    plan: Optional[Dict] = None
    resolution: Optional[Dict] = None

class Alert(BaseModel):
    source: str
    rule_name: str
    severity: str
    message: str
    signals: List[str] = Field(default_factory=list)
    namespace: str
    deployment: str
    timestamp: str
