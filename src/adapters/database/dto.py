# dto.py
from datetime import datetime, timezone
from typing import Any, overload
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from .structures import (
    ChatEventTypeEnum,
    ContactStatusEnum,
    MessageContentMimeTypeEnum,
    MessageContentTypeEnum,
)
from .validation import (
    is_valid_ecdh_public_key,
    is_valid_ed_public_key,
    is_valid_file_mime_type,
    is_valid_file_name,
    is_valid_hashed_password,
)


@overload
def _normalize_utc(value: datetime) -> datetime: ...


@overload
def _normalize_utc(value: None) -> None: ...


def _normalize_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class AddLocalUserDTO(BaseModel):
    server_user_id: UUID
    username: str
    ed_public_key: str
    hashed_password: str
    timezone: int | None = None

    @field_validator("ed_public_key", mode="before")
    @classmethod
    def validate_ed_public_key(cls, v: Any) -> str:
        if not is_valid_ed_public_key(v):
            raise ValueError("Invalid ED public key")
        return v

    @field_validator("hashed_password", mode="before")
    @classmethod
    def validate_hashed_password(cls, v: Any) -> str:
        if not is_valid_hashed_password(v):
            raise ValueError("Invalid hashed password")
        return v


class RequestLocalUserDTO(BaseModel):
    id: UUID
    server_user_id: UUID | None = None
    username: str | None = None
    ed_public_key: str | None = None
    hashed_password: str | None = None
    timezone: int | None = None

    @field_validator("ed_public_key", mode="before")
    @classmethod
    def validate_ed_public_key(cls, v: Any) -> str | None:
        if v is not None and not is_valid_ed_public_key(v):
            raise ValueError("Invalid ED public key")
        return v

    @field_validator("hashed_password", mode="before")
    @classmethod
    def validate_hashed_password(cls, v: Any) -> str | None:
        if v is not None and not is_valid_hashed_password(v):
            raise ValueError("Invalid hashed password")
        return v


class LocalUserDTO(RequestLocalUserDTO):
    id: UUID

    @property
    def file_path(self) -> str | None:
        return None


class AddContactDTO(BaseModel):
    local_user_id: UUID
    server_user_id: UUID
    status: ContactStatusEnum | None = None
    username: str
    ed_public_key: str
    ecdh_public_key: str
    last_seen: datetime | None = None
    online: bool | None = False

    @field_validator("ed_public_key", mode="before")
    @classmethod
    def validate_ed_public_key(cls, v: Any) -> str:
        if not is_valid_ed_public_key(v):
            raise ValueError("Invalid ED public key")
        return v

    @field_validator("ecdh_public_key", mode="before")
    @classmethod
    def validate_ecdh_public_key(cls, v: Any) -> str:
        if not is_valid_ecdh_public_key(v):
            raise ValueError("Invalid ECDH public key")
        return v


class RequestContactDTO(BaseModel):
    local_user_id: UUID | None = None
    server_user_id: UUID | None = None
    status: ContactStatusEnum | None = None
    username: str | None = None
    ed_public_key: str | None = None
    ecdh_public_key: str | None = None
    last_seen: datetime | None = None
    online: bool | None = False

    @field_validator("ed_public_key", mode="before")
    @classmethod
    def validate_ed_public_key(cls, v: Any) -> str:
        if not is_valid_ed_public_key(v):
            raise ValueError("Invalid ED public key")
        return v

    @field_validator("ecdh_public_key", mode="before")
    @classmethod
    def validate_ecdh_public_key(cls, v: Any) -> str:
        if not is_valid_ecdh_public_key(v):
            raise ValueError("Invalid ECDH public key")
        return v


class ContactDTO(AddContactDTO):
    id: UUID


class AddChatDTO(BaseModel):
    local_user_id: UUID
    server_chat_id: UUID
    server_owner_id: UUID | None = None
    name: str | None = None
    created_at: datetime | None = None

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime | None) -> datetime | None:
        return _normalize_utc(value)


class RequestChatDTO(BaseModel):
    id: UUID
    local_user_id: UUID | None = None
    server_chat_id: UUID | None = None
    server_owner_id: UUID | None = None
    name: str | None = None
    created_at: datetime | None = None

    @field_validator("created_at")
    @classmethod
    def normalize_created_at(cls, value: datetime | None) -> datetime | None:
        return _normalize_utc(value)


class ChatDTO(AddChatDTO):
    id: UUID


class AddChatParticipantDTO(BaseModel):
    chat_id: UUID
    contact_id: UUID
    joined_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    left_at: datetime | None = None

    @field_validator("joined_at", "left_at")
    @classmethod
    def normalize_participant_timestamps(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        return _normalize_utc(value)


class RequestChatParticipantDTO(BaseModel):
    chat_id: UUID
    contact_id: UUID
    joined_at: datetime | None = None
    left_at: datetime | None = None

    @field_validator("joined_at", "left_at")
    @classmethod
    def normalize_participant_timestamps(
        cls,
        value: datetime | None,
    ) -> datetime | None:
        return _normalize_utc(value)


class ChatParticipantDTO(AddChatParticipantDTO):
    pass


class AddChatEventDTO(BaseModel):
    chat_id: UUID
    contact_id: UUID | None = None
    server_event_id: UUID | None = None
    actor_server_user_id: UUID | None = None
    target_server_user_id: UUID | None = None
    event_type: ChatEventTypeEnum
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_utc(value)


class RequestChatEventDTO(BaseModel):
    id: UUID
    chat_id: UUID | None = None
    contact_id: UUID | None = None
    server_event_id: UUID | None = None
    actor_server_user_id: UUID | None = None
    target_server_user_id: UUID | None = None
    event_type: ChatEventTypeEnum | None = None
    timestamp: datetime | None = None

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        return _normalize_utc(value)


class ChatEventDTO(AddChatEventDTO):
    id: UUID


class AddMessageTextDTO(BaseModel):
    local_user_id: UUID
    server_message_id: UUID
    contact_id: UUID | None = None
    chat_id: UUID | None = None
    content: str
    content_type: MessageContentTypeEnum = MessageContentTypeEnum.TEXT
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_outgoing: bool
    is_delivered: bool = False

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_utc(value)

    @model_validator(mode="after")
    def check_contact_or_chat(self):
        if self.contact_id is None and self.chat_id is None:
            raise ValueError("Either contact_id or chat_id must be provided")
        return self


class AddMessageFileDTO(BaseModel):
    local_user_id: UUID
    server_message_id: UUID
    contact_id: UUID | None = None
    chat_id: UUID | None = None
    file_name: str
    file_content: bytes
    file_size: int
    file_mime_type: MessageContentMimeTypeEnum
    content_type: MessageContentTypeEnum = MessageContentTypeEnum.DOCUMENT
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_outgoing: bool
    is_delivered: bool = False

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_utc(value)

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str) -> str:
        if not is_valid_file_name(value):
            raise ValueError("File name must not contain a path or extension")
        return value

    @field_validator("file_mime_type", mode="before")
    @classmethod
    def validate_file_mime_type(cls, value: Any) -> Any:
        if not is_valid_file_mime_type(value):
            raise ValueError("File MIME type must be a file extension")
        return value

    @model_validator(mode="after")
    def check_contact_or_chat(self):
        if self.contact_id is None and self.chat_id is None:
            raise ValueError("Either contact_id or chat_id must be provided")
        return self


class RequestMessageDTO(BaseModel):
    id: UUID
    is_delivered: bool | None = None


class MessageDTO(BaseModel):
    id: UUID
    local_user_id: UUID
    server_message_id: UUID
    contact_id: UUID | None
    chat_id: UUID | None
    content_type: MessageContentTypeEnum
    content: str | None = None
    file_name: str | None = None
    file_content: bytes | None = None
    file_size: int | None = None
    file_mime_type: MessageContentMimeTypeEnum | None = None
    timestamp: datetime
    is_outgoing: bool
    is_delivered: bool

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        return _normalize_utc(value)

    @field_validator("file_name")
    @classmethod
    def validate_file_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not is_valid_file_name(value):
            raise ValueError("File name must not contain a path or extension")
        return value

    @field_validator("file_mime_type", mode="before")
    @classmethod
    def validate_file_mime_type(cls, value: Any) -> Any:
        if value is not None and not is_valid_file_mime_type(value):
            raise ValueError("File MIME type must be a file extension")
        return value
