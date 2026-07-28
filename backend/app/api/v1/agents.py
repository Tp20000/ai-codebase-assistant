"""
Agents REST API - Trigger and monitor AI agent executions.

Endpoints:
- GET  /agents/types          - List available agent types
- POST /agents/run            - Run a single agent
- POST /agents/pipeline       - Run multiple agents sequentially
- GET  /agents/tasks/{id}     - Get task status/result
- GET  /agents/tasks          - List recent tasks for a project
"""

from __future__ import annotations

import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.agents.base_agent import AgentConfig, AgentStatus
from app.core.agents.orchestrator import AgentOrchestrator
from app.database import get_db
from app.middleware.auth_middleware import get_current_user
from app.repositories.task_repo import TaskRepository

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"])


def _get_orchestrator() -> AgentOrchestrator:
    """Build orchestrator with available infrastructure."""
    try:
        from app.core.rag.embeddings import EmbeddingService
        from app.core.rag.vector_store import VectorStoreService
        from app.core.rag.retriever import CodeRetriever
        from app.core.llm.streaming import OllamaStreamingClient
        from app.config import settings
        embedding_svc = EmbeddingService()
        vector_store = VectorStoreService()
        retriever = CodeRetriever(embedding_service=embedding_svc, vector_store=vector_store)
        streaming_client = OllamaStreamingClient(
            base_url=settings.OLLAMA_BASE_URL,
            timeout_seconds=float(settings.OLLAMA_TIMEOUT),
        )
    except Exception as exc:
        logger.warning("Agent infrastructure unavailable: %s", exc)
        retriever = None
        streaming_client = None

    orchestrator = AgentOrchestrator(retriever=retriever, streaming_client=streaming_client)
    _register_agents(orchestrator)
    return orchestrator


def _register_agents(orchestrator: AgentOrchestrator) -> None:
    """Register all available agent implementations."""
    agent_modules = [
        ("bug_finder", "app.core.agents.bug_finder", "BugFinderAgent"),
        ("doc_generator", "app.core.agents.doc_generator", "DocGeneratorAgent"),
        ("test_writer", "app.core.agents.test_writer", "TestWriterAgent"),
        ("code_reviewer", "app.core.agents.code_reviewer", "CodeReviewerAgent"),
        ("security_scanner", "app.core.agents.security_scanner", "SecurityScannerAgent"),
        ("refactor", "app.core.agents.refactor_agent", "RefactorAgent"),
        ("performance", "app.core.agents.performance_agent", "PerformanceAgent"),
    ]
    for agent_type, module_path, class_name in agent_modules:
        try:
            import importlib
            module = importlib.import_module(module_path)
            agent_class = getattr(module, class_name)
            orchestrator.register(agent_type, agent_class)
        except ImportError:
            pass
        except Exception as exc:
            logger.warning("Failed to register %s: %s", agent_type, exc)


class RunAgentRequest(BaseModel):
    """Request body for running a single agent."""
    model_config = ConfigDict(protected_namespaces=())
    project_id: UUID = Field(..., description="Project to analyze")
    agent_type: str = Field(..., description="Agent type e.g. bug_finder")
    query: str = Field(default="", max_length=4000)
    model_name: Optional[str] = Field(default=None)
    top_k: int = Field(default=8, ge=1, le=20)
    file_filter: Optional[str] = Field(default=None)
    language_filter: Optional[str] = Field(default=None)
    temperature: float = Field(default=0.1, ge=0.0, le=1.0)
    max_tokens: int = Field(default=2048, ge=256, le=8192)


class RunPipelineRequest(BaseModel):
    """Request body for running multiple agents."""
    model_config = ConfigDict(protected_namespaces=())
    project_id: UUID
    agent_types: list[str] = Field(..., min_length=1)
    query: str = Field(default="")
    model_name: Optional[str] = Field(default=None)
    stop_on_failure: bool = Field(default=False)


class TaskResponse(BaseModel):
    """Response for a single task."""
    model_config = ConfigDict(protected_namespaces=())
    task_id: str
    agent_type: str
    status: str
    progress: float
    current_step: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    report: Optional[str] = None
    sources: Optional[list[dict]] = None
    error: Optional[str] = None
    timing: Optional[dict] = None
    tokens_used: Optional[int] = None
    created_at: str


class AgentTypeInfo(BaseModel):
    """Info about an available agent type."""
    type: str
    display_name: str
    description: str


@router.get("/types", response_model=list[AgentTypeInfo], summary="List available agent types")
async def list_agent_types() -> list[AgentTypeInfo]:
    """Return all registered agent types for the frontend agent panel."""
    orchestrator = _get_orchestrator()
    agents = orchestrator.get_available_agents()
    return [AgentTypeInfo(**a) for a in agents]


@router.post(
    "/run",
    response_model=TaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Run a single agent analysis",
)
async def run_agent(
    body: RunAgentRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> TaskResponse:
    """Trigger a single AI agent to analyze a project."""
    from app.config import settings
    task_repo = TaskRepository(db)
    task = await task_repo.create_task(
        project_id=body.project_id,
        user_id=current_user.id,
        agent_type=body.agent_type,
        query=body.query,
        config={
            "model": body.model_name or settings.OLLAMA_DEFAULT_MODEL,
            "top_k": body.top_k,
            "temperature": body.temperature,
            "max_tokens": body.max_tokens,
        },
    )
    config = AgentConfig(
        project_id=str(body.project_id),
        user_id=str(current_user.id),
        query=body.query,
        file_filter=body.file_filter,
        language_filter=body.language_filter,
        model=body.model_name or settings.OLLAMA_DEFAULT_MODEL,
        top_k=body.top_k,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
    )
    try:
        await task_repo.update_status(task.id, "running", 0.0, "starting")
        orchestrator = _get_orchestrator()
        result = await orchestrator.run_agent(body.agent_type, config)
    except ValueError as exc:
        await task_repo.update_status(task.id, "failed", 0.0, error_message=str(exc))
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.error("Agent run failed: %s", exc, exc_info=True)
        await task_repo.update_status(task.id, "failed", 0.0, error_message=str(exc))
        raise HTTPException(status_code=503, detail=f"Agent execution failed: {exc}")
    await task_repo.complete_task(
        task_id=task.id,
        result=result.result,
        report=result.report,
        sources=result.sources,
        elapsed_ms=result.elapsed_ms,
        retrieval_time_ms=result.retrieval_time_ms,
        llm_time_ms=result.llm_time_ms,
        tokens_used=result.tokens_used,
        error=result.error,
    )
    return TaskResponse(
        task_id=str(task.id),
        agent_type=result.agent_type,
        status=result.status.value,
        progress=1.0,
        current_step="completed",
        result=result.result,
        report=result.report,
        sources=result.sources,
        error=result.error,
        timing={"elapsed_ms": round(result.elapsed_ms, 2), "retrieval_ms": round(result.retrieval_time_ms, 2), "llm_ms": round(result.llm_time_ms, 2)},
        tokens_used=result.tokens_used,
        created_at=task.created_at.isoformat(),
    )


@router.post("/pipeline", summary="Run multiple agents sequentially")
async def run_pipeline(
    body: RunPipelineRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """Run multiple agents in sequence for a comprehensive codebase audit."""
    from app.config import settings
    config = AgentConfig(
        project_id=str(body.project_id),
        user_id=str(current_user.id),
        query=body.query,
        model=body.model_name or settings.OLLAMA_DEFAULT_MODEL,
    )
    try:
        orchestrator = _get_orchestrator()
        results = await orchestrator.run_pipeline(
            agent_types=body.agent_types,
            config=config,
            stop_on_failure=body.stop_on_failure,
        )
    except Exception as exc:
        logger.error("Pipeline failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=503, detail=str(exc))
    return {
        "project_id": str(body.project_id),
        "agents_run": list(results.keys()),
        "results": {at: r.to_dict() for at, r in results.items()},
        "total_agents": len(results),
        "successful": sum(1 for r in results.values() if r.is_success),
    }


@router.get("/tasks/{task_id}", response_model=TaskResponse, summary="Get task status")
async def get_task(
    task_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> TaskResponse:
    """Get the status and result of a specific agent task."""
    task_repo = TaskRepository(db)
    task = await task_repo.get_task(task_id, current_user.id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskResponse(
        task_id=str(task.id),
        agent_type=task.agent_type,
        status=task.status,
        progress=task.progress,
        current_step=task.current_step,
        result=task.result,
        report=task.report,
        sources=task.sources,
        error=task.error_message,
        timing={"elapsed_ms": task.elapsed_ms, "retrieval_ms": task.retrieval_time_ms, "llm_ms": task.llm_time_ms} if task.elapsed_ms else None,
        tokens_used=task.tokens_used,
        created_at=task.created_at.isoformat(),
    )


@router.get("/tasks", summary="List agent tasks for a project")
async def list_tasks(
    project_id: UUID = Query(...),
    agent_type: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
) -> dict:
    """List recent agent tasks for a project."""
    task_repo = TaskRepository(db)
    tasks = await task_repo.list_tasks(
        project_id=project_id,
        user_id=current_user.id,
        limit=limit,
        agent_type=agent_type,
    )
    return {
        "tasks": [{"task_id": str(t.id), "agent_type": t.agent_type, "status": t.status, "progress": t.progress, "query": t.query, "elapsed_ms": t.elapsed_ms, "created_at": t.created_at.isoformat()} for t in tasks],
        "total": len(tasks),
    }
