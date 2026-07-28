"""
Agent Celery Tasks - Step 28
AI Codebase Assistant v2.0

Wraps agent execution in Celery tasks for background processing.

Task flow:
    1. API receives agent run request
    2. API calls run_agent_task.delay(...)  -> returns task_id immediately
    3. Celery worker picks up task
    4. Worker runs agent via AgentOrchestrator
    5. Progress updates stored in Redis (key: task:progress:{task_id})
    6. Final result stored by Celery backend
    7. Client polls GET /api/v1/tasks/{task_id} for status

Progress schema stored in Redis:
    {
        "task_id": str,
        "status": "PENDING|RUNNING|COMPLETED|FAILED",
        "agent_id": str,
        "progress": 0.0-1.0,
        "current_step": str,
        "started_at": ISO timestamp,
        "completed_at": ISO timestamp or null,
        "error": str or null,
    }
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import redis

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)

# =============================================================================
# Redis client for progress updates
# =============================================================================

def _get_redis_client() -> redis.Redis:
    """
    Create a Redis client for storing task progress.

    Uses the same connection parameters as the Celery broker.

    Returns:
        Connected Redis client instance
    """
    url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    return redis.from_url(url, decode_responses=True)


def _store_progress(
    task_id: str,
    status: str,
    progress: float,
    current_step: str,
    agent_id: str,
    error: str | None = None,
    completed_at: str | None = None,
    extra: dict[str, Any] | None = None,
) -> None:
    """
    Store task progress in Redis for WebSocket/polling consumption.

    Key: task:progress:{task_id}
    TTL: 86400 seconds (24 hours)

    Args:
        task_id:      Celery task UUID
        status:       PENDING | RUNNING | COMPLETED | FAILED
        progress:     0.0 to 1.0 float
        current_step: Human-readable current workflow step
        agent_id:     Which agent is running
        error:        Error message if failed
        completed_at: ISO timestamp when done
        extra:        Additional metadata dict
    """
    try:
        client = _get_redis_client()
        payload: dict[str, Any] = {
            "task_id": task_id,
            "status": status,
            "agent_id": agent_id,
            "progress": round(progress, 3),
            "current_step": current_step,
            "error": error,
            "completed_at": completed_at,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if extra:
            payload.update(extra)
        client.setex(
            f"task:progress:{task_id}",
            86400,
            json.dumps(payload),
        )
    except Exception as exc:
        # Progress storage failure should never crash the task
        logger.warning("Failed to store progress for %s: %s", task_id, exc)


def get_task_progress(task_id: str) -> dict[str, Any] | None:
    """
    Retrieve task progress from Redis.

    Args:
        task_id: Celery task UUID

    Returns:
        Progress dict or None if not found
    """
    try:
        client = _get_redis_client()
        raw = client.get(f"task:progress:{task_id}")
        if raw:
            return json.loads(raw)
    except Exception as exc:
        logger.warning("Failed to get progress for %s: %s", task_id, exc)
    return None


# =============================================================================
# Agent Execution Task
# =============================================================================

@celery_app.task(
    name="app.tasks.agent_tasks.run_agent_task",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=600,
    time_limit=720,
    queue="default",
)
def run_agent_task(
    self: Any,
    agent_id: str,
    project_id: str,
    user_id: str,
    code_content: str,
    language: str,
    file_path: str,
    model: str = "tinyllama",
    extra_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Celery task that runs a single agent asynchronously.

    This task is the bridge between the FastAPI API and the
    LangGraph agent system. It handles:
        - Progress tracking in Redis
        - Retry on transient failures
        - Structured result serialization

    Args:
        self:         Celery task instance (bound task)
        agent_id:     Registry key e.g. "security_scanner"
        project_id:   Project UUID for RAG retrieval
        user_id:      User UUID for authorization
        code_content: Source code to analyze
        language:     Programming language string
        file_path:    Original file path for context
        model:        Ollama model name
        extra_config: Additional config dict

    Returns:
        Dict with keys: status, agent_id, task_id,
        result (dict), report (str), elapsed_ms,
        error (str or None)

    Raises:
        celery.exceptions.Retry: On transient failures (retries automatically)
    """
    task_id = self.request.id or "local"
    started_at = datetime.now(timezone.utc).isoformat()

    logger.info(
        "Agent task starting: task_id=%s agent=%s language=%s",
        task_id, agent_id, language,
    )

    # Store initial RUNNING state
    _store_progress(
        task_id=task_id,
        status="RUNNING",
        progress=0.0,
        current_step="initializing",
        agent_id=agent_id,
        extra={"started_at": started_at},
    )

    try:
        # Import here to avoid circular imports at module load
        from app.core.agents.base_agent import AgentConfig
        from app.core.agents.orchestrator import AgentOrchestrator

        # Build config — code_content and language go in extra
        config = AgentConfig(
            project_id=project_id,
            user_id=user_id,
            query=f"Analyze {language} code in {file_path}",
            model=model,
            extra={
                "code_content": code_content,
                "language": language,
                "file_path": file_path,
                **(extra_config or {}),
            },
        )

        # Update progress: loading agent
        _store_progress(
            task_id=task_id,
            status="RUNNING",
            progress=0.1,
            current_step="loading_agent",
            agent_id=agent_id,
        )

        # Run agent (synchronously wrapping async with asyncio.run)
        orch = AgentOrchestrator()

        start_time = time.perf_counter()

        # asyncio.run() creates a new event loop for the sync Celery worker
        agent_result = asyncio.run(
            orch.run_single(agent_id, config)
        )

        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Store completion progress
        completed_at = datetime.now(timezone.utc).isoformat()
        status = (
            "COMPLETED"
            if agent_result.status.value == "completed"
            else "FAILED"
        )

        _store_progress(
            task_id=task_id,
            status=status,
            progress=1.0,
            current_step="done",
            agent_id=agent_id,
            error=agent_result.error,
            completed_at=completed_at,
            extra={
                "started_at": started_at,
                "elapsed_ms": round(elapsed_ms, 2),
            },
        )

        return {
            "status": status,
            "agent_id": agent_id,
            "task_id": task_id,
            "result": agent_result.result,
            "report": agent_result.report,
            "sources": agent_result.sources,
            "elapsed_ms": round(elapsed_ms, 2),
            "tokens_used": agent_result.tokens_used,
            "error": agent_result.error,
            "completed_at": completed_at,
        }

    except Exception as exc:
        logger.error(
            "Agent task failed: task_id=%s agent=%s error=%s",
            task_id, agent_id, exc,
            exc_info=True,
        )

        # Store failure in Redis
        _store_progress(
            task_id=task_id,
            status="FAILED",
            progress=0.0,
            current_step="failed",
            agent_id=agent_id,
            error=str(exc),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

        # Retry on connection errors (transient failures)
        if any(
            keyword in str(exc).lower()
            for keyword in ["connection", "timeout", "refused", "network"]
        ):
            raise self.retry(exc=exc, countdown=30)

        # Non-retryable: return failure result
        return {
            "status": "FAILED",
            "agent_id": agent_id,
            "task_id": task_id,
            "result": None,
            "report": None,
            "sources": [],
            "elapsed_ms": 0.0,
            "tokens_used": 0,
            "error": str(exc),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }


# =============================================================================
# Orchestration Task (run multiple agents)
# =============================================================================

@celery_app.task(
    name="app.tasks.agent_tasks.run_orchestration_task",
    bind=True,
    max_retries=1,
    soft_time_limit=1800,   # 30 minutes for full suite
    time_limit=2100,
    queue="default",
)
def run_orchestration_task(
    self: Any,
    agent_ids: list[str],
    project_id: str,
    user_id: str,
    code_content: str,
    language: str,
    file_path: str,
    mode: str = "parallel",
    model: str = "tinyllama",
) -> dict[str, Any]:
    """
    Celery task that runs multiple agents via the orchestrator.

    Args:
        self:         Celery task instance (bound task)
        agent_ids:    List of agent registry keys (empty = run all)
        project_id:   Project UUID
        user_id:      User UUID
        code_content: Source code to analyze
        language:     Programming language
        file_path:    File path for context
        mode:         "parallel" | "pipeline" | "full"
        model:        Ollama model name

    Returns:
        Dict with orchestration_id, mode, agent_results summary,
        master_report, timing info
    """
    task_id = self.request.id or "local"
    started_at = datetime.now(timezone.utc).isoformat()

    logger.info(
        "Orchestration task: task_id=%s mode=%s agents=%s",
        task_id, mode, agent_ids,
    )

    _store_progress(
        task_id=task_id,
        status="RUNNING",
        progress=0.05,
        current_step="initializing_orchestration",
        agent_id="orchestrator",
        extra={"started_at": started_at, "mode": mode},
    )

    try:
        from app.core.agents.base_agent import AgentConfig
        from app.core.agents.orchestrator import AgentOrchestrator

        config = AgentConfig(
            project_id=project_id,
            user_id=user_id,
            query=f"Complete analysis of {language} code in {file_path}",
            model=model,
            extra={
                "code_content": code_content,
                "language": language,
                "file_path": file_path,
            },
        )

        _store_progress(
            task_id=task_id,
            status="RUNNING",
            progress=0.1,
            current_step="running_agents",
            agent_id="orchestrator",
        )

        orch = AgentOrchestrator()
        start = time.perf_counter()

        if mode == "full" or not agent_ids:
            orch_result = asyncio.run(orch.run_full(config))
        elif mode == "pipeline":
            orch_result = asyncio.run(
                orch.run_pipeline(agent_ids, config)
            )
        else:
            orch_result = asyncio.run(
                orch.run_parallel(agent_ids, config)
            )

        elapsed_ms = (time.perf_counter() - start) * 1000
        completed_at = datetime.now(timezone.utc).isoformat()

        _store_progress(
            task_id=task_id,
            status="COMPLETED",
            progress=1.0,
            current_step="done",
            agent_id="orchestrator",
            completed_at=completed_at,
            extra={
                "started_at": started_at,
                "elapsed_ms": round(elapsed_ms, 2),
                "agents_succeeded": orch_result.agents_succeeded,
                "agents_failed": orch_result.agents_failed,
            },
        )

        # Serialize agent results (AgentResult not JSON-serializable directly)
        serialized_results: dict[str, Any] = {}
        for aid, ar in orch_result.agent_results.items():
            serialized_results[aid] = {
                "task_id": ar.task_id,
                "status": ar.status.value,
                "result": ar.result,
                "report": ar.report,
                "error": ar.error,
                "elapsed_ms": round(ar.elapsed_ms, 2),
                "tokens_used": ar.tokens_used,
            }

        return {
            "status": "COMPLETED",
            "orchestration_id": orch_result.orchestration_id,
            "task_id": task_id,
            "mode": orch_result.mode,
            "agents_succeeded": orch_result.agents_succeeded,
            "agents_failed": orch_result.agents_failed,
            "agent_results": serialized_results,
            "master_report": orch_result.master_report,
            "elapsed_ms": round(elapsed_ms, 2),
            "completed_at": completed_at,
        }

    except Exception as exc:
        logger.error(
            "Orchestration task failed: task_id=%s error=%s",
            task_id, exc,
            exc_info=True,
        )

        _store_progress(
            task_id=task_id,
            status="FAILED",
            progress=0.0,
            current_step="failed",
            agent_id="orchestrator",
            error=str(exc),
            completed_at=datetime.now(timezone.utc).isoformat(),
        )

        return {
            "status": "FAILED",
            "orchestration_id": None,
            "task_id": task_id,
            "mode": mode,
            "agents_succeeded": 0,
            "agents_failed": len(agent_ids) if agent_ids else 7,
            "agent_results": {},
            "master_report": None,
            "elapsed_ms": 0.0,
            "error": str(exc),
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
