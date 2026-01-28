import logging

from ..dao.local_user import AbstractLocalUserDAO
from ..dao.common import AbstractCommonDAO, CommonDAO, error_handler
from src.adapters.database.dto import LocalUserDTO, LocalUserRequestDTO, UpdateLocalUserRequestDTO

class LocalUserService:
    def __init__(self, local_user_dao: AbstractLocalUserDAO, common_dao: AbstractCommonDAO, logger: logging.Logger):
        self._local_user_dao = local_user_dao
        self._common_dao = common_dao
        self._logger = logger

    @error_handler
    async def add_user(self, user: LocalUserRequestDTO) -> LocalUserDTO:
        result = await self._local_user_dao.add_user(user)
        return result

    @error_handler
    async def get_user_data(self, user: LocalUserRequestDTO) -> LocalUserDTO | None:
        return await self._local_user_dao.get_user_data(user)

    @error_handler
    async def update_user_data(self, user: UpdateLocalUserRequestDTO) -> LocalUserDTO | None:
        result = await self._local_user_dao.update_user_data(user)
        return result

    @error_handler
    async def delete_user(self, user: LocalUserRequestDTO) -> bool:
        result = await self._local_user_dao.delete_user(user)
        return result