from abc import ABC, abstractmethod
import logging

from sqlalchemy import select, delete, insert, update, func, case, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database.dto import ContactRequestDTO, ContactDTO, AddContactRequestDTO, UpdateContactRequestDTO
from src.adapters.database.structures import Contact

from src.exceptions import ContactAlreadyExistsError

class AbstractContactDAO(ABC):
    @abstractmethod
    async def add_contact(self, contact: AddContactRequestDTO) -> ContactDTO:
        raise NotImplementedError()

    @abstractmethod
    async def get_contact(self, local_user_id: int, contact_id: int | None = None, username: str | None = None) -> ContactDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_contacts(self, local_user_id: int) -> list[ContactDTO]:
        raise NotImplementedError()

    @abstractmethod
    async def update_contact(self, contact: UpdateContactRequestDTO) -> ContactDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_contact(self, contact_id: int) -> bool:
        raise NotImplementedError()

class ContactDAO(AbstractContactDAO):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_contact(self, contact: AddContactRequestDTO) -> ContactDTO:
        existing_contact = await self.get_contact(
            local_user_id=contact.local_user_id,
            username=contact.username
        )
        if existing_contact:
            raise ContactAlreadyExistsError("Contact with this user already exists")
        stmt = (
            insert(Contact)
            .values(**contact.model_dump())
            .returning(Contact)
        )
        result = await self._session.scalar(stmt)
        return ContactDTO.model_validate(result, from_attributes=True)

    async def get_contact(
            self,
            local_user_id: int,
            contact_id: int | None = None,
            username: str | None = None
    ) -> ContactDTO | None:
        if not contact_id and not username:
            raise ValueError("Either contact_id or username must be provided")
        stmt = select(Contact)
        if contact_id:
            stmt = stmt.where(
                and_(
                    Contact.local_user_id == local_user_id,
                    Contact.server_user_id == contact_id
                )
            )
        if username:
            stmt = stmt.where(
                and_(
                    Contact.local_user_id == local_user_id,
                    Contact.username.ilike(username) |
                    Contact.username.ilike(f"%{username}%")
                )
            ).order_by(
                case(
                    (Contact.username.ilike(username), 0),
                    else_=1
                )
            ).limit(1)
        result = await self._session.scalar(stmt)
        return ContactDTO.model_validate(result, from_attributes=True) if result else None

    async def get_contacts(self, local_user_id: int) -> list[ContactDTO]:
        stmt = select(Contact).where(Contact.local_user_id == local_user_id)
        result = await self._session.scalars(stmt)
        return [ContactDTO.model_validate(contact, from_attributes=True) for contact in result]

    async def update_contact(self, contact: UpdateContactRequestDTO) -> ContactDTO | None:
        stmt = (
            update(Contact)
            .where(
                and_(
                    Contact.local_user_id == contact.local_user_id,
                    Contact.server_user_id == contact.server_user_id
                )
            )
            .values(**contact.model_dump(exclude_unset=True))
            .returning(Contact)
        )
        result = await self._session.scalar(stmt)
        return ContactDTO.model_validate(result, from_attributes=True) if result else None

    async def delete_contact(self, contact_id: int) -> bool:
        stmt = delete(Contact).where(Contact.id == contact_id)
        result = await self._session.execute(stmt)
        return result.rowcount > 0