"""Utilidades compartidas por los modelos ORM."""

from __future__ import annotations

import uuid
from datetime import datetime


def new_uuid() -> str:
    return str(uuid.uuid4())


def now_local() -> datetime:
    return datetime.now()
