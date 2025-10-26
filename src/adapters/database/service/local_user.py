from ..dao.local_user import AbstractLocalUserDAO
from ..dao.common import AbstractCommonDAO
from src.adapters.database.dto import LocalUserDTO, LocalUserRequestDTO

class LocalUserService:
    def __init__(self, local_user_dao: AbstractLocalUserDAO, common_dao: AbstractCommonDAO):
        self._local_user_dao = local_user_dao
        self._common_dao = common_dao

    async def add_user(self, user: LocalUserRequestDTO) -> LocalUserDTO:
        result = await self._local_user_dao.add_user(user)
        await self._common_dao.commit()
        return result

    async def get_user_data(self, user: LocalUserRequestDTO) -> LocalUserDTO | None:
        return await self._local_user_dao.get_user_data(user)

    async def update_user_data(self, user: LocalUserDTO) -> LocalUserDTO | None:
        result = await self._local_user_dao.update_user_data(user)
        await self._common_dao.commit()
        return result