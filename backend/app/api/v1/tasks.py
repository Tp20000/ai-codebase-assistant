"""
Tasks API Router - Step 28
AI Codebase Assistant v2.0

REST endpoints for task management:
    POST /api/v1/tasks/agent          - Queue a single agent task
    POST /api/v1/tasks/orchestrate    - Queue a multi-agent task
    GET  /api/v1/tasks/{task_id}      - Get task status and result
    GET  /api/v1/tasks/{task_id}/progress - Get live progress from Redis
    DELETE /api/v1/tasks/{task_id}    - Revoke a pending task
    GET  /api/v1/tasks/               - List recent tasks (from Celery backend)
"""

from __future__ import annotations

import logging
from typing import Annotated, Any

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.tasks.agent_tasks import (
    get_task_progress,
    run_agent_task,
    run_orchestration_task,
)
from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tasks", tags=["tasks"])


# =============================================================================
# Request / Response Models
# =============================================================================

class AgentTaskRequest(BaseModel):
    """Request body for queuing a single agent task."""

    agent_id: str = Field(
        ...,
        description="Agent registry key e.g. 'security_scanner'",
        examples=["security_scanner"],
    )
    project_id: str = Field(..., description="Project UUID")
    user_id: str = Field(..., description="User UUID")
    code_content: str = Field(
        ...,
        min_length=1,
        description="Source code to analyze",
    )
    language: str = Field(
        ...,
        description="Programming language",
        examples=["python"],
    )
    file_path: str = Field(
        default="uploaded_file",
        description="Original file path for context",
    )
    model: str = Field(
        default="tinyllama",
        description="Ollama model to use",
    )
    extra_config: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional agent configuration",
    )


class OrchestrationTaskRequest(BaseModel):
    """Request body for queuing a multi-agent orchestration task."""

    agent_ids: list[str] = Field(
        default_factory=list,
        description="Agent IDs to run (empty = run all 7)",
    )
    project_id: str = Field(..., description="Project UUID")
    user_id: str = Field(..., description="User UUID")
    code_content: str = Field(..., min_length=1)
    language: str = Field(...)
    file_path: str = Field(default="uploaded_file")
    mode: str = Field(
        default="parallel",
        description="Execution mode: parallel | pipeline | full",
    )
    model: str = Field(default="tinyllama")


class TaskStatusResponse(BaseModel):
    """Response model for task status queries."""

    task_id: str
    status: str
    ready: bool
    successful: bool | None = None
    result: dict[str, Any] | None = None
    error: str | None = None
    progress: dict[str, Any] | None = None


class TaskQueuedResponse(BaseModel):
    """Response when a task is successfully queued."""

    task_id: str
    status: str = "QUEUED"
    message: str
    poll_url: str


# =============================================================================
# Helper: get Celery task result safely
# =============================================================================

def _get_celery_result(task_id: str) -> dict[str, Any]:
    """
    Safely retrieve a Celery AsyncResult and serialize it.

    Args:
        task_id: Celery task UUID string

    Returns:
        Dict with status, ready, successful, result, error keys
    """
    try:
        ar: AsyncResult = AsyncResult(task_id, app=celery_app)
        ready = ar.ready()
        successful = ar.successful() if ready else None

        result_data = None
        error_msg = None

        if ready and successful:
            raw = ar.result
            if isinstance(raw, dict):
                result_data = raw
            else:
                result_data = {"raw": str(raw)}
        elif ready and not successful:
            error_msg = str(ar.result) if ar.result else "Task failed"

        return {
            "task_id": task_id,
            "status": ar.status,
            "ready": ready,
            "successful": successful,
            "result": result_data,
            "error": error_msg,
        }
    except Exception as exc:
        logger.warning("Error getting Celery result for %s: %s", task_id, exc)
        return {
            "task_id": task_id,
            "status": "UNKNOWN",
            "ready": False,
            "successful": None,
            "result": None,
            "error": str(exc),
        }


# =============================================================================
# Endpoints
# =============================================================================

@router.post(
    "/agent",
    response_model=TaskQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a single agent analysis task",
    description=(
        "Queues an agent task for background execution. "
        "Returns immediately with a task_id. "
        "Poll GET /tasks/{task_id} for results."
    ),
)
async def queue_agent_task(
    request: AgentTaskRequest,
) -> TaskQueuedResponse:
    """
    Queue a single agent task for background execution.

    Args:
        request: AgentTaskRequest with agent_id, code, language, etc.

    Returns:
        TaskQueuedResponse with task_id and poll URL
    """
    # Validate agent_id
    from app.core.agents.orchestrator import AGENT_REGISTRY
    if request.agent_id not in AGENT_REGISTRY:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Unknown agent_id: '{request.agent_id}'. "
                f"Available: {list(AGENT_REGISTRY.keys())}"
            ),
        )

    # Validate code content
    if len(request.code_content.strip()) == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="code_content cannot be empty",
        )

    # Queue the task
    task = run_agent_task.apply_async(
        kwargs={
            "agent_id": request.agent_id,
            "project_id": request.project_id,
            "user_id": request.user_id,
            "code_content": request.code_content,
            "language": request.language,
            "file_path": request.file_path,
            "model": request.model,
            "extra_config": request.extra_config,
        },
        queue="default",
    )

    logger.info(
        "Agent task queued: task_id=%s agent=%s",
        task.id, request.agent_id,
    )

    return TaskQueuedResponse(
        task_id=task.id,
        status="QUEUED",
        message=(
            f"Agent '{request.agent_id}' task queued. "
            f"Poll /api/v1/tasks/{task.id} for results."
        ),
        poll_url=f"/api/v1/tasks/{task.id}",
    )


@router.post(
    "/orchestrate",
    response_model=TaskQueuedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Queue a multi-agent orchestration task",
)
async def queue_orchestration_task(
    request: OrchestrationTaskRequest,
) -> TaskQueuedResponse:
    """
    Queue a multi-agent orchestration task.

    Args:
        request: OrchestrationTaskRequest with agent_ids, mode, etc.

    Returns:
        TaskQueuedResponse with task_id and poll URL
    """
    # Validate mode
    valid_modes = {"parallel", "pipeline", "full"}
    if request.mode not in valid_modes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid mode '{request.mode}'. Must be one of: {valid_modes}",
        )

    # Validate agent_ids if provided
    if request.agent_ids:
        from app.core.agents.orchestrator import AGENT_REGISTRY
        invalid = [
            aid for aid in request.agent_ids
            if aid not in AGENT_REGISTRY
        ]
        if invalid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unknown agent IDs: {invalid}",
            )

    task = run_orchestration_task.apply_async(
        kwargs={
            "agent_ids": request.agent_ids,
            "project_id": request.project_id,
            "user_id": request.user_id,
            "code_content": request.code_content,
            "language": request.language,
            "file_path": request.file_path,
            "mode": request.mode,
            "model": request.model,
        },
        queue="default",
    )

    logger.info(
        "Orchestration task queued: task_id=%s mode=%s agents=%s",
        task.id, request.mode, request.agent_ids,
    )

    agent_list = request.agent_ids or ["all 7 agents"]
    return TaskQueuedResponse(
        task_id=task.id,
        status="QUEUED",
        message=(
            f"Orchestration task queued (mode={request.mode}, "
            f"agents={agent_list}). "
            f"Poll /api/v1/tasks/{task.id} for results."
        ),
        poll_url=f"/api/v1/tasks/{task.id}",
    )


@router.get(
    "/{task_id}",
    response_model=TaskStatusResponse,
    summary="Get task status and result",
    description=(
        "Returns the current status of a task. "
        "When status is SUCCESS, result contains the agent output. "
        "Also includes live progress from Redis."
    ),
)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """
    Get the status and result of a queued task.

    Combines Celery backend status with Redis progress data.

    Args:
        task_id: Celery task UUID

    Returns:
        TaskStatusResponse with status, result, and progress
    """
    celery_data = _get_celery_result(task_id)
    redis_progress = get_task_progress(task_id)

    return TaskStatusResponse(
        task_id=task_id,
        status=celery_data["status"],
        ready=celery_data["ready"],
        successful=celery_data["successful"],
        result=celery_data["result"],
        error=celery_data["error"],
        progress=redis_progress,
    )


@router.get(
    "/{task_id}/progress",
    summary="Get live task progress from Redis",
    description="Returns real-time progress for WebSocket/polling clients.",
)
async def get_task_progress_endpoint(
    task_id: str,
) -> dict[str, Any]:
    """
    Get live progress data from Redis for a running task.

    Args:
        task_id: Celery task UUID

    Returns:
        Progress dict with status, progress float, current_step
    """
    progress = get_task_progress(task_id)
    if not progress:
        # Fallback to Celery status
        celery_data = _get_celery_result(task_id)
        return {
            "task_id": task_id,
            "status": celery_data["status"],
            "progress": 1.0 if celery_data["ready"] else 0.0,
            "current_step": "completed" if celery_data["ready"] else "pending",
        }
    return progress


@router.delete(
    "/{task_id}",
    status_code=status.HTTP_200_OK,
    summary="Revoke a pending task",
)
async def revoke_task(task_id: str) -> dict[str, str]:
    """
    Revoke (cancel) a pending or running task.

    Note: Cannot cancel a task that is already executing in a worker.
    Revoked tasks will not be retried.

    Args:
        task_id: Celery task UUID to revoke

    Returns:
        Confirmation message dict
    """
    try:
        celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
        logger.info("Task revoked: task_id=%s", task_id)
        return {
            "task_id": task_id,
            "message": "Task revoke signal sent",
        }
    except Exception as exc:
        logger.error("Failed to revoke task %s: %s", task_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to revoke task: {exc}",
        )


@router.get(
    "/",
    summary="List available agents",
    description="Returns list of all registered agents that can be queued.",
)
async def list_available_agents() -> dict[str, Any]:
    """
    List all agents available for task queuing.

    Returns:
        Dict with agents list and orchestration modes
    """
    from app.core.agents.orchestrator import AGENT_REGISTRY

    return {
        "agents": [
            {
                "agent_id": aid,
                "display": info.get("display", aid),
                "description": info.get("description", ""),
            }
            for aid, info in AGENT_REGISTRY.items()
        ],
        "orchestration_modes": ["parallel", "pipeline", "full"],
        "queue_endpoints": {
            "single_agent": "POST /api/v1/tasks/agent",
            "orchestration": "POST /api/v1/tasks/orchestrate",
        },
    }
