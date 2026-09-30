from collections.abc import AsyncIterator

from dishka import Provider, Scope, provide
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    create_async_engine,
)

from src.adapters.database.structures import Base


class MockDBProvider(Provider):
    @provide(scope=Scope.APP, override=True)
    async def session(self) -> AsyncIterator[AsyncSession]:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            echo=False,
            connect_args={"check_same_thread": False},
        )

        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async with engine.connect() as connection:
                await connection.begin()

                session = AsyncSession(
                    bind=connection,
                    expire_on_commit=False,
                    autoflush=False,
                )

                savepoint = await session.begin_nested()

                try:
                    yield session
                finally:
                    if savepoint.is_active:
                        await savepoint.rollback()
                    await session.close()
                    await connection.rollback()
        finally:
            await engine.dispose()