"""Base Pydantic models and enums."""
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from pydantic import BaseModel, Field


class StatusEnum(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ResolutionStatus(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"
    DEFERRED = "deferred"
    PENDING = "pending"


class SourceType(str, Enum):
    CSV = "csv"
    JSON = "json"
    REST = "rest"


class TimestampBase(BaseModel):
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class PaginatedResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[Any]

    class Config:
        from_attributes = True