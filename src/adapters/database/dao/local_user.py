from abc import ABC, abstractmethod
import logging

from sqlalchemy import select, delete, insert, update, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database.dto import LocalUserRequestDTO, LocalUserDTO
from src.adapters.database.structures import LocalUser

from src.exceptions import UserAlreadyExistsError, UserNotRegisteredError

class AbstractLocalUserDAO(ABC):
    @abstractmethod
    async def add_user(self, user: LocalUserRequestDTO) -> LocalUserDTO:
        raise NotImplementedError()

    @abstractmethod
    async def get_user_data(self, user: LocalUserRequestDTO) -> LocalUserDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def update_user_data(self, user: LocalUserDTO) -> LocalUserDTO | None:
        raise NotImplementedError()

class LocalUserDAO(AbstractLocalUserDAO):
    __slots__ = ("_session", "_logger")

    def __init__(self, session: AsyncSession, logger: logging.Logger | None = None):
        self._session = session
        self._logger = logger or logging.getLogger(__name__)

    async def add_user(self, user: LocalUserRequestDTO) -> LocalUserDTO:
        try:
            existing_user = await self._session.scalar(select(LocalUser).where(LocalUser.username == user.username))
            if existing_user:
                raise UserAlreadyExistsError("Local user already exists")

            stmt = (
                insert(LocalUser)
                .values(**user.model_dump())
                .returning(LocalUser)
            )
            result = await self._session.scalar(stmt)

            return LocalUserDTO.model_validate(result, from_attributes=True)

        except SQLAlchemyError as e:
            self._logger.error(f"Error adding user in database: {e}")
            return None

    async def get_user_data(self, user: LocalUserRequestDTO) -> LocalUserDTO | None:
        try:
            stmt = select(LocalUser).where(LocalUser.username == user.username)
            result = await self._session.scalar(stmt)
            if not result:
                return None

            return LocalUserDTO.model_validate(result, from_attributes=True)

        except SQLAlchemyError as e:
            self._logger.error(f"Error fetching user data in database: {e}")

    async def update_user_data(self, user: LocalUserRequestDTO) -> LocalUserDTO | None:
        try:
            stmt = (
                update(LocalUser)
                .where(LocalUser.username == user.username)
                .values(**user.model_dump(exclude_unset=True))
                .returning(LocalUser)
            )
            result = await self._session.scalar(stmt)

            return LocalUserDTO.model_validate(result, from_attributes=True)

        except Exception as e:
            self._logger.error("Error updating user data in database: %s", e)
            return None