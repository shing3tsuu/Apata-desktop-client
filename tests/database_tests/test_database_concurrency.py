from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.pool import StaticPool

from src.providers.app import (
    SQLITE_BUSY_TIMEOUT_MS,
    create_local_database_engine,
)


@pytest.mark.asyncio
async def test_file_database_allows_write_while_another_session_is_reading(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "concurrent-client.db"
    engine = create_local_database_engine(
        f"sqlite+aiosqlite:///{database_path.as_posix()}"
    )
    session_factory = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    try:
        assert not isinstance(engine.pool, StaticPool)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "CREATE TABLE concurrency_probe ("
                    "id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
                )
            )
            await connection.execute(
                text("INSERT INTO concurrency_probe (value) VALUES (:value)"),
                [{"value": f"seed-{index}"} for index in range(1_000)],
            )

        async with session_factory() as reader, session_factory() as writer:
            journal_mode = await reader.scalar(text("PRAGMA journal_mode"))
            busy_timeout = await reader.scalar(text("PRAGMA busy_timeout"))
            foreign_keys = await reader.scalar(text("PRAGMA foreign_keys"))
            assert str(journal_mode).lower() == "wal"
            assert busy_timeout == SQLITE_BUSY_TIMEOUT_MS
            assert foreign_keys == 1

            streaming_result = await reader.stream(
                text("SELECT id, value FROM concurrency_probe ORDER BY id")
            )
            first_row = await streaming_result.fetchone()
            assert first_row is not None

            await writer.execute(
                text("INSERT INTO concurrency_probe (value) VALUES (:value)"),
                {"value": "written-during-read"},
            )
            await writer.commit()
            await streaming_result.close()

        async with session_factory() as verification_session:
            saved = await verification_session.scalar(
                text("SELECT COUNT(*) FROM concurrency_probe WHERE value = :value"),
                {"value": "written-during-read"},
            )
            assert saved == 1
    finally:
        await engine.dispose()
