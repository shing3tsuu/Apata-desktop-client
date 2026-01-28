import logging
import asyncio
from typing import Tuple, Optional, List, Set
from datetime import datetime

from src.exceptions import *
from dishka import make_async_container, AsyncContainer

from src.providers import AppProvider
from src.presentation.pages import AppState, Contact, Message
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
from src.adapters.encryption.dao import (
    Abstract256Cipher,
    AbstractPasswordHasher,
    AbstractECDHCipher,
    AbstractECDSASignature
)
from src.adapters.encryption.storage import EncryptedKeyStorage

class LoadingManager:
    def __init__(self, app_state: AppState, container: AsyncContainer):
        self._state = app_state
        self._container = container
        self._logger = logging.getLogger(__name__)

    async def synchronize_contacts(self) -> bool:
        try:
            async with self._container() as request_container:
                contact_http_service = await request_container.get(ContactHTTPService)
                contact_http_service.set_token(self._state.token)
                local_user_service = await request_container.get(LocalUserService)
                contact_service = await request_container.get(ContactService)

                self._logger.info("Starting contact synchronization...")

                ecdsa_dict = {}

                local_contacts = await contact_service.get_contacts(local_user_id=self._state.local_user_id)

                for contact in local_contacts:
                    if contact.ecdsa_public_key:
                        ecdsa_dict[contact.server_user_id] = contact.ecdsa_public_key

                # Get all contacts from server with complete information
                server_contacts = await contact_http_service.get_contacts(
                    local_user_id=self._state.local_user_id,
                    server_user_id=self._state.server_user_id,
                    ecdsa_dict=ecdsa_dict
                )

                local_contact_map = {contact.server_user_id: contact for contact in local_contacts}
                # Process each server contact
                for server_contact in server_contacts:
                    self._state.update_contacts(
                        Contact(
                            server_user_id=server_contact.server_user_id,
                            username=server_contact.username,
                            ecdh_public_key=server_contact.ecdh_public_key,
                            last_seen=server_contact.last_seen,
                            online=server_contact.online,
                            status=server_contact.status
                        )
                    )
                    local_contact = local_contact_map.get(server_contact.server_user_id)
                    if local_contact:
                        # Update existing contact
                        await contact_service.update_contact(
                            ContactRequestDTO(
                                local_user_id=self._state.local_user_id,
                                server_user_id=server_contact.server_user_id,
                                username=server_contact.username,
                                ecdh_public_key=server_contact.ecdh_public_key,
                                status=server_contact.status,
                                last_seen=server_contact.last_seen,
                                online=server_contact.online
                            )
                        )
                        self._logger.info(f"Updated contact: {server_contact.username}")
                    else:
                        # Add new contact
                        await contact_service.add_contact(
                            ContactRequestDTO(
                                local_user_id=self._state.local_user_id,
                                server_user_id=server_contact.server_user_id,
                                username=server_contact.username,
                                ecdsa_public_key=server_contact.ecdsa_public_key,
                                ecdh_public_key=server_contact.ecdh_public_key,
                                status=server_contact.status,
                                last_seen=server_contact.last_seen,
                                online=server_contact.online
                            )
                        )
                        self._logger.info(f"Added new contact: {server_contact.username}")

                # Remove local contacts that no longer exist on server (need to test)
                #server_contact_ids = {contact.server_user_id for contact in server_contacts}
                #for local_contact in local_contacts:
                #    if local_contact.server_user_id not in server_contact_ids:
                #        await contact_service.delete_contact(local_contact.id)
                #        self._logger.info(f"Removed local contact: {local_contact.username}")

                self._logger.info(f"Successfully synchronized {len(server_contacts)} contacts")
                return True, "Contacts synchronized successfully"

        except Exception as e:
            error_msg = e
            self._logger.error(f"Contact synchronization failed: {error_msg}")
            return False, error_msg

    async def sync_message_history(self) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                message_http_service = await request_container.get(MessageHTTPService)
                message_http_service.set_token(self._state.token)
                contact_service = await request_container.get(ContactService)
                message_service = await request_container.get(MessageService)
                aes_cipher = await request_container.get(AbstractAES256Cipher)

                contacts = await contact_service.get_contacts(self._state.local_user_id)
                ecdsa_dict = {}

                for contact in contacts:
                    if contact.ecdsa_public_key:
                        ecdsa_dict[contact.server_user_id] = contact.ecdsa_public_key

                self._logger.info("Starting message synchronization...")

                new_messages = await message_http_service.get_undelivered_messages(
                    ecdsa_dict=ecdsa_dict,
                    recipient_ecdh_private_key=self._state.ecdh_private_key
                )

                if new_messages is [] or None:
                    return True, "No new messages to synchronize"

                self._logger.info(f"Received {len(new_messages)} new messages")

                for new_message in new_messages:
                    self._logger.info(f"Adding new message from: {new_message['sender_id']} to local storage...")

                    encrypted_message = await aes_cipher.encrypt(
                        new_message['decrypted_content'],
                        self._state.master_key
                    )

                    await message_service.add_message(
                        MessageRequestDTO(
                            local_user_id=self._state.local_user_id,
                            server_message_id=new_message['id'],
                            contact_id=new_message['sender_id'],
                            content=encrypted_message,
                            content_type=new_message.get('content_type'),
                            timestamp=new_message.get('timestamp', datetime.utcnow()),
                            is_outgoing=False,
                            is_delivered=True
                        )
                    )

                self._logger.info(f"Successfully synchronized {len(new_messages)} messages")
                return True, f"Successfully synchronized {len(new_messages)} messages"

        except Exception as e:
            error_msg = str(e)
            self._logger.error(f"Get undelivered messages failed: {error_msg}")
            return False, error_msg

    async def rotate_keys(self) -> bool:
        try:
            async with self._container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)
                auth_http_service.set_token(self._state.token)
                key_storage = await request_container.get(EncryptedKeyStorage)

                self._logger.info("Rotating keys...")

                ecdh_private_key, ecdh_public_key = await auth_http_service.update_ecdh_key(self._state.ecdsa_private_key)

                if not ecdh_private_key:
                    return False, "Failed to rotate keys"

                key_storage.clear_ecdh_private_key(self._state.username)

                success = await key_storage.store_ecdh_private_key(
                    username=self._state.username,
                    ecdh_private_key=ecdh_private_key,
                    password=self._state.password,
                )

                if not success:
                    return False, "Failed to store ECDH private key"

                self._state.update_ecdh_keys(
                    ecdh_public_key=ecdh_public_key,
                    ecdh_private_key=ecdh_private_key,
                )

                self._logger.info("Keys rotated successfully")
                return True, "Keys rotated successfully"
        except Exception as e:
            error_msg = e
            self._logger.error(f"Key rotation failed: {error_msg}")
            return False, error_msg