from abc import ABC, abstractmethod
import logging

from sqlalchemy import select, delete, insert, update, func, case
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database.dto import ContactRequestDTO, ContactDTO
from src.adapters.database.structures import Contact

from src.exceptions import ContactAlreadyExistsError

class AbstractContactDAO(ABC):
    @abstractmethod
    async def add_contact(self, contact: ContactRequestDTO) -> ContactDTO:
        raise NotImplementedError()

    @abstractmethod
    async def get_contact(self, contact_id: int | None = None, username: str | None = None) -> ContactDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_contacts(self) -> list[ContactDTO]:
        raise NotImplementedError()

    @abstractmethod
    async def update_contact(self, contact: ContactRequestDTO) -> ContactDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_contact(self, contact_id: int) -> bool:
        raise NotImplementedError()

class ContactDAO(AbstractContactDAO):
    __slots__ = ("_session", "_logger")

    def __init__(self, session: AsyncSession, logger: logging.Logger | None = None):
        self._session = session
        self._logger = logger or logging.getLogger(__name__)

    async def add_contact(self, contact: ContactRequestDTO) -> ContactDTO:
        try:
            existing_contact = await self.get_contact(username=contact.username)
            if existing_contact:
                raise ContactAlreadyExistsError("Contact with this user already exists")

            stmt = (
                insert(Contact)
                .values(**contact.model_dump())
                .returning(Contact)
            )
            result = await self._session.scalar(stmt)

            return ContactDTO.model_validate(result, from_attributes=True)

        except SQLAlchemyError as e:
            self._logger.error("Error adding contact: %s", e)
            return None

    async def get_contact(self, contact_id: int | None = None, username: str | None = None) -> ContactDTO | None:
        if not contact_id and not username:
            raise ValueError("Either contact_id or username must be provided")

        try:
            stmt = select(Contact)
            if contact_id:
                stmt = stmt.where(Contact.server_user_id == contact_id)
            if username:
                stmt = stmt.where(
                    Contact.username.ilike(username) |
                    Contact.username.ilike(f"%{username}%")
                ).order_by(
                    case(
                        (Contact.username.ilike(username), 0),
                        else_=1
                    )
                ).limit(1)
            result = await self._session.scalar(stmt)

            return ContactDTO.model_validate(result, from_attributes=True) if result else None

        except SQLAlchemyError as e:
            self._logger.error("Error fetching contact in database: %s", e)
            return None

    async def get_contacts(self) -> list[ContactDTO]:
        try:
            stmt = select(Contact)
            result = await self._session.scalars(stmt)

            return [ContactDTO.model_validate(contact, from_attributes=True) for contact in result]

        except SQLAlchemyError as e:
            self._logger.error("Error fetching contacts in databse: %s", e)
            return []

    async def update_contact(self, contact: ContactRequestDTO) -> ContactDTO | None:
        try:
            stmt = (
                update(Contact)
                .where(Contact.server_user_id == contact.server_user_id)
                .values(**contact.model_dump(exclude_unset=True))
                .returning(Contact)
            )
            result = await self._session.scalar(stmt)

            return ContactDTO.model_validate(result, from_attributes=True) if result else None

        except SQLAlchemyError as e:
            self._logger.error("Error updating contact in database: %s", e)
            return None

    async def delete_contact(self, contact_id: int | None = None) -> bool:
        try:
            stmt = delete(Contact).where(Contact.id == contact_id)
            result = await self._session.execute(stmt)

            return result.rowcount > 0

        except SQLAlchemyError as e:
            self._logger.error("Error deleting contact in database: %s", e)
            return False