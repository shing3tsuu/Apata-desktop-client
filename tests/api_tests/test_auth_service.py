import pytest
import os
import base64
import logging
import random
from typing import Tuple, Optional
from dishka import make_async_container, FromDishka

from src.providers import AppProvider
from src.presentation.pages import AppState, Container

from src.adapters.api.service import AuthHTTPService

from src.adapters.database.service import LocalUserService
from src.adapters.database.dto import LocalUserRequestDTO, LocalUserDTO

from src.adapters.encryption.storage import EncryptedKeyStorage
from src.adapters.encryption.service import AbstractPasswordHasher

from src.exceptions import *

import time as t

test_user = f"test_user_{random.randint(0, 100000)}"
test_password = f"test_password_{random.randint(0, 100000)}"

class TestAuth(Container):
    async def register(self, username: str, password: str):
        try:
            step_start = t.time()
            register_data = await self.state.auth_http_service.register(username=username)
            print(f"Register HTTP: {t.time() - step_start:.2f}s")

            assert register_data["username"] == username
            assert register_data["ecdsa_private_key"] is not None
            assert register_data["ecdh_private_key"] is not None

            ecdh_private_key = register_data["ecdh_private_key"]
            ecdsa_private_key = register_data["ecdsa_private_key"]

            step_start = t.time()
            await self.state.key_storage.register_master_key(
                username=username,
                password=password
            )
            await self.state.key_storage.store_ecdsa_private_key(
                    username=username,
                    private_key_pem=ecdsa_private_key,
                    password=password
            )
            await self.state.key_storage.store_ecdh_private_key(
                    username=username,
                    ecdh_private_key=ecdh_private_key,
                    password=password
            )
            print(f"Register master key and store private keys in keyring: {t.time() - step_start:.2f}s")

            step_start = t.time()
            login_data = await self.state.auth_http_service.login(
                username=username,
                ecdsa_private_key=ecdsa_private_key
            )
            assert login_data["access_token"] is not None
            print(f"Login HTTP: {t.time() - step_start:.2f}s")

            step_start = t.time()
            data = await self.state.auth_http_service.get_current_user_info()
            assert data["id"] is not None
            print(f"Get current user info HTTP: {t.time() - step_start:.2f}s")

            step_start = t.time()
            hashed_password = await self.state.password_hasher.hashing(password)
            print(f"Hashing password with bcrypt (12 rounds): {t.time() - step_start:.2f}s")

            step_start = t.time()
            await self.state.local_user_service.add_user(
                LocalUserRequestDTO(
                    server_user_id=data["id"],
                    username=username,
                    hashed_password=hashed_password
                )
            )
            print(f"Store user to db: {t.time() - step_start:.2f}s")

            step_start = t.time()
            master_key = await self.state.key_storage.get_master_key(
                username=username,
                password=password
            )
            assert master_key is not None
            assert isinstance(master_key, bytes)
            assert len(master_key) == 32
            print(f"Get master key from keyring: {t.time() - step_start:.2f}s")

            step_start = t.time()
            local_user = await self.state.local_user_service.get_user_data(
                LocalUserRequestDTO(
                    username=username
                )
            )
            print(f"Get data user from db: {t.time() - step_start:.2f}s")

            self.state.update_from_login(
                username=username,
                local_user_id=local_user.id,
                server_user_id=data["id"],
                password=password,
                master_key=master_key,
                ecdsa_private_key=ecdsa_private_key,
                ecdh_private_key=ecdh_private_key,
                token=login_data["access_token"],
            )

            step_start = t.time()
            password_valid = await self.state.password_hasher.compare(password, local_user.hashed_password)
            assert password_valid is True
            print(f"Compare password with bcrypt (12 rounds): {t.time() - step_start:.2f}s")

            step_start = t.time()
            get_ecdsa_private_key = await self.state.key_storage.get_ecdsa_private_key(username, password)
            assert get_ecdsa_private_key is not None
            print(f"Get ecdsa private key from keyring: {t.time() - step_start:.2f}s")

            step_start = t.time()
            login_data = await self.state.auth_http_service.login(
                username=username,
                ecdsa_private_key=get_ecdsa_private_key
            )
            assert login_data["access_token"] is not None
            assert login_data["access_token"] != self.state.token
            print(f"Login HTTP with new ecdsa private key: {t.time() - step_start:.2f}s")

            step_start = t.time()
            data = await self.state.auth_http_service.get_current_user_info()
            assert data["id"] is not None
            print(f"Get current user info HTTP: {t.time() - step_start:.2f}s")

            step_start = t.time()
            delete = await self.state.local_user_service.delete_user(
                LocalUserRequestDTO(
                    username=username
                )
            )
            assert delete is True
            print(f"Delete user from db: {t.time() - step_start:.2f}s")

            step_start = t.time()
            self.state.key_storage.clear_storage(username)
            self.state.key_storage.clear_storage("shingetsu")
            empty_ecdsa_private_key = await self.state.key_storage.get_ecdsa_private_key(username, password)
            assert empty_ecdsa_private_key is None
            self.state.clear()
            assert self.state.ecdsa_private_key is None
            print(f"Clear state and keyring: {t.time() - step_start:.2f}s")
        finally:
            await self.state.local_user_service.delete_user(
                LocalUserRequestDTO(
                    username=username
                )
            )
            self.state.key_storage.clear_storage(username)
            self.state.clear()


@pytest.mark.asyncio
async def test_register():
    container = make_async_container(AppProvider())
    app_state = AppState()
    try:
        test_auth = TestAuth(app_state, container)
        await test_auth.setup_services()
        await test_auth.register(test_user, test_password)
    finally:
        await container.close()