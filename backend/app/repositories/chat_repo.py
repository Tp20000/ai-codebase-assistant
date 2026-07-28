"""
Chat repository for database operations on sessions and messages.

Implements the repository pattern for all chat-related persistence.
Provides:
- Session CRUD with soft-delete
- Message persistence with RAG metadata
- Full-text message search
- Conversation history formatting for prompt injection
- Per-session analytics aggregation
- Pagination for large conversation lists
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from sqlalchemy import Select, func, select, update, or_, desc, asc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.chat import ChatMessage, ChatSession
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class ChatRepository(BaseRepository[ChatSession]):
    """Repository for ChatSession and ChatMessage database operations."""

    def __init__(self, db: AsyncSession) -> None:
        """Initialize with async database session."""
        super().__init__(ChatSession, db)

    # ─────────────────────────────────────────────────────────────
    # Session Management
    # ─────────────────────────────────────────────────────────────

    async def create_session(
        self,
        project_id: UUID,
        user_id: UUID,
        title: str = "New Conversation",
    ) -> ChatSession:
        """
        Create a new chat session.

        Args:
            project_id: Project this conversation is about
            user_id: User starting the conversation
            title: Optional conversation title (auto-generated later)

        Returns:
            Created ChatSession instance
        """
        session = ChatSession(
            project_id=project_id,
            user_id=user_id,
            title=title,
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        logger.info("Created chat session %s for user %s", session.id, user_id)
        return session

    async def get_session(
        self, session_id: UUID, user_id: UUID
    ) -> Optional[ChatSession]:
        """
        Get a session by ID with ownership check (no messages loaded).

        Args:
            session_id: Session UUID
            user_id: Owner for authorization check

        Returns:
            ChatSession or None
        """
        result = await self.db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
                ChatSession.is_active == True,
            )
        )
        return result.scalar_one_or_none()

    async def get_session_with_messages(
        self,
        session_id: UUID,
        user_id: Optional[UUID] = None,
    ) -> Optional[ChatSession]:
        """
        Get a session with all messages eagerly loaded.

        Args:
            session_id: Session UUID to fetch
            user_id: Optional owner check (None skips auth check)

        Returns:
            ChatSession with messages or None
        """
        conditions = [
            ChatSession.id == session_id,
            ChatSession.is_active == True,
        ]
        if user_id is not None:
            conditions.append(ChatSession.user_id == user_id)

        result = await self.db.execute(
            select(ChatSession)
            .options(selectinload(ChatSession.messages))
            .where(*conditions)
        )
        return result.scalar_one_or_none()

    async def list_sessions(
        self,
        project_id: UUID,
        user_id: UUID,
        limit: int = 20,
        offset: int = 0,
        order_by: str = "updated_at",
        ascending: bool = False,
    ) -> list[ChatSession]:
        """
        List active chat sessions for a project with pagination.

        Args:
            project_id: Filter by project
            user_id: Filter by user
            limit: Max sessions to return
            offset: Pagination offset
            order_by: Field to sort by (updated_at, created_at, title)
            ascending: Sort direction

        Returns:
            List of ChatSession objects
        """
        sort_col = getattr(ChatSession, order_by, ChatSession.updated_at)
        order_fn = asc if ascending else desc

        result = await self.db.execute(
            select(ChatSession)
            .where(
                ChatSession.project_id == project_id,
                ChatSession.user_id == user_id,
                ChatSession.is_active == True,
            )
            .order_by(order_fn(sort_col))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_sessions(
        self, project_id: UUID, user_id: UUID
    ) -> int:
        """
        Count total active sessions for pagination metadata.

        Args:
            project_id: Project filter
            user_id: User filter

        Returns:
            Total session count
        """
        result = await self.db.execute(
            select(func.count(ChatSession.id)).where(
                ChatSession.project_id == project_id,
                ChatSession.user_id == user_id,
                ChatSession.is_active == True,
            )
        )
        return result.scalar_one() or 0

    async def update_session_title(
        self, session_id: UUID, user_id: UUID, title: str
    ) -> bool:
        """
        Update the title of a chat session.

        Args:
            session_id: Session to update
            user_id: Owner for authorization
            title: New title string (max 255 chars)

        Returns:
            True if updated, False if not found
        """
        result = await self.db.execute(
            update(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
                ChatSession.is_active == True,
            )
            .values(title=title[:255])
        )
        await self.db.commit()
        return result.rowcount > 0

    async def delete_session(
        self, session_id: UUID, user_id: UUID
    ) -> bool:
        """
        Soft-delete a chat session.

        Args:
            session_id: Session to delete
            user_id: Owner for authorization

        Returns:
            True if deleted, False if not found
        """
        result = await self.db.execute(
            update(ChatSession)
            .where(
                ChatSession.id == session_id,
                ChatSession.user_id == user_id,
            )
            .values(is_active=False)
        )
        await self.db.commit()
        deleted = result.rowcount > 0
        if deleted:
            logger.info("Soft-deleted session %s", session_id)
        return deleted

    # ─────────────────────────────────────────────────────────────
    # Message Management
    # ─────────────────────────────────────────────────────────────

    async def add_message(
        self,
        session_id: UUID,
        role: str,
        content: str,
        prompt_type: Optional[str] = None,
        model_used: Optional[str] = None,
        sources: Optional[list] = None,
        retrieval_time_ms: Optional[float] = None,
        llm_time_ms: Optional[float] = None,
        total_time_ms: Optional[float] = None,
        tokens_generated: Optional[int] = None,
        context_tokens: Optional[int] = None,
        cached: bool = False,
    ) -> ChatMessage:
        """
        Add a message to a chat session and increment message count.

        Args:
            session_id: Target session UUID
            role: 'user' or 'assistant'
            content: Message text content
            prompt_type: RAG prompt type used (assistant messages)
            model_used: LLM model name (assistant messages)
            sources: Retrieved code chunks (assistant messages)
            retrieval_time_ms: Retrieval latency metric
            llm_time_ms: LLM generation latency metric
            total_time_ms: Total pipeline latency
            tokens_generated: Number of tokens generated
            context_tokens: Context window tokens used
            cached: Whether response came from cache

        Returns:
            Created ChatMessage instance
        """
        message = ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            prompt_type=prompt_type,
            model_used=model_used,
            sources=sources,
            retrieval_time_ms=retrieval_time_ms,
            llm_time_ms=llm_time_ms,
            total_time_ms=total_time_ms,
            tokens_generated=tokens_generated,
            context_tokens=context_tokens,
            cached=cached,
        )
        self.db.add(message)

        # Atomically increment session message count
        await self.db.execute(
            update(ChatSession)
            .where(ChatSession.id == session_id)
            .values(message_count=ChatSession.message_count + 1)
        )

        await self.db.commit()
        await self.db.refresh(message)
        return message

    async def get_messages(
        self,
        session_id: UUID,
        limit: int = 50,
        offset: int = 0,
        role_filter: Optional[str] = None,
    ) -> list[ChatMessage]:
        """
        Get messages for a session with optional role filter.

        Args:
            session_id: Session to query
            limit: Max messages to return
            offset: Pagination offset
            role_filter: Optional 'user' or 'assistant' filter

        Returns:
            List of ChatMessage objects in chronological order
        """
        conditions = [ChatMessage.session_id == session_id]
        if role_filter:
            conditions.append(ChatMessage.role == role_filter)

        result = await self.db.execute(
            select(ChatMessage)
            .where(*conditions)
            .order_by(asc(ChatMessage.created_at))
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get_conversation_history(
        self,
        session_id: UUID,
        last_n: int = 10,
    ) -> str:
        """
        Get formatted conversation history for prompt injection.

        Retrieves the last N messages and formats them as a readable
        history string for multi-turn conversation context.

        Args:
            session_id: Session to retrieve history from
            last_n: Number of recent messages to include

        Returns:
            Formatted conversation history string
        """
        result = await self.db.execute(
            select(ChatMessage)
            .where(ChatMessage.session_id == session_id)
            .order_by(desc(ChatMessage.created_at))
            .limit(last_n)
        )
        messages = list(reversed(result.scalars().all()))

        if not messages:
            return ""

        parts: list[str] = []
        for msg in messages:
            prefix = "User" if msg.role == "user" else "Assistant"
            content = (
                msg.content[:500] + "..."
                if len(msg.content) > 500
                else msg.content
            )
            parts.append(f"{prefix}: {content}")

        return "\n\n".join(parts)

    # ─────────────────────────────────────────────────────────────
    # Search
    # ─────────────────────────────────────────────────────────────

    async def search_messages(
        self,
        user_id: UUID,
        query: str,
        project_id: Optional[UUID] = None,
        session_id: Optional[UUID] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """
        Full-text search across all messages for a user.

        Uses PostgreSQL ILIKE for case-insensitive substring matching.
        For production scale, this should use PostgreSQL full-text search
        with tsvector/tsquery indexes.

        Args:
            user_id: Restrict search to this user's messages
            query: Search term (case-insensitive)
            project_id: Optional project filter
            session_id: Optional session filter
            limit: Max results to return
            offset: Pagination offset

        Returns:
            List of dicts with message + session metadata
        """
        search_term = f"%{query}%"

        # Join messages with sessions for user ownership check
        stmt = (
            select(ChatMessage, ChatSession)
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(
                ChatSession.user_id == user_id,
                ChatSession.is_active == True,
                ChatMessage.content.ilike(search_term),
            )
        )

        if project_id:
            stmt = stmt.where(ChatSession.project_id == project_id)
        if session_id:
            stmt = stmt.where(ChatMessage.session_id == session_id)

        stmt = (
            stmt.order_by(desc(ChatMessage.created_at))
            .limit(limit)
            .offset(offset)
        )

        result = await self.db.execute(stmt)
        rows = result.all()

        return [
            {
                "message_id": str(row.ChatMessage.id),
                "session_id": str(row.ChatMessage.session_id),
                "session_title": row.ChatSession.title,
                "role": row.ChatMessage.role,
                "content": row.ChatMessage.content,
                "content_preview": (
                    row.ChatMessage.content[:200] + "..."
                    if len(row.ChatMessage.content) > 200
                    else row.ChatMessage.content
                ),
                "prompt_type": row.ChatMessage.prompt_type,
                "created_at": row.ChatMessage.created_at.isoformat(),
            }
            for row in rows
        ]

    # ─────────────────────────────────────────────────────────────
    # Analytics
    # ─────────────────────────────────────────────────────────────

    async def get_session_analytics(
        self, session_id: UUID
    ) -> dict[str, Any]:
        """
        Compute analytics for a single chat session.

        Aggregates token usage, response times, cache hit rate,
        and message distribution for the session.

        Args:
            session_id: Session to analyze

        Returns:
            Dict with aggregated analytics metrics
        """
        result = await self.db.execute(
            select(
                func.count(ChatMessage.id).label("total_messages"),
                func.sum(
                    func.cast(ChatMessage.role == "user", type_=None)
                ).label("user_messages"),
                func.sum(
                    func.cast(ChatMessage.role == "assistant", type_=None)
                ).label("assistant_messages"),
                func.sum(ChatMessage.tokens_generated).label("total_tokens"),
                func.avg(ChatMessage.total_time_ms).label("avg_response_ms"),
                func.avg(ChatMessage.retrieval_time_ms).label("avg_retrieval_ms"),
                func.avg(ChatMessage.llm_time_ms).label("avg_llm_ms"),
                func.sum(
                    func.cast(ChatMessage.cached == True, type_=None)
                ).label("cache_hits"),
            ).where(ChatMessage.session_id == session_id)
        )
        row = result.one()

        total = row.total_messages or 0
        cache_hits = int(row.cache_hits or 0)
        assistant_msgs = int(row.assistant_messages or 0)

        return {
            "total_messages": total,
            "user_messages": int(row.user_messages or 0),
            "assistant_messages": assistant_msgs,
            "total_tokens_generated": int(row.total_tokens or 0),
            "avg_response_ms": round(float(row.avg_response_ms or 0), 2),
            "avg_retrieval_ms": round(float(row.avg_retrieval_ms or 0), 2),
            "avg_llm_ms": round(float(row.avg_llm_ms or 0), 2),
            "cache_hit_rate": round(
                cache_hits / assistant_msgs if assistant_msgs > 0 else 0, 3
            ),
            "cache_hits": cache_hits,
        }

    async def get_project_chat_analytics(
        self, project_id: UUID, user_id: UUID
    ) -> dict[str, Any]:
        """
        Aggregate chat analytics across all sessions for a project.

        Provides project-level insights: total conversations,
        most used prompt types, overall token consumption.

        Args:
            project_id: Project to analyze
            user_id: User filter for authorization

        Returns:
            Dict with project-level chat analytics
        """
        # Session-level stats
        session_result = await self.db.execute(
            select(
                func.count(ChatSession.id).label("total_sessions"),
                func.sum(ChatSession.message_count).label("total_messages"),
            ).where(
                ChatSession.project_id == project_id,
                ChatSession.user_id == user_id,
                ChatSession.is_active == True,
            )
        )
        session_row = session_result.one()

        # Prompt type distribution
        prompt_result = await self.db.execute(
            select(
                ChatMessage.prompt_type,
                func.count(ChatMessage.id).label("count"),
            )
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(
                ChatSession.project_id == project_id,
                ChatSession.user_id == user_id,
                ChatMessage.role == "assistant",
                ChatMessage.prompt_type != None,
            )
            .group_by(ChatMessage.prompt_type)
            .order_by(desc("count"))
        )
        prompt_rows = prompt_result.all()

        # Model usage distribution
        model_result = await self.db.execute(
            select(
                ChatMessage.model_used,
                func.count(ChatMessage.id).label("count"),
                func.sum(ChatMessage.tokens_generated).label("total_tokens"),
            )
            .join(ChatSession, ChatMessage.session_id == ChatSession.id)
            .where(
                ChatSession.project_id == project_id,
                ChatSession.user_id == user_id,
                ChatMessage.role == "assistant",
                ChatMessage.model_used != None,
            )
            .group_by(ChatMessage.model_used)
            .order_by(desc("count"))
        )
        model_rows = model_result.all()

        return {
            "total_sessions": int(session_row.total_sessions or 0),
            "total_messages": int(session_row.total_messages or 0),
            "prompt_type_distribution": [
                {"prompt_type": r.prompt_type, "count": int(r.count)}
                for r in prompt_rows
            ],
            "model_usage": [
                {
                    "model": r.model_used,
                    "messages": int(r.count),
                    "total_tokens": int(r.total_tokens or 0),
                }
                for r in model_rows
            ],
        }
