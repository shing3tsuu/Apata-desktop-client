from abc import ABC, abstractmethod
import logging

from sqlalchemy import select, delete, insert, update, func, case
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database.dto import MessageRequestDTO, MessageDTO
from src.adapters.database.structures import Message

class AbstractMessageDAO(ABC):
    @abstractmethod
    async def add_message(self, message: MessageRequestDTO) -> MessageDTO:
        raise NotImplementedError()

    @abstractmethod
    async def get_messages(self, contact_id: int, limit: int | None = None) -> list[MessageDTO]:
        raise NotImplementedError()

    @abstractmethod
    async def delete_message(self, message_id: int) -> bool:
        raise NotImplementedError()

class MessageDAO(AbstractMessageDAO):
    __slots__ = ("_session", "_logger")

    def __init__ (self, session: AsyncSession, logger: logging.Logger | None = None):
        self._session = session
        self._logger = logger or logging.getLogger(__name__)

    async def add_message(self, message: MessageRequestDTO) -> MessageDTO:
        try:
            stmt = (
                insert(Message)
                .values(**message.model_dump())
                .returning(Message)
            )
            result = await self._session.scalar(stmt)

            return MessageDTO.model_validate(result, from_attributes=True)

        except SQLAlchemyError as e:
            self._logger.error(f"Error adding message in database: {e}")

    async def get_messages(self, contact_id: int, limit: int | None = None) -> list[MessageDTO]:
        try:
            stmt = select(Message).where(Message.contact_id == contact_id)
            if limit:
                stmt = stmt.limit(limit)
            result = await self._session.scalars(stmt)

            return [MessageDTO.model_validate(message, from_attributes=True) for message in result]

        except SQLAlchemyError as e:
            self._logger.error(f"Error fetching messages in database: {e}")
            return []

    async def delete_message(self, message_id: int) -> bool:
        try:
            stmt = delete(Message).where(Message.id == message_id)
            result = await self._session.execute(stmt)

            return result.rowcount > 0

        except SQLAlchemyError as e:
            self._logger.error(f"Error deleting message in database: {e}")
            return False