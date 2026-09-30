from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID


@dataclass(slots=True, kw_only=True, frozen=True)
class EncryptMessageResult:
    encrypted_message: str
    ephemeral_signature: str
    message_uuid: UUID


@dataclass(slots=True, kw_only=True, frozen=True)
class EncryptMessageToChatResult:
    recipient_uuid: UUID
    encrypted_message: str
    ephemeral_signature: str
    message_uuid: UUID


@dataclass(slots=True, kw_only=True, frozen=True)
class GenerateKeyPairResult:
    ecdh_private_key: str
    ecdh_public_key: str
    ed_private_key: str
    ed_public_key: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)

    def __getitem__(self, key: str) -> str:
        return self.as_dict()[key]

    def get(self, key: str, default: Any = None) -> str | Any:
        return self.as_dict().get(key, default)


@dataclass(slots=True, kw_only=True, frozen=True)
class FileEncryptionContext:
    file_id: UUID
    key: bytes


@dataclass(slots=True, kw_only=True, frozen=True)
class FileMetadataEncryptionResult:
    """Encrypted envelope that lets a recipient decrypt an uploaded file."""

    encrypted_metadata: str
    ephemeral_signature: str
    metadata_message_id: UUID


@dataclass(slots=True, kw_only=True, frozen=True)
class FileMessageDescriptor:
    encryption_context: FileEncryptionContext
    file_name: str
    file_mime_type: str
    file_size: int
    plaintext_chunk_size: int
