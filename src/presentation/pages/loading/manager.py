import logging
import asyncio
from typing import Tuple, Optional, List, Set
from datetime import datetime

from src.exceptions import *
from dishka import make_async_container

from src.providers import AppProvider
from src.presentation.pages import AppState

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

from src.adapters.encryption.service import AbstractAES256Cipher, AbstractPasswordHasher
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
                self.state.auth_http_service = await request_container.get(AuthHTTPService)
                self.state.contact_http_service = await request_container.get(ContactHTTPService)
                self.state.message_http_service = await request_container.get(MessageHTTPService)
                # sqlalchemy
                self.state.local_user_service = await request_container.get(LocalUserService)
                self.state.contact_service = await request_container.get(ContactService)
                self.state.message_service = await request_container.get(MessageService)
                # cryptography and keyring storage
                self.state.aes_cipher = await request_container.get(AbstractAES256Cipher)
                self.state.key_storage = await request_container.get(EncryptedKeyStorage)
                self.state.password_hasher = await request_container.get(AbstractPasswordHasher)

            # Check that all services are initialized
            required_services = [
                self.state.auth_http_service,
                self.state.contact_http_service,
                self.state.message_http_service,
                self.state.password_hasher,
                self.state.local_user_service,
                self.state.key_storage
            ]

            if any(service is None for service in required_services):
                self.logger.error("Some services failed to initialize")
                return False

            self.logger.info("All services initialized successfully")
            return True

        except Exception as e:
            self.logger.error(f"Service setup failed: {e}")
            return False

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
                self.state.user_id,
                self.state.token
            )

            if not server_contacts:
                self.logger.info("No contacts found on server")
                return True

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

            # Remove local contacts that no longer exist on server
            server_contact_ids = {contact.server_user_id for contact in server_contacts}
            for local_contact in local_contacts:
                if local_contact.server_user_id not in server_contact_ids:
                    await self.state.contact_service.delete_contact(local_contact.id)
                    self.logger.info(f"Removed local contact: {local_contact.username}")

            self.logger.info(f"Successfully synchronized {len(server_contacts)} contacts")
            return True

        except Exception as e:
            self.logger.error(f"Contact synchronization failed: {e}")
            return False

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
                user_private_key=self.state.ecdh_private_key,
                sender_public_keys=self.state.public_keys_cache,
                token=self.state.token
            )
            if not new_messages:
                self.logger.info("No new messages to synchronize")
                return True
            # Adding new messages to local storage and state
            for new_message in new_messages:
                self.logger.info(f"Adding new message from: {new_message.recipient_id} to local storage...")
                self.state.messages.append(MessageRequestDTO(
                        server_message_id=new_message.id,
                        contact_id=new_message.sender_id,
                        content=new_message.message,
                        timestamp=new_message.timestamp,
                        type=None,
                        is_outgoing=False,
                        is_delivered=True
                    ))
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
            return True
        except Exception as e:
            self.logger.error(f"Get undelivered messages failed: {e}")
            return False

    async def rotate_keys(self) -> bool:
        try:
            self.logger.info("Rotating keys...")
            self.logger.info("Deleting old ECDH private key...")
            self.key_storage.clear_ecdh_key(self.state.username)

            return True
        except Exception as e:
            self.logger.error(f"Key rotation failed: {e}")
            return False