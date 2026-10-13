import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any
from uuid import UUID

from src.exceptions import (
    AccessTokenExpiredError,
    AuthenticationError,
    NetworkError,
)

from ..dao.websocket import WebSocketDAO

RealtimeCallback = Callable[[dict[str, Any]], Awaitable[bool | None]]
ConnectionCallback = Callable[[bool], Awaitable[None] | None]
AccessTokenRotationHandler = Callable[[str | None], Awaitable[str]]

_REALTIME_EVENT_TYPES = {
    "presence",
    "message_available",
    "presence_changed",
    "contact_changed",
    "chat_changed",
}


class WebSocketService:
    _LISTENER_RESTART_DELAY = 1.0
    _PRESENCE_COMMAND_TYPE = "presence_update"

    def __init__(
        self,
        websocket_dao: WebSocketDAO,
        access_token_rotation_handler: AccessTokenRotationHandler | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._websocket_dao = websocket_dao
        self._access_token_rotation_handler = access_token_rotation_handler
        self._logger = logger or logging.getLogger(__name__)
        self._current_token: str | None = None
        self._event_callback: RealtimeCallback | None = None
        self._connection_callback: ConnectionCallback | None = None
        self._is_listening = False
        self._listening_task: asyncio.Task[None] | None = None
        self._desired_presence_online = False

    async def start_websocket_listener(
        self,
        token: str,
        event_callback: RealtimeCallback,
        connection_callback: ConnectionCallback | None = None,
    ) -> bool:
        if self._is_listening:
            await self.set_presence(True)
            return True
        if not token or event_callback is None:
            return False

        self._desired_presence_online = True
        self._current_token = token
        self._event_callback = event_callback
        self._connection_callback = connection_callback

        try:
            await self._websocket_dao.connect(token)
        except AccessTokenExpiredError:
            try:
                await self._rotate_access_token()
            except NetworkError:
                self._logger.warning(
                    "WebSocket reconnect after token rotation will continue "
                    "in the background"
                )
            except Exception:
                self._clear_listener_state()
                await self._websocket_dao.disconnect()
                raise
        except AuthenticationError:
            self._clear_listener_state()
            await self._websocket_dao.disconnect()
            raise
        except NetworkError as error:
            self._logger.warning(
                "Initial WebSocket connection failed; reconnecting in background: %s",
                error,
            )
        except Exception:
            self._logger.exception("Failed to initialize WebSocket listener")
            self._clear_listener_state()
            await self._websocket_dao.disconnect()
            return False

        self._is_listening = True
        self._listening_task = asyncio.create_task(self._websocket_listener_loop())
        return True

    async def _websocket_listener_loop(self) -> None:
        task = asyncio.current_task()
        try:
            while self._is_listening and self._current_token is not None:
                try:
                    await self._websocket_dao.listen_for_messages(
                        self._handle_websocket_message,
                        self._handle_connection_state,
                    )
                except asyncio.CancelledError:
                    raise
                except AccessTokenExpiredError:
                    try:
                        await self._rotate_access_token()
                    except NetworkError:
                        self._logger.warning(
                            "WebSocket reconnect after token rotation failed; "
                            "continuing background retries"
                        )
                    except Exception:
                        self._logger.exception(
                            "WebSocket access token rotation failed"
                        )
                        break
                    continue
                except AuthenticationError:
                    self._logger.warning("WebSocket authentication expired")
                    break
                except Exception:
                    self._logger.exception(
                        "WebSocket listener stopped unexpectedly; restarting"
                    )

                if not self._is_listening or self._current_token is None:
                    break

                self._logger.warning("WebSocket listener exited; restarting")
                await asyncio.sleep(self._LISTENER_RESTART_DELAY)
        except asyncio.CancelledError:
            raise
        finally:
            if self._listening_task is task:
                await self._websocket_dao.disconnect()
                try:
                    await self._handle_connection_state(False)
                except Exception:
                    self._logger.exception(
                        "WebSocket disconnection callback failed"
                    )
                self._clear_listener_state()

    async def _handle_websocket_message(self, raw_message: str | bytes) -> None:
        try:
            event = json.loads(raw_message)
            if not isinstance(event, dict):
                raise ValueError("Realtime event must be an object")
            if event.get("version") != 1:
                raise ValueError("Unsupported realtime event version")
            if event.get("type") not in _REALTIME_EVENT_TYPES:
                raise ValueError("Unsupported realtime event type")
            UUID(str(event["event_id"]))
            datetime.fromisoformat(str(event["occurred_at"]))
            if not isinstance(event.get("payload"), dict):
                raise ValueError("Realtime event payload must be an object")
        except (json.JSONDecodeError, KeyError, TypeError, ValueError, UnicodeDecodeError):
            self._logger.warning("Ignoring malformed realtime WebSocket event")
            return

        callback = self._event_callback
        if callback is not None:
            await callback(event)

    async def _handle_connection_state(self, connected: bool) -> None:
        if connected:
            await self._send_presence_update()

        callback = self._connection_callback
        if callback is None:
            return
        result = callback(connected)
        if asyncio.iscoroutine(result):
            await result

    async def set_presence(self, online: bool) -> bool:
        self._desired_presence_online = online
        return await self._send_presence_update()

    async def _send_presence_update(self) -> bool:
        if not self._websocket_dao.is_connected:
            return False
        return await self._websocket_dao.send_json(
            {
                "version": 1,
                "type": self._PRESENCE_COMMAND_TYPE,
                "online": self._desired_presence_online,
            }
        )

    async def _rotate_access_token(self) -> None:
        rotation_handler = self._access_token_rotation_handler
        if rotation_handler is None:
            raise AuthenticationError(
                "WebSocket access token expired and cannot be rotated"
            )
        rotated_token = await rotation_handler(self._current_token)
        if not rotated_token:
            raise AuthenticationError("Access token rotation returned no token")
        self._current_token = rotated_token
        await self._websocket_dao.connect(rotated_token)
        self._logger.info("WebSocket access token rotated")

    async def stop_websocket_listener(self) -> None:
        task = self._listening_task
        await self.set_presence(False)
        self._is_listening = False
        try:
            if task is not None and task is not asyncio.current_task() and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await self._websocket_dao.disconnect()
            await self._handle_connection_state(False)
        finally:
            self._clear_listener_state()

    def get_connection_status(self) -> dict[str, Any]:
        return {
            "is_connected": self._websocket_dao.is_connected,
            "is_listening": self._is_listening,
            "has_token": self._current_token is not None,
            "has_callback": self._event_callback is not None,
            "desired_presence_online": self._desired_presence_online,
            "timestamp": datetime.now().astimezone().isoformat(),
        }

    def _clear_listener_state(self) -> None:
        self._current_token = None
        self._event_callback = None
        self._connection_callback = None
        self._is_listening = False
        self._listening_task = None
        self._desired_presence_online = False
