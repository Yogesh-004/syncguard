"""Conflict detection and resolution schemas."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from backend.app.schemas.base import RiskLevel, ResolutionStatus


class ConflictField(BaseModel):
    field_name: str
    values: Dict[str, Any] = Field(default_factory=dict)
    sources: List[str] = Field(default_factory=list)
    conflict_type: str = Field(..., description="mismatch|missing|type_error")

    class Config:
        from_attributes = True


class ConflictBase(BaseModel):
    record_a_id: int
    record_b_id: int
    match_id: Optional[int] = None
    conflicting_fields: List[ConflictField] = Field(default_factory=list)


class ConflictCreate(ConflictBase):
    pass


class Conflict(ConflictBase):
    id: int
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    risk_level: RiskLevel = RiskLevel.MEDIUM
    evidence: Dict[str, Any] = Field(default_factory=dict)
    recommendation: Optional[str] = None
    resolution_status: ResolutionStatus = ResolutionStatus.PENDING
    resolution_detail: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    auto_resolvable: bool = False

    class Config:
        from_attributes = True


class ResolutionRequest(BaseModel):
    action: str = Field(..., description="approve|reject|modify|defer")
    modified_values: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None

    class Config:
        from_attributes = True


class ResolutionResponse(BaseModel):
    conflict_id: int
    status: ResolutionStatus
    message: str
    resolved_at: Optional[datetime] = None