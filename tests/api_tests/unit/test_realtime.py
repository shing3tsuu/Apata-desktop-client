import asyncio
import json
from typing import Any
from uuid import uuid4

import pytest

from src.adapters.api.service.websocket import WebSocketService
from src.exceptions import NetworkError


class FakeWebSocketDAO:
    def __init__(self, *, fail_initial_connection: bool = False) -> None:
        self.fail_initial_connection = fail_initial_connection
        self.listen_started = asyncio.Event()
        self.disconnected = False

    @property
    def is_connected(self) -> bool:
        return not self.fail_initial_connection and not self.disconnected

    async def connect(self, token: str) -> None:
        if self.fail_initial_connection:
            raise NetworkError("offline")

    async def listen_for_messages(self, message_handler, connection_handler) -> None:
        self.listen_started.set()
        await asyncio.Event().wait()

    async def disconnect(self) -> None:
        self.disconnected = True


@pytest.mark.asyncio
async def test_websocket_service_dispatches_valid_realtime_event() -> None:
    websocket_dao = FakeWebSocketDAO()
    service = WebSocketService(websocket_dao)  # type: ignore[arg-type]
    received: list[dict[str, Any]] = []

    async def callback(event: dict[str, Any]) -> bool:
        received.append(event)
        return True

    event = {
        "version": 1,
        "event_id": str(uuid4()),
        "type": "message_available",
        "occurred_at": "2026-09-27T12:00:00+00:00",
        "payload": {"message_id": str(uuid4())},
    }
    service._event_callback = callback

    await service._handle_websocket_message(json.dumps(event))
    await service._handle_websocket_message("not-json")

    assert received == [event]


@pytest.mark.asyncio
async def test_initial_network_failure_keeps_reconnect_listener_running() -> None:
    websocket_dao = FakeWebSocketDAO(fail_initial_connection=True)
    service = WebSocketService(websocket_dao)  # type: ignore[arg-type]

    async def callback(event: dict[str, Any]) -> bool:
        return True

    started = await service.start_websocket_listener(
        token="access-token",
        event_callback=callback,
    )
    await asyncio.wait_for(websocket_dao.listen_started.wait(), timeout=1)

    assert started is True
    assert service.get_connection_status()["is_listening"] is True
    await service.stop_websocket_listener()
    assert websocket_dao.disconnected is True
