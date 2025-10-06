from typing import Optional, Dict, Any
from dataclasses import dataclass

@dataclass
class AppState:
    """Улучшенный класс состояния приложения"""
    token: Optional[str] = None
    username: Optional[str] = None
    user_id: Optional[int] = None
    ecdsa_private_key: Optional[str] = None
    ecdh_private_key: Optional[str] = None
    is_authenticated: bool = False

    # Сервисы
    auth_service: Any = None
    password_hasher: Any = None
    local_user_dao: Any = None
    key_storage: Any = None
    encryption_service: Any = None
    message_service: Any = None

    # Кэши
    public_keys_cache: Dict[int, str] = None
    _container: Any = None  # DI контейнер

    def __post_init__(self):
        if self.public_keys_cache is None:
            self.public_keys_cache = {}

    def update_from_login(self, username: str, ecdsa_private_key: str,
                         ecdh_private_key: str, token: str, user_id: int):
        """Обновить состояние после успешной аутентификации"""
        self.username = username
        self.ecdsa_private_key = ecdsa_private_key
        self.ecdh_private_key = ecdh_private_key
        self.token = token
        self.user_id = user_id
        self.is_authenticated = True

    def clear(self):
        """Очистить состояние при выходе"""
        self.token = None
        self.username = None
        self.user_id = None
        self.ecdsa_private_key = None
        self.ecdh_private_key = None
        self.is_authenticated = False
        self.public_keys_cache.clear()

    def get_session_info(self) -> Dict[str, Any]:
        return {
            "username": self.username,
            "user_id": self.user_id,
            "is_authenticated": self.is_authenticated
        }