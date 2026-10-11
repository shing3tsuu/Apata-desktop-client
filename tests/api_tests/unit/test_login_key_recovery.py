from typing import cast
from unittest.mock import AsyncMock, MagicMock, call

import pytest
from dishka import AsyncContainer

from src.adapters.api.service import AuthHTTPService
from src.adapters.encryption.storage import EncryptedKeyStorage
from src.presentation.interactors.login import (
    GetPrivateKeysInteractor,
    RecoverECDHKeyInteractor,
    RotateKeysInteractor,
)
from src.providers.state import AppState


class FakeRequestContainer:
    def __init__(self, services: dict[type, object]):
        self._services = services

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    async def get(self, dependency_type: type):
        return self._services[dependency_type]


class FakeContainer:
    def __init__(self, services: dict[type, object]):
        self._request_container = FakeRequestContainer(services)

    def __call__(self):
        return self._request_container


def _container(services: dict[type, object]) -> AsyncContainer:
    return cast(AsyncContainer, FakeContainer(services))


def _login_state(*, ecdh_private_key: str | None = None) -> AppState:
    state = AppState()
    state.username = "recovery-user"
    state.password = "password"
    state.token = "access-token"
    state.ed_private_key = "ed-private-key"
    state.ecdh_private_key = ecdh_private_key
    return state


@pytest.mark.asyncio
async def test_private_key_loading_allows_missing_ecdh_recovery() -> None:
    state = _login_state()
    state.ed_private_key = None
    state.master_key = None
    key_storage = MagicMock(spec=EncryptedKeyStorage)
    key_storage.get_ed_private_key = AsyncMock(return_value="ed-private-key")
    key_storage.get_master_key = AsyncMock(return_value=b"master-key")
    key_storage.get_ecdh_private_key = AsyncMock(return_value=None)

    result = await GetPrivateKeysInteractor()(
        _container(
            {
                AppState: state,
                EncryptedKeyStorage: key_storage,
            }
        )
    )

    assert result == (True, "ECDH KEY RECOVERY REQUIRED", True)
    assert state.ed_private_key == "ed-private-key"
    assert state.master_key == b"master-key"
    assert state.ecdh_private_key is None
    assert state.ecdh_public_key is None


@pytest.mark.asyncio
async def test_recovery_issues_and_stores_ecdh_key_without_clearing() -> None:
    state = _login_state()
    auth_service = MagicMock(spec=AuthHTTPService)
    auth_service.update_ecdh_key = AsyncMock(
        return_value=("new-private-key", "new-public-key")
    )
    key_storage = MagicMock(spec=EncryptedKeyStorage)
    key_storage.store_ecdh_private_key = AsyncMock(return_value=True)

    result = await RecoverECDHKeyInteractor()(
        _container(
            {
                AppState: state,
                AuthHTTPService: auth_service,
                EncryptedKeyStorage: key_storage,
            }
        )
    )

    assert result == (True, "SUCCESS")
    assert auth_service.token == "access-token"
    auth_service.update_ecdh_key.assert_awaited_once_with("ed-private-key")
    key_storage.clear_ecdh_private_key.assert_not_called()
    key_storage.store_ecdh_private_key.assert_awaited_once_with(
        username="recovery-user",
        ecdh_private_key="new-private-key",
        password="password",
    )
    assert state.ecdh_private_key == "new-private-key"
    assert state.ecdh_public_key == "new-public-key"


@pytest.mark.asyncio
async def test_normal_rotation_still_clears_old_key_before_storage() -> None:
    state = _login_state(ecdh_private_key="old-private-key")
    auth_service = MagicMock(spec=AuthHTTPService)
    auth_service.update_ecdh_key = AsyncMock(
        return_value=("new-private-key", "new-public-key")
    )
    key_storage = MagicMock(spec=EncryptedKeyStorage)
    key_storage.store_ecdh_private_key = AsyncMock(return_value=True)
    operations = MagicMock()
    operations.attach_mock(key_storage.clear_ecdh_private_key, "clear")
    operations.attach_mock(key_storage.store_ecdh_private_key, "store")

    result = await RotateKeysInteractor()(
        _container(
            {
                AppState: state,
                AuthHTTPService: auth_service,
                EncryptedKeyStorage: key_storage,
            }
        )
    )

    assert result == (True, "SUCCESS")
    assert operations.mock_calls[:2] == [
        call.clear("recovery-user"),
        call.store(
            username="recovery-user",
            ecdh_private_key="new-private-key",
            password="password",
        ),
    ]
    assert state.ecdh_private_key == "new-private-key"
    assert state.ecdh_public_key == "new-public-key"


@pytest.mark.asyncio
async def test_recovery_failure_does_not_publish_key_to_application_state() -> None:
    state = _login_state()
    auth_service = MagicMock(spec=AuthHTTPService)
    auth_service.update_ecdh_key = AsyncMock(
        return_value=("new-private-key", "new-public-key")
    )
    key_storage = MagicMock(spec=EncryptedKeyStorage)
    key_storage.store_ecdh_private_key = AsyncMock(return_value=False)

    result = await RecoverECDHKeyInteractor()(
        _container(
            {
                AppState: state,
                AuthHTTPService: auth_service,
                EncryptedKeyStorage: key_storage,
            }
        )
    )

    assert result == (False, "FAILED TO STORE ECDH PRIVATE KEY")
    assert state.ecdh_private_key is None
    assert state.ecdh_public_key is None
