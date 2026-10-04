from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import cast
from uuid import UUID

from sqlalchemy import and_, delete, insert, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database.dto import (
    AddMessageFileDTO,
    AddMessageTextDTO,
    MessageDTO,
)
from src.adapters.database.structures import (
    Message,
)


class AbstractMessageDAO(ABC):
    @abstractmethod
    async def add_message_text(self, message: AddMessageTextDTO) -> MessageDTO:
        raise NotImplementedError()

    @abstractmethod
    async def add_message_file(self, message: AddMessageFileDTO) -> MessageDTO:
        raise NotImplementedError()

    @abstractmethod
    async def get_messages(
        self, local_user_id: UUID, contact_id: UUID, limit: int | None = None
    ) -> list[MessageDTO]:
        raise NotImplementedError()

    @abstractmethod
    async def get_recent_messages(
        self,
        local_user_id: UUID,
        *,
        contact_id: UUID | None = None,
        chat_id: UUID | None = None,
        limit: int = 10,
    ) -> list[MessageDTO]:
        raise NotImplementedError()

    @abstractmethod
    async def delete_message(self, message_id: UUID) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def mark_messages_failed(
        self,
        local_user_id: UUID,
        server_message_ids: Sequence[UUID],
    ) -> int:
        raise NotImplementedError()


class MessageDAO(AbstractMessageDAO):
    __slots__ = ("_session",)

    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_message_text(self, message: AddMessageTextDTO) -> MessageDTO:
        existing = await self._get_message_by_server_id(
            local_user_id=message.local_user_id,
            server_message_id=message.server_message_id,
        )
        if existing is not None:
            return existing

        stmt = (
            insert(Message)
            .values(**message.model_dump(exclude_unset=True))
            .returning(Message)
        )
        result = await self._session.scalar(stmt)

        return MessageDTO.model_validate(result, from_attributes=True)

    async def add_message_file(self, message: AddMessageFileDTO) -> MessageDTO:
        existing = await self._get_message_by_server_id(
            local_user_id=message.local_user_id,
            server_message_id=message.server_message_id,
        )
        if existing is not None:
            return existing

        stmt = (
            insert(Message)
            .values(**message.model_dump(exclude_unset=True))
            .returning(Message)
        )
        result = await self._session.scalar(stmt)

        return MessageDTO.model_validate(result, from_attributes=True)

    async def _get_message_by_server_id(
        self, local_user_id: UUID, server_message_id: UUID
    ) -> MessageDTO | None:
        stmt = select(Message).where(
            and_(
                Message.local_user_id == local_user_id,
                Message.server_message_id == server_message_id,
            )
        )
        result = await self._session.scalar(stmt)
        return (
            MessageDTO.model_validate(result, from_attributes=True) if result else None
        )

    async def get_messages(
        self, local_user_id: UUID, contact_id: UUID, limit: int | None = None
    ) -> list[MessageDTO]:
        stmt = select(Message).where(
            and_(
                Message.local_user_id == local_user_id, Message.contact_id == contact_id
            )
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await self._session.scalars(stmt)
        return [
            MessageDTO.model_validate(message, from_attributes=True)
            for message in result
        ]

    async def get_recent_messages(
        self,
        local_user_id: UUID,
        *,
        contact_id: UUID | None = None,
        chat_id: UUID | None = None,
        limit: int = 10,
    ) -> list[MessageDTO]:
        if (contact_id is None) == (chat_id is None):
            raise ValueError("Exactly one conversation ID is required")
        if limit < 1:
            raise ValueError("Limit must be positive")

        conversation_filter = (
            Message.contact_id == contact_id
            if contact_id is not None
            else Message.chat_id == chat_id
        )
        stmt = (
            select(
                Message.id,
                Message.local_user_id,
                Message.server_message_id,
                Message.logical_message_id,
                Message.contact_id,
                Message.chat_id,
                Message.content_type,
                Message.content,
                Message.file_name,
                Message.file_size,
                Message.file_mime_type,
                Message.timestamp,
                Message.is_outgoing,
                Message.is_delivered,
                Message.failed,
            )
            .where(Message.local_user_id == local_user_id, conversation_filter)
            .order_by(Message.timestamp.desc(), Message.id.desc())
            .limit(limit)
        )
        if contact_id is not None:
            stmt = stmt.where(Message.chat_id.is_(None))
        result = await self._session.execute(stmt)
        return [
            MessageDTO.model_validate({**row, "file_content": None})
            for row in reversed(result.mappings().all())
        ]

    async def delete_message(self, message_id: UUID) -> bool:
        stmt = delete(Message).where(Message.id == message_id)
        result = await self._session.execute(stmt)
        return (cast(CursorResult[object], result).rowcount or 0) > 0

    async def mark_messages_failed(
        self,
        local_user_id: UUID,
        server_message_ids: Sequence[UUID],
    ) -> int:
        if not server_message_ids:
            return 0

        stmt = (
            update(Message)
            .where(
                Message.local_user_id == local_user_id,
                Message.server_message_id.in_(server_message_ids),
                Message.is_outgoing.is_(True),
            )
            .values(failed=True)
        )
        result = await self._session.execute(stmt)
        return cast(CursorResult[object], result).rowcount or 0
