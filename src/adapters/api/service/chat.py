from uuid import UUID

from datetime import datetime

from src.adapters.api.dto import (
    ChatDTO,
    ChatEventDTO,
    ChatParticipantChangeDTO,
    ChatParticipantDTO,
)
from src.exceptions import AuthenticationError

from ..dao.chat import ChatHTTPDAO


class ChatHTTPService:
    def __init__(self, chat_dao: ChatHTTPDAO):
        self._chat_dao = chat_dao
        self._current_token: str | None = None

    @property
    def token(self) -> str | None:
        return self._current_token

    @token.setter
    def token(self, value: str) -> None:
        if not value:
            raise ValueError("Token cannot be empty")
        self._current_token = value

    @token.deleter
    def token(self) -> None:
        self._current_token = None

    def _require_token(self) -> str:
        token = self.token
        if token is None:
            raise AuthenticationError(
                "Authentication required for chat operations",
                context={"operation": "chat_service"},
            )
        return token

    async def get_chats(self) -> list[ChatDTO]:
        token = self._require_token()
        try:
            response = await self._chat_dao.get_chats(token=token)
            return [ChatDTO.from_mapping(chat) for chat in response]
        except AuthenticationError:
            del self.token
            raise

    async def create_chat(self, name: str | None = None) -> ChatDTO:
        token = self._require_token()

        try:
            response = await self._chat_dao.create_chat(
                name=name,
                token=token,
            )
            return ChatDTO.from_mapping(response)
        except AuthenticationError:
            del self.token
            raise

    async def delete_chat(self, chat_id: UUID) -> bool:
        token = self._require_token()

        try:
            await self._chat_dao.delete_chat(
                chat_id=chat_id,
                token=token,
            )
            return True
        except AuthenticationError:
            del self.token
            raise

    async def add_participant(
        self,
        chat_id: UUID,
        user_id: UUID,
    ) -> ChatParticipantChangeDTO:
        token = self._require_token()

        try:
            response = await self._chat_dao.add_participant(
                chat_id=chat_id,
                user_id=user_id,
                token=token,
            )
            return ChatParticipantChangeDTO.from_mapping(response)
        except AuthenticationError:
            del self.token
            raise

    async def remove_participant(
        self,
        chat_id: UUID,
        user_id: UUID,
    ) -> ChatParticipantChangeDTO:
        token = self._require_token()

        try:
            response = await self._chat_dao.remove_participant(
                chat_id=chat_id,
                user_id=user_id,
                token=token,
            )
            return ChatParticipantChangeDTO.from_mapping(response)
        except AuthenticationError:
            del self.token
            raise

    async def get_participants(
        self,
        chat_id: UUID,
    ) -> list[ChatParticipantDTO]:
        token = self._require_token()
        try:
            response = await self._chat_dao.get_participants(
                chat_id=chat_id,
                token=token,
            )
            return [ChatParticipantDTO.from_mapping(participant) for participant in response]
        except AuthenticationError:
            del self.token
            raise

    async def get_events(
        self,
        chat_id: UUID,
        after: datetime | None = None,
    ) -> list[ChatEventDTO]:
        token = self._require_token()
        try:
            response = await self._chat_dao.get_events(
                chat_id=chat_id,
                token=token,
                after=after,
            )
            return [ChatEventDTO.from_mapping(event) for event in response]
        except AuthenticationError:
            del self.token
            raise
