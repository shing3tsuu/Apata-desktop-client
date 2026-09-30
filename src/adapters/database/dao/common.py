from abc import ABC, abstractmethod
from functools import wraps
from typing import Awaitable, Callable, TypeVar

from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.exceptions import DatabaseError

T = TypeVar("T")


class AbstractCommonDAO(ABC):
    @abstractmethod
    async def flush(self) -> None:
        raise NotImplementedError()

    @abstractmethod
    async def commit(self):
        raise NotImplementedError()

    @abstractmethod
    async def rollback(self):
        raise NotImplementedError()


class CommonDAO(AbstractCommonDAO):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def flush(self) -> None:
        await self._session.flush()

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()


def error_handler(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
    @wraps(func)
    async def wrapper(self, *args, **kwargs) -> T:
        try:
            result = await func(self, *args, **kwargs)
            await self._common_dao.commit()
            return result
        except (SQLAlchemyError, IntegrityError) as e:
            print(e)
            raise DatabaseError(
                f"SQLAlchemy error in database in method: {func.__name__}",
                original_error=e,
            )

    return wrapper
