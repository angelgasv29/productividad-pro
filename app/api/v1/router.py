"""Agregador de routers de la API v1."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import (
    achievements,
    analytics,
    auth,
    backup,
    exceptions,
    nodes,
    objectives,
    schedule,
    system,
    timer,
    users,
    workspaces,
)

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(workspaces.router)
api_router.include_router(nodes.router)
api_router.include_router(schedule.router)
api_router.include_router(timer.router)
api_router.include_router(exceptions.router)
api_router.include_router(objectives.router)
api_router.include_router(achievements.router)
api_router.include_router(analytics.router)
api_router.include_router(system.router)
api_router.include_router(backup.router)
