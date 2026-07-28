"""
Models package — exports all SQLAlchemy ORM models.

Import from here to ensure all models are registered
with SQLAlchemy metadata before Alembic runs migrations.

Usage:
    from app.models import User, Project, ProjectFile, ChatSession, ChatMessage, Task
"""

from app.models.chat import ChatMessage, ChatSession
from app.models.file import ProjectFile
from app.models.project import Project
from app.models.task import Task
from app.models.user import User

__all__ = [
    "User",
    "Project",
    "ProjectFile",
    "ChatSession",
    "ChatMessage",
    "Task",
]
