import asyncio
import logging
import os
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from dishka import Scope, make_async_container

from src.adapters.api.dao import AuthHTTPDAO
from src.adapters.api.service import AuthHTTPService, ContactHTTPService, FileHTTPService, MessageHTTPService
from src.adapters.encryption.service import EncryptionService
from src.providers import AppProvider
from tests.timing_wrapper import timer

TEST_IMAGE_PATH = Path(__file__).parents[2] / "test_data" / "images" / "image_1.png"

DEFAULT_API_BASE_URL = "http://127.0.0.1:8001"


def api_base_url() -> str:
    explicit_url = os.getenv("APATA_API_BASE_URL") or os.getenv("API_BASE_URL")
    if explicit_url:
        return explicit_url.rstrip("/")
    return DEFAULT_API_BASE_URL


def _make_container():
    return make_async_container(
        AppProvider(
            scope=Scope.APP,
            logger=logging.getLogger(__name__),
            symmetric_cipher="AESGCMSIV",
            asymmetric_cipher="X25519",
            signature_cipher="ED-25519",
            password_cipher="BCRYPT",
            base_url=api_base_url(),
            verify_ssl=False,
            base_ws_url="ws://127.0.0.1:8001",
        )
    )


@timer()
def test_send_multiple_text_and_one_file_message_to_user_222() -> None:
    async def scenario() -> None:
        container = _make_container()
        try:
            async with container() as request_container:
                auth_service = await request_container.get(AuthHTTPService)
                auth_dao = await request_container.get(AuthHTTPDAO)
                contact_service = await request_container.get(ContactHTTPService)
                encryption_service = await request_container.get(EncryptionService)
                message_service = await request_container.get(MessageHTTPService)
                file_service = await request_container.get(FileHTTPService)

                sender_username = f"sender_{uuid4().hex[:8]}"
                registration = await auth_service.register(sender_username)
                login = await auth_service.login(
                    username=sender_username,
                    ed_private_key=registration.ed_private_key,
                )
                sender = {
                    "id": registration.id,
                    "access_token": login.access_token,
                    "ed_private_key": registration.ed_private_key,
                    "ecdh_private_key": registration.ecdh_private_key,
                }

                contact_service.token = sender["access_token"]
                search_results = await contact_service.search_contacts("222")
                if not search_results.items:
                    pytest.skip("User '222' not found – cannot run E2E test")

                receiver = search_results.items[0]
                receiver_id = UUID(receiver.user_id)

                receiver_keys = await auth_dao.get_public_keys(
                    receiver_id, sender["access_token"]
                )

                message_service.token = sender["access_token"]
                file_service.token = sender["access_token"]

                plaintexts = ["Hello", "How are you?", "Test message"]
                for plaintext in plaintexts:
                    ephemeral_keys = await encryption_service.generate_key_pairs()
                    msg_id = await message_service.send_encrypted_message_text(
                        recipient_id=receiver_id,
                        chat_id=None,
                        message=plaintext,
                        recipient_ed_public_key=receiver_keys["ed_public_key"],
                        sender_ed_private_key=sender["ed_private_key"],
                        sender_ecdh_private_key=ephemeral_keys.ecdh_private_key,
                        ephemeral_ecdh_public_key=ephemeral_keys.ecdh_public_key,
                    )
                    assert msg_id is not None, "Text message ID is None"

                file_content = TEST_IMAGE_PATH.read_bytes()
                ephemeral_keys = await encryption_service.generate_key_pairs()
                file_message_id = await file_service.send_encrypted_message_file(
                    chat_id=None,
                    recipient_id=receiver_id,
                    recipient_ed_public_key=receiver_keys["ed_public_key"],
                    sender_ed_private_key=sender["ed_private_key"],
                    sender_ecdh_private_key=ephemeral_keys.ecdh_private_key,
                    ephemeral_ecdh_public_key=ephemeral_keys.ecdh_public_key,
                    file_name="test_image",
                    file_mime_type=".png",
                    file_content=file_content,
                )
                assert file_message_id is not None, "File message ID is None"

        finally:
            await container.close()

    asyncio.run(scenario())