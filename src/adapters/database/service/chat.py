import logging
from datetime import datetime, timezone
from uuid import UUID

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
from src.adapters.database.structures import ChatEventTypeEnum
from src.exceptions import ChatAlreadyExistsError, ChatNotFoundError

from ..dao.chat import AbstractChatDAO
from ..dao.common import AbstractCommonDAO, error_handler


class ChatService:
    def __init__(
        self,
        chat_dao: AbstractChatDAO,
        common_dao: AbstractCommonDAO,
        logger: logging.Logger,
    ):
        self._chat_dao = chat_dao
        self._common_dao = common_dao
        self._logger = logger

    @error_handler
    async def add_chat(self, chat: AddChatDTO) -> ChatDTO:
        existing = await self._chat_dao.get_chat(
            local_user_id=chat.local_user_id,
            server_chat_id=chat.server_chat_id,
        )
        if existing:
            raise ChatAlreadyExistsError("Chat already exists")
        return await self._chat_dao.add_chat(chat)

    @error_handler
    async def get_chat_by_id(self, chat_id: UUID) -> ChatDTO:
        result = await self._chat_dao.get_chat_by_id(chat_id)
        if not result:
            raise ChatNotFoundError(f"Chat with id {chat_id} not found")
        return result

    @error_handler
    async def get_chat_by_server_id(
        self,
        local_user_id: UUID,
        server_chat_id: UUID,
    ) -> ChatDTO:
        result = await self._chat_dao.get_chat(
            local_user_id=local_user_id,
            server_chat_id=server_chat_id,
        )
        if not result:
            raise ChatNotFoundError(
                f"Chat with server id {server_chat_id} not found for user {local_user_id}"
            )
        return result

    @error_handler
    async def get_chat_by_name(
        self,
        local_user_id: UUID,
        name: str,
    ) -> ChatDTO:
        result = await self._chat_dao.get_chat(
            local_user_id=local_user_id,
            name=name,
        )
        if not result:
            raise ChatNotFoundError(
                f"Chat with name '{name}' not found for user {local_user_id}"
            )
        return result

    @error_handler
    async def get_chats(self, local_user_id: UUID) -> list[ChatDTO]:
        return await self._chat_dao.get_chats(local_user_id)

    @error_handler
    async def update_chat(self, chat: RequestChatDTO) -> ChatDTO | None:
        return await self._chat_dao.update_chat(chat)

    @error_handler
    async def delete_chat(self, chat_id: UUID) -> bool:
        return await self._chat_dao.delete_chat(chat_id)

    @error_handler
    async def add_participant(
        self,
        participant: AddChatParticipantDTO,
        create_join_event: bool = True,
    ) -> ChatParticipantDTO:
        existing = await self._chat_dao.get_participant(
            chat_id=participant.chat_id,
            contact_id=participant.contact_id,
        )
        if existing and existing.left_at is None:
            return existing

        if existing:
            restored = await self._chat_dao.update_participant(
                RequestChatParticipantDTO(
                    chat_id=participant.chat_id,
                    contact_id=participant.contact_id,
                    joined_at=participant.joined_at,
                    left_at=None,
                )
            )
            if restored is None:
                raise ChatNotFoundError("Chat participant not found")
            created = restored
        else:
            created = await self._chat_dao.add_participant(participant)

        if create_join_event:
            await self._chat_dao.add_chat_event(
                AddChatEventDTO(
                    chat_id=created.chat_id,
                    contact_id=created.contact_id,
                    event_type=ChatEventTypeEnum.MEMBER_ADDED,
                    timestamp=created.joined_at,
                )
            )
        return created

    @error_handler
    async def get_chat_participants(self, chat_id: UUID) -> list[ContactDTO]:
        return await self._chat_dao.get_chat_participants(chat_id)

    @error_handler
    async def get_participant(
        self,
        chat_id: UUID,
        contact_id: UUID,
    ) -> ChatParticipantDTO | None:
        return await self._chat_dao.get_participant(chat_id, contact_id)

    @error_handler
    async def update_participant(
        self,
        participant: RequestChatParticipantDTO,
    ) -> ChatParticipantDTO | None:
        return await self._chat_dao.update_participant(participant)

    @error_handler
    async def get_contact_chats(self, contact_id: UUID) -> list[ChatDTO]:
        return await self._chat_dao.get_contact_chats(contact_id)

    @error_handler
    async def delete_participant(
        self,
        chat_id: UUID,
        contact_id: UUID,
        create_left_event: bool = True,
        left_at: datetime | None = None,
    ) -> bool:
        existing = await self._chat_dao.get_participant(
            chat_id=chat_id,
            contact_id=contact_id,
        )
        if not existing or existing.left_at is not None:
            return False

        participant_left_at = left_at or datetime.now(timezone.utc)
        updated = await self._chat_dao.update_participant(
            RequestChatParticipantDTO(
                chat_id=chat_id,
                contact_id=contact_id,
                left_at=participant_left_at,
            )
        )
        if updated and create_left_event:
            await self._chat_dao.add_chat_event(
                AddChatEventDTO(
                    chat_id=chat_id,
                    contact_id=contact_id,
                    event_type=ChatEventTypeEnum.MEMBER_REMOVED,
                    timestamp=participant_left_at,
                )
            )
        return updated is not None

    @error_handler
    async def add_chat_event(self, event: AddChatEventDTO) -> ChatEventDTO:
        if event.server_event_id is not None:
            existing = await self._chat_dao.get_chat_event_by_server_event_id(
                event.server_event_id
            )
            if existing:
                return existing
        return await self._chat_dao.add_chat_event(event)

    @error_handler
    async def get_chat_event_by_id(self, event_id: UUID) -> ChatEventDTO | None:
        return await self._chat_dao.get_chat_event_by_id(event_id)

    @error_handler
    async def get_chat_event_by_server_event_id(
        self,
        server_event_id: UUID,
    ) -> ChatEventDTO | None:
        return await self._chat_dao.get_chat_event_by_server_event_id(
            server_event_id
        )

    @error_handler
    async def get_latest_server_event_timestamp(
        self,
        chat_id: UUID,
    ) -> datetime | None:
        return await self._chat_dao.get_latest_server_event_timestamp(chat_id)

    @error_handler
    async def get_chat_events(
        self,
        chat_id: UUID,
        limit: int | None = None,
    ) -> list[ChatEventDTO]:
        return await self._chat_dao.get_chat_events(chat_id, limit)

    @error_handler
    async def update_chat_event(
        self,
        event: RequestChatEventDTO,
    ) -> ChatEventDTO | None:
        return await self._chat_dao.update_chat_event(event)

    @error_handler
    async def delete_chat_event(self, event_id: UUID) -> bool:
        return await self._chat_dao.delete_chat_event(event_id)
