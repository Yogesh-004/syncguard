"""Matching and entity resolution schemas."""
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from backend.app.schemas.base import RiskLevel, ResolutionStatus


class MatchResult(BaseModel):
    record_a_id: int
    record_b_id: int
    confidence: float = Field(..., ge=0.0, le=1.0)
    match_method: str = Field(..., description="exact|normalized|fuzzy")
    matched_fields: List[str] = Field(default_factory=list)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    is_resolved: bool = False

    class Config:
        from_attributes = True


class MatchingRule(BaseModel):
    field_name: str
    match_type: str = Field(..., description="exact|prefix|suffix|contains|fuzzy")
    weight: float = Field(default=1.0, ge=0.0, le=1.0)
    threshold: Optional[float] = None

    class Config:
        from_attributes = True


class EntityGroup(BaseModel):
    group_id: str
    record_ids: List[int] = Field(default_factory=list)
    representative_id: Optional[int] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    match_method: str = "deterministic"
    created_at: Optional[str] = None

    class Config:
        from_attributes = True