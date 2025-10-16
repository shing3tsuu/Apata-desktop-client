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

    async def send_message(self, recipient_id: int, message: str, token: str) -> dict[str, Any]:
        """
        Sending an encrypted message
        :param recipient_id:
        :param message:
        :param token:
        :return:
        """
        try:
            self._http_client.set_auth_token(token)
            data = {
                "recipient_id": recipient_id,
                "message": message,
                "timestamp": datetime.utcnow().isoformat()
            }
            return await self._http_client.post("/send", data)
        except Exception as e:
            self._logger.error("Send message request failed: %s", e)
            return None

    async def get_undelivered_messages(self, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        try:
            return await self._http_client.get("/get-undelivered-messages")
        except Exception as e:
            self._logger.error(f"Get undelivered messages request failed: {e}")
            return {"has_messages": False, "messages": []}

    async def poll_messages(self, timeout: int, token: str) -> dict[str, Any]:
        """
        Long-polling to receive new messages
        :param timeout: Server-side timeout in seconds
        :param token:
        :return:
        """
        self._http_client.set_auth_token(token)
        params = {"timeout": timeout}

        try:
            response = await self._http_client.get("/poll", params=params)
            return {
                "has_messages": response.get("has_messages", False),
                "messages": response.get("messages", []),
                "last_message_id": response.get("last_message_id")
            }
        except Exception as e:
            self._logger.error(f"Polling request failed: {e}")
            return {"has_messages": False, "messages": []}

    async def ack_messages(self, message_ids: list[int], token: str) -> dict[str, Any]:
        """
        Confirmation of receipt of messages
        :param message_ids:
        :param token:
        :return:
        """
        self._http_client.set_auth_token(token)
        data = {"message_ids": message_ids}
        return await self._http_client.post("/ack", data)