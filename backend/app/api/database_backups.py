from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.background import BackgroundTask
from starlette.responses import FileResponse

from backend.app.api.auth import current_user_dependency
from backend.app.core.config import settings
from backend.app.db.session import get_session
from backend.app.models.auth import AppUser
from backend.app.services.auth_service import get_current_user_from_token
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


async def _restore_user_id_dependency(
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> int:
    user = await get_current_user_from_token(
        session,
        request.cookies.get(settings.session_cookie_name),
    )
    if user is None:
        raise HTTPException(status_code=401, detail="not_authenticated")

    user_id = user.id
    # 恢复会覆盖全库；认证阶段的连接必须先释放，避免 pg_restore 清理对象时被当前请求占用。
    await session.close()
    return user_id


@router.post("/restore")
async def restore_database_backup_route(
    request: Request,
    user_id: int = Depends(_restore_user_id_dependency),
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
                user_id=user_id,
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
