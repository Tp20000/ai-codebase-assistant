"""Task model for tracking background agent executions."""
from __future__ import annotations
import uuid
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base


class Task(Base):
    """A background agent execution task."""
    __tablename__ = "tasks"

    # Primary key
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)

    # Ownership
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(UUID(as_uuid=True), nullable=False, index=True)

    # Task identification (original schema)
    task_type = Column(String(100), nullable=False, default="agent", index=True)
    task_name = Column(String(255), nullable=True)
    celery_task_id = Column(String(255), nullable=True, unique=True)

    # Status (original schema)
    status = Column(String(50), nullable=False, default="pending", index=True)
    progress = Column(Float, nullable=False, default=0.0)
    status_message = Column(String(500), nullable=True)
    error_message = Column(Text, nullable=True)
    error_traceback = Column(Text, nullable=True)

    # Input/Output (original schema)
    input_params = Column(JSONB, nullable=True)
    result = Column(JSONB, nullable=True)

    # Agent-specific fields (added via ALTER TABLE)
    agent_type = Column(String(50), nullable=True, index=True)
    query = Column(Text, nullable=True)
    config = Column(JSON, nullable=True)
    report = Column(Text, nullable=True)
    sources = Column(JSON, nullable=True)
    current_step = Column(String(100), nullable=True)
    elapsed_ms = Column(Float, nullable=True)
    retrieval_time_ms = Column(Float, nullable=True)
    llm_time_ms = Column(Float, nullable=True)
    tokens_used = Column(Integer, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    project = relationship("Project", back_populates="tasks", lazy="select")

    def __repr__(self) -> str:
        return f"<Task id={self.id} agent={self.agent_type} status={self.status}>"
