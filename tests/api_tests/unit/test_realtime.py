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
        self.sent_payloads: list[dict[str, Any]] = []

    @property
    def is_connected(self) -> bool:
        return not self.fail_initial_connection and not self.disconnected

    async def connect(self, token: str) -> None:
        if self.fail_initial_connection:
            raise NetworkError("offline")

    async def listen_for_messages(self, message_handler, connection_handler) -> None:
        if connection_handler is not None and not self.fail_initial_connection:
            await connection_handler(True)
        self.listen_started.set()
        await asyncio.Event().wait()

    async def send_json(self, data: dict[str, Any]) -> bool:
        self.sent_payloads.append(data)
        return True

    async def disconnect(self) -> None:
        self.disconnected = True


class RestartingWebSocketDAO:
    def __init__(self, *, fail_first_listener: bool) -> None:
        self.fail_first_listener = fail_first_listener
        self.listen_calls = 0
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.second_listener_started = asyncio.Event()
        self.release_second_listener = asyncio.Event()
        self.connected = False
        self.sent_payloads: list[dict[str, Any]] = []

    @property
    def is_connected(self) -> bool:
        return self.connected

    async def connect(self, token: str) -> None:
        self.connect_calls += 1
        self.connected = True

    async def listen_for_messages(self, message_handler, connection_handler) -> None:
        self.listen_calls += 1
        if connection_handler is not None:
            await connection_handler(True)
        if self.listen_calls == 1:
            if self.fail_first_listener:
                raise RuntimeError("listener crashed")
            return
        self.second_listener_started.set()
        await self.release_second_listener.wait()

    async def send_json(self, data: dict[str, Any]) -> bool:
        self.sent_payloads.append(data)
        return True

    async def disconnect(self) -> None:
        self.disconnect_calls += 1
        self.connected = False


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


@pytest.mark.asyncio
@pytest.mark.parametrize("fail_first_listener", [False, True])
async def test_websocket_service_restarts_finished_listener(
    fail_first_listener: bool,
) -> None:
    websocket_dao = RestartingWebSocketDAO(
        fail_first_listener=fail_first_listener
    )
    service = WebSocketService(websocket_dao)  # type: ignore[arg-type]
    service._LISTENER_RESTART_DELAY = 0

    async def callback(event: dict[str, Any]) -> bool:
        return True

    started = await service.start_websocket_listener(
        token="access-token",
        event_callback=callback,
    )
    await asyncio.wait_for(websocket_dao.second_listener_started.wait(), timeout=1)

    assert started is True
    assert websocket_dao.listen_calls == 2
    assert service.get_connection_status()["is_listening"] is True

    await service.stop_websocket_listener()


@pytest.mark.asyncio
async def test_websocket_service_uses_one_supervisor_and_stop_prevents_restart() -> None:
    websocket_dao = RestartingWebSocketDAO(fail_first_listener=False)
    service = WebSocketService(websocket_dao)  # type: ignore[arg-type]
    service._LISTENER_RESTART_DELAY = 0

    async def callback(event: dict[str, Any]) -> bool:
        return True

    assert await service.start_websocket_listener("access-token", callback) is True
    first_task = service._listening_task
    assert await service.start_websocket_listener("access-token", callback) is True
    assert service._listening_task is first_task

    await asyncio.wait_for(websocket_dao.second_listener_started.wait(), timeout=1)
    await service.stop_websocket_listener()
    calls_after_stop = websocket_dao.listen_calls
    await asyncio.sleep(0)

    assert websocket_dao.listen_calls == calls_after_stop
    assert service.get_connection_status()["is_listening"] is False
    assert websocket_dao.disconnect_calls >= 1


@pytest.mark.asyncio
async def test_websocket_service_reports_online_and_offline_presence() -> None:
    websocket_dao = FakeWebSocketDAO()
    service = WebSocketService(websocket_dao)  # type: ignore[arg-type]

    async def callback(event: dict[str, Any]) -> bool:
        return True

    assert await service.start_websocket_listener("access-token", callback) is True
    await asyncio.wait_for(websocket_dao.listen_started.wait(), timeout=1)

    assert websocket_dao.sent_payloads == [
        {"version": 1, "type": "presence_update", "online": True}
    ]

    await service.stop_websocket_listener()

    assert websocket_dao.sent_payloads[-1] == {
        "version": 1,
        "type": "presence_update",
        "online": False,
    }


@pytest.mark.asyncio
async def test_websocket_service_resends_presence_after_listener_restart() -> None:
    websocket_dao = RestartingWebSocketDAO(fail_first_listener=True)
    service = WebSocketService(websocket_dao)  # type: ignore[arg-type]
    service._LISTENER_RESTART_DELAY = 0

    async def callback(event: dict[str, Any]) -> bool:
        return True

    assert await service.start_websocket_listener("access-token", callback) is True
    await asyncio.wait_for(websocket_dao.second_listener_started.wait(), timeout=1)

    online_payload = {"version": 1, "type": "presence_update", "online": True}
    assert websocket_dao.sent_payloads == [online_payload, online_payload]

    await service.stop_websocket_listener()
