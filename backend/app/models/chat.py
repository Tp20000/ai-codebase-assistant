"""
Chat session and message models.
Matches actual database schema from Step 3 migration.
"""

from __future__ import annotations

import uuid
from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Float,
    ForeignKey, Index, Integer, JSON, String, Text
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class ChatSession(Base):
    """A conversation thread for a specific project."""

    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(500), nullable=False, default="New Conversation")
    is_active = Column(Boolean, nullable=False, default=True)
    model_used = Column(String(100), nullable=False, default="llama3.2")
    message_count = Column(Integer, nullable=False, default=0)
    total_tokens_used = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_message_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    project = relationship("Project", back_populates="chat_sessions", lazy="select")
    user = relationship("User", back_populates="chat_sessions", lazy="select")
    messages = relationship(
        "ChatMessage",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
        lazy="select",
        foreign_keys="ChatMessage.session_id",
    )

    def __repr__(self) -> str:
        return f"<ChatSession id={self.id} title='{self.title}'>"


class ChatMessage(Base):
    """A single message in a chat conversation."""

    __tablename__ = "chat_messages"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)

    # Original schema columns
    model = Column(String(100), nullable=True)
    prompt_tokens = Column(Integer, nullable=False, default=0)
    completion_tokens = Column(Integer, nullable=False, default=0)
    generation_time_ms = Column(Float, nullable=True)
    rag_context_chunks = Column(JSONB, nullable=True)
    rag_sources = Column(JSONB, nullable=True)
    rag_similarity_scores = Column(JSONB, nullable=True)
    is_streaming = Column(Boolean, nullable=False, default=False)
    is_error = Column(Boolean, nullable=False, default=False)
    error_detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Added columns (via ALTER TABLE in our migrations)
    prompt_type = Column(String(50), nullable=True)
    model_used = Column(String(100), nullable=True)
    sources = Column(JSON, nullable=True)
    retrieval_time_ms = Column(Float, nullable=True)
    llm_time_ms = Column(Float, nullable=True)
    total_time_ms = Column(Float, nullable=True)
    tokens_generated = Column(Integer, nullable=True)
    context_tokens = Column(Integer, nullable=True)
    cached = Column(Boolean, nullable=False, default=False)

    # Relationship
    session = relationship("ChatSession", back_populates="messages", lazy="select")

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} role={self.role}>"
