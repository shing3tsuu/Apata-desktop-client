from typing import Optional, Dict, Any
from dataclasses import dataclass
from dishka import AsyncContainer
from pydantic import BaseModel
from datetime import datetime

from src.adapters.api.service import (
    AuthHTTPService,
    ContactHTTPService,
    MessageHTTPService
)

from src.adapters.encryption.service import (
    AbstractAES256Cipher,
    AbstractECDHCipher,
    AbstractPasswordHasher
)

from src.adapters.encryption.storage import EncryptedKeyStorage

from src.adapters.database.service import (
    LocalUserService,
    ContactService,
    MessageService
)

from src.adapters.database.dto import MessageRequestDTO

class Message(BaseModel):
    server_message_id: int
    contact_id: int
    content: bytes
    timestamp: datetime
    type: str | None = None  # "text", "image", "video", "audio", "file"
    is_outgoing: bool  # True - outgoing, False - incoming
    is_delivered: bool

@dataclass
class AppState:
    token: str | None = None
    username: str | None = None
    user_id: int | None = None
    master_key: bytes | None = None
    ecdsa_private_key: str | None = None
    ecdh_private_key: str | None = None
    is_authenticated: bool = False

    auth_http_service: AuthHTTPService = None
    contact_http_service: ContactHTTPService = None
    message_http_service: MessageHTTPService = None

    aes_cipher: AbstractAES256Cipher = None
    password_hasher: AbstractPasswordHasher = None
    key_storage: EncryptedKeyStorage = None

    local_user_service: LocalUserService = None
    contact_service: ContactService = None
    message_service: MessageService = None

    public_keys_cache: dict[int, str] = None
    messages: list[Message] = None
    _container: AsyncContainer = None

    def __post_init__(self):
        if self.public_keys_cache is None:
            self.public_keys_cache = {}
        if self.messages is None:
            self.messages = []

    def update_from_login(
            self,
            master_key: bytes,
            username: str,
            ecdsa_private_key: str,
            ecdh_private_key: str,
            token: str,
            user_id: int
    ):
        self.username = username
        self.master_key = master_key
        self.ecdsa_private_key = ecdsa_private_key
        self.ecdh_private_key = ecdh_private_key
        self.token = token
        self.user_id = user_id
        self.is_authenticated = True

    def update_ecdh_key(self, ecdh_private_key: str):
        self.ecdh_private_key = ecdh_private_key

    def clear(self):
        self.token = None
        self.username = None
        self.user_id = None
        self.master_key = None
        self.ecdsa_private_key = None
        self.ecdh_private_key = None
        self.is_authenticated = False
        self.public_keys_cache.clear()

    def get_session_info(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "user_id": self.user_id,
            "is_authenticated": self.is_authenticated
        }