import logging
import asyncio
from typing import Tuple, Optional, List, Set
from datetime import datetime

from src.exceptions import *
from dishka import AsyncContainer

from src.providers import AppProvider
from .state import AppState

from src.adapters.api.dao import (
    ContactHTTPDAO,
    MessageHTTPDAO
)

from src.adapters.api.service import (
    AuthHTTPService,
    ContactHTTPService,
    MessageHTTPService
)

from src.adapters.database.service import (
    LocalUserService,
    ContactService,
    MessageService
)

from src.adapters.database.dto import (
    LocalUserRequestDTO, LocalUserDTO,
    ContactRequestDTO, ContactDTO,
    MessageRequestDTO, MessageDTO
)

from src.adapters.encryption.service import (
    AbstractAES256Cipher,
    AbstractPasswordHasher,
    AbstractECDHCipher
)

from src.adapters.encryption.storage import EncryptedKeyStorage

class Container:
    def __init__(self, app_state: AppState, container: AsyncContainer):
        self.state = app_state
        self.container = container
        self.logger = logging.getLogger(__name__)

    async def setup_services(self) -> bool:
        try:
            async with self.container() as request_container:
                # httpx
                self.state.contact_http_dao = await request_container.get(ContactHTTPDAO)
                self.state.message_http_dao = await request_container.get(MessageHTTPDAO)

                self.state.auth_http_service = await request_container.get(AuthHTTPService)
                self.state.contact_http_service = await request_container.get(ContactHTTPService)
                self.state.message_http_service = await request_container.get(MessageHTTPService)
                # sqlalchemy
                self.state.local_user_service = await request_container.get(LocalUserService)
                self.state.contact_service = await request_container.get(ContactService)
                self.state.message_service = await request_container.get(MessageService)
                # cryptography and keyring storage
                self.state.aes_cipher = await request_container.get(AbstractAES256Cipher)
                self.state.ecdh_cipher = await request_container.get(AbstractECDHCipher)
                self.state.key_storage = await request_container.get(EncryptedKeyStorage)
                self.state.password_hasher = await request_container.get(AbstractPasswordHasher)

            # Check that all services are initialized
            required_services = [
                self.state.contact_http_dao,
                self.state.message_http_dao,
                self.state.auth_http_service,
                self.state.contact_http_service,
                self.state.message_http_service,
                self.state.local_user_service,
                self.state.contact_service,
                self.state.message_service,
                self.state.aes_cipher,
                self.state.ecdh_cipher,
                self.state.key_storage,
                self.state.password_hasher
            ]

            if any(service is None for service in required_services):
                return False, "Some services failed to initialize"

            self.state.auth_http_service.set_token(self.state.token)
            self.state.contact_http_dao.set_token(self.state.token)
            self.state.message_http_dao.set_token(self.state.token)

            return True, "All services initialized successfully"

        except Exception as e:
            error_msg = e
            self.logger.critical(f"Service setup failed: {error_msg}")
            return False, error_msg