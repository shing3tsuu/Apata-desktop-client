from typing import Optional, Dict, Any
from dataclasses import dataclass, field
from dishka import AsyncContainer
from datetime import datetime

@dataclass(kw_only=True)
class Contact:
    server_user_id: int
    username: str
    ecdh_public_key: str
    last_seen: datetime
    online: bool

    status: str | None = field(default=None)

@dataclass(kw_only=True)
class Message:
    server_message_id: int
    contact_id: int
    content: bytes
    timestamp: datetime
    is_outgoing: bool  # True - outgoing, False - incoming
    is_delivered: bool

    type: str | None = field(default=None)  # "text", "image", "video", "audio", "file"

@dataclass
class AppState:
    username: str | None = None
    local_user_id: int | None = None
    server_user_id: int | None = None
    password: str | None = None
    master_key: bytes | None = None
    ecdsa_private_key: str | None = None
    ecdh_public_key: str | None = None
    ecdh_private_key: str | None = None
    token: str | None = None
    is_authenticated: bool = False

    def update_from_login(
            self,
            username: str,
            local_user_id: int,
            server_user_id: int,
            password: str,
            master_key: bytes,
            ecdsa_private_key: str,
            ecdh_public_key: str,
            ecdh_private_key: str,
            token: str,
    ):
        self.username = username
        self.local_user_id = local_user_id
        self.server_user_id = server_user_id
        self.password = password
        self.master_key = master_key
        self.ecdsa_private_key = ecdsa_private_key
        self.ecdh_public_key = ecdh_public_key
        self.ecdh_private_key = ecdh_private_key
        self.token = token
        self.is_authenticated = True

    def update_ecdh_public(self, ecdh_public_key: str):
        self.ecdh_public_key = ecdh_public_key

    def update_ecdh_keys(self, ecdh_public_key: str, ecdh_private_key: str):
        self.ecdh_public_key = ecdh_public_key
        self.ecdh_private_key = ecdh_private_key

    def clear(self):
        self.token = None
        self.username = None
        self.local_user_id = None
        self.server_user_id = None
        self.master_key = None
        self.ecdsa_private_key = None
        self.ecdh_public_key = None
        self.ecdh_private_key = None
        self.is_authenticated = False

    def get_session_info(self) -> dict[str, Any]:
        return {
            "username": self.username,
            "local_user_id": self.local_user_id,
            "server_user_id": self.server_user_id,
            "is_authenticated": self.is_authenticated
        }