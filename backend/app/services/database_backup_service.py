from __future__ import annotations

import asyncio
import logging
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from backend.app.core.config import settings
from backend.app.db.session import engine


logger = logging.getLogger(__name__)
_operation_lock = asyncio.Lock()


class DatabaseBackupError(RuntimeError):
    detail = "backup_operation_failed"


class BackupRestoreBusyError(DatabaseBackupError):
    detail = "backup_restore_busy"


class InvalidBackupFileError(DatabaseBackupError):
    detail = "invalid_backup_file"


class BackupExportError(DatabaseBackupError):
    detail = "backup_export_failed"


class BackupRestoreError(DatabaseBackupError):
    detail = "backup_restore_failed"


class PgCommandError(DatabaseBackupError):
    def __init__(self, command: str, stderr: str) -> None:
        super().__init__(stderr)
        self.command = command
        self.stderr = stderr


@dataclass(frozen=True)
class DatabaseBackupExport:
    path: Path
    filename: str
    size_bytes: int
    created_at: datetime


@dataclass(frozen=True)
class DatabaseBackupRestoreResult:
    status: str
    restored_at: datetime
    file_size_bytes: int


def operation_lock() -> asyncio.Lock:
    return _operation_lock


def postgres_tool_url(database_url: str) -> str:
    return database_url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def create_database_backup(*, user_id: int) -> DatabaseBackupExport:
    if _operation_lock.locked():
        logger.warning("database backup rejected operation=export user_id=%s reason=busy", user_id)
        raise BackupRestoreBusyError("database backup or restore already running")

    await _operation_lock.acquire()
    try:
        created_at = datetime.now(UTC)
        backup_path = _new_export_path(created_at)
        command = [
            "pg_dump",
            "--format=custom",
            "--compress=9",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(backup_path),
            postgres_tool_url(settings.database_url),
        ]
        logger.info("database backup started operation=export user_id=%s", user_id)
        try:
            await _run_pg_command(command)
        except PgCommandError as exc:
            backup_path.unlink(missing_ok=True)
            logger.warning(
                "database backup failed operation=export user_id=%s command=%s stderr=%s",
                user_id,
                exc.command,
                _safe_error_summary(exc.stderr),
            )
            raise BackupExportError("pg_dump failed") from exc

        size_bytes = backup_path.stat().st_size
        logger.info(
            "database backup completed operation=export user_id=%s size_bytes=%s",
            user_id,
            size_bytes,
        )
        return DatabaseBackupExport(
            path=backup_path,
            filename=backup_path.name,
            size_bytes=size_bytes,
            created_at=created_at,
        )
    finally:
        _operation_lock.release()


async def restore_database_backup(
    *,
    backup_path: Path,
    user_id: int,
) -> DatabaseBackupRestoreResult:
    if _operation_lock.locked():
        logger.warning("database backup rejected operation=restore user_id=%s reason=busy", user_id)
        raise BackupRestoreBusyError("database backup or restore already running")

    await _operation_lock.acquire()
    try:
        file_size_bytes = backup_path.stat().st_size
        if backup_path.read_bytes()[:5] != b"PGDMP":
            logger.warning(
                "database backup rejected operation=restore user_id=%s reason=invalid_header size_bytes=%s",
                user_id,
                file_size_bytes,
            )
            raise InvalidBackupFileError("backup file is not a PostgreSQL custom dump")

        logger.info(
            "database backup started operation=restore user_id=%s size_bytes=%s",
            user_id,
            file_size_bytes,
        )
        try:
            await _run_pg_command(["pg_restore", "--list", str(backup_path)])
        except PgCommandError as exc:
            logger.warning(
                "database backup rejected operation=restore user_id=%s reason=invalid_archive stderr=%s",
                user_id,
                _safe_error_summary(exc.stderr),
            )
            raise InvalidBackupFileError("pg_restore could not list archive") from exc

        # 恢复会重建全库对象，先释放应用连接池，避免旧连接持有事务或锁影响 pg_restore。
        await engine.dispose()
        command = [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "--single-transaction",
            "--exit-on-error",
            "--dbname",
            postgres_tool_url(settings.database_url),
            str(backup_path),
        ]
        try:
            await _run_pg_command(command)
        except PgCommandError as exc:
            logger.warning(
                "database backup failed operation=restore user_id=%s command=%s stderr=%s",
                user_id,
                exc.command,
                _safe_error_summary(exc.stderr),
            )
            raise BackupRestoreError("pg_restore failed") from exc

        restored_at = datetime.now(UTC)
        logger.info(
            "database backup completed operation=restore user_id=%s size_bytes=%s",
            user_id,
            file_size_bytes,
        )
        return DatabaseBackupRestoreResult(
            status="ok",
            restored_at=restored_at,
            file_size_bytes=file_size_bytes,
        )
    finally:
        _operation_lock.release()


def _new_export_path(created_at: datetime) -> Path:
    timestamp = created_at.strftime("%Y%m%d-%H%M%S")
    handle = tempfile.NamedTemporaryFile(
        prefix=f"learning-coach-db-{timestamp}-",
        suffix=".dump",
        delete=False,
    )
    handle.close()
    return Path(handle.name)


async def _run_pg_command(args: list[str]) -> None:
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise PgCommandError(args[0], stderr.decode(errors="replace"))


def _safe_error_summary(value: str) -> str:
    compact = " ".join(value.split())
    if len(compact) > 300:
        return compact[:300] + "..."
    return compact
