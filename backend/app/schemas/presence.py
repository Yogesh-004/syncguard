"""Presence observation schemas (Phase 5C). Read-only exposure; no directives."""
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class PresenceState(str, Enum):
    BOTH_PRESENT = "BOTH_PRESENT"
    ONLY_IN_A = "ONLY_IN_A"
    ONLY_IN_B = "ONLY_IN_B"
    UNKNOWN = "UNKNOWN"


class PresenceObservation(BaseModel):
    id: int
    job_id: Optional[int] = None
    record_ref: str
    record_presence: PresenceState
    entity_presence: Optional[PresenceState] = None
    basis: str
    explanation: str
    scope: Dict[str, Any]
    snapshot_a_ref: str = ""
    snapshot_b_ref: str = ""
    observed_at: Optional[datetime] = None
    pipeline_version: str = ""

    class Config:
        from_attributes = True


class PresenceSummary(BaseModel):
    job_id: Optional[int] = None
    total: int
    counts: Dict[str, int]
    bases: Dict[str, int]
