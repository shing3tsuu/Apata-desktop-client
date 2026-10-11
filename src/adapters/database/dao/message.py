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
    async def get_file_messages(
        self,
        local_user_id: UUID,
        message_ids: Sequence[UUID],
    ) -> list[MessageDTO]:
        raise NotImplementedError()

    @abstractmethod
    async def get_message_by_server_id(
        self,
        local_user_id: UUID,
        server_message_id: UUID,
    ) -> MessageDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_message_by_general_uuid(
        self,
        local_user_id: UUID,
        chat_id: UUID,
        general_message_uuid: UUID,
    ) -> MessageDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_messages_by_ids(
        self,
        local_user_id: UUID,
        message_ids: Sequence[UUID],
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
        existing = await self.get_message_by_server_id(
            local_user_id=message.local_user_id,
            server_message_id=message.server_message_id,
        )
        if existing is not None:
            return existing

        prepared = await self._resolve_reply_target(message)
        stmt = (
            insert(Message)
            .values(**prepared.model_dump(exclude_unset=True))
            .returning(Message)
        )
        result = await self._session.scalar(stmt)
        saved = MessageDTO.model_validate(result, from_attributes=True)
        await self._resolve_pending_replies(saved)
        return saved

    async def add_message_file(self, message: AddMessageFileDTO) -> MessageDTO:
        existing = await self.get_message_by_server_id(
            local_user_id=message.local_user_id,
            server_message_id=message.server_message_id,
        )
        if existing is not None:
            return existing

        prepared = await self._resolve_reply_target(message)
        stmt = (
            insert(Message)
            .values(**prepared.model_dump(exclude_unset=True))
            .returning(Message)
        )
        result = await self._session.scalar(stmt)
        saved = MessageDTO.model_validate(result, from_attributes=True)
        await self._resolve_pending_replies(saved)
        return saved

    async def get_message_by_server_id(
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

    async def get_message_by_general_uuid(
        self,
        local_user_id: UUID,
        chat_id: UUID,
        general_message_uuid: UUID,
    ) -> MessageDTO | None:
        result = await self._session.scalar(
            select(Message).where(
                Message.local_user_id == local_user_id,
                Message.chat_id == chat_id,
                Message.general_message_uuid == general_message_uuid,
            )
        )
        return (
            MessageDTO.model_validate(result, from_attributes=True) if result else None
        )

    async def _resolve_reply_target(
        self,
        message: AddMessageTextDTO | AddMessageFileDTO,
    ) -> AddMessageTextDTO | AddMessageFileDTO:
        if message.reply_to_id is not None:
            return message
        target = None
        if message.server_reply_to_id is not None:
            target = await self.get_message_by_server_id(
                message.local_user_id,
                message.server_reply_to_id,
            )
        if (
            target is None
            and message.chat_id is not None
            and message.reply_to_general_message_uuid is not None
        ):
            target = await self.get_message_by_general_uuid(
                message.local_user_id,
                message.chat_id,
                message.reply_to_general_message_uuid,
            )
        if target is None:
            return message
        return message.model_copy(update={"reply_to_id": target.id})

    async def _resolve_pending_replies(self, message: MessageDTO) -> None:
        await self._session.execute(
            update(Message)
            .where(
                Message.local_user_id == message.local_user_id,
                Message.server_reply_to_id == message.server_message_id,
                Message.reply_to_id.is_(None),
            )
            .values(reply_to_id=message.id)
        )
        if message.chat_id is not None and message.general_message_uuid is not None:
            await self._session.execute(
                update(Message)
                .where(
                    Message.local_user_id == message.local_user_id,
                    Message.chat_id == message.chat_id,
                    Message.reply_to_general_message_uuid
                    == message.general_message_uuid,
                    Message.reply_to_id.is_(None),
                    Message.id != message.id,
                )
                .values(reply_to_id=message.id)
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
                Message.general_message_uuid,
                Message.server_reply_to_id,
                Message.reply_to_general_message_uuid,
                Message.reply_to_id,
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

    async def get_file_messages(
        self,
        local_user_id: UUID,
        message_ids: Sequence[UUID],
    ) -> list[MessageDTO]:
        if not message_ids:
            return []

        stmt = select(Message).where(
            Message.local_user_id == local_user_id,
            Message.id.in_(message_ids),
            Message.file_content.is_not(None),
        )
        result = await self._session.scalars(stmt)
        return [
            MessageDTO.model_validate(message, from_attributes=True)
            for message in result
        ]

    async def get_messages_by_ids(
        self,
        local_user_id: UUID,
        message_ids: Sequence[UUID],
    ) -> list[MessageDTO]:
        if not message_ids:
            return []

        result = await self._session.scalars(
            select(Message).where(
                Message.local_user_id == local_user_id,
                Message.id.in_(message_ids),
            )
        )
        return [
            MessageDTO.model_validate(message, from_attributes=True)
            for message in result
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
