import asyncio
from typing import Any

import httpx
import pytest

from src.adapters.api.dao.common import CommonHTTPClient
from src.adapters.api.dto import AuthChallengeDTO, AuthTokenResponseDTO
from src.adapters.api.service.auth import AuthHTTPService
from src.adapters.api.service.websocket import WebSocketService
from src.exceptions import (
    AccessTokenExpiredError,
    AuthenticationError,
    NetworkError,
)
from src.providers.state import AppState


class _RotatingAuthDAO:
    def __init__(self) -> None:
        self.challenge_calls = 0
        self.login_calls = 0

    async def get_challenge(self, username: str) -> AuthChallengeDTO:
        self.challenge_calls += 1
        await asyncio.sleep(0)
        return AuthChallengeDTO(challenge=f"challenge-for-{username}")

    async def login(
        self,
        username: str,
        signature: str,
    ) -> AuthTokenResponseDTO:
        self.login_calls += 1
        assert username == "alice"
        assert signature == "signed:challenge-for-alice"
        return AuthTokenResponseDTO(access_token="new-access-token")


class _FailingAuthDAO(_RotatingAuthDAO):
    async def login(
        self,
        username: str,
        signature: str,
    ) -> AuthTokenResponseDTO:
        self.login_calls += 1
        raise AuthenticationError("Invalid signature")


class _SigningEncryptionService:
    async def sign_string(self, private_key_pem: str, string: str) -> str:
        assert private_key_pem == "local-ed-private-key"
        return f"signed:{string}"


def _build_auth_service(
    auth_dao: _RotatingAuthDAO,
) -> tuple[AuthHTTPService, AppState, CommonHTTPClient]:
    app_state = AppState()
    app_state.username = "alice"
    app_state.ed_private_key = "local-ed-private-key"
    app_state.token = "expired-access-token"
    http_client = CommonHTTPClient(base_url="http://testserver")
    http_client.set_auth_token("expired-access-token")
    service = AuthHTTPService(
        auth_dao=auth_dao,  # type: ignore[arg-type]
        encryption_service=_SigningEncryptionService(),  # type: ignore[arg-type]
        app_state=app_state,
        http_client=http_client,
    )
    service.token = "expired-access-token"
    return service, app_state, http_client


@pytest.mark.asyncio
async def test_common_http_client_rotates_and_retries_expired_access_once() -> None:
    requests: list[httpx.Request] = []
    rotation_tokens: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.headers.get("Authorization") == "Bearer expired-access-token":
            return httpx.Response(401, json={"detail": "Token expired"})
        return httpx.Response(200, json={"status": "ok"})

    async def rotate(expired_token: str | None) -> str:
        rotation_tokens.append(expired_token)
        return "new-access-token"

    async with CommonHTTPClient(
        base_url="http://testserver",
        max_retries=1,
        transport=httpx.MockTransport(handler),
    ) as client:
        client.set_auth_token("expired-access-token")
        client.set_access_token_rotation_handler(rotate)

        response = await client.get("/protected")
        client.set_auth_token("expired-access-token")
        response_after_stale_service_token = await client.get("/protected")

    assert response == {"status": "ok"}
    assert response_after_stale_service_token == {"status": "ok"}
    assert rotation_tokens == ["expired-access-token"]
    assert len(requests) == 3
    assert requests[1].headers["Authorization"] == "Bearer new-access-token"
    assert requests[2].headers["Authorization"] == "Bearer new-access-token"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "status_code", "detail"),
    [
        ("/protected", 401, "Invalid token"),
        ("/protected", 403, "Access forbidden"),
        ("/auth/login", 401, "Token expired"),
        ("/auth/challenges", 401, "Token expired"),
    ],
)
async def test_common_http_client_does_not_rotate_unrelated_auth_failures(
    endpoint: str,
    status_code: int,
    detail: str,
) -> None:
    rotation_calls = 0

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json={"detail": detail})

    async def rotate(_: str | None) -> str:
        nonlocal rotation_calls
        rotation_calls += 1
        return "new-access-token"

    async with CommonHTTPClient(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    ) as client:
        client.set_auth_token("expired-access-token")
        client.set_access_token_rotation_handler(rotate)

        expected_error = (
            AccessTokenExpiredError
            if detail == "Token expired"
            else AuthenticationError
        )
        with pytest.raises(expected_error):
            await client.get(endpoint)

    assert rotation_calls == 0


@pytest.mark.asyncio
async def test_rotation_failure_does_not_retry_original_http_request() -> None:
    request_count = 0
    rotation_count = 0

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal request_count
        request_count += 1
        return httpx.Response(401, json={"detail": "Token expired"})

    async def rotate(_: str | None) -> str:
        nonlocal rotation_count
        rotation_count += 1
        raise AuthenticationError("Access token rotation failed")

    async with CommonHTTPClient(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    ) as client:
        client.set_auth_token("expired-access-token")
        client.set_access_token_rotation_handler(rotate)

        with pytest.raises(AuthenticationError, match="rotation failed"):
            await client.get("/protected")

    assert request_count == 1
    assert rotation_count == 1


@pytest.mark.asyncio
async def test_concurrent_rotation_uses_one_challenge_login_flow() -> None:
    auth_dao = _RotatingAuthDAO()
    service, app_state, http_client = _build_auth_service(auth_dao)

    rotated_tokens = await asyncio.gather(
        service.rotate_access_token("expired-access-token"),
        service.rotate_access_token("expired-access-token"),
        service.rotate_access_token("expired-access-token"),
    )

    assert rotated_tokens == ["new-access-token"] * 3
    assert auth_dao.challenge_calls == 1
    assert auth_dao.login_calls == 1
    assert app_state.token == "new-access-token"
    assert http_client.get_current_token() == "new-access-token"


@pytest.mark.asyncio
async def test_late_expired_http_response_reuses_completed_rotation() -> None:
    old_request_count = 0
    both_old_requests_started = asyncio.Event()
    rotation_completed = asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal old_request_count
        if request.headers.get("Authorization") != "Bearer expired-access-token":
            return httpx.Response(200, json={"status": "ok"})

        old_request_count += 1
        if old_request_count == 1:
            await both_old_requests_started.wait()
        else:
            both_old_requests_started.set()
            await rotation_completed.wait()
        return httpx.Response(401, json={"detail": "Token expired"})

    auth_dao = _RotatingAuthDAO()
    app_state = AppState()
    app_state.username = "alice"
    app_state.ed_private_key = "local-ed-private-key"
    app_state.token = "expired-access-token"

    async with CommonHTTPClient(
        base_url="http://testserver",
        max_retries=1,
        transport=httpx.MockTransport(handler),
    ) as http_client:
        http_client.set_auth_token("expired-access-token")
        auth_service = AuthHTTPService(
            auth_dao=auth_dao,  # type: ignore[arg-type]
            encryption_service=_SigningEncryptionService(),  # type: ignore[arg-type]
            app_state=app_state,
            http_client=http_client,
        )
        auth_service.token = "expired-access-token"

        async def rotate(expired_token: str | None) -> str:
            rotated_token = await auth_service.rotate_access_token(expired_token)
            rotation_completed.set()
            return rotated_token

        http_client.set_access_token_rotation_handler(rotate)
        responses = await asyncio.gather(
            http_client.get("/protected/first"),
            http_client.get("/protected/second"),
        )

    assert responses == [{"status": "ok"}, {"status": "ok"}]
    assert old_request_count == 2
    assert auth_dao.challenge_calls == 1
    assert auth_dao.login_calls == 1


@pytest.mark.asyncio
async def test_rotation_failure_clears_session_and_notifies_application() -> None:
    service, app_state, http_client = _build_auth_service(_FailingAuthDAO())
    app_state.hashed_password = "stored-password-hash"
    session_expired = asyncio.Event()
    service.set_session_expired_callback(session_expired.set)

    with pytest.raises(AuthenticationError, match="Invalid signature"):
        await service.rotate_access_token("expired-access-token")

    assert session_expired.is_set()
    assert app_state.token is None
    assert app_state.username is None
    assert app_state.ed_private_key is None
    assert app_state.hashed_password is None
    assert http_client.get_current_token() is None


@pytest.mark.asyncio
async def test_rotation_without_local_ed_key_terminates_session() -> None:
    service, app_state, _ = _build_auth_service(_RotatingAuthDAO())
    app_state.ed_private_key = None
    session_expired = asyncio.Event()
    service.set_session_expired_callback(session_expired.set)

    with pytest.raises(AuthenticationError, match="local ED25519 key"):
        await service.rotate_access_token("expired-access-token")

    assert session_expired.is_set()
    assert app_state.token is None


class _ExpiringWebSocketDAO:
    def __init__(self) -> None:
        self.connect_tokens: list[str] = []
        self.listen_calls = 0
        self.sent_payloads: list[dict[str, Any]] = []
        self.connected = False
        self.reconnected = asyncio.Event()
        self.release_listener = asyncio.Event()

    @property
    def is_connected(self) -> bool:
        return self.connected

    async def connect(self, token: str) -> None:
        self.connect_tokens.append(token)
        self.connected = True

    async def listen_for_messages(self, message_handler, connection_handler) -> None:
        del message_handler
        self.listen_calls += 1
        if connection_handler is not None:
            await connection_handler(True)
        if self.listen_calls == 1:
            self.connected = False
            raise AccessTokenExpiredError("WebSocket access token expired")
        self.reconnected.set()
        await self.release_listener.wait()

    async def send_json(self, data: dict[str, Any]) -> bool:
        self.sent_payloads.append(data)
        return True

    async def disconnect(self) -> None:
        self.connected = False


class _InterruptedRotationWebSocketDAO(_ExpiringWebSocketDAO):
    def __init__(self) -> None:
        super().__init__()
        self.current_token: str | None = None
        self.rotation_reconnect_failed = False

    async def connect(self, token: str) -> None:
        self.current_token = token
        self.connect_tokens.append(token)
        if token == "new-access-token" and not self.rotation_reconnect_failed:
            self.rotation_reconnect_failed = True
            self.connected = False
            raise NetworkError("Temporary WebSocket network failure")
        self.connected = True

    async def listen_for_messages(self, message_handler, connection_handler) -> None:
        del message_handler
        self.listen_calls += 1
        if self.listen_calls == 1:
            self.connected = False
            raise AccessTokenExpiredError("WebSocket access token expired")
        if not self.connected and self.current_token is not None:
            await self.connect(self.current_token)
        if connection_handler is not None:
            await connection_handler(True)
        self.reconnected.set()
        await self.release_listener.wait()


@pytest.mark.asyncio
async def test_websocket_expiration_rotates_reconnects_and_restores_presence() -> None:
    websocket_dao = _ExpiringWebSocketDAO()
    rotation_tokens: list[str | None] = []

    async def rotate(expired_token: str | None) -> str:
        rotation_tokens.append(expired_token)
        return "new-access-token"

    async def callback(_: dict[str, Any]) -> bool:
        return True

    service = WebSocketService(
        websocket_dao=websocket_dao,  # type: ignore[arg-type]
        access_token_rotation_handler=rotate,
    )

    assert await service.start_websocket_listener(
        "expired-access-token",
        callback,
    )
    await asyncio.wait_for(websocket_dao.reconnected.wait(), timeout=1)

    online_payload = {"version": 1, "type": "presence_update", "online": True}
    assert rotation_tokens == ["expired-access-token"]
    assert websocket_dao.connect_tokens == [
        "expired-access-token",
        "new-access-token",
    ]
    assert websocket_dao.sent_payloads == [online_payload, online_payload]

    await service.stop_websocket_listener()


@pytest.mark.asyncio
async def test_websocket_keeps_retrying_after_rotated_token_network_failure() -> None:
    websocket_dao = _InterruptedRotationWebSocketDAO()

    async def rotate(_: str | None) -> str:
        return "new-access-token"

    async def callback(_: dict[str, Any]) -> bool:
        return True

    service = WebSocketService(
        websocket_dao=websocket_dao,  # type: ignore[arg-type]
        access_token_rotation_handler=rotate,
    )

    assert await service.start_websocket_listener(
        "expired-access-token",
        callback,
    )
    await asyncio.wait_for(websocket_dao.reconnected.wait(), timeout=1)

    assert websocket_dao.connect_tokens == [
        "expired-access-token",
        "new-access-token",
        "new-access-token",
    ]

    await service.stop_websocket_listener()


@pytest.mark.asyncio
async def test_simultaneous_http_and_websocket_expiration_share_rotation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("Authorization") == "Bearer expired-access-token":
            return httpx.Response(401, json={"detail": "Token expired"})
        return httpx.Response(200, json={"status": "ok"})

    auth_dao = _RotatingAuthDAO()
    app_state = AppState()
    app_state.username = "alice"
    app_state.ed_private_key = "local-ed-private-key"
    app_state.token = "expired-access-token"
    websocket_dao = _ExpiringWebSocketDAO()

    async with CommonHTTPClient(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    ) as http_client:
        http_client.set_auth_token("expired-access-token")
        auth_service = AuthHTTPService(
            auth_dao=auth_dao,  # type: ignore[arg-type]
            encryption_service=_SigningEncryptionService(),  # type: ignore[arg-type]
            app_state=app_state,
            http_client=http_client,
        )
        auth_service.token = "expired-access-token"
        http_client.set_access_token_rotation_handler(
            auth_service.rotate_access_token
        )
        websocket_service = WebSocketService(
            websocket_dao=websocket_dao,  # type: ignore[arg-type]
            access_token_rotation_handler=auth_service.rotate_access_token,
        )

        async def callback(_: dict[str, Any]) -> bool:
            return True

        assert await websocket_service.start_websocket_listener(
            "expired-access-token",
            callback,
        )
        http_response, _ = await asyncio.gather(
            http_client.get("/protected"),
            asyncio.wait_for(websocket_dao.reconnected.wait(), timeout=1),
        )

        assert http_response == {"status": "ok"}
        assert auth_dao.challenge_calls == 1
        assert auth_dao.login_calls == 1
        assert websocket_dao.connect_tokens[-1] == "new-access-token"

        await websocket_service.stop_websocket_listener()
