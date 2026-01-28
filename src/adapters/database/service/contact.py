import logging
from pydantic import ValidationError

from ..dao.contact import AbstractContactDAO
from ..dao.common import AbstractCommonDAO, CommonDAO, error_handler

from src.adapters.database.dto import ContactRequestDTO, ContactDTO, AddContactRequestDTO, UpdateContactRequestDTO

class ContactService:
    def __init__(self, contact_dao: AbstractContactDAO, common_dao: AbstractCommonDAO, logger: logging.Logger):
        self._contact_dao = contact_dao
        self._common_dao = common_dao
        self._logger = logger

    @error_handler
    async def add_contact(self, contact: AddContactRequestDTO) -> ContactDTO:
        existing_contact = await self._contact_dao.get_contact(
            local_user_id=contact.local_user_id,
            contact_id=contact.contact_id
        )
        if existing_contact:
            return existing_contact
        else:
            result = await self._contact_dao.add_contact(contact)
            return result

    @error_handler
    async def get_contact(
            self,
            local_user_id: int,
            contact_id: int | None = None,
            username: str | None = None
    ) -> ContactDTO | None:
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

    @error_handler
    async def get_contacts(self, local_user_id: int) -> list[ContactDTO]:
        return await self._contact_dao.get_contacts(local_user_id)

    @error_handler
    async def update_contact(self, contact: UpdateContactRequestDTO) -> ContactDTO | None:
        result = await self._contact_dao.update_contact(contact)
        return result

    @error_handler
    async def delete_contact(self, contact_id: int | None = None) -> bool:
        result = await self._contact_dao.delete_contact(contact_id=contact_id)
        return result