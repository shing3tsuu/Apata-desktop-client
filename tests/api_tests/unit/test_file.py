import asyncio
import logging
from pathlib import Path
from uuid import UUID, uuid4

from dishka import Scope, make_async_container

from src.adapters.api.dao import AuthHTTPDAO
from src.adapters.api.service import AuthHTTPService, FileHTTPService
from src.adapters.encryption.service import EncryptionService
from src.providers import AppProvider
from tests.timing_wrapper import timer

API_BASE_URL = "http://127.0.0.1:8000"
TEST_IMAGE_PATH = Path(__file__).parents[2] / "test_data" / "images" / "image_1.png"
TEST_VIDEO_PATH = Path(__file__).parents[2] / "test_data" / "video" / "video_1.mp4"
OUTPUT_IMAGE_PATH = (
    Path(__file__).parents[2] / "test_data" / "output" / "received_from_api_image_1.png"
)
OUTPUT_VIDEO_PATH = (
    Path(__file__).parents[2] / "test_data" / "output" / "received_from_api_video_1.mp4"
)


def _make_container():
    return make_async_container(
        AppProvider(
            scope=Scope.APP,
            logger=logging.getLogger(__name__),
            symmetric_cipher="AESGCMSIV",
            asymmetric_cipher="X25519",
            signature_cipher="ED-25519",
            password_cipher="BCRYPT",
            base_url=API_BASE_URL,
            verify_ssl=False,
            base_ws_url="ws://127.0.0.1:8001",
        )
    )


def _unique_username() -> str:
    return f"file{uuid4().hex[:12]}"


async def _register_and_login(auth_service: AuthHTTPService) -> dict[str, str]:
    username = _unique_username()
    registration = await auth_service.register(username)
    login = await auth_service.login(
        username=username,
        ed_private_key=registration.ed_private_key,
    )
    return {
        "id": registration.id,
        "access_token": login.access_token,
        "ed_private_key": registration.ed_private_key,
        "ecdh_private_key": registration.ecdh_private_key,
    }


def _send_receive_and_save_file(
    *,
    source_path: Path,
    output_path: Path,
    expected_content_type: str,
) -> None:
    assert source_path.is_file(), f"Test file is missing: {source_path}"
    file_content = source_path.read_bytes()

    async def scenario() -> tuple[UUID, list, list]:
        container = _make_container()
        try:
            async with container() as request_container:
                auth_service = await request_container.get(AuthHTTPService)
                auth_dao = await request_container.get(AuthHTTPDAO)
                encryption_service = await request_container.get(EncryptionService)
                file_service = await request_container.get(FileHTTPService)

                sender = await _register_and_login(auth_service)
                recipient = await _register_and_login(auth_service)
                recipient_keys = await auth_dao.get_public_keys(
                    recipient["id"], sender["access_token"]
                )
                sender_keys = await auth_dao.get_public_keys(
                    sender["id"], recipient["access_token"]
                )
                ephemeral_keys = await encryption_service.generate_key_pairs()

                file_service.token = sender["access_token"]
                message_id = await file_service.send_encrypted_message_file(
                    chat_id=None,
                    recipient_id=UUID(recipient["id"]),
                    recipient_ed_public_key=recipient_keys["ed_public_key"],
                    sender_ed_private_key=sender["ed_private_key"],
                    sender_ecdh_private_key=ephemeral_keys.ecdh_private_key,
                    ephemeral_ecdh_public_key=ephemeral_keys.ecdh_public_key,
                    file_name=source_path.stem,
                    file_mime_type=source_path.suffix,
                    file_content=file_content,
                )
                assert message_id is not None

                file_service.token = recipient["access_token"]
                received = await file_service.get_undelivered_message_files(
                    ed_dict={UUID(sender["id"]): sender_keys["ed_public_key"]},
                    recipient_ecdh_private_key=recipient["ecdh_private_key"],
                )
                remaining = await file_service.get_undelivered_message_files(
                    ed_dict={UUID(sender["id"]): sender_keys["ed_public_key"]},
                    recipient_ecdh_private_key=recipient["ecdh_private_key"],
                )
                return message_id, received, remaining
        finally:
            await container.close()

    message_id, received, remaining = asyncio.run(scenario())

    assert len(received) == 1
    received_file = received[0]
    assert received_file.message_id == message_id
    assert received_file.chat_id is None
    assert received_file.file_name == source_path.stem
    assert received_file.file_mime_type == source_path.suffix
    assert received_file.file_size == len(file_content)
    assert received_file.file_content == file_content
    assert received_file.content_type == expected_content_type
    assert remaining == []

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(received_file.file_content)
    assert output_path.read_bytes() == file_content


@timer()
def test_file_service_sends_receives_and_acks_image_against_live_api() -> None:
    _send_receive_and_save_file(
        source_path=TEST_IMAGE_PATH,
        output_path=OUTPUT_IMAGE_PATH,
        expected_content_type="image",
    )


@timer()
def test_file_service_sends_receives_and_acks_chunked_video_against_live_api() -> None:
    assert TEST_VIDEO_PATH.stat().st_size > 4 * 1024 * 1024

    _send_receive_and_save_file(
        source_path=TEST_VIDEO_PATH,
        output_path=OUTPUT_VIDEO_PATH,
        expected_content_type="video",
    )
