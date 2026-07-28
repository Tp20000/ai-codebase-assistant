"""
Application Configuration - Pydantic v2 Settings

All configuration loaded from environment variables or .env file.
Sensitive values (secrets, passwords) are never hardcoded.

Usage:
    from app.config import settings          # direct singleton
    from app.config import get_settings      # cached factory (for DI)
"""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings with automatic environment variable loading.
    Pydantic v2 BaseSettings reads from .env file and environment.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # -- Application --
    APP_NAME: str = "AI Codebase Assistant"
    VERSION: str = "2.0.0"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    LOG_LEVEL: str = "INFO"

    # -- Security --
    SECRET_KEY: str = "change-this-secret-key-in-production-minimum-32-chars"
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
    ]

    # -- JWT --
    JWT_PRIVATE_KEY: Optional[str] = None
    JWT_PUBLIC_KEY: Optional[str] = None
    JWT_ISSUER: str = "ai-codebase-assistant"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 15
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # -- Password Hashing --
    BCRYPT_ROUNDS: int = 12

    # -- Database --
    DATABASE_URL: str = "postgresql+asyncpg://aiassistant:aiassistant_secret@localhost:5433/ai_codebase_db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    DB_POOL_TIMEOUT: int = 30

    # -- Redis --
    REDIS_URL: str = "redis://localhost:6379/0"

    # -- Ollama --
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_DEFAULT_MODEL: str = "tinyllama"
    OLLAMA_CODE_MODEL: str = "codellama"
    OLLAMA_TIMEOUT: float = 120.0

    # -- ChromaDB --
    CHROMA_PERSIST_DIR: str = "./chroma_db"
    CHROMA_HOST: str = "chromadb"
    CHROMA_PORT: int = 8000
    CHROMA_COLLECTION_PREFIX: str = "project_"
    EMBEDDING_MODEL: str = "sentence-transformers/all-MiniLM-L6-v2"

    # -- File Upload --
    UPLOAD_DIR: str = "./uploads"
    MAX_UPLOAD_SIZE_MB: int = 100
    ALLOWED_EXTENSIONS: list[str] = [
        ".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".cpp", ".c",
        ".h", ".go", ".rs", ".rb", ".php", ".cs", ".zip",
    ]

    # -- RAG Pipeline --
    RAG_TOP_K: int = 8
    RAG_CACHE_TTL: int = 3600
    RAG_MAX_CONTEXT_TOKENS: int = 3000

    # -- Celery --
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # -- Email (optional) --
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USERNAME: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    FROM_EMAIL: str = "noreply@ai-assistant.local"

    @field_validator("DATABASE_URL")
    @classmethod
    def validate_database_url(cls, v: str) -> str:
        """Ensure database URL uses asyncpg driver."""
        if "postgresql" in v and "asyncpg" not in v:
            v = v.replace("postgresql://", "postgresql+asyncpg://")
        return v

    @field_validator("LOG_LEVEL")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Normalize log level to uppercase."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        v_upper = v.upper()
        if v_upper not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of {valid_levels}")
        return v_upper

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value: Any) -> list[str]:
        """Parse CORS origins from JSON string or list."""
        if isinstance(value, str):
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return [o.strip() for o in value.split(",")]
        return value


# ----------------------------------------------------------------
# Two ways to access settings - BOTH supported throughout the app
# ----------------------------------------------------------------

# Option 1: Direct singleton (imported as 'from app.config import settings')
settings = Settings()


# Option 2: Cached factory (used with FastAPI Depends)
@lru_cache
def get_settings() -> Settings:
    """
    Return cached Settings instance for dependency injection.
    Uses lru_cache so .env is only read once per process.
    """
    return Settings()
