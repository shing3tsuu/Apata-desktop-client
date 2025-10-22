import logging
import asyncio
from typing import Tuple, Optional, List, Set
from datetime import datetime

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

class LoadingManager:
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

    async def synchronize_contacts(self) -> bool:
        """
        Synchronize contacts with the server.
        - Get all contacts from server (new and updated, including new ecdh keys)
        - Compare with local contacts
        :return:
        """
        try:
            self.logger.info("Starting contact synchronization...")

            # Get all contacts from server with complete information
            server_contacts = await self.state.contact_http_service.get_contacts(
                self.state.user_id
            )

            if not server_contacts:
                self.logger.info("No contacts found on server")
                return True, "No contacts found on server"

            # Get local contacts for comparison
            local_contacts = await self.state.contact_service.get_contacts()
            local_contact_map = {contact.server_user_id: contact for contact in local_contacts}

            # Process each server contact
            for server_contact in server_contacts:
                local_contact = local_contact_map.get(server_contact.server_user_id)

                if local_contact:
                    # Update existing contact
                    await self.state.contact_service.update_contact(server_contact)
                    self.logger.debug(f"Updated contact: {server_contact.username}")
                else:
                    # Add new contact
                    await self.state.contact_service.add_contact(server_contact)
                    self.logger.info(f"Added new contact: {server_contact.username}")

                self.state.contacts_cache.append(
                    Contact(
                        server_user_id=server_contact.server_user_id,
                        username=server_contact.username,
                        ecdh_public_key=server_contact.ecdh_public_key,
                        status=server_contact.status,
                        last_seen=server_contact.last_seen,
                    )
                )

            # Remove local contacts that no longer exist on server
            server_contact_ids = {contact.server_user_id for contact in server_contacts}
            for local_contact in local_contacts:
                if local_contact.server_user_id not in server_contact_ids:
                    await self.state.contact_service.delete_contact(local_contact.id)
                    self.logger.info(f"Removed local contact: {local_contact.username}")

            self.logger.info(f"Successfully synchronized {len(server_contacts)} contacts")
            return True, "Contacts synchronized successfully"

        except Exception as e:
            error_msg = e
            self.logger.error(f"Contact synchronization failed: {error_msg}")
            return False, error_msg

    async def sync_message_history(self) -> bool:
        """
        Sync message history with the server.
        - Get all undelivered messages from server
        - Decrypt messages with old ecdh private key, to which the message was encrypted in the absence of the user
        - Compare with local messages
        :return:
        """
        try:
            self.logger.info("Starting message synchronization...")
            # Get contacts with their keys
            contacts = await self.state.contact_service.get_contacts()
            # Update keys state
            for contact in contacts:
                self.state.public_keys_cache.update({contact.server_user_id: contact.ecdh_public_key})
            # Get undelivered messages
            new_messages = await self.state.message_http_service.get_undelivered_messages(
                user_private_key=self.state.ecdh_private_key
            )
            if not new_messages:
                return True, "No new messages to synchronize"
            # Adding new messages to local storage and state
            for new_message in new_messages:
                self.logger.info(f"Adding new message from: {new_message.recipient_id} to local storage...")
                encrypted_message = await self.state.aes_cipher.encrypt(
                    new_message.message,
                    self.state.master_key
                )

                await self.state.message_service.add_message(
                    MessageRequestDTO(
                        server_message_id=new_message.id,
                        contact_id=new_message.sender_id,
                        content=encrypted_message,
                        timestamp=new_message.timestamp,
                        type=None,
                        is_outgoing=False,
                        is_delivered=True
                    )
                )
            return True, "Messages synchronized successfully"

        except Exception as e:
            error_msg = e
            self.logger.error(f"Get undelivered messages failed: {error_msg}")
            return False, error_msg

    async def rotate_keys(self) -> bool:
        try:
            self.logger.info("Rotating keys...")

            response = await self.state.auth_http_service.update_ecdh_key()
            ecdh_private_key = response["ecdh_private_key"]

            if not ecdh_private_key:
                return False, "Failed to rotate keys"

            self.state.key_storage.clear_ecdh_private_key(self.state.username)

            if not await self.state.key_storage.store_ecdh_private_key(
                    username=self.state.username,
                    ecdh_private_key=ecdh_private_key,
                    password=self.state.password,
            ):
                return False, "Failed to store ECDH private key"

            data = await self.state.auth_http_service.get_public_keys(self.state.user_id)

            self.state.update_ecdh_keys(
                ecdh_public_key=data["ecdh_public_key"],
                ecdh_private_key=ecdh_private_key,
            )

            return True, "Keys rotated successfully"
        except Exception as e:
            error_msg = e
            self.logger.error(f"Key rotation failed: {error_msg}")
            return False, error_msg