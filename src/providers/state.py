from uuid import UUID

from .cache import ChatCache, ContactCache

class AppState:
    def __init__(self):
        self._username: str | None = None
        self._local_user_id: UUID | None = None
        self._server_user_id: UUID | None = None
        self._password: str | None = None
        self._hashed_password: str | None = None
        self._master_key: bytes | None = None
        self._ed_public_key: str | None = None
        self._ed_private_key: str | None = None
        self._ecdh_public_key: str | None = None
        self._ecdh_private_key: str | None = None
        self._token: str | None = None
        self._websocket_connected = False
        self._active_server_chat_ids: set[UUID] | None = None
        self._contacts_cache: list[ContactCache] = []
        self._chats_cache: list[ChatCache] = []

    @property
    def contacts_cache(self) -> list[ContactCache]:
        return self._contacts_cache

    @contacts_cache.setter
    def contacts_cache(self, contacts: list[ContactCache]) -> None:
        self._contacts_cache = contacts

    @property
    def chats_cache(self) -> list[ChatCache]:
        return self._chats_cache

    @chats_cache.setter
    def chats_cache(self, chats: list[ChatCache]) -> None:
        self._chats_cache = chats

    @property
    def active_server_chat_ids(self) -> set[UUID] | None:
        return self._active_server_chat_ids

    @active_server_chat_ids.setter
    def active_server_chat_ids(self, chat_ids: set[UUID]) -> None:
        self._active_server_chat_ids = chat_ids

    @property
    def username(self) -> str | None:
        return self._username

    @username.setter
    def username(self, username: str) -> None:
        self._username = username

    @property
    def local_user_id(self) -> UUID | None:
        return self._local_user_id

    @local_user_id.setter
    def local_user_id(self, local_user_id: UUID | None) -> None:
        self._local_user_id = local_user_id

    @property
    def server_user_id(self) -> UUID | None:
        return self._server_user_id

    @server_user_id.setter
    def server_user_id(self, server_user_id: UUID | None) -> None:
        self._server_user_id = server_user_id

    @property
    def password(self) -> str | None:
        return self._password

    @password.setter
    def password(self, password: str) -> None:
        self._password = password

    @property
    def hashed_password(self) -> str | None:
        return self._hashed_password

    @hashed_password.setter
    def hashed_password(self, hashed_password: str) -> None:
        self._hashed_password = hashed_password

    @property
    def master_key(self) -> bytes | None:
        return self._master_key

    @master_key.setter
    def master_key(self, master_key: bytes | None) -> None:
        self._master_key = master_key

    @property
    def ed_public_key(self) -> str | None:
        return self._ed_public_key

    @ed_public_key.setter
    def ed_public_key(self, ed_public_key: str | None) -> None:
        self._ed_public_key = ed_public_key

    @property
    def ed_private_key(self) -> str | None:
        return self._ed_private_key

    @ed_private_key.setter
    def ed_private_key(self, ed_private_key: str | None) -> None:
        self._ed_private_key = ed_private_key

    @property
    def ecdh_public_key(self) -> str | None:
        return self._ecdh_public_key

    @ecdh_public_key.setter
    def ecdh_public_key(self, ecdh_public_key: str | None) -> None:
        self._ecdh_public_key = ecdh_public_key

    @property
    def ecdh_private_key(self) -> str | None:
        return self._ecdh_private_key

    @ecdh_private_key.setter
    def ecdh_private_key(self, ecdh_private_key: str | None) -> None:
        self._ecdh_private_key = ecdh_private_key

    @property
    def token(self) -> str | None:
        return self._token

    @token.setter
    def token(self, token: str) -> None:
        self._token = token

    @token.deleter
    def token(self) -> None:
        self._token = None

    @property
    def websocket_connected(self) -> bool:
        return self._websocket_connected

    @websocket_connected.setter
    def websocket_connected(self, connected: bool) -> None:
        self._websocket_connected = connected

    def clear_state(self) -> None:
        self._contacts_cache = []
        self._chats_cache = []
        self._username = None
        self._local_user_id = None
        self._server_user_id = None
        self._password = None
        self._master_key = None
        self._ed_public_key = None
        self._ed_private_key = None
        self._ecdh_public_key = None
        self._ecdh_private_key = None
        self._token = None
        self._websocket_connected = False
        self._active_server_chat_ids = None
