from collections.abc import Sequence
from typing import Any
from uuid import UUID

from src.adapters.api.dto import ChatMessageBatchDTO, MessageProcessingResultDTO
from src.exceptions import APIError

from .common import CommonHTTPClient


class MessageHTTPDAO:
    def __init__(self, http_client: CommonHTTPClient):
        self._http_client = http_client

    @staticmethod
    def _expect_object(response: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if isinstance(response, dict):
            return response

        raise APIError(
            "Expected JSON object response from message API",
            response_data={"response_type": type(response).__name__},
        )

    @staticmethod
    def _expect_list(response: dict[str, Any] | list[Any]) -> list[dict[str, Any]]:
        if isinstance(response, list) and all(
            isinstance(item, dict) for item in response
        ):
            return response
        raise APIError(
            "Expected JSON object list response from message API",
            response_data={"response_type": type(response).__name__},
        )

    async def send_message_text(
        self,
        recipient_id: UUID,
        chat_id: UUID | None,
        message: str,
        message_id: UUID,
        content_type: str,
        ephemeral_public_key: str,
        ephemeral_signature: str,
        token: str,
    ) -> None:
        self._http_client.set_auth_token(token)
        data = {
            "recipient_id": str(recipient_id),
            "chat_id": str(chat_id) if chat_id else None,
            "message": message,
            "message_id": str(message_id),
            "content_type": content_type,
            "ephemeral_public_key": ephemeral_public_key,
            "ephemeral_signature": ephemeral_signature,
        }
        await self._http_client.post("/send", data)

    async def send_chat_message_text(
        self,
        chat_id: UUID,
        batch: ChatMessageBatchDTO,
        token: str,
    ) -> list[dict[str, Any]]:
        self._http_client.set_auth_token(token)
        return self._expect_list(
            await self._http_client.post(
                f"/chats/{chat_id}/messages",
                batch.as_dict(),
            )
        )

    async def get_undelivered_messages(self, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return self._expect_object(await self._http_client.get("/undelivered"))

    async def ack_messages(
        self,
        results: Sequence[MessageProcessingResultDTO],
        token: str,
    ) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        data = {"results": [result.as_dict() for result in results]}
        return self._expect_object(await self._http_client.post("/ack", data))

    async def get_failed_messages(self, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return self._expect_object(await self._http_client.get("/failed"))

    async def health_check(self) -> bool:
        return await self._http_client.health_check()
