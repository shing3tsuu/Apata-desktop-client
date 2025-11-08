import pytest
import logging
import random
from dishka import make_async_container

from src.providers import AppProvider
from src.presentation.pages import AppState

from src.adapters.api.service import AuthHTTPService
from src.adapters.database.service import LocalUserService, ContactService
from src.adapters.database.dto import LocalUserRequestDTO, ContactRequestDTO
from src.adapters.encryption.storage import EncryptedKeyStorage
from src.adapters.encryption.service import AbstractPasswordHasher

import time as t

test_user_1 = f"test_sender_{random.randint(0, 100000)}"
test_user_2 = f"test_receiver_{random.randint(0, 100000)}"
test_password = f"test_password_{random.randint(0, 100000)}"


class TestContact:
    __test__ = False
    def __init__(self, user_1_state: AppState, user_2_state: AppState, container):
        self._state = app_state
        self._container = container
        self._logger = logging.getLogger(__name__)

        self._user_1_state = user_1_state
        self._user_2_state = user_2_state

    async def setup_users(self):
        async with self._container() as request_container:
            auth_http_service = await request_container.get(AuthHTTPService)
            local_user_service = await request_container.get(LocalUserService)

            user_1_register_data = await auth_http_service.register(username=test_user_1)
            user_1_login_data = await auth_http_service.login(
                username=test_sender,
                ecdsa_private_key=user_1_register_data["ecdsa_private_key"]
            )
            user_1_data = await auth_http_service.get_current_user_info()

            hashed_password = await (await request_container.get(AbstractPasswordHasher)).hashing(test_password)
            await local_user_service.add_user(
                LocalUserRequestDTO(
                    server_user_id=user_1_data["id"],
                    username=test_user_1,
                    hashed_password=hashed_password
                )
            )

            local_user_1 = await local_user_service.get_user_data(LocalUserRequestDTO(username=test_user_1))
            data = await auth_http_service.get_public_keys(user_1_data["id"])
            self._test_user_1_state.update_from_login(
                username=test_user_1,
                local_user_id=local_user_1.id,
                server_user_id=user_1_data["id"],
                password=test_password,
                master_key=b"test_master_key_32_bytes_123456789012",  # Mock
                ecdsa_private_key=sender_register_data["ecdsa_private_key"],
                ecdh_public_key=data["ecdh_public_key"],
                ecdh_private_key=sender_register_data["ecdh_private_key"],
                token=sender_login_data["access_token"],
            )

            receiver_register_data = await auth_http_service.register(username=test_receiver)
            receiver_login_data = await auth_http_service.login(
                username=test_receiver,
                ecdsa_private_key=receiver_register_data["ecdsa_private_key"]
            )
            receiver_user_data = await auth_http_service.get_current_user_info()

            await local_user_service.add_user(
                LocalUserRequestDTO(
                    server_user_id=receiver_user_data["id"],
                    username=test_receiver,
                    hashed_password=hashed_password
                )
            )

            local_receiver_user = await local_user_service.get_user_data(LocalUserRequestDTO(username=test_receiver))
            data = await auth_http_service.get_public_keys(receiver_user_data["id"])
            self._receiver_state.update_from_login(
                username=test_receiver,
                local_user_id=local_receiver_user.id,
                server_user_id=receiver_user_data["id"],
                password=test_password,
                master_key=b"test_master_key_32_bytes_123456789012",
                ecdsa_private_key=receiver_register_data["ecdsa_private_key"],
                ecdh_public_key=data["ecdh_public_key"],
                ecdh_private_key=receiver_register_data["ecdh_private_key"],
                token=receiver_login_data["access_token"],
            )


@pytest.mark.asyncio
async def test_add_contact():
    container = make_async_container(AppProvider())
    sender_state = AppState()
    receiver_state = AppState()

    test_contacts = None

    try:
        test_contacts = TestContact(sender_state, receiver_state, container)

        await test_messaging.setup_users()

        await test_messaging.test_undelivered_messages()

        await test_messaging.test_websocket_message_flow()

        assert sender_state.is_authenticated
        assert receiver_state.is_authenticated
        assert sender_state.token is not None
        assert receiver_state.token is not None

    finally:
        if test_messaging:
            await test_messaging.cleanup()
        await container.close()