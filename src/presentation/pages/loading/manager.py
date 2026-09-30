import logging
from datetime import datetime
from uuid import UUID

from dishka import AsyncContainer

from src.adapters.api.service import (
    AuthHTTPService,
    ContactHTTPService,
    MessageHTTPService,
)
from src.adapters.database.dto import (
    AddContactDTO,
    AddMessageTextDTO,
    RequestContactDTO,
)
from src.adapters.database.service import (
    ContactService,
    MessageService,
)
from src.adapters.encryption.storage import EncryptedKeyStorage
from src.presentation.pages import AppState, Contact


class LoadingManager:
    def __init__(self, app_state: AppState, container: AsyncContainer):
        self._state = app_state
        self._container = container
        self._logger = logging.getLogger(__name__)

    async def synchronize_contacts(self) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                contact_http_service = await request_container.get(ContactHTTPService)
                contact_http_service.token = self._state.require_token
                contact_service = await request_container.get(ContactService)

                self._logger.info("Starting contact synchronization...")

                local_contacts = await contact_service.get_contacts(
                    local_user_id=self._state.require_local_user_id
                )

                # Get all contacts from server with complete information
                server_contacts = await contact_http_service.get_contacts(
                    local_user_id=self._state.require_local_user_id,
                    server_user_id=self._state.require_server_user_id,
                )

                local_contact_map = {
                    contact.server_user_id: contact for contact in local_contacts
                }
                # Process each server contact
                for server_contact in server_contacts:
                    self._state.update_contacts(
                        Contact(
                            server_user_id=server_contact.server_user_id,
                            username=server_contact.username,
                            ecdsa_public_key=server_contact.ed_public_key,
                            ecdh_public_key=server_contact.ecdh_public_key,
                            last_seen=server_contact.last_seen or datetime.utcnow(),
                            online=bool(server_contact.online),
                            status=server_contact.status,
                        )
                    )
                    local_contact = local_contact_map.get(server_contact.server_user_id)
                    if local_contact:
                        # Update existing contact
                        await contact_service.update_contact(
                            RequestContactDTO(
                                local_user_id=self._state.require_local_user_id,
                                server_user_id=server_contact.server_user_id,
                                username=server_contact.username,
                                ecdh_public_key=server_contact.ecdh_public_key,
                                status=server_contact.status,
                                last_seen=server_contact.last_seen,
                                online=server_contact.online,
                            )
                        )
                        self._logger.info(f"Updated contact: {server_contact.username}")
                    else:
                        # Add new contact
                        await contact_service.add_contact(
                            AddContactDTO(
                                local_user_id=self._state.require_local_user_id,
                                server_user_id=server_contact.server_user_id,
                                username=server_contact.username,
                                ed_public_key=server_contact.ed_public_key,
                                ecdh_public_key=server_contact.ecdh_public_key,
                                status=server_contact.status,
                                last_seen=server_contact.last_seen,
                                online=server_contact.online,
                            )
                        )
                        self._logger.info(
                            f"Added new contact: {server_contact.username}"
                        )

                # Remove local contacts that no longer exist on server (need to test)
                # server_contact_ids = {contact.server_user_id for contact in server_contacts}
                # for local_contact in local_contacts:
                #    if local_contact.server_user_id not in server_contact_ids:
                #        await contact_service.delete_contact(local_contact.id)
                #        self._logger.info(f"Removed local contact: {local_contact.username}")

                self._logger.info(
                    f"Successfully synchronized {len(server_contacts)} contacts"
                )
                return True, "Contacts synchronized successfully"

        except Exception as e:
            error_msg = str(e)
            self._logger.error(f"Contact synchronization failed: {error_msg}")
            return False, error_msg

    async def sync_message_history(self) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                message_http_service = await request_container.get(MessageHTTPService)
                message_http_service.token = self._state.require_token
                contact_service = await request_container.get(ContactService)
                message_service = await request_container.get(MessageService)

                contacts = await contact_service.get_contacts(
                    self._state.require_local_user_id
                )
                ed_dict = {}

                for contact in contacts:
                    if contact.ed_public_key:
                        ed_dict[contact.server_user_id] = contact.ed_public_key

                self._logger.info("Starting message synchronization...")

                new_messages = await message_http_service.get_undelivered_messages(
                    ed_dict=ed_dict,
                    recipient_ecdh_private_key=self._state.require_ecdh_private_key,
                )

                if not new_messages:
                    return True, "No new messages to synchronize"

                self._logger.info(f"Received {len(new_messages)} new messages")
                message_service.master_key = self._state.require_master_key
                for new_message in new_messages:
                    self._logger.info(
                        f"Adding new message from: {new_message['sender_id']} to local storage..."
                    )

                    sender_id = UUID(str(new_message["sender_id"]))
                    contact = await contact_service.get_contact_by_server_user_id(
                        local_user_id=self._state.require_local_user_id,
                        server_user_id=sender_id,
                    )
                    if contact is None:
                        self._logger.warning(
                            "Cannot persist message from unknown sender %s", sender_id
                        )
                        continue

                    message_id = UUID(str(new_message["id"]))

                    await message_service.add_message_text(
                        AddMessageTextDTO(
                            local_user_id=self._state.require_local_user_id,
                            server_message_id=message_id,
                            contact_id=contact.id,
                            content=new_message["decrypted_content"],
                            content_type=new_message.get("content_type", "text"),
                            is_outgoing=False,
                            is_delivered=True,
                        )
                    )
                self._logger.info(
                    f"Successfully synchronized {len(new_messages)} messages"
                )
                return True, f"Successfully synchronized {len(new_messages)} messages"

        except Exception as e:
            error_msg = str(e)
            self._logger.error(f"Get undelivered messages failed: {error_msg}")
            return False, error_msg

    async def rotate_keys(self) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)
                auth_http_service.token = self._state.require_token
                key_storage = await request_container.get(EncryptedKeyStorage)

                self._logger.info("Rotating keys...")

                (
                    ecdh_private_key,
                    ecdh_public_key,
                ) = await auth_http_service.update_ecdh_key(
                    self._state.require_ecdsa_private_key
                )

                if not ecdh_private_key:
                    return False, "Failed to rotate keys"

                key_storage.clear_ecdh_private_key(self._state.require_username)

                success = await key_storage.store_ecdh_private_key(
                    username=self._state.require_username,
                    ecdh_private_key=ecdh_private_key,
                    password=self._state.require_password,
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
            error_msg = str(e)
            self._logger.error(f"Key rotation failed: {error_msg}")
            return False, error_msg
