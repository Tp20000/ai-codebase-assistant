"""Project model - matches actual database schema."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Double,
    ForeignKey, Integer, String, Text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Project(Base):
    """
    A user's codebase project.
    Contains metadata about the uploaded/cloned repository
    and its indexing status.
    """

    __tablename__ = "projects"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Owner
    owner_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Basic info
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    repo_url = Column(String(500), nullable=True)
    language = Column(String(50), nullable=False, default="python")

    # Status tracking
    status = Column(String(50), nullable=False, default="pending", index=True)
    error_message = Column(Text, nullable=True)
    index_progress = Column(Double, nullable=False, default=0.0)

    # File statistics
    total_files = Column(Integer, nullable=False, default=0)
    file_count = Column(Integer, nullable=False, default=0)
    total_lines = Column(BigInteger, nullable=False, default=0)
    total_size_bytes = Column(BigInteger, nullable=False, default=0)

    # Language analysis
    primary_language = Column(String(100), nullable=True)
    language_breakdown = Column(JSONB, nullable=True)

    # Embedding / ChromaDB
    chroma_collection_name = Column(String(255), nullable=True, unique=True)
    embedding_count = Column(Integer, nullable=False, default=0)

    # Complexity metrics
    avg_complexity = Column(Double, nullable=True)
    complexity_report = Column(JSONB, nullable=True)

    # Soft delete / active flag (added via migration)
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
    indexed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    owner = relationship("User", back_populates="projects", lazy="select")
    chat_sessions = relationship(
        "ChatSession", back_populates="project",
        cascade="all, delete-orphan", lazy="select"
    )
    files = relationship(
        "ProjectFile", back_populates="project",
        cascade="all, delete-orphan", lazy="select"
    )
    tasks = relationship(
        "Task", back_populates="project",
        cascade="all, delete-orphan", lazy="select"
    )

    def __repr__(self) -> str:
        return f"<Project id={self.id} name={self.name} status={self.status}>"
