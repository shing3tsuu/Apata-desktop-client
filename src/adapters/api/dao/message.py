from typing import List, Optional, Dict, Any
import base64
import logging
from datetime import datetime

from .common import CommonHTTPClient
from src.exceptions import APIError, NetworkError

class MessageHTTPDAO:
    def __init__(self, http_client: CommonHTTPClient):
        self._http_client = http_client
        self._logger = logging.getLogger(__name__)

    async def send_message(
            self,
            recipient_id: int,
            message: str,
            content_type: str | None,
            ephemeral_public_key: str,
            ephemeral_signature: str,
            token: str
    ) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        data = {
            "recipient_id": recipient_id,
            "message": message,
            "content_type": content_type,
            "ephemeral_public_key": ephemeral_public_key,
            "ephemeral_signature": ephemeral_signature
        }
        return await self._http_client.post("/send", data)

    async def get_undelivered_messages(self, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return await self._http_client.get("/undelivered")

    async def ack_messages(self, message_ids: list[int], token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        data = {"message_ids": message_ids}
        return await self._http_client.post("/ack", data)