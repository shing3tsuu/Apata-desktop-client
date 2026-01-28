from abc import ABC, abstractmethod
import logging

from sqlalchemy import select, delete, insert, update, func, case, and_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database.dto import MessageRequestDTO, MessageDTO
from src.adapters.database.structures import Message

class AbstractMessageDAO(ABC):
    @abstractmethod
    async def add_message(self, message: MessageRequestDTO) -> MessageDTO:
        raise NotImplementedError()

    @abstractmethod
    async def get_messages(self, local_user_id: int, contact_id: int, limit: int | None = None) -> list[MessageDTO]:
        raise NotImplementedError()

    @abstractmethod
    async def delete_message(self, message_id: int) -> bool:
        raise NotImplementedError()

class MessageDAO(AbstractMessageDAO):
    __slots__ = "_session"

    def __init__ (self, session: AsyncSession):
        self._session = session

    async def add_message(self, message: MessageRequestDTO) -> MessageDTO:
        stmt = (
            insert(Message)
            .values(**message.model_dump(exclude_unset=True))
            .returning(Message)
        )
        result = await self._session.scalar(stmt)

        return MessageDTO.model_validate(result, from_attributes=True)

    async def get_messages(self, local_user_id: int, contact_id: int, limit: int | None = None) -> list[MessageDTO]:
        stmt = select(Message).where(
            and_(
                Message.local_user_id == local_user_id,
                Message.contact_id == contact_id
            )
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await self._session.scalars(stmt)
        return [MessageDTO.model_validate(message, from_attributes=True) for message in result]

    async def delete_message(self, message_id: int) -> bool:
        stmt = delete(Message).where(Message.id == message_id)
        result = await self._session.execute(stmt)
        return result.rowcount > 0