"""
Database table creation script for production deployment.
Uses SQLAlchemy metadata.create_all() instead of Alembic migrations.
This avoids migration file conflicts and is reliable for initial deployment.
"""

import asyncio
import logging
import os
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def create_all_tables() -> None:
    """Create all database tables using SQLAlchemy metadata."""
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    db_url = os.environ.get("DATABASE_URL", "")
    if not db_url:
        logger.error("DATABASE_URL environment variable not set!")
        sys.exit(1)

    # Ensure correct asyncpg prefix
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql+asyncpg://", 1)
    elif db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    logger.info("Connecting to database...")
    engine = create_async_engine(db_url, poolclass=NullPool, echo=False)

    # Import ALL models so metadata is populated
    try:
        from app.database import Base
        import app.models.user    # noqa: F401
        import app.models.project # noqa: F401
        import app.models.file    # noqa: F401
        import app.models.chat    # noqa: F401
        import app.models.task    # noqa: F401
        logger.info(f"Models loaded: {list(Base.metadata.tables.keys())}")
    except ImportError as e:
        logger.error(f"Failed to import models: {e}")
        sys.exit(1)

    async with engine.begin() as conn:
        logger.info("Creating tables...")
        await conn.run_sync(Base.metadata.create_all)
        logger.info("All tables created successfully!")

    await engine.dispose()
    logger.info("Database setup complete!")


if __name__ == "__main__":
    asyncio.run(create_all_tables())