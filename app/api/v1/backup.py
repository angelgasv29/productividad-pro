"""Exportación e importación de backups JSON."""

from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, File, UploadFile
from fastapi.responses import StreamingResponse

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.core.exceptions import BackupError
from app.schemas.analytics import ImportResultOut
from app.schemas.system import BackupSlotInfo, RestoreResponse
from app.services import backup_service

router = APIRouter(prefix="/backup", tags=["backup"])


@router.get("/export")
def export(user: CurrentUser, db: DbSession) -> StreamingResponse:
    payload = backup_service.export_payload(db, user)
    content = json.dumps(payload, ensure_ascii=False, indent=2)
    filename = f"ProductividadPro_{user.username}_{datetime.now().date().isoformat()}.json"
    return StreamingResponse(
        iter([content]),
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import", response_model=ImportResultOut)
async def import_backup(
    user: CurrentUser,
    db: DbSession,
    file: UploadFile = File(...),
) -> ImportResultOut:
    raw = await file.read()
    if len(raw) > settings.max_import_bytes:
        raise BackupError(
            f"El archivo supera el límite de {settings.max_import_bytes // (1024 * 1024)} MB."
        )
    try:
        text = raw.decode("utf-8-sig")
        payload = json.loads(text)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupError("El archivo no es un JSON UTF-8 válido.") from exc
    counts, version, warnings = backup_service.import_payload(db, user, payload)
    db.commit()
    return ImportResultOut(
        ok=True,
        imported=counts,
        source_schema_version=version,
        warnings=warnings,
        message="Importación completada. Tus datos anteriores fueron reemplazados.",
    )


@router.get("/slots", response_model=dict[str, BackupSlotInfo])
def slots(user: CurrentUser) -> dict[str, BackupSlotInfo]:
    return backup_service.backup_info(user)


@router.post("/restore/{slot}", response_model=RestoreResponse)
def restore(slot: str, user: CurrentUser, db: DbSession) -> RestoreResponse:
    counts, version, warnings = backup_service.restore_slot(db, user, slot)
    db.commit()
    return RestoreResponse(
        ok=True,
        slot=slot.upper(),
        message=f"Backup restaurado desde el slot {slot.upper()}.",
        imported=counts,
    )
