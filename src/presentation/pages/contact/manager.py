import logging
import asyncio
from typing import Tuple, Optional, List, Set
from datetime import datetime

from pyexpat.errors import messages
from src.exceptions import *
from dishka import AsyncContainer

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
    AbstractECDHCipher
)
from src.adapters.encryption.storage import EncryptedKeyStorage

class ContactManager:
    def __init__(self, app_state: AppState, container: AsyncContainer):
        self._state = app_state
        self._container = container
        self._logger = logging.getLogger(__name__)

    async def find_contacts(self, username: str) -> list[Contact]:
        try:
            async with self._container() as request_container:
                contact_http_service = await request_container.get(ContactHTTPService)
                contact_http_service.set_token(self._state.token)

                self._logger.info(f"Searching for contacts with username: {username}")

                contacts = await contact_http_service.search_users(username)
                return [
                    Contact(
                        server_user_id=contact.get("id", None),
                        username=contact.get("username", None),
                        ecdh_public_key=contact.get("ecdh_public_key", None),
                        last_seen=contact.get("last_seen", None),
                        online=contact.get("online", None),
                    ) for contact in contacts
                ]
        except Exception as e:
            self._logger.error("Error searching contacts: %s", e)
            return []

    async def send_request(self, contact_id: int) -> bool:
        try:
            async with self._container() as request_container:
                contact_http_service = await request_container.get(ContactHTTPService)
                contact_http_service.set_token(self._state.token)
                contact_service = await request_container.get(ContactService)

                contacts = await contact_service.get_contacts(self._state.local_user_id)
                if contact_id in [c.server_user_id for c in contacts]:
                    raise ContactAlreadyExistsError(f"Contact with id {contact_id} already exists")

                self._logger.info(f"Sending request to contact with id: {contact_id}")

                request = await contact_http_service.send_contact_request(
                    receiver_id=contact_id
                )
                if request.get('id') == contact_id:
                    result = await contact_service.add_contact(
                        ContactRequestDTO(
                            local_user_id=self._state.local_user_id,
                            server_user_id=request['id'],
                            status=request['status'],
                            username=request['username'],
                            ecdh_public_key=request['ecdh_public_key'],
                            last_seen=request['last_seen'],
                            online=request['online'],
                        )
                    )
                    if result.id:
                        return True
                    else:
                        return False
                else:
                    self._logger.error(f"Error sending request to contact with id: {contact_id}")
                    return False
        except Exception as e:
            self._logger.error(f"Error sending request to contact with id: {contact_id}, error: {e}")
            return False

    async def accept_request(self, contact_id: int) -> bool:
        try:
            async with self._container() as request_container:
                contact_http_service = await request_container.get(ContactHTTPService)
                contact_http_service.set_token(self._state.token)
                contact_service = await request_container.get(ContactService)

                request = await contact_http_service.accept_contact_request(
                    receiver_id=contact_id
                )

                if request is not None:
                    result = await contact_service.update_contact(
                        ContactRequestDTO(
                            local_user_id=self._state.local_user_id,
                            server_user_id=contact_id,
                            status="accepted",
                        )
                    )
                    if result.id:
                        return True
                    else:
                        return False
                else:
                    self._logger.error(f"Error accepted request to contact with id: {contact_id}")
                    return False
        except Exception as e:
            self._logger.error(f"Error accepting request from contact with id: {contact_id}, error: {e}")
            return False

    async def reject_request(self, contact_id: int) -> bool:
        try:
            async with self._container() as request_container:
                contact_http_service = await request_container.get(ContactHTTPService)
                contact_http_service.set_token(self._state.token)
                contact_service = await request_container.get(ContactService)

                request = await contact_http_service.reject_contact_request(
                    receiver_id=contact_id
                )

                if request is not None:
                    result = await contact_service.update_contact(
                        ContactRequestDTO(
                            local_user_id=self._state.local_user_id,
                            server_user_id=contact_id,
                            status="rejected",
                        )
                    )
                    if result.id:
                        return True
                    else:
                        return False
                else:
                    self._logger.error(f"Error rejecting request to contact with id: {contact_id}")
                    return False
        except Exception as e:
            self._logger.error(f"Error rejecting request from contact with id: {contact_id}, error: {e}")
            return False

    async def get_pending_requests(self) -> list[Contact]:
        try:
            async with self._container() as request_container:
                contact_http_service = await request_container.get(ContactHTTPService)
                contact_http_service.set_token(self._state.token)
                contact_service = await request_container.get(ContactService)

                contacts = await contact_service.get_contacts(self._state.local_user_id)
                pending_contacts = [c for c in contacts if getattr(c, 'status', None) == 'pending']

                return [
                    Contact(
                        server_user_id=contact.server_user_id,
                        username=contact.username,
                        ecdh_public_key=contact.ecdh_public_key,
                        last_seen=contact.last_seen,
                        online=contact.online,
                        status="pending"
                    ) for contact in pending_contacts
                ]
        except Exception as e:
            self._logger.error(f"Error getting pending requests: {e}")
            return []

    async def get_blacklist(self) -> list[Contact]:
        try:
            async with self._container() as request_container:
                contact_service = await request_container.get(ContactService)

                contacts = await contact_service.get_contacts(self._state.local_user_id)
                rejected_contacts = [c for c in contacts if getattr(c, 'status', None) == 'rejected']

                return [
                    Contact(
                        server_user_id=contact.server_user_id,
                        username=contact.username,
                        ecdh_public_key=contact.ecdh_public_key,
                        last_seen=contact.last_seen,
                        online=contact.online,
                        status="rejected"
                    ) for contact in rejected_contacts
                ]
        except Exception as e:
            self._logger.error(f"Error getting blacklist: {e}")
            return []

    async def remove_contact(self, contact_id: int) -> bool:
        try:
            async with self._container() as request_container:
                contact_http_service = await request_container.get(ContactHTTPService)
                contact_http_service.set_token(self._state.token)
                contact_service = await request_container.get(ContactService)

                request = await contact_http_service.reject_contact_request(
                    receiver_id=contact_id
                )
                if request:
                    await contact_service.update_contact(
                        ContactRequestDTO(
                            local_user_id=self._state.local_user_id,
                            contact_id=contact_id,
                            status="rejected"
                        )
                    )
                    return True
                return False
        except Exception as e:
            self._logger.error(f"Error removing contact {contact_id}: {e}")
            return False

    async def synchronize_contacts(self) -> bool:
        try:
            async with self._container() as request_container:
                contact_http_service = await request_container.get(ContactHTTPService)
                contact_http_service.set_token(self._state.token)
                contact_service = await request_container.get(ContactService)

                self._logger.info("Starting contact synchronization...")

                # Get all contacts from server with complete information
                server_contacts = await contact_http_service.get_contacts(server_user_id=self._state.server_user_id)
                if not server_contacts:
                    self._logger.info("No contacts found on server")
                    return True, "No contacts found on server"
                # Get local contacts for comparison
                local_contacts = await contact_service.get_contacts(
                    local_user_id=self._state.local_user_id
                )
                local_contact_map = {contact.server_user_id: contact for contact in local_contacts}
                # Process each server contact
                for server_contact in server_contacts:
                    self._state.clear_contacts()
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
                                ecdh_public_key=server_contact.ecdh_public_key,
                                status=server_contact.status,
                                last_seen=server_contact.last_seen,
                                online=server_contact.online
                            )
                        )
                        self._logger.info(f"Added new contact: {server_contact.username}")

                # Remove local contacts that no longer exist on server
                server_contact_ids = {contact.server_user_id for contact in server_contacts}
                for local_contact in local_contacts:
                    if local_contact.server_user_id not in server_contact_ids:
                        await contact_service.delete_contact(local_contact.id)
                        self._logger.info(f"Removed local contact: {local_contact.username}")

                self._logger.info(f"Successfully synchronized {len(server_contacts)} contacts")
                return True

        except Exception as e:
            self._logger.error(f"Contact synchronization failed: {e}")
            return False