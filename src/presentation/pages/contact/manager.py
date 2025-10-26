import logging
import asyncio
from typing import Tuple, Optional, List, Set
from datetime import datetime

from pyexpat.errors import messages
from src.exceptions import *
from dishka import AsyncContainer

from src.providers import AppProvider
from src.presentation.pages import AppState, Contact, Message, Container

from src.adapters.database.dto import (
    LocalUserRequestDTO, LocalUserDTO,
    ContactRequestDTO, ContactDTO,
    MessageRequestDTO, MessageDTO
)

class ContactManager(Container):
    async def find_contacts(self, username: str) -> list[Contact]:
        """
        Find contacts from server by username ilike
        :param username:
        :return:
        """
        try:
            self.logger.info(f"Searching for contacts with username: {username}")
            contacts = await self.state.contact_http_service.search_users(username)
            return [
                Contact(
                    server_user_id=contact.get("id", None),
                    username=contact.get("username", None),
                    ecdh_public_key=contact.get("ecdh_public_key", None),
                    last_seen=contact.get("last_seen", None),
                ) for contact in contacts
            ]
        except Exception as e:
            self.logger.error("Error searching contacts: %s", e)
            return []

    async def send_request(self, contact_id: int) -> bool:
        try:
            if contact_id in [c.server_user_id for c in self.state.contacts_cache]:
                raise ContactAlreadyExistsError(f"Contact with id {contact_id} already exists")
            self.logger.info(f"Sending request to contact with id: {contact_id}")
            request = await self.state.contact_http_service.send_contact_request(
                sender_id=self.state.server_user_id,
                receiver_id=contact_id
            )
            if request.id == contact_id:
                await self.state.contact_service.add_contact(
                    ContactRequestDTO(
                        local_user_id=self.state.local_user_id,
                        server_user_id=request.id,
                        status=request.status,
                        username=request.username,
                        ecdh_public_key=request.ecdh_public_key,
                        last_seen=request.last_seen,
                    )
                )
                self.state.contacts_cache.append(
                    Contact(
                        server_user_id=request.id,
                        username=request.username,
                        ecdh_public_key=request.ecdh_public_key,
                        last_seen=request.last_seen,
                        status=request.status,
                    )
                )
                return True
            else:
                self.logger.error(f"Error sending request to contact with id: {contact_id}")
                return False
        except Exception as e:
            self.logger.error(f"Error sending request to contact with id: {contact_id}, error: {e}")
            return False