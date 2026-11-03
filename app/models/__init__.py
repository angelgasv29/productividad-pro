"""Registro central de modelos ORM (importar activa el metadata de Alembic)."""

from app.models.achievement import Achievement
from app.models.exception_log import TimeException
from app.models.history import DailyActivitySnapshot, DailyScoreHistory
from app.models.objective import Objective, ObjectiveHistorySnapshot, ObjectiveTaskLink
from app.models.schedule import DailyScheduleSlot, ScheduleSkip
from app.models.task_node import TaskNode
from app.models.timer import ActiveTimerState, TimerSession
from app.models.user import User, UserPreferences
from app.models.workspace import Workspace

__all__ = [
    "Achievement",
    "ActiveTimerState",
    "DailyActivitySnapshot",
    "DailyScheduleSlot",
    "DailyScoreHistory",
    "Objective",
    "ObjectiveHistorySnapshot",
    "ObjectiveTaskLink",
    "ScheduleSkip",
    "TaskNode",
    "TimeException",
    "TimerSession",
    "User",
    "UserPreferences",
    "Workspace",
]
