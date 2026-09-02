"""Source and schema schemas."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from backend.app.schemas.base import SourceType


class SchemaField(BaseModel):
    name: str
    data_type: str = Field(..., description="string|integer|float|boolean|datetime|array|object")
    nullable: bool = True
    unique: bool = False
    description: Optional[str] = None
    example: Optional[Any] = None

    class Config:
        from_attributes = True


class SchemaBase(BaseModel):
    source_id: int
    fields: List[SchemaField] = Field(default_factory=list)
    field_count: int = 0


class SchemaCreate(BaseModel):
    source_id: str
    fields: List[SchemaField] = Field(default_factory=list)


class Schema(BaseModel):
    id: int
    source_id: str
    fields: List[SchemaField] = Field(default_factory=list)
    field_count: int = 0
    version: int = 1
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SchemaDrift(BaseModel):
    field_name: str
    change_type: str = Field(..., description="added|removed|renamed|type_changed")
    old_type: Optional[str] = None
    new_type: Optional[str] = None
    old_name: Optional[str] = None
    new_name: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    likely_impact: Optional[str] = None

    class Config:
        from_attributes = True


class SchemaDriftReport(BaseModel):
    source_id: str
    schema_id_a: int
    schema_id_b: int
    drifts: List[SchemaDrift] = Field(default_factory=list)
    total_changes: int = 0
    detected_at: Optional[datetime] = None

    class Config:
        from_attributes = True