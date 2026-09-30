import asyncio
import logging
import os
from uuid import uuid4

import pytest
from dishka import Scope, make_async_container

from src.adapters.api.dao import AuthHTTPDAO
from src.adapters.api.dto import AuthRegisterResponseDTO
from src.adapters.api.service import AuthHTTPService
from src.adapters.encryption.service import EncryptionService
from src.adapters.encryption.service.dto import GenerateKeyPairResult
from src.exceptions import UserAlreadyExistsError
from src.providers import AppProvider
from tests.timing_wrapper import timer

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"
SIGNATURE_CIPHER = "ED-25519"


def api_base_url() -> str:
    explicit_url = os.getenv("APATA_API_BASE_URL") or os.getenv("API_BASE_URL")
    if explicit_url is not None and explicit_url:
        return explicit_url.rstrip("/")
    return DEFAULT_API_BASE_URL


def _make_container():
    return make_async_container(
        AppProvider(
            scope=Scope.APP,
            logger=logging.getLogger(__name__),
            symmetric_cipher="AESGCMSIV",
            asymmetric_cipher="X25519",
            signature_cipher=SIGNATURE_CIPHER,
            password_cipher="BCRYPT",
            base_url=api_base_url(),
            verify_ssl=False,
            base_ws_url="ws://127.0.0.1:8001",
        )
    )


def _unique_username() -> str:
    return f"apit{uuid4().hex[:10]}"


async def _register_user(
    dao: AuthHTTPDAO,
    encryption_service: EncryptionService,
    username: str,
) -> tuple[GenerateKeyPairResult, AuthRegisterResponseDTO]:
    keys = await encryption_service.generate_key_pairs()
    ecdh_signature = await encryption_service.sign_string(
        private_key_pem=keys.ed_private_key,
        string=keys.ecdh_public_key,
    )

    response = await dao.register_user(
        username=username,
        ed_public_key=keys.ed_public_key,
        ecdh_public_key=keys.ecdh_public_key,
        ecdh_signature=ecdh_signature,
    )

    return keys, response


@timer()
def test_auth_dao_registers_user_against_live_api() -> None:
    async def scenario() -> None:
        username = _unique_username()
        container = _make_container()
        try:
            async with container() as request_container:
                dao = await request_container.get(AuthHTTPDAO)
                encryption_service = await request_container.get(EncryptionService)

                _, response = await _register_user(dao, encryption_service, username)
        finally:
            await container.close()

        assert response.username == username
        assert response.id

    asyncio.run(scenario())


@timer()
def test_auth_dao_challenge_login_and_logout_against_live_api() -> None:
    async def scenario() -> None:
        username = _unique_username()
        container = _make_container()
        try:
            async with container() as request_container:
                dao = await request_container.get(AuthHTTPDAO)
                encryption_service = await request_container.get(EncryptionService)
                keys, _ = await _register_user(dao, encryption_service, username)

                challenge_response = await dao.get_challenge(username)
                signature = await encryption_service.sign_string(
                    private_key_pem=keys.ed_private_key,
                    string=challenge_response.challenge,
                )

                token_response = await dao.login(username, signature)
                logout_response = await dao.logout(token_response.access_token)
        finally:
            await container.close()

        assert isinstance(challenge_response.challenge, str)
        assert challenge_response.challenge
        assert token_response.access_token
        assert logout_response == {}

    asyncio.run(scenario())


@timer()
def test_auth_service_registers_user_against_live_api() -> None:
    async def scenario() -> None:
        username = _unique_username()
        container = _make_container()
        try:
            async with container() as request_container:
                service = await request_container.get(AuthHTTPService)

                response = await service.register(username)
        finally:
            await container.close()

        assert response.username == username
        assert response.id
        assert response.ed_private_key
        assert response.ecdsa_private_key == response.ed_private_key
        assert response.ecdh_private_key

    asyncio.run(scenario())


@timer()
def test_auth_service_login_against_live_api() -> None:
    async def scenario() -> None:
        username = _unique_username()
        container = _make_container()
        try:
            async with container() as request_container:
                service = await request_container.get(AuthHTTPService)

                register_response = await service.register(username)
                login_response = await service.login(
                    username=username,
                    ed_private_key=register_response.ed_private_key,
                )
                session_status = service.get_session_status()
                current_token = service.token
        finally:
            await container.close()

        assert login_response.access_token
        assert current_token == login_response.access_token
        assert session_status["is_authenticated"] is True
        assert session_status["has_token"] is True

    asyncio.run(scenario())


@timer()
def test_auth_service_maps_duplicate_username_against_live_api() -> None:
    async def scenario() -> None:
        username = _unique_username()
        container = _make_container()
        try:
            async with container() as request_container:
                service = await request_container.get(AuthHTTPService)

                await service.register(username)
                with pytest.raises(UserAlreadyExistsError) as exc_info:
                    await service.register(username)
        finally:
            await container.close()

        assert exc_info.value.context == {"username": username}

    asyncio.run(scenario())
