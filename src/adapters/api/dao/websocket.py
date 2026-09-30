import asyncio
import inspect
import json
import logging
import ssl
from collections.abc import Awaitable, Callable
from typing import Any

import websockets

from src.exceptions import AuthenticationError, InfrastructureError, NetworkError

WebSocketMessage = str | bytes
MessageHandler = Callable[[WebSocketMessage], Awaitable[None] | None]
ConnectionHandler = Callable[[bool], Awaitable[None] | None]


class WebSocketDAO:
    _PING_INTERVAL = 20
    _PING_TIMEOUT = 10
    _CLOSE_TIMEOUT = 10
    _INITIAL_RECONNECT_DELAY = 1.0
    _MAX_RECONNECT_DELAY = 30.0

    def __init__(
        self,
        base_ws_url: str,
        logger: logging.Logger | None = None,
        verify: bool = False,
    ):
        self.base_ws_url = base_ws_url.rstrip("/")
        self.verify = verify

        self._logger = logger or logging.getLogger(__name__)
        self._websocket: Any | None = None
        self._token: str | None = None

    @property
    def is_connected(self) -> bool:
        return self._websocket is not None and not self._is_websocket_closed(
            self._websocket
        )

    async def connect(self, token: str) -> None:
        self._token = token
        await self._close_websocket()

        try:
            self._websocket = await websockets.connect(
                self._connection_url(),
                **self._connection_options(token),
            )
        except websockets.exceptions.InvalidStatus as error:
            self._websocket = None
            status_code = self._handshake_status_code(error)
            if status_code in {401, 403}:
                raise AuthenticationError(
                    "WebSocket authentication failed",
                    original_error=error,
                    context={"status_code": status_code},
                ) from error
            raise NetworkError(
                "WebSocket handshake failed",
                original_error=error,
                context={"status_code": status_code},
            ) from error
        except websockets.exceptions.InvalidURI as error:
            self._websocket = None
            raise InfrastructureError(
                "Invalid WebSocket URL",
                original_error=error,
                context={"base_ws_url": self.base_ws_url},
            ) from error
        except websockets.exceptions.InvalidHandshake as error:
            self._websocket = None
            raise NetworkError(
                "WebSocket handshake failed",
                original_error=error,
            ) from error
        except OSError as error:
            self._websocket = None
            raise NetworkError(
                "WebSocket network connection failed",
                original_error=error,
            ) from error
        except Exception as error:
            self._websocket = None
            raise InfrastructureError("Unexpected WebSocket connection error") from error

    async def listen_for_messages(
        self,
        message_handler: MessageHandler,
        connection_handler: ConnectionHandler | None = None,
    ) -> None:
        if self._token is None:
            self._logger.warning("WebSocket listener started without a token")
            return

        reconnect_delay = self._INITIAL_RECONNECT_DELAY

        if self.is_connected:
            await self._dispatch_connection_state(True, connection_handler)

        while self._token is not None:
            if not self.is_connected:
                try:
                    await self.connect(self._token)
                    await self._dispatch_connection_state(True, connection_handler)
                except AuthenticationError:
                    self._token = None
                    raise
                except NetworkError:
                    reconnect_delay = await self._wait_before_reconnect(
                        reconnect_delay
                    )
                    continue

            reconnect_delay = self._INITIAL_RECONNECT_DELAY
            websocket = self._websocket
            if websocket is None:
                continue

            drop_connection = False
            try:
                async for message in websocket:
                    try:
                        await self._dispatch_message(message, message_handler)
                    except asyncio.CancelledError:
                        raise
                    except AuthenticationError:
                        self._token = None
                        drop_connection = True
                        raise
                    except Exception:
                        self._logger.exception("WebSocket message handler failed")
                drop_connection = True
            except asyncio.CancelledError:
                raise
            except AuthenticationError:
                raise
            except websockets.exceptions.ConnectionClosed:
                self._logger.warning("WebSocket connection closed")
                drop_connection = True
            except websockets.exceptions.WebSocketException as error:
                self._logger.error(f"WebSocket error: {error}")
                drop_connection = True
            except Exception as error:
                self._logger.error(f"Error in WebSocket message loop: {error}")
                drop_connection = True
            finally:
                if drop_connection and self._websocket is websocket:
                    await self._close_websocket()
                    await self._dispatch_connection_state(False, connection_handler)

            if drop_connection and self._token is not None:
                reconnect_delay = await self._wait_before_reconnect(reconnect_delay)

    async def send_json(self, data: dict[str, Any]) -> bool:
        if not self.is_connected or self._websocket is None:
            return False

        try:
            await self._websocket.send(json.dumps(data))
            return True
        except TypeError as error:
            self._logger.error(f"Invalid WebSocket JSON payload: {error}")
            return False
        except Exception as error:
            self._logger.error(f"Error sending WebSocket message: {error}")
            await self._close_websocket()
            return False

    async def disconnect(self) -> None:
        self._token = None
        await self._close_websocket()
        self._logger.info("WebSocket disconnected")

    def _connection_url(self) -> str:
        return f"{self.base_ws_url}/ws"

    def _connection_options(self, token: str) -> dict[str, Any]:
        options: dict[str, Any] = {
            "ping_interval": self._PING_INTERVAL,
            "ping_timeout": self._PING_TIMEOUT,
            "close_timeout": self._CLOSE_TIMEOUT,
            "additional_headers": {"Authorization": f"Bearer {token}"},
        }

        ssl_context = self._ssl_context()
        if ssl_context is not None:
            options["ssl"] = ssl_context

        return options

    def _ssl_context(self) -> ssl.SSLContext | None:
        if not self.base_ws_url.startswith("wss://") or self.verify:
            return None

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context

    async def _wait_before_reconnect(self, current_delay: float) -> float:
        delay = min(current_delay, self._MAX_RECONNECT_DELAY)
        self._logger.info(f"Reconnecting in {delay:g} seconds...")
        await asyncio.sleep(delay)
        return min(delay * 2, self._MAX_RECONNECT_DELAY)

    async def _dispatch_message(
        self, message: WebSocketMessage, message_handler: MessageHandler
    ) -> None:
        result = message_handler(message)
        if inspect.isawaitable(result):
            await result

    async def _dispatch_connection_state(
        self,
        connected: bool,
        connection_handler: ConnectionHandler | None,
    ) -> None:
        if connection_handler is None:
            return
        result = connection_handler(connected)
        if inspect.isawaitable(result):
            await result

    async def _close_websocket(self) -> None:
        websocket = self._websocket
        self._websocket = None
        if websocket is not None:
            try:
                await websocket.close()
            except Exception as error:
                self._logger.debug(f"Error closing WebSocket: {error}")

    @staticmethod
    def _is_websocket_closed(websocket: Any) -> bool:
        closed = getattr(websocket, "closed", None)
        if isinstance(closed, bool):
            return closed

        close_code = getattr(websocket, "close_code", None)
        if close_code is not None:
            return True

        state = getattr(websocket, "state", None)
        state_name = getattr(state, "name", None)
        return state_name is not None and state_name != "OPEN"

    @staticmethod
    def _handshake_status_code(error: websockets.exceptions.InvalidStatus) -> int:
        return int(error.response.status_code)
