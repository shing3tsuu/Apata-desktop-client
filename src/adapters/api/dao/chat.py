from typing import Any
from datetime import datetime
from uuid import UUID

from src.exceptions import APIError

from .common import CommonHTTPClient


class ChatHTTPDAO:
    def __init__(self, http_client: CommonHTTPClient):
        self._http_client = http_client

    @staticmethod
    def _expect_object(response: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if isinstance(response, dict):
            return response

        raise APIError(
            "Expected JSON object response from chat API",
            response_data={"response_type": type(response).__name__},
        )

    @staticmethod
    def _expect_list(response: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
        if isinstance(response, list) and all(
            isinstance(item, dict) for item in response
        ):
            return response

        raise APIError(
            "Expected JSON object list response from chat API",
            response_data={"response_type": type(response).__name__},
        )

    async def get_chats(self, token: str) -> list[dict[str, Any]]:
        self._http_client.set_auth_token(token)
        return self._expect_list(await self._http_client.get("/chats"))

    async def create_chat(
        self,
        name: str | None,
        token: str,
    ) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return self._expect_object(
            await self._http_client.post(
                "/chats",
                {"name": name},
            )
        )

    async def delete_chat(
        self,
        chat_id: UUID,
        token: str,
    ) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return self._expect_object(await self._http_client.delete(f"/chats/{chat_id}"))

    async def add_participant(
        self,
        chat_id: UUID,
        user_id: UUID,
        token: str,
    ) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return self._expect_object(
            await self._http_client.post(
                f"/chats/{chat_id}/participants",
                {"user_id": str(user_id)},
            )
        )

    async def remove_participant(
        self,
        chat_id: UUID,
        user_id: UUID,
        token: str,
    ) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return self._expect_object(
            await self._http_client.delete(f"/chats/{chat_id}/participants/{user_id}")
        )

    async def get_participants(
        self,
        chat_id: UUID,
        token: str,
    ) -> list[dict[str, Any]]:
        self._http_client.set_auth_token(token)
        return self._expect_list(
            await self._http_client.get(f"/chats/{chat_id}/participants")
        )

    async def get_events(
        self,
        chat_id: UUID,
        token: str,
        after: datetime | None = None,
    ) -> list[dict[str, Any]]:
        self._http_client.set_auth_token(token)
        params = {"after": after.isoformat()} if after is not None else None
        return self._expect_list(
            await self._http_client.get(
                f"/chats/{chat_id}/events",
                params=params,
            )
        )
