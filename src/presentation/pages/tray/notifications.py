"""Build system-tray notifications from decrypted conversation caches."""

from dataclasses import dataclass
from datetime import datetime
from collections.abc import Iterator
from uuid import UUID

from src.adapters.database.structures import MessageContentTypeEnum
from src.providers.cache import MessageCache
from src.providers.state import AppState


@dataclass(frozen=True, slots=True)
class TrayNotification:
    message_id: UUID
    title: str
    body: str
    timestamp: datetime


class MessageNotificationTracker:
    _MAX_PREVIEW_LENGTH = 120

    def __init__(self, app_state: AppState) -> None:
        self._app_state = app_state
        self._known_message_ids: set[UUID] = set()
        self._armed = False

    def arm_from_state(self) -> None:
        self._known_message_ids = {
            message.id for message, _title in self._iter_cached_messages()
        }
        self._armed = True

    def reset(self) -> None:
        self._known_message_ids.clear()
        self._armed = False

    def collect_new(self) -> list[TrayNotification]:
        cached_messages = list(self._iter_cached_messages())
        current_ids = {message.id for message, _title in cached_messages}
        if not self._armed:
            self._known_message_ids = current_ids
            self._armed = True
            return []

        notifications = [
            TrayNotification(
                message_id=message.id,
                title=title,
                body=self._message_preview(message),
                timestamp=message.timestamp,
            )
            for message, title in cached_messages
            if message.id not in self._known_message_ids and not message.is_outgoing
        ]
        self._known_message_ids.update(current_ids)
        return sorted(notifications, key=lambda item: item.timestamp.timestamp())

    def _iter_cached_messages(self) -> Iterator[tuple[MessageCache, str]]:
        for contact in self._app_state.contacts_cache:
            for message in contact.messages:
                yield message, contact.username

        contacts_by_id = {
            contact.id: contact for contact in self._app_state.contacts_cache
        }
        for chat in self._app_state.chats_cache:
            chat_name = chat.name or "CHAT"
            for message in chat.messages:
                sender = contacts_by_id.get(message.contact_id)
                title = (
                    f"{sender.username} · {chat_name}"
                    if sender is not None and not message.is_outgoing
                    else chat_name
                )
                yield message, title

    @classmethod
    def _message_preview(cls, message: MessageCache) -> str:
        if message.content_type is MessageContentTypeEnum.TEXT:
            preview = " ".join((message.content or "").split()) or "NEW MESSAGE"
        elif message.content_type is MessageContentTypeEnum.IMAGE:
            preview = "PHOTO"
        elif message.content_type is MessageContentTypeEnum.VIDEO:
            preview = "VIDEO"
        elif message.content_type is MessageContentTypeEnum.AUDIO:
            preview = "AUDIO"
        else:
            preview = message.file_name or "FILE"

        if len(preview) <= cls._MAX_PREVIEW_LENGTH:
            return preview
        return f"{preview[: cls._MAX_PREVIEW_LENGTH - 3]}..."
