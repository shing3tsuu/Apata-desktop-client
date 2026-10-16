from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from dishka import AsyncContainer

from src.adapters.api.service import AuthHTTPService
from src.presentation.interactors.login import LogoutInteractor, RealtimeInteractor
from src.providers.cache import ChatCache, ContactCache
from src.providers.state import AppState


class FakeRequestContainer:
    def __init__(self, services: dict[type, object]) -> None:
        self._services = services

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> bool:
        return False

    async def get(self, dependency_type: type):
        return self._services[dependency_type]


class FakeContainer:
    def __init__(self, services: dict[type, object]) -> None:
        self._request_container = FakeRequestContainer(services)

    def __call__(self):
        return self._request_container


def _container(services: dict[type, object]) -> AsyncContainer:
    return cast(AsyncContainer, FakeContainer(services))


def _authenticated_state() -> AppState:
    state = AppState()
    state.username = "logout-user"
    state.password = "password"
    state.token = "access-token"
    state.master_key = b"master-key"
    state.ed_private_key = "ed-private-key"
    state.ecdh_private_key = "ecdh-private-key"
    state.contacts_cache = [cast(ContactCache, object())]
    state.chats_cache = [cast(ChatCache, object())]
    state.websocket_connected = True
    return state


@pytest.mark.asyncio
async def test_logout_stops_realtime_revokes_token_and_clears_state() -> None:
    state = _authenticated_state()
    auth_service = MagicMock(spec=AuthHTTPService)
    auth_service.logout = AsyncMock(return_value=True)
    realtime = MagicMock(spec=RealtimeInteractor)
    realtime.set_presence = AsyncMock(return_value=True)
    realtime.stop = AsyncMock()
    interactor = LogoutInteractor(cast(RealtimeInteractor, realtime))

    success, message = await interactor(
        _container({AuthHTTPService: auth_service, AppState: state})
    )

    assert success is True
    assert message == "SUCCESS"
    realtime.set_presence.assert_awaited_once_with(False)
    realtime.stop.assert_awaited_once_with()
    auth_service.logout.assert_awaited_once_with()
    assert state.token is None
    assert state.username is None
    assert state.master_key is None
    assert state.contacts_cache == []
    assert state.chats_cache == []
    assert state.websocket_connected is False


@pytest.mark.asyncio
async def test_logout_finishes_locally_when_remote_revocation_fails() -> None:
    state = _authenticated_state()
    auth_service = MagicMock(spec=AuthHTTPService)
    auth_service.logout = AsyncMock(return_value=False)
    realtime = MagicMock(spec=RealtimeInteractor)
    realtime.set_presence = AsyncMock(side_effect=RuntimeError("socket closed"))
    realtime.stop = AsyncMock(side_effect=RuntimeError("listener failed"))
    interactor = LogoutInteractor(cast(RealtimeInteractor, realtime))

    success, message = await interactor(
        _container({AuthHTTPService: auth_service, AppState: state})
    )

    assert success is True
    assert message == "LOGGED OUT LOCALLY; REMOTE TOKEN REVOCATION FAILED"
    auth_service.logout.assert_awaited_once_with()
    assert state.token is None
    assert state.username is None
    assert state.contacts_cache == []
    assert state.chats_cache == []
