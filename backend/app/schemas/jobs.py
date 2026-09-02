"""Job and synchronization schemas."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from backend.app.schemas.base import StatusEnum


class JobBase(BaseModel):
    job_type: str = Field(..., description="reconciliation|synchronization")
    source_id: Optional[str] = None
    status: StatusEnum = StatusEnum.PENDING
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    total_records: int = 0
    processed_records: int = 0
    error_message: Optional[str] = None
    idempotency_key: Optional[str] = None

    class Config:
        from_attributes = True


class JobCreate(BaseModel):
    job_type: str
    source_id: Optional[str] = None
    idempotency_key: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


class Job(JobBase):
    id: int
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    retry_count: int = 0
    max_retries: int = 3
    attempts: List[Dict[str, Any]] = Field(default_factory=list)

    class Config:
        from_attributes = True


class Attempt(BaseModel):
    id: int
    job_id: int
    attempt_number: int
    status: StatusEnum
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SyncJobCreate(BaseModel):
    source_id: str
    target_source_id: Optional[str] = None
    idempotency_key: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id: int
    status: StatusEnum
    progress: float
    message: str
    error: Optional[str] = None