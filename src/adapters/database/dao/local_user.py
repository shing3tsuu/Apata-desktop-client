from abc import ABC, abstractmethod
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database.dto import (
    LocalUserDTO,
    AddLocalUserDTO,
    RequestLocalUserDTO,
)
from src.adapters.database.structures import LocalUser
from src.exceptions import UserAlreadyExistsError, UserNotFoundError


class AbstractLocalUserDAO(ABC):
    @abstractmethod
    async def add_user(self, user: AddLocalUserDTO) -> LocalUserDTO:
        raise NotImplementedError()

    @abstractmethod
    async def get_user_data_by_id(self, user_id: UUID) -> LocalUserDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_user_data_by_name(self, username: str) -> LocalUserDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_users(self) -> list[LocalUserDTO]:
        raise NotImplementedError()

    @abstractmethod
    async def update_user_data(
        self, user: RequestLocalUserDTO
    ) -> LocalUserDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_user(self, username: str) -> bool:
        raise NotImplementedError()


class LocalUserDAO(AbstractLocalUserDAO):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_user(self, user: AddLocalUserDTO) -> LocalUserDTO:
        existing_user = await self._session.scalar(
            select(LocalUser).where(LocalUser.username == user.username)
        )
        if existing_user:
            raise UserAlreadyExistsError("Local user already exists")

        stmt = insert(LocalUser).values(**user.model_dump()).returning(LocalUser)
        result = await self._session.scalar(stmt)

        return LocalUserDTO.model_validate(result, from_attributes=True)

    async def get_user_data_by_id(self, user_id: UUID) -> LocalUserDTO | None:
        stmt = select(LocalUser).where(LocalUser.id == user_id)
        result = await self._session.scalar(stmt)
        if not result:
            raise UserNotFoundError("Local user not found")
        return LocalUserDTO.model_validate(result, from_attributes=True)

    async def get_user_data_by_name(self, username: str) -> LocalUserDTO | None:
        stmt = select(LocalUser).where(LocalUser.username == username)
        result = await self._session.scalar(stmt)
        if not result:
            return None
        return LocalUserDTO.model_validate(result, from_attributes=True)

    async def get_users(self) -> list[LocalUserDTO]:
        stmt = select(LocalUser).order_by(LocalUser.username)
        result = await self._session.scalars(stmt)
        return [
            LocalUserDTO.model_validate(user, from_attributes=True)
            for user in result
        ]

    async def update_user_data(
            self, user: RequestLocalUserDTO
    ) -> LocalUserDTO | None:
        data = user.model_dump(exclude_unset=True)
        data.pop("id", None)

        stmt = (
            update(LocalUser)
            .where(LocalUser.id == user.id)
            .values(**data)
            .returning(LocalUser)
        )
        result = await self._session.scalar(stmt)
        return LocalUserDTO.model_validate(result, from_attributes=True) if result else None

    async def delete_user(self, username: str) -> bool:
        stmt = delete(LocalUser).where(LocalUser.username == username)
        result = await self._session.execute(stmt)
        if result.rowcount > 0:
            return True
        else:
            return False
