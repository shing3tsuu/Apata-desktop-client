import logging

from ..dao.contact import AbstractContactDAO
from ..dao.common import AbstractCommonDAO
from src.adapters.database.dto import ContactDTO, ContactRequestDTO

class ContactService:
    __slots__ = (
        "_contact_dao",
        "_common_dao",
        "_logger",
        "__weakref__"
    )
    def __init__(self, contact_dao: AbstractContactDAO, common_dao: AbstractCommonDAO, logger: logging.Logger):
        self._contact_dao = contact_dao
        self._common_dao = common_dao
        self._logger = logger

    async def add_contact(self, contact: ContactRequestDTO) -> ContactDTO:
        try:
            result = await self._contact_dao.add_contact(contact)
            await self._common_dao.commit()
            return result
        except Exception as e:
            self._logger.error(f"Error adding contact: {e}")
            await self._common_dao.rollback()
            raise

    async def get_contact(
            self,
            local_user_id: int,
            contact_id: int | None = None,
            username: str | None = None
    ) -> ContactDTO | None:
        try:
            if contact_id:
                return await self._contact_dao.get_contact(
                    local_user_id=local_user_id,
                    contact_id=contact_id
                )
            if username:
                return await self._contact_dao.get_contact(
                    local_user_id=local_user_id,
                    username=username
                )
        except Exception as e:
            self._logger.error(f"Error getting contact: {e}")
            return None

    async def get_contacts(self, local_user_id: int) -> list[ContactDTO]:
        try:
            return await self._contact_dao.get_contacts(local_user_id)
        except Exception as e:
            self._logger.error(f"Error getting contacts: {e}")
            return []

    async def update_contact(self, contact: ContactRequestDTO) -> ContactDTO | None:
        try:
            result = await self._contact_dao.update_contact(contact)
            await self._common_dao.commit()
            return result
        except Exception as e:
            self._logger.error(f"Error updating contact: {e}")
            await self._common_dao.rollback()
            return None

    async def delete_contact(self, contact_id: int | None = None) -> bool:
        try:
            result = await self._contact_dao.delete_contact(contact_id=contact_id)
            await self._common_dao.commit()
            return result
        except Exception as e:
            self._logger.error(f"Error deleting contact: {e}")
            await self._common_dao.rollback()
            return False