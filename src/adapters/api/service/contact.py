from typing import Any
import base64
import asyncio
from datetime import datetime

from ..dao.contact import ContactHTTPDAO
from ..dao.auth import AuthHTTPDAO

class ContactHTTPService:
    def __init__(self, contact_dao: ContactHTTPDAO, auth_dao: AuthHTTPDAO):
        self._contact_dao = contact_dao
        self._auth_dao = auth_dao

    async def search_users(self, username: str, token: str) -> list[dict[str, Any]]:
        return await self._contact_dao.search_users(username=username, token=token)

    async def contact_data_synchronization(self, users_ids: list[int], token: str) -> list[dict[str, Any]]:
        if not users_ids:
            return []
        result = await self._contact_dao.get_users_data(users_ids=users_ids, token=token)
        return result

    async def send_contact_request(self, sender_id: int, receiver_id: int, token: str) -> dict[str, Any]:
        return await self._contact_dao.send_contact_request(sender_id, receiver_id, token)

    async def get_pending_requests(self, user_id: int, token: str) -> list[dict[str, Any]]:
        return await self._contact_dao.get_contact_requests(user_id, token)

    async def accept_request(self, sender_id: int, receiver_id: int, token: str) -> dict[str, Any]:
        return await self._contact_dao.accept_contact_request(sender_id, receiver_id, token)

    async def reject_request(self, sender_id: int, receiver_id: int, token: str) -> dict[str, Any]:
        return await self._contact_dao.reject_contact_request(sender_id, receiver_id, token)
