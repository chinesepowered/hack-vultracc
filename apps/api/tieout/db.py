"""Database: Vultr Managed PostgreSQL in production (system of record), local Postgres in development."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

from .config import settings

JSONType = JSON().with_variant(JSONB(), "postgresql")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _engine():
    url = settings.database_url
    kw: dict = {"pool_pre_ping": True}
    if url.startswith("postgresql"):
        kw.update(pool_size=10, max_overflow=20, pool_recycle=1800)
    else:
        kw.update(connect_args={"check_same_thread": False})
    return create_engine(url, **kw)


engine = _engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    title: Mapped[str] = mapped_column(String(120), default="")
    role: Mapped[str] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Client(Base):
    __tablename__ = "clients"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    industry: Mapped[str] = mapped_column(String(200), default="")
    gl_cash_account: Mapped[str] = mapped_column(String(20), default="1010")
    materiality: Mapped[str] = mapped_column(String(20), default="0.00")
    profile_json: Mapped[dict] = mapped_column(JSONType, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class InputFile(Base):
    __tablename__ = "input_files"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    run_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    period: Mapped[str] = mapped_column(String(10))
    kind: Mapped[str] = mapped_column(String(40))
    name: Mapped[str] = mapped_column(String(120))
    object_key: Mapped[str] = mapped_column(String(400))
    sha256: Mapped[str] = mapped_column(String(64))
    bytes: Mapped[int] = mapped_column(Integer)
    rows: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Batch(Base):
    __tablename__ = "batches"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    period: Mapped[str] = mapped_column(String(10))
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="running")


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    batch_id: Mapped[str | None] = mapped_column(ForeignKey("batches.id"), index=True, nullable=True)
    client_id: Mapped[str] = mapped_column(ForeignKey("clients.id"), index=True)
    period: Mapped[str] = mapped_column(String(10), default="2026-09")
    kind: Mapped[str] = mapped_column(String(20), default="original")
    replay_of: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="queued", index=True)
    recon_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    approval_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sandbox_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    sandbox_host: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sandbox_state: Mapped[str] = mapped_column(String(20), default="none")
    image_digest: Mapped[str | None] = mapped_column(String(300), nullable=True)
    model_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    attestation_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    docker_summary_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    limits_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    inputs_json: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    result_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    memo_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_hashes_json: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    steps_json: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    untrusted_json: Mapped[list | None] = mapped_column(JSONType, nullable=True)
    step_count: Mapped[int] = mapped_column(Integer, default=0)
    matched_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    bank_line_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_in: Mapped[int] = mapped_column(BigInteger, default=0)
    tokens_out: Mapped[int] = mapped_column(BigInteger, default=0)
    llm_calls: Mapped[int] = mapped_column(Integer, default=0)
    tool_calls: Mapped[int] = mapped_column(Integer, default=0)
    replay_match: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class RunEvent(Base):
    __tablename__ = "run_events"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    seq: Mapped[int] = mapped_column(Integer)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    type: Mapped[str] = mapped_column(String(40))
    payload_json: Mapped[dict] = mapped_column(JSONType)
    sha256: Mapped[str] = mapped_column(String(64))
    prev_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)


class Artifact(Base):
    __tablename__ = "artifacts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    object_key: Mapped[str] = mapped_column(String(400))
    sha256: Mapped[str] = mapped_column(String(64))
    bytes: Mapped[int] = mapped_column(Integer)
    content_type: Mapped[str] = mapped_column(String(120))


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id"), index=True)
    reviewer_id: Mapped[str] = mapped_column(ForeignKey("users.id"))
    decision: Mapped[str] = mapped_column(String(20))
    comment: Mapped[str] = mapped_column(Text, default="")
    signed_sha256: Mapped[str] = mapped_column(String(64))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    seq: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor: Mapped[str] = mapped_column(String(200))
    action: Mapped[str] = mapped_column(String(80))
    target: Mapped[str] = mapped_column(String(200), default="")
    detail_json: Mapped[dict] = mapped_column(JSONType, default=dict)
    sha256: Mapped[str] = mapped_column(String(64))
    prev_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)


class SystemState(Base):
    __tablename__ = "system_state"
    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    value_json: Mapped[dict] = mapped_column(JSONType, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=func.now())


def create_all() -> None:
    Base.metadata.create_all(engine)
