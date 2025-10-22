import logging
import asyncio
from typing import Tuple, Optional, List, Set
from datetime import datetime

from pyexpat.errors import messages
from src.exceptions import *
from dishka import make_async_container

from src.providers import AppProvider
from src.presentation.pages import AppState, Contact, Message

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

class MessengerManager:
    def __init__(self, app_state):
        self.state = app_state
        self.logger = logging.getLogger(__name__)

    async def setup_services(self) -> bool:
        try:
            self.state._container = make_async_container(AppProvider())

            async with self.state._container() as request_container:
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

    async def get_contacts(self) -> list[Contact]:
        """
        Returns a list of actual contacts from the cache
        :return:
        """
        return self.state.contacts_cache

    async def get_messages(self, contact_id: int) -> list[dict]:
        """
        Get messages for a specific contact from the database (decrypted)
        :param contact_id:
        :return:
        """
        try:
            # Get messages from the database
            self.logger.info(f"Getting messages for contact {contact_id}")
            db_messages = await self.state.message_service.get_messages(contact_id=contact_id, limit=50)

            # If there are no messages, return a welcome message
            if not db_messages:
                self.logger.info("No messages found for contact")
                return [{
                    "id": 0,
                    "text": "Напишите свое первое сообщение!",
                    "is_outgoing": False,
                    "timestamp": ""
                }]

            # Decrypt and convert to the required format
            messages = []
            for message in db_messages:
                self.logger.info(f"Start decrypting {len(db_messages)} messages content")
                try:
                    decrypted_content = await self.state.aes_cipher.decrypt(
                        ciphertext=message.content,
                        key=self.state.master_key
                    )

                    messages.append({
                        "id": message.server_message_id,
                        "text": decrypted_content,
                        "is_outgoing": message.is_outgoing,
                        "timestamp": self._format_timestamp(message.timestamp)
                    })

                except Exception as e:
                    self.logger.error(f"Error decrypting message: {e}", exc_info=True,)
                    continue

            return messages
        except Exception as e:
            self.logger.error(f"Error fetching messages: {e}", exc_info=True)
            return []

    @staticmethod
    def _format_timestamp(timestamp):
        """
        Formats a timestamp for the UI
        :param timestamp:
        :return:
        """
        if not timestamp:
            return ""

        if isinstance(timestamp, str):
            return timestamp

        # Format datetime in a readable format
        now = datetime.utcnow()
        if isinstance(timestamp, datetime):
            diff = now - timestamp
            if diff.total_seconds() < 60:
                return "just now"
            elif diff.total_seconds() < 3600:
                minutes = int(diff.total_seconds() / 60)
                return f"{minutes} min ago"
            else:
                return timestamp.strftime("%H:%M")

        return str(timestamp)

    async def send_message(self, contact_id: int, text: str) -> bool:
        # TODO: Realize sending messages (adding in local db, send to server, start message polling for possible response)
        self.logger.info(f"Sending message to {contact_id}: {text}")
        return True