from typing import List, Optional, Dict, Any
import base64
import logging

from .common import CommonHTTPClient

class ContactHTTPDAO:
    def __init__(self, http_client: CommonHTTPClient):
        self._http_client = http_client

    async def search_users(self, username: str, token: str) -> list[dict[str, Any]]:
        """
        Searches for users with the given username.
        :param username:
        :param token:
        :return:
        """
        self._http_client.set_auth_token(token)
        return await self._http_client.get("/search-users", params={"username": username})

    async def get_users_data(self, users_ids: list[int], current_user_id: int, token: str) -> list[dict[str, Any]]:
        """
        Gets user data for the given list of user ids with contact status.
        :param users_ids:
        :param current_user_id
        :param token:
        :return:
        """
        self._http_client.set_auth_token(token)
        # Convert list to comma-separated string for URL params
        users_ids_str = ','.join(map(str, users_ids))
        return await self._http_client.get("/users-by-ids", params={
            "users_ids": users_ids_str,
            "current_user_id": current_user_id
        })

    async def get_contacts(self, user_id: int, token: str) -> list[dict[str, Any]]:
        """
        Gets all contacts for the given user id.
        :param user_id:
        :param token:
        :return:
        """
        self._http_client.set_auth_token(token)
        return await self._http_client.get(f"/get-contacts", params={"user_id": user_id})

    async def send_contact_request(self, sender_id: int, receiver_id: int, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        data = {
            "sender_id": sender_id,
            "receiver_id": receiver_id
        }
        return await self._http_client.post("/send-contact-request", data)

    async def get_contact_requests(self, user_id: int, token: str) -> list[dict[str, Any]]:
        self._http_client.set_auth_token(token)
        return await self._http_client.get("/get-contact-requests", params={"user_id": user_id})

    async def accept_contact_request(self, sender_id: int, receiver_id: int, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        data = {
            "sender_id": sender_id,
            "receiver_id": receiver_id
        }
        return await self._http_client.put("/accept-contact-request", data)

    async def reject_contact_request(self, sender_id: int, receiver_id: int, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        data = {
            "sender_id": sender_id,
            "receiver_id": receiver_id
        }
        return await self._http_client.put("/reject-contact-request", data)