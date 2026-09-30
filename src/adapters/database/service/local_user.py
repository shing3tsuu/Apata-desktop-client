from uuid import UUID

from src.adapters.database.dto import (
    AddLocalUserDTO,
    LocalUserDTO,
    RequestLocalUserDTO,
)

from ..dao.common import AbstractCommonDAO, error_handler
from ..dao.local_user import AbstractLocalUserDAO


class LocalUserService:
    def __init__(
        self, local_user_dao: AbstractLocalUserDAO, common_dao: AbstractCommonDAO
    ):
        self._local_user_dao = local_user_dao
        self._common_dao = common_dao

    @error_handler
    async def add_user(self, user: AddLocalUserDTO) -> LocalUserDTO:
        result = await self._local_user_dao.add_user(user)
        await self._common_dao.commit()
        return result

    @error_handler
    async def get_user_by_id(self, user_id: UUID) -> LocalUserDTO | None:
        return await self._local_user_dao.get_user_data_by_id(user_id)

    @error_handler
    async def get_user_by_username(self, username: str) -> LocalUserDTO | None:
        return await self._local_user_dao.get_user_data_by_name(
            username=username
        )

    @error_handler
    async def get_users(self) -> list[LocalUserDTO]:
        return await self._local_user_dao.get_users()

    @error_handler
    async def update_user_data(
        self, user: RequestLocalUserDTO
    ) -> LocalUserDTO | None:
        result = await self._local_user_dao.update_user_data(user)
        if result is not None:
            await self._common_dao.commit()
        return result

    @error_handler
    async def delete_user(self, username: str) -> bool:
        result = await self._local_user_dao.delete_user(username)
        if result:
            await self._common_dao.commit()
        return result
