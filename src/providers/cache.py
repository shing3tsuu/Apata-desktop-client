"""Decrypted conversation previews kept in application memory."""

from dataclasses import dataclass, field
from datetime import datetime
from uuid import UUID

from src.adapters.database.structures import (
    ContactStatusEnum,
    MessageContentMimeTypeEnum,
    MessageContentTypeEnum,
)


@dataclass(slots=True)
class MessageCache:
    id: UUID
    server_message_id: UUID
    contact_id: UUID | None
    chat_id: UUID | None
    content_type: MessageContentTypeEnum
    content: str | None
    file_name: str | None
    file_size: int | None
    file_mime_type: MessageContentMimeTypeEnum | None
    timestamp: datetime
    is_outgoing: bool
    is_delivered: bool
    failed: bool | None = None


@dataclass(slots=True)
class ContactCache:
    id: UUID
    server_user_id: UUID
    username: str
    status: ContactStatusEnum | None
    last_seen: datetime | None
    online: bool | None
    ed_public_key: str | None = None
    ecdh_public_key: str | None = None
    messages: list[MessageCache] = field(default_factory=list)


@dataclass(slots=True)
class ChatCache:
    id: UUID
    server_chat_id: UUID
    server_owner_id: UUID | None
    name: str | None
    created_at: datetime | None
    messages: list[MessageCache] = field(default_factory=list)
