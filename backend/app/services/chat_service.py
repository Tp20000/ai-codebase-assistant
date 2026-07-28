"""
Chat Service — High-level business logic for chat history management.

Sits between API routes and the repository layer.
Handles:
- Auto-generating session titles from first user message
- Exporting conversations to Markdown and JSON formats
- Conversation threading helpers
- Title suggestions using simple NLP heuristics
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.chat import ChatMessage, ChatSession
from app.repositories.chat_repo import ChatRepository

logger = logging.getLogger(__name__)


class ChatService:
    """
    High-level service for chat history management.

    Provides business logic that spans multiple repository operations
    and requires domain knowledge beyond simple CRUD.
    """

    # Maximum title length for auto-generated titles
    MAX_TITLE_LENGTH: int = 60

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize with database session.

        Args:
            db: Async SQLAlchemy session
        """
        self.db = db
        self._repo = ChatRepository(db)

    async def create_session(
        self,
        project_id: UUID,
        user_id: UUID,
        title: Optional[str] = None,
    ) -> ChatSession:
        """
        Create a new chat session with an optional title.

        If no title is provided, creates with 'New Conversation'
        placeholder. Title is auto-updated after first user message.

        Args:
            project_id: Project context
            user_id: Owning user
            title: Optional custom title

        Returns:
            Created ChatSession
        """
        return await self._repo.create_session(
            project_id=project_id,
            user_id=user_id,
            title=title or "New Conversation",
        )

    async def add_user_message(
        self,
        session_id: UUID,
        content: str,
        prompt_type: Optional[str] = None,
        auto_title: bool = True,
    ) -> ChatMessage:
        """
        Add a user message and auto-generate title if this is the first message.

        Args:
            session_id: Target session
            content: Message text
            prompt_type: Optional prompt type hint
            auto_title: If True, auto-generate title from first message

        Returns:
            Created ChatMessage
        """
        message = await self._repo.add_message(
            session_id=session_id,
            role="user",
            content=content,
            prompt_type=prompt_type,
        )

        # Auto-generate title from first user message
        if auto_title:
            session = await self._repo.get_session(session_id, user_id=None)
            if session and session.message_count <= 1:
                title = self._generate_title(content)
                await self._repo.update_session_title(
                    session_id=session_id,
                    user_id=session.user_id,
                    title=title,
                )
                logger.debug("Auto-generated title: '%s'", title)

        return message

    async def export_session_markdown(
        self,
        session_id: UUID,
        user_id: UUID,
    ) -> str:
        """
        Export a chat session as a formatted Markdown document.

        Includes session metadata, all messages with timestamps,
        and source attribution for AI responses.

        Args:
            session_id: Session to export
            user_id: Owner for authorization

        Returns:
            Markdown-formatted string of the conversation

        Raises:
            ValueError: If session not found or not authorized
        """
        session = await self._repo.get_session_with_messages(
            session_id=session_id, user_id=user_id
        )
        if not session:
            raise ValueError("Session not found or access denied")

        lines: list[str] = [
            f"# {session.title}",
            f"",
            f"**Project:** {session.project_id}",
            f"**Created:** {session.created_at.strftime('%Y-%m-%d %H:%M UTC')}",
            f"**Messages:** {session.message_count}",
            f"",
            "---",
            "",
        ]

        for msg in session.messages:
            timestamp = msg.created_at.strftime("%H:%M")
            if msg.role == "user":
                lines.append(f"## 🧑 User ({timestamp})")
                lines.append("")
                lines.append(msg.content)
                lines.append("")
            else:
                model_info = f" · {msg.model_used}" if msg.model_used else ""
                cached_info = " · ⚡ cached" if msg.cached else ""
                lines.append(f"## 🤖 Assistant ({timestamp}{model_info}{cached_info})")
                lines.append("")
                lines.append(msg.content)
                lines.append("")

                # Add sources if present
                if msg.sources:
                    lines.append("**Sources:**")
                    for src in msg.sources[:5]:
                        file_path = src.get("file_path", "unknown")
                        lines_ref = f"L{src.get('start_line', '?')}-{src.get('end_line', '?')}"
                        score = src.get("similarity_score", 0)
                        lines.append(f"- {file_path} {lines_ref} (score: {score:.3f})")
                    lines.append("")

                # Add timing metadata as HTML comment (hidden in rendered MD)
                if msg.total_time_ms:
                    lines.append(
                        f"<!-- tokens:{msg.tokens_generated} "
                        f"time:{msg.total_time_ms:.0f}ms -->"
                    )
                    lines.append("")

            lines.append("---")
            lines.append("")

        return "\n".join(lines)

    async def export_session_json(
        self,
        session_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any]:
        """
        Export a chat session as a structured JSON object.

        Includes full message content, RAG metadata, and analytics.
        Suitable for programmatic processing or re-import.

        Args:
            session_id: Session to export
            user_id: Owner for authorization

        Returns:
            Dict with complete session data

        Raises:
            ValueError: If session not found
        """
        session = await self._repo.get_session_with_messages(
            session_id=session_id, user_id=user_id
        )
        if not session:
            raise ValueError("Session not found or access denied")

        analytics = await self._repo.get_session_analytics(session_id)

        return {
            "export_version": "2.0",
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "session": {
                "id": str(session.id),
                "title": session.title,
                "project_id": str(session.project_id),
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "message_count": session.message_count,
            },
            "messages": [
                {
                    "id": str(m.id),
                    "role": m.role,
                    "content": m.content,
                    "prompt_type": m.prompt_type,
                    "model_used": m.model_used,
                    "sources": m.sources or [],
                    "cached": m.cached,
                    "metrics": {
                        "retrieval_ms": m.retrieval_time_ms,
                        "llm_ms": m.llm_time_ms,
                        "total_ms": m.total_time_ms,
                        "tokens": m.tokens_generated,
                        "context_tokens": m.context_tokens,
                    },
                    "created_at": m.created_at.isoformat(),
                }
                for m in session.messages
            ],
            "analytics": analytics,
        }

    async def get_session_summary(
        self,
        session_id: UUID,
        user_id: UUID,
    ) -> dict[str, Any]:
        """
        Get a summary of a session with analytics and recent messages.

        Used by the frontend sidebar to show session previews without
        loading the full message history.

        Args:
            session_id: Session to summarize
            user_id: Owner for authorization

        Returns:
            Dict with session metadata and analytics
        """
        session = await self._repo.get_session(session_id, user_id)
        if not session:
            raise ValueError("Session not found")

        analytics = await self._repo.get_session_analytics(session_id)

        # Get the last assistant message as preview
        messages = await self._repo.get_messages(
            session_id=session_id, limit=2, role_filter="assistant"
        )
        last_response = messages[-1].content[:200] if messages else None

        return {
            "session_id": str(session.id),
            "title": session.title,
            "project_id": str(session.project_id),
            "message_count": session.message_count,
            "created_at": session.created_at.isoformat(),
            "updated_at": session.updated_at.isoformat(),
            "last_response_preview": last_response,
            "analytics": analytics,
        }

    def _generate_title(self, first_message: str) -> str:
        """
        Auto-generate a conversation title from the first user message.

        Applies heuristics to create a short, meaningful title:
        - Remove filler words and question words
        - Capitalize properly
        - Truncate to MAX_TITLE_LENGTH

        Args:
            first_message: The first user message text

        Returns:
            Generated title string
        """
        # Clean the message
        text = first_message.strip()

        # Remove leading question words and filler phrases
        filler_patterns = [
            r"^(can you|could you|please|would you|help me|i need|i want|i'd like to)\s+",
            r"^(what|how|why|when|where|who|which|is|are|does|do|can|should|would)\s+",
            r"[?!]+$",
        ]
        for pattern in filler_patterns:
            text = re.sub(pattern, "", text, flags=re.IGNORECASE).strip()

        # Take first sentence or up to MAX_TITLE_LENGTH chars
        first_sentence = re.split(r"[.!?\n]", text)[0].strip()

        if not first_sentence:
            first_sentence = text

        # Capitalize and truncate
        title = first_sentence.capitalize()
        if len(title) > self.MAX_TITLE_LENGTH:
            title = title[: self.MAX_TITLE_LENGTH - 3].rsplit(" ", 1)[0] + "..."

        return title or "Conversation"
