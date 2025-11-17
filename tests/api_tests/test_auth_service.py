import pytest
import os
import base64
import logging
import random
from typing import Tuple, Optional
from dishka import make_async_container, FromDishka

from src.providers import AppProvider
from src.presentation.pages import AppState

from src.adapters.api.service import AuthHTTPService

from src.adapters.database.service import LocalUserService
from src.adapters.database.dto import LocalUserRequestDTO, LocalUserDTO

from src.adapters.encryption.storage import EncryptedKeyStorage
from src.adapters.encryption.service import AbstractPasswordHasher

from src.exceptions import *

import time as t

test_user = f"test_user_{random.randint(0, 100000)}"
test_password = f"test_password_{random.randint(0, 100000)}"

class TestAuth:
    __test__ = False
    def __init__(self, state: AppState, container):
        self._state = state
        self._container = container
        self._logger = logging.getLogger(__name__)

    async def register(self, username: str, password: str):
        async with self._container() as request_container:
            auth_http_service = await request_container.get(AuthHTTPService)
            local_user_service = await request_container.get(LocalUserService)
            key_storage = await request_container.get(EncryptedKeyStorage)
            password_hasher = await request_container.get(AbstractPasswordHasher)
            try:
                register_data = await auth_http_service.register(username=username)

                assert register_data["username"] == username
                assert register_data["ecdsa_private_key"] is not None
                assert register_data["ecdh_private_key"] is not None

                ecdh_private_key = register_data["ecdh_private_key"]
                ecdsa_private_key = register_data["ecdsa_private_key"]

                await key_storage.register_master_key(
                    username=username,
                    password=password
                )
                await key_storage.store_ecdsa_private_key(
                        username=username,
                        private_key_pem=ecdsa_private_key,
                        password=password
                )
                await key_storage.store_ecdh_private_key(
                        username=username,
                        ecdh_private_key=ecdh_private_key,
                        password=password
                )

                login_data = await auth_http_service.login(
                    username=username,
                    ecdsa_private_key=ecdsa_private_key
                )
                assert login_data["access_token"] is not None

                data = await auth_http_service.get_current_user_info()
                assert data["id"] is not None

                hashed_password = await password_hasher.hashing(password)

                await local_user_service.add_user(
                    LocalUserRequestDTO(
                        server_user_id=data["id"],
                        username=username,
                        hashed_password=hashed_password
                    )
                )

                master_key = await key_storage.get_master_key(
                    username=username,
                    password=password
                )
                assert master_key is not None
                assert isinstance(master_key, bytes)
                assert len(master_key) == 32

                local_user = await local_user_service.get_user_data(
                    LocalUserRequestDTO(
                        username=username
                    )
                )

                self._state.update_from_login(
                    username=username,
                    local_user_id=local_user.id,
                    server_user_id=data["id"],
                    password=password,
                    master_key=master_key,
                    ecdsa_private_key=ecdsa_private_key,
                    ecdh_public_key=None,
                    ecdh_private_key=ecdh_private_key,
                    token=login_data["access_token"],
                )

                password_valid = await password_hasher.compare(password, local_user.hashed_password)
                assert password_valid is True

                get_ecdsa_private_key = await key_storage.get_ecdsa_private_key(username, password)
                assert get_ecdsa_private_key is not None

                login_data = await auth_http_service.login(
                    username=username,
                    ecdsa_private_key=get_ecdsa_private_key
                )
                assert login_data["access_token"] is not None
                assert login_data["access_token"] != self._state.token

                data = await auth_http_service.get_current_user_info()
                assert data["id"] is not None

                delete = await local_user_service.delete_user(
                    LocalUserRequestDTO(
                        username=username
                    )
                )
                assert delete is True

                key_storage.clear_storage(username)
                empty_ecdsa_private_key = await key_storage.get_ecdsa_private_key(username, password)
                assert empty_ecdsa_private_key is None
                self._state.clear()
                assert self._state.ecdsa_private_key is None
            finally:
                await local_user_service.delete_user(
                    LocalUserRequestDTO(
                        username=username
                    )
                )
                key_storage.clear_storage(username)
                self._state.clear()


@pytest.mark.asyncio
async def test_register():
    container = make_async_container(AppProvider())
    app_state = AppState()
    try:
        test_auth = TestAuth(app_state, container)
        await test_auth.register(test_user, test_password)
    finally:
        await container.close()