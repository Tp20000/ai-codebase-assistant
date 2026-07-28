"""Task repository for agent execution tracking."""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID
from sqlalchemy import select, update, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.task import Task
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class TaskRepository(BaseRepository[Task]):
    """Repository for Task database operations."""

    def __init__(self, db: AsyncSession) -> None:
        super().__init__(Task, db)

    async def create_task(
        self,
        project_id: UUID,
        user_id: UUID,
        agent_type: str,
        query: str = "",
        config: Optional[dict] = None,
    ) -> Task:
        """Create a new pending agent task."""
        task = Task(
            project_id=project_id,
            user_id=user_id,
            agent_type=agent_type,
            task_type="agent",
            task_name=f"Agent: {agent_type}",
            status="pending",
            progress=0.0,
            query=query,
            config=config or {},
            input_params={"query": query, "agent_type": agent_type},
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        logger.info("Task created: %s [%s]", task.id, agent_type)
        return task

    async def update_status(
        self,
        task_id: UUID,
        status: str,
        progress: float = 0.0,
        current_step: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> None:
        """Update task execution status and progress."""
        values = {"status": status, "progress": progress}
        if current_step:
            values["current_step"] = current_step
            values["status_message"] = current_step
        if error_message:
            values["error_message"] = error_message
        if status == "running":
            values["started_at"] = datetime.now(timezone.utc)
        await self.db.execute(update(Task).where(Task.id == task_id).values(**values))
        await self.db.commit()

    async def complete_task(
        self,
        task_id: UUID,
        result: Optional[dict],
        report: Optional[str],
        sources: Optional[list],
        elapsed_ms: float,
        retrieval_time_ms: float,
        llm_time_ms: float,
        tokens_used: int,
        error: Optional[str] = None,
    ) -> None:
        """Mark a task as completed with full result data."""
        status = "failed" if error else "completed"
        await self.db.execute(
            update(Task).where(Task.id == task_id).values(
                status=status,
                progress=1.0,
                result=result,
                report=report,
                sources=sources or [],
                elapsed_ms=elapsed_ms,
                retrieval_time_ms=retrieval_time_ms,
                llm_time_ms=llm_time_ms,
                tokens_used=tokens_used,
                error_message=error,
                completed_at=datetime.now(timezone.utc),
                current_step="completed" if not error else "failed",
            )
        )
        await self.db.commit()
        logger.info("Task completed: %s status=%s", task_id, status)

    async def get_task(self, task_id: UUID, user_id: UUID) -> Optional[Task]:
        """Get a task by ID with ownership check."""
        result = await self.db.execute(
            select(Task).where(Task.id == task_id, Task.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_tasks(
        self,
        project_id: UUID,
        user_id: UUID,
        limit: int = 20,
        agent_type: Optional[str] = None,
    ) -> list[Task]:
        """List recent tasks for a project."""
        conditions = [Task.project_id == project_id, Task.user_id == user_id]
        if agent_type:
            conditions.append(Task.agent_type == agent_type)
        result = await self.db.execute(
            select(Task).where(*conditions).order_by(desc(Task.created_at)).limit(limit)
        )
        return list(result.scalars().all())
