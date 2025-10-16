from typing import Any
import base64
import asyncio
from datetime import datetime
import logging

from ..dao.contact import ContactHTTPDAO
from ..dao.auth import AuthHTTPDAO
from src.adapters.database.dto import ContactRequestDTO


class ContactHTTPService:
    def __init__(self, contact_dao: ContactHTTPDAO, auth_dao: AuthHTTPDAO, logger: logging.Logger = None):
        self._contact_dao = contact_dao
        self._auth_dao = auth_dao
        self._logger = logger or logging.getLogger(__name__)

    async def search_users(self, username: str) -> list[dict[str, Any]]:
        return await self._contact_dao.search_users(username=username)

    async def contact_data_synchronization(self, users_ids: list[int], current_user_id: int, token: str) -> list[
        dict[str, Any]]:
        try:
            if not users_ids:
                return []
            result = await self._contact_dao.get_users_data(
                users_ids=users_ids,
                current_user_id=current_user_id,
                token=token
            )
            return result
        except Exception as e:
            self._logger.error(f"Error during contact data synchronization: {e}")
            return []

    async def get_contacts(self, user_id: int) -> list[ContactRequestDTO]:
        """
        Gets all contacts for user with detailed information including ECDH keys
        :param user_id:
        :param token:
        :return:
        """
        try:
            # First get contact relationships
            contacts = await self._contact_dao.get_contacts(
                user_id=user_id
            )

            if not contacts:
                return []

            # Extract all contact user IDs
            contact_ids = []
            for contact in contacts:
                if contact['sender_id'] == user_id:
                    contact_ids.append(contact['receiver_id'])
                elif contact['receiver_id'] == user_id:
                    contact_ids.append(contact['sender_id'])

            if not contact_ids:
                return []

            # Get detailed user data for all contacts
            users_data = await self._contact_dao.get_users_data(
                users_ids=contact_ids,
                current_user_id=user_id
            )

            # Create mapping from user ID to contact status
            status_map = {}
            for contact in contacts:
                other_user_id = contact['receiver_id'] if contact['sender_id'] == user_id else contact['sender_id']
                status_map[other_user_id] = contact['status']

            # Convert to ContactRequestDTO
            result = []
            for user_data in users_data:
                user_id_key = user_data['id']
                result.append(ContactRequestDTO(
                    server_user_id=user_id_key,
                    username=user_data['username'],
                    status=status_map.get(user_id_key, 'none'),
                    ecdh_public_key=user_data.get('ecdh_public_key', '')
                ))

            return result

        except Exception as e:
            self._logger.error(f"Error getting contacts: {e}")
            return []

    async def send_contact_request(self, sender_id: int, receiver_id: int) -> dict[str, Any]:
        return await self._contact_dao.send_contact_request(sender_id, receiver_id)

    async def get_pending_requests(self, user_id: int) -> list[dict[str, Any]]:
        return await self._contact_dao.get_contact_requests(user_id)

    async def accept_request(self, sender_id: int, receiver_id: int) -> dict[str, Any]:
        return await self._contact_dao.accept_contact_request(sender_id, receiver_id)

    async def reject_request(self, sender_id: int, receiver_id: int) -> dict[str, Any]:
        return await self._contact_dao.reject_contact_request(sender_id, receiver_id)