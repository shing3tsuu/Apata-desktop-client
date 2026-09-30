from abc import ABC, abstractmethod
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import and_, case, delete, insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.adapters.database.dto import (
    AddChatDTO,
    AddChatEventDTO,
    AddChatParticipantDTO,
    ChatDTO,
    ChatEventDTO,
    ChatParticipantDTO,
    ContactDTO,
    RequestChatParticipantDTO,
    RequestChatEventDTO,
    RequestChatDTO,
)
from src.adapters.database.structures import Chat, ChatEvent, ChatParticipant, Contact


class AbstractChatDAO(ABC):
    @abstractmethod
    async def add_chat(self, chat: AddChatDTO) -> ChatDTO:
        raise NotImplementedError()

    @abstractmethod
    async def get_chat_by_id(self, chat_id: UUID) -> ChatDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_chat(
        self,
        local_user_id: UUID,
        server_chat_id: UUID | None = None,
        name: str | None = None,
    ) -> ChatDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_chats(self, local_user_id: UUID) -> list[ChatDTO]:
        raise NotImplementedError()

    @abstractmethod
    async def update_chat(self, chat: RequestChatDTO) -> ChatDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_chat(self, chat_id: UUID) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def add_participant(
        self, participant: AddChatParticipantDTO
    ) -> ChatParticipantDTO:
        raise NotImplementedError()

    @abstractmethod
    async def update_participant(
        self, participant: RequestChatParticipantDTO
    ) -> ChatParticipantDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_participant(
        self, chat_id: UUID, contact_id: UUID
    ) -> ChatParticipantDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_chat_participants(self, chat_id: UUID) -> list[ContactDTO]:
        raise NotImplementedError()

    @abstractmethod
    async def get_contact_chats(self, contact_id: UUID) -> list[ChatDTO]:
        raise NotImplementedError()

    @abstractmethod
    async def delete_participant(self, chat_id: UUID, contact_id: UUID) -> bool:
        raise NotImplementedError()

    @abstractmethod
    async def add_chat_event(self, event: AddChatEventDTO) -> ChatEventDTO:
        raise NotImplementedError()

    @abstractmethod
    async def get_chat_event_by_id(self, event_id: UUID) -> ChatEventDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_chat_event_by_server_event_id(
        self,
        server_event_id: UUID,
    ) -> ChatEventDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_latest_server_event_timestamp(
        self,
        chat_id: UUID,
    ) -> datetime | None:
        raise NotImplementedError()

    @abstractmethod
    async def get_chat_events(
        self, chat_id: UUID, limit: int | None = None
    ) -> list[ChatEventDTO]:
        raise NotImplementedError()

    @abstractmethod
    async def update_chat_event(
        self, event: RequestChatEventDTO
    ) -> ChatEventDTO | None:
        raise NotImplementedError()

    @abstractmethod
    async def delete_chat_event(self, event_id: UUID) -> bool:
        raise NotImplementedError()


class ChatDAO(AbstractChatDAO):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def add_chat(self, chat: AddChatDTO) -> ChatDTO:
        stmt = insert(Chat).values(**chat.model_dump()).returning(Chat)
        result = await self._session.scalar(stmt)
        return ChatDTO.model_validate(result, from_attributes=True)

    async def get_chat_by_id(self, chat_id: UUID) -> ChatDTO | None:
        stmt = select(Chat).where(Chat.id == chat_id)
        result = await self._session.scalar(stmt)
        return ChatDTO.model_validate(result, from_attributes=True) if result else None

    async def get_chat(
        self,
        local_user_id: UUID,
        server_chat_id: UUID | None = None,
        name: str | None = None,
    ) -> ChatDTO | None:
        if not server_chat_id and not name:
            raise ValueError("Either server_chat_id or name must be provided")

        stmt = select(Chat).where(Chat.local_user_id == local_user_id)
        if server_chat_id:
            stmt = stmt.where(Chat.server_chat_id == server_chat_id)
        if name:
            stmt = (
                stmt.where(Chat.name.ilike(name) | Chat.name.ilike(f"%{name}%"))
                .order_by(case((Chat.name.ilike(name), 0), else_=1))
                .limit(1)
            )

        result = await self._session.scalar(stmt)
        return ChatDTO.model_validate(result, from_attributes=True) if result else None

    async def get_chats(self, local_user_id: UUID) -> list[ChatDTO]:
        stmt = select(Chat).where(Chat.local_user_id == local_user_id)
        result = await self._session.scalars(stmt)
        return [ChatDTO.model_validate(chat, from_attributes=True) for chat in result]

    async def update_chat(self, chat: RequestChatDTO) -> ChatDTO | None:
        data = chat.model_dump(exclude_unset=True)
        data.pop("id", None)

        if not data:
            return await self.get_chat_by_id(chat.id)

        stmt = (
            update(Chat)
            .where(Chat.id == chat.id)
            .values(**data)
            .returning(Chat)
        )
        result = await self._session.scalar(stmt)
        return ChatDTO.model_validate(result, from_attributes=True) if result else None

    async def delete_chat(self, chat_id: UUID) -> bool:
        stmt = delete(Chat).where(Chat.id == chat_id)
        result = await self._session.execute(stmt)
        return result.rowcount > 0

    async def add_participant(
        self, participant: AddChatParticipantDTO
    ) -> ChatParticipantDTO:
        stmt = (
            insert(ChatParticipant)
            .values(**participant.model_dump())
            .returning(ChatParticipant)
        )
        result = await self._session.scalar(stmt)
        return ChatParticipantDTO.model_validate(result, from_attributes=True)

    async def update_participant(
        self, participant: RequestChatParticipantDTO
    ) -> ChatParticipantDTO | None:
        data = participant.model_dump(exclude_unset=True)
        data.pop("chat_id", None)
        data.pop("contact_id", None)

        if not data:
            return await self.get_participant(
                participant.chat_id,
                participant.contact_id,
            )

        stmt = (
            update(ChatParticipant)
            .where(
                and_(
                    ChatParticipant.chat_id == participant.chat_id,
                    ChatParticipant.contact_id == participant.contact_id,
                )
            )
            .values(**data)
            .returning(ChatParticipant)
        )
        result = await self._session.scalar(stmt)
        return (
            ChatParticipantDTO.model_validate(result, from_attributes=True)
            if result
            else None
        )

    async def get_participant(
        self, chat_id: UUID, contact_id: UUID
    ) -> ChatParticipantDTO | None:
        stmt = select(ChatParticipant).where(
            and_(
                ChatParticipant.chat_id == chat_id,
                ChatParticipant.contact_id == contact_id,
            )
        )
        result = await self._session.scalar(stmt)
        return (
            ChatParticipantDTO.model_validate(result, from_attributes=True)
            if result
            else None
        )

    async def get_chat_participants(self, chat_id: UUID) -> list[ContactDTO]:
        stmt = (
            select(Contact)
            .join(ChatParticipant, ChatParticipant.contact_id == Contact.id)
            .where(
                and_(
                    ChatParticipant.chat_id == chat_id,
                    ChatParticipant.left_at.is_(None),
                )
            )
            .order_by(ChatParticipant.joined_at)
        )
        result = await self._session.scalars(stmt)
        return [
            ContactDTO.model_validate(contact, from_attributes=True)
            for contact in result
        ]

    async def get_contact_chats(self, contact_id: UUID) -> list[ChatDTO]:
        stmt = (
            select(Chat)
            .join(ChatParticipant, ChatParticipant.chat_id == Chat.id)
            .where(
                and_(
                    ChatParticipant.contact_id == contact_id,
                    ChatParticipant.left_at.is_(None),
                )
            )
            .order_by(ChatParticipant.joined_at)
        )
        result = await self._session.scalars(stmt)
        return [ChatDTO.model_validate(chat, from_attributes=True) for chat in result]

    async def delete_participant(self, chat_id: UUID, contact_id: UUID) -> bool:
        stmt = delete(ChatParticipant).where(
            and_(
                ChatParticipant.chat_id == chat_id,
                ChatParticipant.contact_id == contact_id,
            )
        )
        result = await self._session.execute(stmt)
        return result.rowcount > 0

    async def add_chat_event(self, event: AddChatEventDTO) -> ChatEventDTO:
        stmt = insert(ChatEvent).values(**event.model_dump()).returning(ChatEvent)
        result = await self._session.scalar(stmt)
        return ChatEventDTO.model_validate(result, from_attributes=True)

    async def get_chat_event_by_id(self, event_id: UUID) -> ChatEventDTO | None:
        stmt = select(ChatEvent).where(ChatEvent.id == event_id)
        result = await self._session.scalar(stmt)
        return (
            ChatEventDTO.model_validate(result, from_attributes=True)
            if result
            else None
        )

    async def get_chat_event_by_server_event_id(
        self,
        server_event_id: UUID,
    ) -> ChatEventDTO | None:
        stmt = select(ChatEvent).where(ChatEvent.server_event_id == server_event_id)
        result = await self._session.scalar(stmt)
        return (
            ChatEventDTO.model_validate(result, from_attributes=True)
            if result
            else None
        )

    async def get_latest_server_event_timestamp(
        self,
        chat_id: UUID,
    ) -> datetime | None:
        stmt = (
            select(ChatEvent.timestamp)
            .where(
                and_(
                    ChatEvent.chat_id == chat_id,
                    ChatEvent.server_event_id.is_not(None),
                )
            )
            .order_by(ChatEvent.timestamp.desc())
            .limit(1)
        )
        timestamp = await self._session.scalar(stmt)
        if timestamp is not None and timestamp.tzinfo is None:
            return timestamp.replace(tzinfo=timezone.utc)
        return timestamp

    async def get_chat_events(
        self, chat_id: UUID, limit: int | None = None
    ) -> list[ChatEventDTO]:
        stmt = (
            select(ChatEvent)
            .where(ChatEvent.chat_id == chat_id)
            .order_by(ChatEvent.timestamp)
        )
        if limit:
            stmt = stmt.limit(limit)
        result = await self._session.scalars(stmt)
        return [
            ChatEventDTO.model_validate(event, from_attributes=True)
            for event in result
        ]

    async def update_chat_event(
        self, event: RequestChatEventDTO
    ) -> ChatEventDTO | None:
        data = event.model_dump(exclude_unset=True)
        data.pop("id", None)

        if not data:
            return await self.get_chat_event_by_id(event.id)

        stmt = (
            update(ChatEvent)
            .where(ChatEvent.id == event.id)
            .values(**data)
            .returning(ChatEvent)
        )
        result = await self._session.scalar(stmt)
        return (
            ChatEventDTO.model_validate(result, from_attributes=True)
            if result
            else None
        )

    async def delete_chat_event(self, event_id: UUID) -> bool:
        stmt = delete(ChatEvent).where(ChatEvent.id == event_id)
        result = await self._session.execute(stmt)
        return result.rowcount > 0
