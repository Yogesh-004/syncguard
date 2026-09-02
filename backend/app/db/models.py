"""SQLAlchemy database models."""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float, ForeignKey, JSON, Enum as SAEnum, Index
from sqlalchemy.orm import relationship
from backend.app.db.database import Base
from backend.app.schemas.base import StatusEnum, RiskLevel, ResolutionStatus, SourceType
import enum


class SourceModel(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    source_type = Column(SAEnum(SourceType), nullable=False)
    connection_string = Column(String(500), nullable=True)
    config = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    records = relationship("RecordModel", back_populates="source", lazy="dynamic")
    schemas = relationship("SchemaModel", back_populates="source", lazy="dynamic")


class RecordModel(Base):
    __tablename__ = "records"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False, index=True)
    source_record_id = Column(String(200), nullable=False)
    data = Column(JSON, nullable=False)
    raw_data = Column(JSON, nullable=True)
    normalized_data = Column(JSON, nullable=True)
    is_processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    source = relationship("SourceModel", back_populates="records")
    matches = relationship("MatchModel", foreign_keys="MatchModel.record_a_id", back_populates="record_a", lazy="dynamic")
    matches_b = relationship("MatchModel", foreign_keys="MatchModel.record_b_id", back_populates="record_b", lazy="dynamic")
    conflicts = relationship("ConflictModel", foreign_keys="ConflictModel.record_a_id", back_populates="record_a", lazy="dynamic")
    conflicts_b = relationship("ConflictModel", foreign_keys="ConflictModel.record_b_id", back_populates="record_b", lazy="dynamic")


class SchemaModel(Base):
    __tablename__ = "schemas"

    id = Column(Integer, primary_key=True, index=True)
    source_id = Column(Integer, ForeignKey("sources.id"), nullable=False, index=True)
    fields = Column(JSON, nullable=False, default=[])
    field_count = Column(Integer, default=0)
    version = Column(Integer, default=1)
    created_at = Column(DateTime, default=datetime.utcnow)

    source = relationship("SourceModel", back_populates="schemas")


class MatchModel(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    record_a_id = Column(Integer, ForeignKey("records.id"), nullable=False)
    record_b_id = Column(Integer, ForeignKey("records.id"), nullable=False)
    confidence = Column(Float, nullable=False)
    match_method = Column(String(50), nullable=False)
    matched_fields = Column(JSON, nullable=False, default=[])
    evidence = Column(JSON, nullable=False, default={})
    is_resolved = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    record_a = relationship("RecordModel", foreign_keys=[record_a_id], back_populates="matches")
    record_b = relationship("RecordModel", foreign_keys=[record_b_id], back_populates="matches_b")
    conflicts = relationship("ConflictModel", back_populates="match", lazy="dynamic")
    entity_group_id = Column(String(100), nullable=True, index=True)


class ConflictModel(Base):
    __tablename__ = "conflicts"

    id = Column(Integer, primary_key=True, index=True)
    record_a_id = Column(Integer, ForeignKey("records.id"), nullable=False)
    record_b_id = Column(Integer, ForeignKey("records.id"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=True)
    confidence = Column(Float, default=0.0)
    conflicting_fields = Column(JSON, nullable=False, default=[])
    evidence = Column(JSON, nullable=False, default={})
    risk_level = Column(String(20), default="medium")
    recommendation = Column(Text, nullable=True)
    resolution_status = Column(String(20), default="pending")
    resolution_detail = Column(Text, nullable=True)
    resolved_by = Column(String(100), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    auto_resolvable = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    record_a = relationship("RecordModel", foreign_keys=[record_a_id], back_populates="conflicts")
    record_b = relationship("RecordModel", foreign_keys=[record_b_id], back_populates="conflicts_b")
    match = relationship("MatchModel", back_populates="conflicts")
    resolutions = relationship("ResolutionLogModel", back_populates="conflict", lazy="dynamic")


class ResolutionLogModel(Base):
    __tablename__ = "resolution_logs"

    id = Column(Integer, primary_key=True, index=True)
    conflict_id = Column(Integer, ForeignKey("conflicts.id"), nullable=False)
    action = Column(String(20), nullable=False)
    detail = Column(Text, nullable=True)
    resolved_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    conflict = relationship("ConflictModel", back_populates="resolutions")


class ReconciliationJobModel(Base):
    __tablename__ = "reconciliation_jobs"

    id = Column(Integer, primary_key=True, index=True)
    job_type = Column(String(50), nullable=False)
    source_id = Column(String(100), nullable=True)
    status = Column(String(20), default="pending")
    progress = Column(Float, default=0.0)
    total_records = Column(Integer, default=0)
    processed_records = Column(Integer, default=0)
    error_message = Column(Text, nullable=True)
    idempotency_key = Column(String(200), nullable=True, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)

    attempts = relationship("AttemptModel", back_populates="job", lazy="dynamic")
    sync_jobs = relationship("SyncJobModel", back_populates="reconciliation_job", lazy="dynamic")


class SyncJobModel(Base):
    __tablename__ = "sync_jobs"

    id = Column(Integer, primary_key=True, index=True)
    reconciliation_job_id = Column(Integer, ForeignKey("reconciliation_jobs.id"), nullable=True)
    source_id = Column(String(100), nullable=False)
    target_source_id = Column(String(100), nullable=True)
    status = Column(String(20), default="pending")
    progress = Column(Float, default=0.0)
    error_message = Column(Text, nullable=True)
    idempotency_key = Column(String(200), nullable=True, unique=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    reconciliation_job = relationship("ReconciliationJobModel", back_populates="sync_jobs")
    attempts = relationship("SyncAttemptModel", back_populates="job", lazy="dynamic")


class AttemptModel(Base):
    __tablename__ = "attempts"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("reconciliation_jobs.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    job = relationship("ReconciliationJobModel", back_populates="attempts")


class SyncAttemptModel(Base):
    __tablename__ = "sync_attempts"

    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(Integer, ForeignKey("sync_jobs.id"), nullable=False)
    attempt_number = Column(Integer, nullable=False)
    status = Column(String(20), nullable=False)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    job = relationship("SyncJobModel", back_populates="attempts")


class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(100), nullable=True, index=True)
    job_id = Column(Integer, nullable=True, index=True)
    source_id = Column(String(100), nullable=True, index=True)
    action = Column(String(100), nullable=False)
    entity_type = Column(String(50), nullable=True)
    entity_id = Column(String(100), nullable=True)
    details = Column(JSON, nullable=True)
    processing_time_ms = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_audit_created", "created_at"),
    )