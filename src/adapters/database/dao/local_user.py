from abc import ABC, abstractmethod
import logging

from sqlalchemy import select, delete, insert, update, func
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database.dto import LocalUserRequestDTO, LocalUserDTO, UpdateLocalUserRequestDTO
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
    async def update_user_data(self, user: UpdateLocalUserRequestDTO) -> LocalUserDTO | None:
        raise NotImplementedError()

class LocalUserDAO(AbstractLocalUserDAO):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_user(self, user: LocalUserRequestDTO) -> LocalUserDTO:
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

    async def get_user_data(self, user: LocalUserRequestDTO) -> LocalUserDTO | None:
        stmt = select(LocalUser).where(LocalUser.username == user.username)
        result = await self._session.scalar(stmt)
        if not result:
            return None
        return LocalUserDTO.model_validate(result, from_attributes=True)

    async def update_user_data(self, user: UpdateLocalUserRequestDTO) -> LocalUserDTO | None:
        stmt = (
            update(LocalUser)
            .where(LocalUser.username == user.username)
            .values(**user.model_dump(exclude_unset=True))
            .returning(LocalUser)
        )
        result = await self._session.scalar(stmt)
        return LocalUserDTO.model_validate(result, from_attributes=True)

    async def delete_user(self, user: LocalUserRequestDTO) -> bool:
        stmt = delete(LocalUser).where(LocalUser.username == user.username)
        result = await self._session.execute(stmt)
        if result.rowcount > 0:
            return True
        else:
            return False