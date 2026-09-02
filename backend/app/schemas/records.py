"""Record schemas."""
from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field
from backend.app.schemas.base import TimestampBase, SourceType


class RecordBase(TimestampBase):
    source_id: int = Field(..., description="External source identifier")
    source_record_id: str = Field(..., description="Record ID in source system")
    data: Dict[str, Any] = Field(..., description="Raw record data")
    raw_data: Optional[Dict[str, Any]] = None


class RecordCreate(RecordBase):
    pass


class RecordUpdate(BaseModel):
    data: Optional[Dict[str, Any]] = None


class Record(RecordBase):
    id: int
    normalized_data: Optional[Dict[str, Any]] = None
    is_processed: bool = False

    class Config:
        from_attributes = True


class UploadResponse(BaseModel):
    upload_id: str
    source_id: str
    filename: str
    record_count: int
    status: str
    message: str


class SourceCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    source_type: SourceType
    connection_string: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class Source(BaseModel):
    id: int
    name: str
    source_type: SourceType
    connection_string: Optional[str] = None
    config: Optional[Dict[str, Any]] = None
    is_active: bool = True
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True