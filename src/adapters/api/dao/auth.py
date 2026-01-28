from typing import Any
import logging
import asyncio

from .common import CommonHTTPClient
from src.exceptions import APIError, NetworkError

class AuthHTTPDAO:
    def __init__(self, http_client: CommonHTTPClient):
        self._http_client = http_client

    async def register_user(self, username: str, ecdsa_public_key: str, ecdh_public_key: str) -> dict[str, Any]:
        data = {
            "username": username,
            "ecdsa_public_key": ecdsa_public_key,
            "ecdh_public_key": ecdh_public_key
        }
        return await self._http_client.post("/register", data)

    async def get_challenge(self, username: str) -> dict[str, Any]:
        result = await self._http_client.get(f"/challenge/{username}")
        return result

    async def login(self, username: str, signature: str) -> dict[str, Any]:
        data = {
            "username": username,
            "signature": signature
        }
        return await self._http_client.post("/login", data)

    async def logout(self, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        result = await self._http_client.post("/logout", {})
        return result

    async def get_current_user(self, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return await self._http_client.get("/me")

    async def get_public_keys(self, user_id: int, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return await self._http_client.get(f"/public-keys/{user_id}")

    async def update_ecdsa_key(self, ecdsa_public_key: str, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        data = {"ecdsa_public_key": ecdsa_public_key}
        return await self._http_client.put("/ecdsa-update-key", data)

    async def update_ecdh_key(self, ecdh_public_key: str, signature: str, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        data = {
            "ecdh_public_key": ecdh_public_key,
            "ecdh_signature": signature
        }
        return await self._http_client.put("/ecdh-update-key", data)

    async def refresh_token(self, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        result = await self._http_client.post("/refresh", {})
        if "access_token" in result:
            self.set_token(result["access_token"])
        return result