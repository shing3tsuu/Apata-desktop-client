from typing import Any
import base64
import asyncio
from datetime import datetime
import logging

from rsa.cli import verify

from ..dao.contact import ContactHTTPDAO
from ..dao.auth import AuthHTTPDAO
from src.adapters.database.dto import ContactRequestDTO
from src.adapters.encryption.service import AbstractECDSASignature
from src.exceptions import (
    CryptographyError
)


class ContactHTTPService:
    __slots__ = (
        "_contact_dao",
        "_auth_dao",
        "_logger",
        "_ecdsa_signer",
        "_current_token",
        "__weakref__"
    )
    def __init__(
        self,
        contact_dao: ContactHTTPDAO,
        auth_dao: AuthHTTPDAO,
        ecdsa_signer: AbstractECDSASignature,
        logger: logging.Logger = None
    ):
        self._contact_dao = contact_dao
        self._auth_dao = auth_dao
        self._ecdsa_signer = ecdsa_signer
        self._logger = logger or logging.getLogger(__name__)

        self._current_token: str | None = None

    def set_token(self, token: str):
        self._current_token = token

    def clear_token(self):
        self._current_token = None

    async def search_users(self, username: str) -> list[dict[str, Any]]:
        return await self._contact_dao.search_users(username=username, token=self._current_token)

    async def contact_data_synchronization(self, users_ids: list[int]) -> list[dict[str, Any]]:
        try:
            if not users_ids:
                return []
            result = await self._contact_dao.get_users_data(
                users_ids=users_ids,
                token=self._current_token
            )
            return result
        except Exception as e:
            self._logger.error(f"Error during contact data synchronization: {e}")
            return []

    async def get_contacts(self, local_user_id: int, server_user_id: int, ecdsa_dict: dict[int, str]) -> list[ContactRequestDTO]:
        try:
            # First get contact relationships
            contacts = await self._contact_dao.get_contacts(token=self._current_token)

            if not contacts:
                return []

            # Extract all contact user IDs
            contact_ids = []
            for contact in contacts:
                if contact['sender_id'] == server_user_id:
                    contact_ids.append(contact['receiver_id'])
                elif contact['receiver_id'] == server_user_id:
                    contact_ids.append(contact['sender_id'])

            if not contact_ids:
                return []

            # Get detailed user data for all contacts
            users_data = await self._contact_dao.get_users_data(
                users_ids=contact_ids,
                token=self._current_token
            )

            # Create mapping from user ID to contact status
            status_map = {}
            for contact in contacts:
                other_user_id = contact['receiver_id'] if contact['sender_id'] == server_user_id else contact['sender_id']
                status_map[other_user_id] = contact['status']

            # Convert to ContactRequestDTO
            result = []
            for user_data in users_data:
                user_id_key = user_data['id']
                sender_id = user_data.get('id')
                sender_ecdsa_public_key = ecdsa_dict.get(sender_id)

                if sender_ecdsa_public_key:
                    verify = await self._ecdsa_signer.verify_signature(
                        public_key_pem=sender_ecdsa_public_key,
                        message=user_data.get('ecdh_public_key', ''),
                        signature=user_data.get('ecdh_signature', '')
                    )
                else:
                    verify = await self._ecdsa_signer.verify_signature(
                        public_key_pem=user_data.get('ecdsa_public_key', ''),
                        message=user_data.get('ecdh_public_key', ''),
                        signature=user_data.get('ecdh_signature', '')
                    )

                if not verify:
                    raise CryptographyError(f"Invalid ECDH signature for user with name: {user_data['username']}")
                else:
                    result.append(ContactRequestDTO(
                        local_user_id=local_user_id,
                        server_user_id=user_id_key,
                        username=user_data['username'],
                        status=status_map.get(user_id_key, 'none'),
                        ecdsa_public_key=user_data.get('ecdsa_public_key', ''),
                        ecdh_public_key=user_data.get('ecdh_public_key', ''),
                        last_seen=user_data.get('last_seen', ''),
                        online=user_data.get('online', False),
                    ))

            return result

        except Exception as e:
            self._logger.error(f"Error getting contacts: {e}")
            return []

    async def send_contact_request(self, receiver_id: int) -> dict[str, Any]:
        try:
            return await self._contact_dao.send_contact_request(receiver_id, self._current_token)
        except Exception as e:
            self._logger.error(f"Error sending contact request: {e}")
            return {}

    async def get_pending_contact_requests(self, user_id: int) -> list[dict[str, Any]]:
        try:
            return await self._contact_dao.get_contact_requests(user_id, self._current_token)
        except Exception as e:
            self._logger.error(f"Error getting pending requests: {e}")
            return []

    async def accept_contact_request(self, receiver_id: int) -> dict[str, Any]:
        try:
            return await self._contact_dao.accept_contact_request(receiver_id, self._current_token)
        except Exception as e:
            self._logger.error(f"Error accepting contact request: {e}")
            return {}

    async def reject_contact_request(self, receiver_id: int) -> dict[str, Any]:
        try:
            return await self._contact_dao.reject_contact_request(receiver_id, self._current_token)
        except Exception as e:
            self._logger.error(f"Error rejecting contact request: {e}")
            return {}