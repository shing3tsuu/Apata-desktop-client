from datetime import datetime, UTC
import logging
from uuid import UUID

from src.adapters.database.dto import (
    AddContactDTO,
    ContactDTO,
    RequestContactDTO,
)
from src.adapters.database.structures import ContactStatusEnum
from src.exceptions import ContactAlreadyExistsError, ContactNotFoundError

from ..dao.common import AbstractCommonDAO, error_handler
from ..dao.contact import AbstractContactDAO


class ContactService:
    def __init__(
        self,
        contact_dao: AbstractContactDAO,
        common_dao: AbstractCommonDAO,
        logger: logging.Logger,
    ):
        self._contact_dao = contact_dao
        self._common_dao = common_dao
        self._logger = logger

    @error_handler
    async def add_contact(self, contact: AddContactDTO) -> ContactDTO:
        existing = await self._contact_dao.get_contact(
            local_user_id=contact.local_user_id,
            contact_id=contact.server_user_id,
        )
        if existing:
            raise ContactAlreadyExistsError("Contact already exists")
        if contact.status is None:
            contact.status = ContactStatusEnum.BLANK
        if contact.last_seen is None:
            contact = contact.model_copy(update={"last_seen": datetime.now(UTC)})
        if contact.online is None:
            contact = contact.model_copy(update={"online": False})
        return await self._contact_dao.add_contact(contact)

    @error_handler
    async def get_contact_by_id(self, contact_id: UUID) -> ContactDTO:
        result = await self._contact_dao.get_contact_by_id(contact_id)
        if not result:
            raise ContactNotFoundError(f"Contact with id {contact_id} not found")
        return result

    @error_handler
    async def get_contact_by_username(
        self,
        local_user_id: UUID,
        username: str,
    ) -> ContactDTO:
        result = await self._contact_dao.get_contact(
            local_user_id=local_user_id,
            username=username,
        )
        if not result:
            raise ContactNotFoundError(
                f"Contact with username '{username}' not found for user {local_user_id}"
            )
        return result

    @error_handler
    async def get_contact_by_server_user_id(
        self, local_user_id: UUID, server_user_id: UUID
    ) -> ContactDTO | None:
        return await self._contact_dao.get_contact(
            local_user_id=local_user_id,
            contact_id=server_user_id,
        )

    @error_handler
    async def get_contacts(self, local_user_id: UUID) -> list[ContactDTO]:
        return await self._contact_dao.get_contacts(local_user_id)

    @error_handler
    async def search_contacts_by_username(
        self,
        local_user_id: UUID,
        username: str,
    ) -> list[ContactDTO]:
        query = username.strip()
        if not query:
            return []
        return await self._contact_dao.search_contacts_by_username(
            local_user_id=local_user_id,
            username=query,
        )

    @error_handler
    async def update_contact(
        self,
        contact: RequestContactDTO,
    ) -> ContactDTO | None:
        if contact.last_seen is None and "last_seen" in contact.model_fields_set:
            contact = contact.model_copy(update={"last_seen": datetime.now(UTC)})
        if contact.online is None and "online" in contact.model_fields_set:
            contact = contact.model_copy(update={"online": False})
        return await self._contact_dao.update_contact(contact)

    @error_handler
    async def delete_contact(self, contact_id: UUID) -> bool:
        return await self._contact_dao.delete_contact(contact_id)

    @error_handler
    async def send_contact_request(self, contact_id: UUID) -> ContactDTO | None:
        contact = await self._contact_dao.get_contact_by_id(contact_id)
        if not contact:
            raise ContactNotFoundError("Contact not found")
        update_dto = RequestContactDTO(
            local_user_id=contact.local_user_id,
            server_user_id=contact.server_user_id,
            status=ContactStatusEnum.PENDING_OUTGOING,
        )
        result = await self._contact_dao.update_contact(update_dto)
        return result

    @error_handler
    async def accept_contact_request(self, contact_id: UUID) -> ContactDTO | None:
        contact = await self._contact_dao.get_contact_by_id(contact_id)
        if not contact:
            raise ContactNotFoundError("Contact not found")
        update_dto = RequestContactDTO(
            local_user_id=contact.local_user_id,
            server_user_id=contact.server_user_id,
            status=ContactStatusEnum.ACCEPTED,
        )
        return await self._contact_dao.update_contact(update_dto)

    @error_handler
    async def reject_contact_request(self, contact_id: UUID) -> ContactDTO | None:
        contact = await self._contact_dao.get_contact_by_id(contact_id)
        if not contact:
            raise ContactNotFoundError("Contact not found")
        update_dto = RequestContactDTO(
            local_user_id=contact.local_user_id,
            server_user_id=contact.server_user_id,
            status=ContactStatusEnum.BLANK,
        )
        return await self._contact_dao.update_contact(update_dto)

    @error_handler
    async def block_contact(self, contact_id: UUID) -> ContactDTO | None:
        contact = await self._contact_dao.get_contact_by_id(contact_id)
        if not contact:
            raise ContactNotFoundError("Contact not found")
        update_dto = RequestContactDTO(
            local_user_id=contact.local_user_id,
            server_user_id=contact.server_user_id,
            status=ContactStatusEnum.BLACKLIST,
        )
        return await self._contact_dao.update_contact(update_dto)

    @error_handler
    async def unblock_contact(self, contact_id: UUID) -> ContactDTO | None:
        contact = await self._contact_dao.get_contact_by_id(contact_id)
        if not contact:
            raise ContactNotFoundError("Contact not found")
        update_dto = RequestContactDTO(
            local_user_id=contact.local_user_id,
            server_user_id=contact.server_user_id,
            status=ContactStatusEnum.BLANK,
        )
        return await self._contact_dao.update_contact(update_dto)
