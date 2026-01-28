import asyncio
import json
import logging
from typing import Callable, Optional, Dict, Any
import websockets
from src.exceptions import NetworkError, APIError
import ssl

class WebSocketDAO:
    def __init__(self, base_ws_url: str, logger: logging.Logger = None, verify: bool = False):
        self.base_ws_url = base_ws_url.rstrip('/')
        self.verify = verify

        self._logger = logger or logging.getLogger(__name__)
        self._websocket = None
        self._is_connected = False
        self._reconnect_delay = 1
        self._max_reconnect_delay = 30
        self._message_handler = None
        self._current_token = None
        self._should_reconnect = True
        self._reconnect_task = None

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    async def connect(self, token: str) -> bool:
        self._current_token = token
        try:
            ssl_context = None
            if not self.verify:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE

            url = f"{self.base_ws_url}/ws?token={token}"
            self._websocket = await websockets.connect(
                url,
                ping_interval=20,
                ping_timeout=10,
                close_timeout=10,
                ssl=ssl_context if ssl_context else True
            )
            self._is_connected = True
            self._reconnect_delay = 1
            self._logger.info("WebSocket connected successfully")
            return True
        except Exception as e:
            self._logger.error(f"WebSocket connection failed: {e}")
            return False

    async def listen_for_messages(self, message_handler: Callable):
        self._message_handler = message_handler

        while self._should_reconnect:
            if not self._is_connected and self._current_token:
                success = await self.connect(self._current_token)
                if not success:
                    delay = min(self._reconnect_delay, self._max_reconnect_delay)
                    self._logger.info(f"Reconnecting in {delay} seconds...")
                    await asyncio.sleep(delay)
                    self._reconnect_delay *= 2
                    continue

            self._reconnect_delay = 1

            try:
                async for message in self._websocket:
                    await self._message_handler(message)
            except websockets.exceptions.ConnectionClosed:
                self._logger.warning("WebSocket connection closed")
                self._is_connected = False
            except websockets.exceptions.WebSocketException as e:
                self._logger.error(f"WebSocket error: {e}")
                self._is_connected = False
            except Exception as e:
                self._logger.error(f"Error in WebSocket message loop: {e}")
                self._is_connected = False

    async def send_json(self, data: dict) -> bool:
        if not self._is_connected or not self._websocket:
            return False

        try:
            message = json.dumps(data)
            await self._websocket.send(message)
            return True
        except Exception as e:
            self._logger.error(f"Error sending WebSocket message: {e}")
            self._is_connected = False
            return False

    async def disconnect(self):
        self._should_reconnect = False
        self._is_connected = False
        if self._websocket:
            await self._websocket.close()
            self._websocket = None
        self._logger.info("WebSocket disconnected")