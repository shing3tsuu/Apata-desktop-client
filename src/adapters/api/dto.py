from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from src.exceptions import APIError


class DictCompatibleDTO:
    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    def __getitem__(self, key: str) -> Any:
        return self.as_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.as_dict().get(key, default)

    def keys(self):
        return self.as_dict().keys()

    def items(self):
        return self.as_dict().items()

    def values(self):
        return self.as_dict().values()

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and key in self.as_dict()


@dataclass(slots=True, kw_only=True, frozen=True)
class MessageProcessingResultDTO(DictCompatibleDTO):
    message_id: UUID
    failed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "message_id": str(self.message_id),
            "failed": self.failed,
        }


@dataclass(slots=True, kw_only=True, frozen=True)
class ECDHPublicKeyDTO(DictCompatibleDTO):
    user_id: UUID
    ecdh_public_key: str
    ecdh_signature: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ECDHPublicKeyDTO:
        try:
            return cls(
                user_id=UUID(_required_str(data, "user_id", cls.__name__)),
                ecdh_public_key=_required_str(
                    data,
                    "ecdh_public_key",
                    cls.__name__,
                ),
                ecdh_signature=_required_str(
                    data,
                    "ecdh_signature",
                    cls.__name__,
                ),
            )
        except ValueError as error:
            raise APIError(
                "Invalid UUID field in ECDHPublicKeyDTO",
                response_data=data,
            ) from error


@dataclass(slots=True, kw_only=True, frozen=True)
class ChatMessageDeliveryDTO(DictCompatibleDTO):
    recipient_id: UUID
    message_id: UUID
    message: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "recipient_id": str(self.recipient_id),
            "message_id": str(self.message_id),
            "message": self.message,
        }


@dataclass(slots=True, kw_only=True, frozen=True)
class ChatMessageBatchDTO(DictCompatibleDTO):
    logical_message_id: UUID
    content_type: str
    ephemeral_public_key: str
    ephemeral_signature: str
    deliveries: list[ChatMessageDeliveryDTO]

    def as_dict(self) -> dict[str, Any]:
        return {
            "logical_message_id": str(self.logical_message_id),
            "content_type": self.content_type,
            "ephemeral_public_key": self.ephemeral_public_key,
            "ephemeral_signature": self.ephemeral_signature,
            "deliveries": [delivery.as_dict() for delivery in self.deliveries],
        }


@dataclass(slots=True, kw_only=True, frozen=True)
class SentChatMessageDeliveryDTO(DictCompatibleDTO):
    id: UUID
    logical_message_id: UUID
    recipient_id: UUID
    timestamp: datetime

    @classmethod
    def from_mapping(
        cls,
        data: dict[str, Any],
    ) -> SentChatMessageDeliveryDTO:
        try:
            return cls(
                id=UUID(_required_str(data, "id", cls.__name__)),
                logical_message_id=UUID(
                    _required_str(data, "logical_message_id", cls.__name__)
                ),
                recipient_id=UUID(_required_str(data, "recipient_id", cls.__name__)),
                timestamp=datetime.fromisoformat(
                    _required_str(data, "timestamp", cls.__name__)
                ),
            )
        except ValueError as error:
            raise APIError(
                "Invalid UUID or datetime field in SentChatMessageDeliveryDTO",
                response_data=data,
            ) from error


@dataclass(slots=True, kw_only=True, frozen=True)
class FailedMessageDTO(DictCompatibleDTO):
    id: UUID
    recipient_id: UUID
    chat_id: UUID | None
    timestamp: datetime
    is_delivered: bool
    failed: bool

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> FailedMessageDTO:
        chat_id = data.get("chat_id")
        is_delivered = data.get("is_delivered")
        failed = data.get("failed")
        if is_delivered is not True or failed is not True:
            raise APIError(
                "Expected a delivered failed message in FailedMessageDTO",
                response_data=data,
            )

        try:
            return cls(
                id=UUID(_required_str(data, "id", cls.__name__)),
                recipient_id=UUID(_required_str(data, "recipient_id", cls.__name__)),
                chat_id=UUID(str(chat_id)) if chat_id is not None else None,
                timestamp=datetime.fromisoformat(
                    _required_str(data, "timestamp", cls.__name__)
                ),
                is_delivered=is_delivered,
                failed=failed,
            )
        except ValueError as error:
            raise APIError(
                "Invalid UUID or datetime field in FailedMessageDTO",
                response_data=data,
            ) from error


def _required_str(data: dict[str, Any], field: str, dto_name: str) -> str:
    value = data.get(field)
    if isinstance(value, str) and value:
        return value

    raise APIError(
        f"Expected non-empty string field '{field}' in {dto_name}",
        response_data=data,
    )


def _optional_str(data: dict[str, Any], field: str) -> str | None:
    value = data.get(field)
    if value is None:
        return None
    return str(value)


@dataclass(slots=True, kw_only=True, frozen=True)
class AuthRegisterResponseDTO(DictCompatibleDTO):
    id: str
    username: str

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> AuthRegisterResponseDTO:
        return cls(
            id=_required_str(data, "id", cls.__name__),
            username=_required_str(data, "username", cls.__name__),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class AuthChallengeDTO(DictCompatibleDTO):
    challenge: str
    expires_at: str | None = None
    username: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> AuthChallengeDTO:
        return cls(
            challenge=_required_str(data, "challenge", cls.__name__),
            expires_at=_optional_str(data, "expires_at"),
            username=_optional_str(data, "username"),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class AuthTokenResponseDTO(DictCompatibleDTO):
    access_token: str
    token_type: str | None = None
    expires_in: int | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> AuthTokenResponseDTO:
        expires_in = data.get("expires_in")
        return cls(
            access_token=_required_str(data, "access_token", cls.__name__),
            token_type=_optional_str(data, "token_type"),
            expires_in=expires_in if isinstance(expires_in, int) else None,
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class AuthRegistrationResultDTO(DictCompatibleDTO):
    id: str
    username: str
    ed_private_key: str
    ecdh_private_key: str

    @property
    def ecdsa_private_key(self) -> str:
        return self.ed_private_key

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "ed_private_key": self.ed_private_key,
            "ecdsa_private_key": self.ecdsa_private_key,
            "ecdh_private_key": self.ecdh_private_key,
        }


@dataclass(slots=True, kw_only=True, frozen=True)
class ContactPublicDTO(DictCompatibleDTO):
    contact_id: str | None
    user_id: str
    username: str
    ed_public_key: str
    ecdh_public_key: str
    status: str
    online: bool | None
    last_seen: str | None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ContactPublicDTO:
        online = data.get("online")
        return cls(
            contact_id=_optional_str(data, "contact_id"),
            user_id=_required_str(data, "user_id", cls.__name__),
            username=_required_str(data, "username", cls.__name__),
            ed_public_key=_required_str(data, "ed_public_key", cls.__name__),
            ecdh_public_key=_required_str(data, "ecdh_public_key", cls.__name__),
            status=_required_str(data, "status", cls.__name__),
            online=online if isinstance(online, bool) else None,
            last_seen=_optional_str(data, "last_seen"),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class ContactPageDTO(DictCompatibleDTO):
    items: list[ContactPublicDTO]
    next_after_id: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ContactPageDTO:
        raw_items = data.get("items", [])
        if not isinstance(raw_items, list):
            raise APIError(
                "Expected contacts page items list",
                response_data={"items_type": type(raw_items).__name__},
            )

        items = []
        for item in raw_items:
            if not isinstance(item, dict):
                raise APIError(
                    "Expected contact item object",
                    response_data={"item_type": type(item).__name__},
                )
            items.append(ContactPublicDTO.from_mapping(item))

        return cls(
            items=items,
            next_after_id=_optional_str(data, "next_after_id"),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "items": [item.as_dict() for item in self.items],
            "next_after_id": self.next_after_id,
        }


@dataclass(slots=True, kw_only=True, frozen=True)
class ChatDTO(DictCompatibleDTO):
    id: UUID
    owner_id: UUID
    name: str | None
    created_at: datetime

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ChatDTO:
        name = data.get("name")
        if name is not None and not isinstance(name, str):
            raise APIError(
                "Expected string or null field 'name' in ChatDTO",
                response_data=data,
            )

        try:
            return cls(
                id=UUID(_required_str(data, "id", cls.__name__)),
                owner_id=UUID(_required_str(data, "owner_id", cls.__name__)),
                name=name,
                created_at=datetime.fromisoformat(
                    _required_str(data, "created_at", cls.__name__)
                ),
            )
        except ValueError as error:
            raise APIError(
                "Invalid UUID or datetime field in ChatDTO",
                response_data=data,
            ) from error


@dataclass(slots=True, kw_only=True, frozen=True)
class ChatParticipantDTO(DictCompatibleDTO):
    chat_id: UUID
    user_id: UUID
    invited_by_user_id: UUID | None
    joined_at: datetime
    left_at: datetime | None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ChatParticipantDTO:
        invited_by_user_id = data.get("invited_by_user_id")
        left_at = data.get("left_at")

        try:
            return cls(
                chat_id=UUID(_required_str(data, "chat_id", cls.__name__)),
                user_id=UUID(_required_str(data, "user_id", cls.__name__)),
                invited_by_user_id=(
                    UUID(str(invited_by_user_id))
                    if invited_by_user_id is not None
                    else None
                ),
                joined_at=datetime.fromisoformat(
                    _required_str(data, "joined_at", cls.__name__)
                ),
                left_at=(
                    datetime.fromisoformat(str(left_at))
                    if left_at is not None
                    else None
                ),
            )
        except ValueError as error:
            raise APIError(
                "Invalid UUID or datetime field in ChatParticipantDTO",
                response_data=data,
            ) from error


@dataclass(slots=True, kw_only=True, frozen=True)
class ChatEventDTO(DictCompatibleDTO):
    id: UUID
    chat_id: UUID
    user_id: UUID
    event_type: str
    timestamp: datetime
    target_user_id: UUID | None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ChatEventDTO:
        target_user_id = data.get("target_user_id")

        try:
            return cls(
                id=UUID(_required_str(data, "id", cls.__name__)),
                chat_id=UUID(_required_str(data, "chat_id", cls.__name__)),
                user_id=UUID(_required_str(data, "user_id", cls.__name__)),
                event_type=_required_str(data, "event_type", cls.__name__),
                timestamp=datetime.fromisoformat(
                    _required_str(data, "timestamp", cls.__name__)
                ),
                target_user_id=(
                    UUID(str(target_user_id)) if target_user_id is not None else None
                ),
            )
        except ValueError as error:
            raise APIError(
                "Invalid UUID or datetime field in ChatEventDTO",
                response_data=data,
            ) from error


@dataclass(slots=True, kw_only=True, frozen=True)
class ChatParticipantChangeDTO(DictCompatibleDTO):
    participant: ChatParticipantDTO
    event: ChatEventDTO

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> ChatParticipantChangeDTO:
        participant = data.get("participant")
        if not isinstance(participant, dict):
            raise APIError(
                "Expected object field 'participant' in ChatParticipantChangeDTO",
                response_data=data,
            )

        event = data.get("event")
        if not isinstance(event, dict):
            raise APIError(
                "Expected object field 'event' in ChatParticipantChangeDTO",
                response_data=data,
            )

        return cls(
            participant=ChatParticipantDTO.from_mapping(participant),
            event=ChatEventDTO.from_mapping(event),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class FileUploadSessionDTO(DictCompatibleDTO):
    upload_id: str
    file_id: str
    chunk_size: int
    offset: int
    expires_at: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> FileUploadSessionDTO:
        chunk_size = data.get("chunk_size")
        offset = data.get("offset", 0)
        if not isinstance(chunk_size, int) or chunk_size <= 0:
            raise APIError(
                "Expected positive integer field 'chunk_size' in file upload session",
                response_data=data,
            )
        if not isinstance(offset, int) or offset < 0:
            raise APIError(
                "Expected non-negative integer field 'offset' in file upload session",
                response_data=data,
            )

        return cls(
            upload_id=_required_str(data, "upload_id", cls.__name__),
            file_id=_required_str(data, "file_id", cls.__name__),
            chunk_size=chunk_size,
            offset=offset,
            expires_at=_optional_str(data, "expires_at"),
        )


@dataclass(slots=True, kw_only=True, frozen=True)
class UndeliveredMessageFileDTO(DictCompatibleDTO):
    message_id: UUID
    sender_id: UUID
    chat_id: UUID | None = None
    file_id: UUID
    file_name: str
    file_mime_type: str
    file_size: int
    file_content: bytes
    content_type: str
    timestamp: datetime
