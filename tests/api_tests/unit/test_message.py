import asyncio
import logging
import os
from typing import Any
from uuid import UUID, uuid4, uuid7

from dishka import Scope, make_async_container

from src.adapters.api.dao import AuthHTTPDAO, MessageHTTPDAO
from src.adapters.api.dto import MessageProcessingResultDTO
from src.adapters.api.service import (
    AuthHTTPService,
    ContactHTTPService,
    MessageHTTPService,
)
from src.adapters.encryption.service import EncryptionService
from src.providers import AppProvider
from tests.timing_wrapper import timer

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"


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


def _unique_username() -> str:
    return f"msg{uuid4().hex[:12]}"


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


@timer()
def test_message_service_reads_empty_inbox_against_live_api() -> None:
    async def scenario() -> list[dict[str, Any]]:
        container = _make_container()
        try:
            async with container() as request_container:
                auth_service = await request_container.get(AuthHTTPService)
                message_service = await request_container.get(MessageHTTPService)

                recipient = await _register_and_login(auth_service)
                message_service.token = recipient["access_token"]
                return await message_service.get_undelivered_messages(
                    ed_dict={},
                    recipient_ecdh_private_key=recipient["ecdh_private_key"],
                )
        finally:
            await container.close()

    assert asyncio.run(scenario()) == []


@timer()
def test_message_dao_sends_receives_and_acks_against_live_api() -> None:
    async def scenario() -> tuple[UUID, dict[str, Any], dict[str, Any]]:
        container = _make_container()
        try:
            async with container() as request_container:
                auth_service = await request_container.get(AuthHTTPService)
                message_dao = await request_container.get(MessageHTTPDAO)

                sender = await _register_and_login(auth_service)
                recipient = await _register_and_login(auth_service)
                message_id = uuid7()

                await message_dao.send_message_text(
                    recipient_id=UUID(recipient["id"]),
                    chat_id=None,
                    message="transport test payload",
                    message_id=message_id,
                    content_type="text",
                    ephemeral_public_key="transport-test-public-key",
                    ephemeral_signature="transport-test-signature",
                    token=sender["access_token"],
                )
                undelivered = await message_dao.get_undelivered_messages(
                    recipient["access_token"]
                )
                matching = [
                    item
                    for item in undelivered.get("messages", [])
                    if str(item.get("id")) == str(message_id)
                ]
                assert len(matching) == 1

                await message_dao.ack_messages(
                    [
                        MessageProcessingResultDTO(
                            message_id=message_id,
                            failed=False,
                        )
                    ],
                    recipient["access_token"],
                )
                remaining = await message_dao.get_undelivered_messages(
                    recipient["access_token"]
                )
                return message_id, matching[0], remaining
        finally:
            await container.close()

    message_id, received, remaining = asyncio.run(scenario())

    assert UUID(str(received["id"])) == message_id
    assert received["message"] == "transport test payload"
    assert received["content_type"] == "text"
    assert remaining.get("has_messages") is False
    assert remaining.get("messages") == []


@timer()
def test_failed_acknowledgement_is_visible_to_sender_against_live_api() -> None:
    async def scenario() -> tuple[UUID, list[UUID]]:
        container = _make_container()
        try:
            async with container() as request_container:
                auth_service = await request_container.get(AuthHTTPService)
                message_dao = await request_container.get(MessageHTTPDAO)

                sender = await _register_and_login(auth_service)
                recipient = await _register_and_login(auth_service)
                message_id = uuid7()
                await message_dao.send_message_text(
                    recipient_id=UUID(recipient["id"]),
                    chat_id=None,
                    message="invalid ciphertext",
                    message_id=message_id,
                    content_type="text",
                    ephemeral_public_key="invalid-public-key",
                    ephemeral_signature="invalid-signature",
                    token=sender["access_token"],
                )
                await message_dao.ack_messages(
                    [
                        MessageProcessingResultDTO(
                            message_id=message_id,
                            failed=True,
                        )
                    ],
                    recipient["access_token"],
                )
                response = await message_dao.get_failed_messages(sender["access_token"])
                failed_ids = [
                    UUID(str(message["id"])) for message in response.get("messages", [])
                ]
                return message_id, failed_ids
        finally:
            await container.close()

    message_id, failed_ids = asyncio.run(scenario())

    assert message_id in failed_ids


@timer()
def test_message_service_delivers_and_acks_against_live_api() -> None:
    async def scenario() -> tuple[
        UUID,
        str,
        list[dict[str, Any]],
        list[dict[str, Any]],
    ]:
        container = _make_container()
        try:
            async with container() as request_container:
                auth_service = await request_container.get(AuthHTTPService)
                auth_dao = await request_container.get(AuthHTTPDAO)
                contact_service = await request_container.get(ContactHTTPService)
                encryption_service = await request_container.get(EncryptionService)
                message_service = await request_container.get(MessageHTTPService)

                sender = await _register_and_login(auth_service)
                recipient = await _register_and_login(auth_service)
                recipient_keys = await auth_dao.get_public_keys(
                    recipient["id"],
                    sender["access_token"],
                )
                ephemeral_keys = await encryption_service.generate_key_pairs()

                plaintext = "live message test"
                message_service.token = sender["access_token"]
                message_id = await message_service.send_encrypted_message_text(
                    recipient_id=UUID(recipient["id"]),
                    chat_id=None,
                    message=plaintext,
                    recipient_ed_public_key=recipient_keys["ed_public_key"],
                    sender_ed_private_key=sender["ed_private_key"],
                    sender_ecdh_private_key=ephemeral_keys.ecdh_private_key,
                    ephemeral_ecdh_public_key=ephemeral_keys.ecdh_public_key,
                )
                assert message_id is not None

                contact_service.token = recipient["access_token"]
                contacts = await contact_service.list_all_contacts()
                sender_contact = next(
                    contact for contact in contacts if contact.user_id == sender["id"]
                )

                message_service.token = recipient["access_token"]
                received = await message_service.get_undelivered_messages(
                    ed_dict={
                        UUID(sender["id"]): sender_contact.ed_public_key,
                    },
                    recipient_ecdh_private_key=recipient["ecdh_private_key"],
                )
                remaining = await message_service.get_undelivered_messages(
                    ed_dict={
                        UUID(sender["id"]): sender_contact.ed_public_key,
                    },
                    recipient_ecdh_private_key=recipient["ecdh_private_key"],
                )
                return message_id, sender_contact.status, received, remaining
        finally:
            await container.close()

    message_id, contact_status, received, remaining = asyncio.run(scenario())

    assert contact_status == "blank"
    assert len(received) == 1
    assert UUID(str(received[0]["id"])) == message_id
    assert received[0]["decrypted_content"] == "live message test"
    assert received[0]["decryption_status"] == "success"
    assert received[0]["content_type"] == "text"
    assert remaining == []
