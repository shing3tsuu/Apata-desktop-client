from pydantic import BaseModel, constr
from datetime import datetime
from typing import List

class LocalUserRequestDTO(BaseModel):
    server_user_id: int | None = None
    username: str | None = None
    hashed_password: str | None = None

class LocalUserDTO(LocalUserRequestDTO):
    id: int

class ContactRequestDTO(BaseModel):
    local_user_id: int | None = None
    server_user_id: int | None = None
    status: str | None = None
    username: str | None = None
    ecdh_public_key: str | None = None
    last_seen: datetime | None = None

class ContactDTO(ContactRequestDTO):
    id: int

class MessageRequestDTO(BaseModel):
    local_user_id: int
    server_message_id: int
    contact_id: int
    content: bytes
    timestamp: datetime
    type: str | None = None # "text", "image", "video", "audio", "file"
    is_outgoing: bool  # True - outgoing, False - incoming
    is_delivered: bool

class MessageDTO(MessageRequestDTO):
    id: int