from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JobRecord(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True, default=lambda: "job_" + uuid.uuid4().hex)
    type: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(30), default="queued")
    stage: Mapped[str] = mapped_column(String(80), default="queued")
    progress: Mapped[float] = mapped_column(default=0.0)
    message: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.UTC))
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.UTC), onupdate=lambda: dt.datetime.now(dt.UTC))


class BuildRecord(Base):
    __tablename__ = "builds"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    source_filename: Mapped[str] = mapped_column(String(512))
    source_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    active_version_id: Mapped[str] = mapped_column(String(64))
    summary: Mapped[dict] = mapped_column(JSON)
    storage_key: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.UTC))


class BuildVersionRecord(Base):
    __tablename__ = "build_versions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    build_id: Mapped[str] = mapped_column(ForeignKey("builds.id", ondelete="CASCADE"), index=True)
    parent_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    patch_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manifest_key: Mapped[str] = mapped_column(String(1024))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=lambda: dt.datetime.now(dt.UTC))


class ChunkBlobRecord(Base):
    __tablename__ = "chunk_blobs"
    hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    compression: Mapped[str] = mapped_column(String(20))
    encoding: Mapped[str] = mapped_column(String(20))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    storage_key: Mapped[str] = mapped_column(String(1024))


class PatchRecord(Base):
    __tablename__ = "patches"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    build_id: Mapped[str] = mapped_column(ForeignKey("builds.id", ondelete="CASCADE"), index=True)
    parent_version_id: Mapped[str] = mapped_column(String(64))
    new_version_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(30))
    author: Mapped[str] = mapped_column(String(255))
    reason: Mapped[str] = mapped_column(Text)
    operations: Mapped[list] = mapped_column(JSON)
    validation: Mapped[dict] = mapped_column(JSON, default=dict)
