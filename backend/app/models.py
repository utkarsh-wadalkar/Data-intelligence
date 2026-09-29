from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base, utcnow


def new_id() -> str:
    return str(uuid4())


class Workflow(Base):
    __tablename__ = "workflows"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(String(128), index=True)
    creator_id: Mapped[str] = mapped_column(String(128))
    prompt: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(160))
    queries: Mapped[list] = mapped_column(JSON)
    fields: Mapped[list] = mapped_column(JSON)
    identity_fields: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(24), default="draft")
    cadence: Mapped[str] = mapped_column(String(12), default="none")
    local_hour: Mapped[int] = mapped_column(Integer, default=9)
    week_day: Mapped[int] = mapped_column(Integer, default=0)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    pause_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_run_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("workflow_id", "run_key", name="uq_run_workflow_key"),
        Index("ix_runs_org_status", "org_id", "status"),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    org_id: Mapped[str] = mapped_column(String(128), index=True)
    run_key: Mapped[str] = mapped_column(String(100))
    trigger: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(24), default="queued")
    stage: Mapped[str] = mapped_column(String(40), default="queued")
    pause_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    searched: Mapped[int] = mapped_column(Integer, default=0)
    scraped: Mapped[int] = mapped_column(Integer, default=0)
    observations: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Source(Base):
    __tablename__ = "sources"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(String(128), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(String(300), default="")
    excerpt: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Observation(Base):
    __tablename__ = "observations"
    __table_args__ = (UniqueConstraint("run_id", "record_key", name="uq_observation_run_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(String(128), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    record_key: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)
    evidence: Mapped[str] = mapped_column(Text)
    observed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Record(Base):
    __tablename__ = "records"
    __table_args__ = (UniqueConstraint("workflow_id", "record_key", name="uq_record_workflow_key"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(String(128), index=True)
    workflow_id: Mapped[str] = mapped_column(ForeignKey("workflows.id"), index=True)
    record_key: Mapped[str] = mapped_column(String(64))
    data: Mapped[dict] = mapped_column(JSON)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.id"))
    evidence: Mapped[str] = mapped_column(Text)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    observation_count: Mapped[int] = mapped_column(Integer, default=1)


class QuotaUsage(Base):
    __tablename__ = "quota_usage"
    __table_args__ = (UniqueConstraint("org_id", "kind", "period", name="uq_quota_period"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    org_id: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(24))
    period: Mapped[str] = mapped_column(String(10))
    used: Mapped[int] = mapped_column(Integer, default=0)


class ExecutionLease(Base):
    __tablename__ = "execution_leases"
    org_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
