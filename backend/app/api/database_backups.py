from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from backend.app.api.auth import current_user_dependency
from backend.app.core.config import settings
from backend.app.models.auth import AppUser
from backend.app.services.database_backup_service import (
    BackupRestoreBusyError,
    DatabaseBackupError,
    InvalidBackupFileError,
    create_database_backup,
    restore_database_backup,
)


router = APIRouter(prefix="/database-backups", tags=["database-backups"])


@router.get("/export")
async def export_database_backup_route(
    user: AppUser = Depends(current_user_dependency),
) -> FileResponse:
    try:
        backup = await create_database_backup(user_id=user.id)
    except BackupRestoreBusyError as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except DatabaseBackupError as exc:
        raise HTTPException(status_code=500, detail=exc.detail) from exc
    return FileResponse(
        backup.path,
        filename=backup.filename,
        media_type="application/octet-stream",
        background=BackgroundTask(_cleanup_backup_file, backup.path),
    )


@router.post("/restore")
async def restore_database_backup_route(
    request: Request,
    user: AppUser = Depends(current_user_dependency),
) -> dict[str, object]:
    body = await request.body()
    if len(body) > settings.database_backup_max_bytes:
        raise HTTPException(status_code=413, detail="backup_file_too_large")

    backup_path = _create_temp_restore_path()
    try:
        backup_path.write_bytes(body)
        try:
            result = await restore_database_backup(
                backup_path=backup_path,
                user_id=user.id,
            )
        except InvalidBackupFileError as exc:
            raise HTTPException(status_code=400, detail=exc.detail) from exc
        except BackupRestoreBusyError as exc:
            raise HTTPException(status_code=409, detail=exc.detail) from exc
        except DatabaseBackupError as exc:
            raise HTTPException(status_code=500, detail=exc.detail) from exc
        return {
            "status": result.status,
            "restored_at": _format_utc_datetime(result.restored_at),
            "file_size_bytes": result.file_size_bytes,
        }
    finally:
        backup_path.unlink(missing_ok=True)


def _cleanup_backup_file(path: Path) -> None:
    path.unlink(missing_ok=True)


def _create_temp_restore_path() -> Path:
    handle = tempfile.NamedTemporaryFile(
        prefix="learning-coach-restore-",
        suffix=".dump",
        delete=False,
    )
    handle.close()
    return Path(handle.name)


def _format_utc_datetime(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
