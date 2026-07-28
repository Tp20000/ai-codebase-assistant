"""
Session Service — User session management using Redis.

Session Strategy:
  - On login: create session with user data + device info
  - Sessions stored in Redis with TTL (auto-expire)
  - User can have multiple active sessions (multi-device)
  - All sessions for a user tracked in a Redis Set for bulk revocation
  - On logout: delete specific session + remove from user set

Session vs JWT:
  - JWT handles stateless authentication (verify without DB)
  - Sessions handle stateful data: active devices, preferences, context
  - Together they provide: fast auth (JWT) + session tracking (Redis)
"""

import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import redis.asyncio as aioredis

from app.services.cache_service import RedisKeys

logger = logging.getLogger(__name__)

# Session TTL — matches refresh token lifetime
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60  # 7 days


class SessionData:
    """
    Represents a user session stored in Redis.
    Serialized as JSON for Redis storage.
    """

    def __init__(
        self,
        session_id: str,
        user_id: str,
        email: str,
        username: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        self.session_id = session_id
        self.user_id = user_id
        self.email = email
        self.username = username
        self.device_info = device_info or "unknown"
        self.ip_address = ip_address or "unknown"
        self.created_at = datetime.now(timezone.utc).isoformat()
        self.last_active = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict:
        """Serialize session to dictionary for Redis storage."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "email": self.email,
            "username": self.username,
            "device_info": self.device_info,
            "ip_address": self.ip_address,
            "created_at": self.created_at,
            "last_active": self.last_active,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "SessionData":
        """Deserialize session from Redis-stored dictionary."""
        session = cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            email=data["email"],
            username=data["username"],
            device_info=data.get("device_info"),
            ip_address=data.get("ip_address"),
        )
        session.created_at = data.get("created_at", session.created_at)
        session.last_active = data.get("last_active", session.last_active)
        return session


class SessionService:
    """
    Manages user sessions in Redis.
    Each session = one logged-in device/browser.
    """

    def __init__(self, redis: aioredis.Redis) -> None:
        self.redis = redis

    async def create_session(
        self,
        user_id: str,
        email: str,
        username: str,
        device_info: Optional[str] = None,
        ip_address: Optional[str] = None,
        ttl: int = SESSION_TTL_SECONDS,
    ) -> SessionData:
        """
        Create and persist a new user session.

        Args:
            user_id: UUID string of the authenticated user
            email: User email for session metadata
            username: Username for session metadata
            device_info: User-Agent string from request headers
            ip_address: Client IP from request
            ttl: Session lifetime in seconds

        Returns:
            Created SessionData object
        """
        session_id = str(uuid.uuid4())
        session = SessionData(
            session_id=session_id,
            user_id=user_id,
            email=email,
            username=username,
            device_info=device_info,
            ip_address=ip_address,
        )

        # Store session data with TTL
        session_key = RedisKeys.format(RedisKeys.SESSION, session_id=session_id)
        await self.redis.setex(
            session_key,
            ttl,
            json.dumps(session.to_dict()),
        )

        # Track session in user's session set (for listing/revoking all sessions)
        user_sessions_key = RedisKeys.format(
            RedisKeys.USER_SESSIONS, user_id=user_id
        )
        await self.redis.sadd(user_sessions_key, session_id)
        # Set TTL on the set too (extend to match longest session)
        await self.redis.expire(user_sessions_key, ttl)

        logger.info(
            f"Session created: session_id={session_id}, "
            f"user_id={user_id}, ip={ip_address}"
        )
        return session

    async def get_session(self, session_id: str) -> Optional[SessionData]:
        """
        Retrieve an active session by ID.

        Args:
            session_id: UUID string of the session

        Returns:
            SessionData if found and active, None if expired/not found
        """
        session_key = RedisKeys.format(RedisKeys.SESSION, session_id=session_id)
        raw = await self.redis.get(session_key)
        if not raw:
            return None
        try:
            data = json.loads(raw)
            return SessionData.from_dict(data)
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning(f"Session parse error for {session_id}: {exc}")
            return None

    async def update_last_active(self, session_id: str) -> bool:
        """
        Update the last_active timestamp for a session.
        Called on each authenticated request to track activity.

        Args:
            session_id: Session UUID string

        Returns:
            True if session exists and was updated
        """
        session = await self.get_session(session_id)
        if not session:
            return False
        session.last_active = datetime.now(timezone.utc).isoformat()
        session_key = RedisKeys.format(RedisKeys.SESSION, session_id=session_id)
        remaining_ttl = await self.redis.ttl(session_key)
        if remaining_ttl > 0:
            await self.redis.setex(
                session_key,
                remaining_ttl,
                json.dumps(session.to_dict()),
            )
        return True

    async def delete_session(self, session_id: str, user_id: str) -> bool:
        """
        Delete a specific session (single device logout).

        Args:
            session_id: Session to delete
            user_id: User who owns the session (for set cleanup)

        Returns:
            True if session was found and deleted
        """
        session_key = RedisKeys.format(RedisKeys.SESSION, session_id=session_id)
        deleted = await self.redis.delete(session_key)

        # Remove from user's session set
        user_sessions_key = RedisKeys.format(
            RedisKeys.USER_SESSIONS, user_id=user_id
        )
        await self.redis.srem(user_sessions_key, session_id)

        if deleted:
            logger.info(f"Session deleted: {session_id}")
        return deleted > 0

    async def delete_all_user_sessions(self, user_id: str) -> int:
        """
        Delete ALL sessions for a user (logout from all devices).
        Used when: password changed, account compromised, admin deactivation.

        Args:
            user_id: UUID string of the user

        Returns:
            Number of sessions deleted
        """
        user_sessions_key = RedisKeys.format(
            RedisKeys.USER_SESSIONS, user_id=user_id
        )
        session_ids = await self.redis.smembers(user_sessions_key)

        deleted_count = 0
        for session_id in session_ids:
            session_key = RedisKeys.format(
                RedisKeys.SESSION, session_id=session_id
            )
            result = await self.redis.delete(session_key)
            deleted_count += result

        # Delete the user sessions set
        await self.redis.delete(user_sessions_key)

        logger.info(
            f"All {deleted_count} sessions deleted for user_id={user_id}"
        )
        return deleted_count

    async def get_user_sessions(self, user_id: str) -> list[SessionData]:
        """
        List all active sessions for a user.
        Used in the Security settings page to show logged-in devices.

        Args:
            user_id: UUID string of the user

        Returns:
            List of active SessionData objects (expired sessions auto-excluded)
        """
        user_sessions_key = RedisKeys.format(
            RedisKeys.USER_SESSIONS, user_id=user_id
        )
        session_ids = await self.redis.smembers(user_sessions_key)

        sessions = []
        stale_ids = []

        for session_id in session_ids:
            session = await self.get_session(session_id)
            if session:
                sessions.append(session)
            else:
                # Session expired — clean up from set
                stale_ids.append(session_id)

        # Clean up stale session IDs from set
        if stale_ids:
            await self.redis.srem(user_sessions_key, *stale_ids)

        return sessions

    async def count_user_sessions(self, user_id: str) -> int:
        """
        Count active sessions for a user.

        Args:
            user_id: UUID string of the user

        Returns:
            Number of currently active sessions
        """
        sessions = await self.get_user_sessions(user_id)
        return len(sessions)
