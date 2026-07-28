"""
Notification Celery Tasks - Step 31
AI Codebase Assistant v2.0

Async email delivery tasks via Celery.
All email sends go through Celery so the API never blocks on SMTP.

Task naming convention: send_{notification_type}_email
"""

from __future__ import annotations

import logging
from typing import Any

from app.tasks.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="app.tasks.notification_tasks.send_agent_complete_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=60,
    queue="high",
)
def send_agent_complete_email(
    self: Any,
    to_email: str,
    user_id: str,
    agent_display_name: str,
    file_path: str,
    quality_score: int | None,
    total_findings: int,
    critical_count: int,
    elapsed_seconds: float,
    project_id: str,
) -> dict[str, Any]:
    """
    Celery task: send agent analysis completion email.

    Retries up to 3 times on SMTP failures with 60-second delay.

    Args:
        self:               Celery task instance
        to_email:           Recipient email address
        user_id:            User UUID for rate limiting
        agent_display_name: Agent display name e.g. "Security Scanner"
        file_path:          Analyzed file path
        quality_score:      Code quality score or None
        total_findings:     Total findings count
        critical_count:     Critical severity count
        elapsed_seconds:    Analysis duration
        project_id:         Project UUID for URL generation

    Returns:
        Email send result dict
    """
    logger.info(
        "Sending agent complete email: to=%s agent=%s findings=%d",
        to_email, agent_display_name, total_findings,
    )
    try:
        from app.services.notification_service import notification_service
        result = notification_service.send_agent_complete(
            to_email=to_email,
            user_id=user_id,
            agent_display_name=agent_display_name,
            file_path=file_path,
            quality_score=quality_score,
            total_findings=total_findings,
            critical_count=critical_count,
            elapsed_seconds=elapsed_seconds,
            project_id=project_id,
        )
        return result
    except Exception as exc:
        logger.error("send_agent_complete_email failed: %s", exc)
        if "smtp" in str(exc).lower() or "connection" in str(exc).lower():
            raise self.retry(exc=exc, countdown=60)
        return {"success": False, "error": str(exc)}


@celery_app.task(
    name="app.tasks.notification_tasks.send_indexing_complete_email",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=60,
    queue="high",
)
def send_indexing_complete_email(
    self: Any,
    to_email: str,
    user_id: str,
    project_name: str,
    total_files: int,
    indexed_count: int,
    failed_count: int,
    total_chunks: int,
    elapsed_seconds: float,
    project_id: str,
) -> dict[str, Any]:
    """
    Celery task: send indexing completion email.

    Args:
        self:            Celery task instance
        to_email:        Recipient email
        user_id:         User UUID
        project_name:    Project display name
        total_files:     Total files processed
        indexed_count:   Successfully indexed
        failed_count:    Failed files
        total_chunks:    Chunks stored in ChromaDB
        elapsed_seconds: Indexing duration
        project_id:      Project UUID

    Returns:
        Email send result dict
    """
    logger.info(
        "Sending indexing complete email: to=%s project=%s files=%d",
        to_email, project_name, indexed_count,
    )
    try:
        from app.services.notification_service import notification_service
        return notification_service.send_indexing_complete(
            to_email=to_email,
            user_id=user_id,
            project_name=project_name,
            total_files=total_files,
            indexed_count=indexed_count,
            failed_count=failed_count,
            total_chunks=total_chunks,
            elapsed_seconds=elapsed_seconds,
            project_id=project_id,
        )
    except Exception as exc:
        logger.error("send_indexing_complete_email failed: %s", exc)
        if "smtp" in str(exc).lower() or "connection" in str(exc).lower():
            raise self.retry(exc=exc, countdown=60)
        return {"success": False, "error": str(exc)}


@celery_app.task(
    name="app.tasks.notification_tasks.send_security_alert_email",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    soft_time_limit=60,
    queue="high",
)
def send_security_alert_email(
    self: Any,
    to_email: str,
    user_id: str,
    file_path: str,
    critical_count: int,
    high_count: int,
    top_findings: list[dict[str, Any]],
    project_id: str,
) -> dict[str, Any]:
    """
    Celery task: send security vulnerability alert email.

    Only sends when critical_count > 0 or high_count >= 3.

    Args:
        self:          Celery task instance
        to_email:      Recipient email
        user_id:       User UUID
        file_path:     Scanned file path
        critical_count: CRITICAL severity count
        high_count:    HIGH severity count
        top_findings:  List of top finding dicts
        project_id:    Project UUID

    Returns:
        Email send result dict
    """
    logger.info(
        "Sending security alert: to=%s critical=%d high=%d",
        to_email, critical_count, high_count,
    )
    try:
        from app.services.notification_service import notification_service
        return notification_service.send_security_alert(
            to_email=to_email,
            user_id=user_id,
            file_path=file_path,
            critical_count=critical_count,
            high_count=high_count,
            top_findings=top_findings,
            project_id=project_id,
        )
    except Exception as exc:
        logger.error("send_security_alert_email failed: %s", exc)
        if "smtp" in str(exc).lower() or "connection" in str(exc).lower():
            raise self.retry(exc=exc, countdown=30)
        return {"success": False, "error": str(exc)}


@celery_app.task(
    name="app.tasks.notification_tasks.send_task_failed_email",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=60,
    queue="high",
)
def send_task_failed_email(
    self: Any,
    to_email: str,
    user_id: str,
    task_type: str,
    agent_id: str,
    error_message: str,
    project_id: str,
) -> dict[str, Any]:
    """
    Celery task: send task failure notification email.

    Args:
        self:          Celery task instance
        to_email:      Recipient email
        user_id:       User UUID
        task_type:     Human-readable task type
        agent_id:      Failed agent ID
        error_message: Error description
        project_id:    Project UUID

    Returns:
        Email send result dict
    """
    logger.info(
        "Sending task failed email: to=%s task=%s agent=%s",
        to_email, task_type, agent_id,
    )
    try:
        from app.services.notification_service import notification_service
        return notification_service.send_task_failed(
            to_email=to_email,
            user_id=user_id,
            task_type=task_type,
            agent_id=agent_id,
            error_message=error_message,
            project_id=project_id,
        )
    except Exception as exc:
        logger.error("send_task_failed_email failed: %s", exc)
        if "smtp" in str(exc).lower() or "connection" in str(exc).lower():
            raise self.retry(exc=exc, countdown=60)
        return {"success": False, "error": str(exc)}
