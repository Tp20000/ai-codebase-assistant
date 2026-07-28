"""
Tasks Package - AI Codebase Assistant v2.0

Exports Celery app and all task functions.
"""

from app.tasks.celery_app import celery_app
from app.tasks.agent_tasks import (
    get_task_progress,
    run_agent_task,
    run_orchestration_task,
)
from app.tasks.indexing_tasks import (
    get_indexing_progress,
    index_project_files,
    reindex_single_file,
)
from app.tasks.notification_tasks import (
    send_agent_complete_email,
    send_indexing_complete_email,
    send_security_alert_email,
    send_task_failed_email,
)

__all__ = [
    "celery_app",
    "run_agent_task",
    "run_orchestration_task",
    "get_task_progress",
    "index_project_files",
    "reindex_single_file",
    "get_indexing_progress",
    "send_agent_complete_email",
    "send_indexing_complete_email",
    "send_security_alert_email",
    "send_task_failed_email",
]
