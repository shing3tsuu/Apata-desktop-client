from pydantic import BaseModel, constr, validator
from datetime import datetime
from typing import List

class LocalUserRequestDTO(BaseModel):
    server_user_id: int
    username: str
    ecdsa_public_key: str
    hashed_password: str
    timezone: int | None = None

class UpdateLocalUserRequestDTO(BaseModel):
    id: int
    server_user_id: int | None = None
    username: str | None = None
    ecdsa_public_key: str | None = None
    hashed_password: str | None = None
    timezone: int | None = None

class LocalUserDTO(LocalUserRequestDTO):
    id: int

class ContactRequestDTO(BaseModel):
    local_user_id: int
    server_user_id: int
    status: str
    username: str
    ecdsa_public_key: str
    ecdh_public_key: str
    last_seen: datetime | None = None
    online: bool | None = False

class AddContactRequestDTO(BaseModel):
    local_user_id: int
    server_user_id: int
    status: str
    username: str
    ecdsa_public_key: str
    ecdh_public_key: str
    last_seen: datetime | None = datetime.utcnow()
    online: bool | None = False

class UpdateContactRequestDTO(BaseModel):
    local_user_id: int
    server_user_id: int | None = None
    status: str | None = None
    username: str | None = None
    ecdsa_public_key: str | None = None
    ecdh_public_key: str | None = None
    last_seen: datetime | None = None
    online: bool | None = None

class ContactDTO(ContactRequestDTO):
    id: int

class MessageRequestDTO(BaseModel):
    local_user_id: int
    server_message_id: int
    contact_id: int
    content: str
    content_type: str | None = None  # "text", "image", "video", "audio", "file"
    timestamp: datetime
    is_outgoing: bool  # True - outgoing, False - incoming
    is_delivered: bool

class MessageDTO(MessageRequestDTO):
    id: int