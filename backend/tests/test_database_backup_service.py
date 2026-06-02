from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.core.config import settings
from backend.app.services import database_backup_service
from backend.app.services.database_backup_service import (
    BackupRestoreBusyError,
    InvalidBackupFileError,
    create_database_backup,
    restore_database_backup,
)


def test_postgres_url_from_asyncpg_url_keeps_credentials() -> None:
    converted = database_backup_service.postgres_tool_url(
        "postgresql+asyncpg://learning_coach:secret@postgres:5432/learning_coach"
    )

    assert converted == "postgresql://learning_coach:secret@postgres:5432/learning_coach"


@pytest.mark.asyncio
async def test_create_database_backup_runs_pg_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commands: list[list[str]] = []

    async def fake_run_pg_command(args: list[str]) -> None:
        commands.append(args)
        Path(args[args.index("--file") + 1]).write_bytes(b"PGDMP exported")

    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql+asyncpg://learning_coach:secret@postgres:5432/learning_coach",
    )
    monkeypatch.setattr(database_backup_service, "_run_pg_command", fake_run_pg_command)

    backup = await create_database_backup(user_id=7)

    assert backup.filename.startswith("learning-coach-db-")
    assert backup.filename.endswith(".dump")
    assert backup.path.read_bytes() == b"PGDMP exported"
    assert backup.size_bytes == len(b"PGDMP exported")
    assert commands == [
        [
            "pg_dump",
            "--format=custom",
            "--compress=9",
            "--no-owner",
            "--no-privileges",
            "--file",
            str(backup.path),
            "postgresql://learning_coach:secret@postgres:5432/learning_coach",
        ]
    ]
    backup.path.unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_restore_database_backup_validates_then_runs_pg_restore(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    commands: list[list[str]] = []
    backup_path = tmp_path / "backup.dump"
    backup_path.write_bytes(b"PGDMP valid archive")

    async def fake_run_pg_command(args: list[str]) -> None:
        commands.append(args)

    monkeypatch.setattr(
        settings,
        "database_url",
        "postgresql+asyncpg://learning_coach:secret@postgres:5432/learning_coach",
    )
    monkeypatch.setattr(database_backup_service, "_run_pg_command", fake_run_pg_command)

    result = await restore_database_backup(backup_path=backup_path, user_id=7)

    assert result.status == "ok"
    assert result.file_size_bytes == len(b"PGDMP valid archive")
    assert commands == [
        ["pg_restore", "--list", str(backup_path)],
        [
            "pg_restore",
            "--clean",
            "--if-exists",
            "--no-owner",
            "--no-privileges",
            "--single-transaction",
            "--exit-on-error",
            "--dbname",
            "postgresql://learning_coach:secret@postgres:5432/learning_coach",
            str(backup_path),
        ],
    ]


@pytest.mark.asyncio
async def test_restore_database_backup_rejects_non_custom_dump(
    tmp_path: Path,
) -> None:
    backup_path = tmp_path / "backup.dump"
    backup_path.write_bytes(b"not a postgres dump")

    with pytest.raises(InvalidBackupFileError):
        await restore_database_backup(backup_path=backup_path, user_id=7)


@pytest.mark.asyncio
async def test_create_database_backup_rejects_concurrent_operation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lock = database_backup_service.operation_lock()
    await lock.acquire()
    try:
        with pytest.raises(BackupRestoreBusyError):
            await create_database_backup(user_id=7)
    finally:
        lock.release()
