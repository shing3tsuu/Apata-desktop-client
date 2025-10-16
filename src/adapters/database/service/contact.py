from ..dao.contact import AbstractContactDAO
from ..dao.common import AbstractCommonDAO
from src.adapters.database.dto import ContactDTO, ContactRequestDTO

class ContactService:
    def __init__(self, contact_dao: AbstractContactDAO, common_dao: AbstractCommonDAO):
        self._contact_dao = contact_dao
        self._common_dao = common_dao

    async def add_contact(self, contact: ContactRequestDTO) -> ContactDTO:
        result = await self._contact_dao.add_contact(contact)
        await self._common_dao.commit()
        return result

    async def get_contact(self, contact_id: int | None = None, username: str | None = None) -> ContactDTO | None:
        return await self._contact_dao.get_contact(contact_id=contact_id, username=username)

    async def get_contacts(self) -> list[ContactDTO]:
        return await self._contact_dao.get_contacts()

    async def update_contact(self, contact: ContactRequestDTO) -> ContactDTO | None:
        result = await self._contact_dao.update_contact(contact)
        await self._common_dao.commit()
        return result

    async def delete_contact(self, contact_id: int | None = None) -> bool:
        result = await self._contact_dao.delete_contact(contact_id=contact_id)
        await self._common_dao.commit()
        return result