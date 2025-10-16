from pydantic import BaseModel, constr
from datetime import datetime
from typing import List

class LocalUserRequestDTO(BaseModel):
    server_user_id: int
    username: str
    hashed_password: str

class LocalUserDTO(LocalUserRequestDTO):
    id: int

class ContactRequestDTO(BaseModel):
    server_user_id: int
    status: str | None = None
    username: str
    ecdh_public_key: str

class ContactDTO(ContactRequestDTO):
    id: int

class MessageRequestDTO(BaseModel):
    server_message_id: int
    contact_id: int
    content: bytes
    timestamp: datetime
    type: str | None = None # "text", "image", "video", "audio", "file"
    is_outgoing: bool  # True - outgoing, False - incoming
    is_delivered: bool

class MessageDTO(MessageRequestDTO):
    id: int