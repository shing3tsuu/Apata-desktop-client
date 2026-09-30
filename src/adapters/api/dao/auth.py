from typing import Any
from uuid import UUID

from src.adapters.api.dto import (
    AuthChallengeDTO,
    AuthRegisterResponseDTO,
    AuthTokenResponseDTO,
)
from src.exceptions import APIError

from .common import CommonHTTPClient


class AuthHTTPDAO:
    def __init__(self, http_client: CommonHTTPClient):
        self._http_client = http_client

    @staticmethod
    def _expect_object(response: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if isinstance(response, dict):
            return response

        raise APIError(
            "Expected JSON object response from auth API",
            response_data={"response_type": type(response).__name__},
        )

    async def register_user(
        self,
        username: str,
        ed_public_key: str,
        ecdh_public_key: str,
        ecdh_signature: str,
    ) -> AuthRegisterResponseDTO:
        data = {
            "username": username,
            "ed_public_key": ed_public_key,
            "ecdh_public_key": ecdh_public_key,
            "ecdh_signature": ecdh_signature,
        }
        response = self._expect_object(
            await self._http_client.post("/auth/register", data)
        )
        return AuthRegisterResponseDTO.from_mapping(response)

    async def get_challenge(self, username: str) -> AuthChallengeDTO:
        response = self._expect_object(
            await self._http_client.post("/auth/challenges", {"username": username})
        )
        return AuthChallengeDTO.from_mapping(response)

    async def login(self, username: str, signature: str) -> AuthTokenResponseDTO:
        data = {"username": username, "signature": signature}
        response = self._expect_object(await self._http_client.post("/auth/login", data))
        return AuthTokenResponseDTO.from_mapping(response)

    async def logout(self, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return self._expect_object(
            await self._http_client.delete("/auth/tokens/current")
        )

    async def get_current_user(self, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return self._expect_object(await self._http_client.get("/me"))

    async def get_public_keys(
        self, user_id: UUID | str, token: str
    ) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return self._expect_object(
            await self._http_client.get(f"/public-keys/{user_id}")
        )

    async def update_ecdh_key(
        self, ecdh_public_key: str, signature: str, token: str
    ) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        data = {"ecdh_public_key": ecdh_public_key, "ecdh_signature": signature}
        return self._expect_object(
            await self._http_client.patch("/ecdh-update-key", data)
        )

    async def refresh_token(self, token: str) -> AuthTokenResponseDTO:
        self._http_client.set_auth_token(token)
        response = self._expect_object(await self._http_client.post("/refresh", {}))
        result = AuthTokenResponseDTO.from_mapping(response)
        self._http_client.set_auth_token(result.access_token)
        return result
