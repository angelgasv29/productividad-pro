"""DTOs comunes."""

from __future__ import annotations

from pydantic import BaseModel


class MessageResponse(BaseModel):
    message: str
    ok: bool = True
