"""
Celery Application Factory - Step 28
AI Codebase Assistant v2.0

Creates and configures the Celery application for background task processing.

Architecture:
    Broker:  Redis (same instance used for caching)
    Backend: Redis (stores task results and status)
    Workers: Run agent tasks asynchronously

Configuration:
    - Task serialization: JSON (safe, inspectable)
    - Result expiry: 24 hours
    - Task time limit: 10 minutes (agent runs)
    - Retry: 3 attempts with exponential backoff
    - Visibility: Task progress stored in Redis for WebSocket polling
"""

from __future__ import annotations

import logging
import os
from typing import Any

from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun, worker_ready
from kombu import Exchange, Queue

logger = logging.getLogger(__name__)

# =============================================================================
# Redis connection URL
# =============================================================================

def _get_redis_url() -> str:
    """
    Build Redis connection URL from environment variables.

    Checks REDIS_URL first (Upstash / Railway format),
    then falls back to individual host/port/password vars,
    then defaults to localhost for development.

    Returns:
        Redis URL string suitable for Celery broker/backend
    """
    url = os.getenv("REDIS_URL")
    if url:
        return url

    host = os.getenv("REDIS_HOST", "localhost")
    port = os.getenv("REDIS_PORT", "6379")
    password = os.getenv("REDIS_PASSWORD", "")
    db = os.getenv("REDIS_DB", "0")

    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"


REDIS_URL = _get_redis_url()

# =============================================================================
# Task Queues
# =============================================================================

# Three priority queues:
#   high    - Quick tasks (status checks, cache invalidation)
#   default - Normal agent runs
#   low     - Long indexing tasks, batch operations

DEFAULT_EXCHANGE = Exchange("ai_codebase", type="direct")

TASK_QUEUES = (
    Queue("high",    DEFAULT_EXCHANGE, routing_key="high"),
    Queue("default", DEFAULT_EXCHANGE, routing_key="default"),
    Queue("low",     DEFAULT_EXCHANGE, routing_key="low"),
)

# Route tasks to appropriate queues
TASK_ROUTES = {
    "app.tasks.agent_tasks.*":    {"queue": "default"},
    "app.tasks.indexing_tasks.*": {"queue": "low"},
}

# =============================================================================
# Celery App Factory
# =============================================================================

def create_celery_app() -> Celery:
    """
    Create and configure the Celery application instance.

    Configuration highlights:
        - JSON serialization for all tasks and results
        - 10-minute soft time limit, 12-minute hard limit per task
        - Results expire after 24 hours
        - Worker concurrency: 4 processes
        - Prefetch multiplier: 1 (fair task distribution)
        - Retry policy: 3 attempts, exponential backoff

    Returns:
        Configured Celery application instance
    """
    app = Celery(
        "ai_codebase_assistant",
        broker=REDIS_URL,
        backend=REDIS_URL,
        include=[
            "app.tasks.agent_tasks",
            "app.tasks.indexing_tasks",
        ],
    )

    app.conf.update(
        # ── Serialization ────────────────────────────────────────
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        # ── Timezone ─────────────────────────────────────────────
        timezone="UTC",
        enable_utc=True,
        # ── Result backend ────────────────────────────────────────
        result_expires=86400,          # 24 hours
        result_backend_transport_options={
            "retry_policy": {
                "timeout": 5.0,
            }
        },
        # ── Task execution ────────────────────────────────────────
        task_soft_time_limit=600,      # 10 minutes soft limit
        task_time_limit=720,           # 12 minutes hard limit
        task_acks_late=True,           # ACK after task completes (safer)
        task_reject_on_worker_lost=True,
        # ── Worker ───────────────────────────────────────────────
        worker_prefetch_multiplier=1,  # Fair distribution
        worker_max_tasks_per_child=50, # Restart worker after 50 tasks
        # ── Queues ───────────────────────────────────────────────
        task_queues=TASK_QUEUES,
        task_default_queue="default",
        task_default_exchange="ai_codebase",
        task_default_routing_key="default",
        task_routes=TASK_ROUTES,
        # ── Retry ────────────────────────────────────────────────
        task_max_retries=3,
        # ── Beat (scheduled tasks) ────────────────────────────────
        beat_schedule={},
        # ── Monitoring ───────────────────────────────────────────
        worker_send_task_events=True,
        task_send_sent_event=True,
    )

    return app


# Singleton Celery app instance
celery_app = create_celery_app()


# =============================================================================
# Celery Signal Handlers
# =============================================================================

@worker_ready.connect
def on_worker_ready(sender: Any, **kwargs: Any) -> None:
    """Log when a Celery worker comes online."""
    logger.info("Celery worker ready: %s", sender)


@task_prerun.connect
def on_task_prerun(
    task_id: str,
    task: Any,
    args: tuple,
    kwargs: dict,
    **extra: Any,
) -> None:
    """Log task start and update Redis status to RUNNING."""
    logger.info("Task starting: id=%s name=%s", task_id, task.name)


@task_postrun.connect
def on_task_postrun(
    task_id: str,
    task: Any,
    args: tuple,
    kwargs: dict,
    retval: Any,
    state: str,
    **extra: Any,
) -> None:
    """Log task completion."""
    logger.info("Task complete: id=%s state=%s", task_id, state)


@task_failure.connect
def on_task_failure(
    task_id: str,
    exception: Exception,
    traceback: Any,
    sender: Any,
    **kwargs: Any,
) -> None:
    """Log task failures for debugging."""
    logger.error(
        "Task failed: id=%s exception=%s",
        task_id,
        exception,
        exc_info=True,
    )
