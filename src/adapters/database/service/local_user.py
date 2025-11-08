import logging

from ..dao.local_user import AbstractLocalUserDAO
from ..dao.common import AbstractCommonDAO
from src.adapters.database.dto import LocalUserDTO, LocalUserRequestDTO

class LocalUserService:
    __slots__ = (
        "_local_user_dao",
        "_common_dao",
        "_logger",
        "__weakref__"
    )
    def __init__(self, local_user_dao: AbstractLocalUserDAO, common_dao: AbstractCommonDAO, logger: logging.Logger):
        self._local_user_dao = local_user_dao
        self._common_dao = common_dao
        self._logger = logger

    async def add_user(self, user: LocalUserRequestDTO) -> LocalUserDTO:
        try:
            result = await self._local_user_dao.add_user(user)
            await self._common_dao.commit()
            return result
        except Exception as e:
            self._logger.error(f"Error adding local user: {e}")
            await self._common_dao.rollback()
            raise

    async def get_user_data(self, user: LocalUserRequestDTO) -> LocalUserDTO | None:
        try:
            return await self._local_user_dao.get_user_data(user)
        except Exception as e:
            self._logger.error(f"Error getting local user data: {e}")
            return None

    async def update_user_data(self, user: LocalUserRequestDTO) -> LocalUserDTO | None:
        try:
            result = await self._local_user_dao.update_user_data(user)
            await self._common_dao.commit()
            return result
        except Exception as e:
            self._logger.error(f"Error updating local user data: {e}")
            await self._common_dao.rollback()
            return None

    async def delete_user(self, user: LocalUserRequestDTO) -> bool:
        try:
            result = await self._local_user_dao.delete_user(user)
            await self._common_dao.commit()
            return result
        except Exception as e:
            self._logger.error(f"Error deleting local user: {e}")
            await self._common_dao.rollback()
            return False