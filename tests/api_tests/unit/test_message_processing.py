import logging
from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dishka import AsyncContainer

from src.adapters.api.dao.auth import AuthHTTPDAO
from src.adapters.api.dao.message import MessageHTTPDAO
from src.adapters.api.dto import FailedMessageDTO
from src.adapters.api.service.file import FileHTTPService
from src.adapters.api.service.message import MessageHTTPService
from src.adapters.database.service import ChatService, ContactService, MessageService
from src.adapters.encryption.service import EncryptionService
from src.exceptions import DecryptionError
from src.presentation.interactors.login import SyncMessageHistoryInteractor
from src.providers.state import AppState


class FakeRequestContainer:
    def __init__(self, services: dict[type, object]):
        self._services = services

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def get(self, dependency_type):
        return self._services[dependency_type]


class FakeContainer:
    def __init__(self, services: dict[type, object]):
        self._services = services

    def __call__(self):
        return FakeRequestContainer(self._services)


@pytest.mark.asyncio
async def test_message_processing_acknowledges_success_and_failure() -> None:
    message_dao = AsyncMock(spec=MessageHTTPDAO)
    auth_dao = AsyncMock(spec=AuthHTTPDAO)
    encryption_service = AsyncMock(spec=EncryptionService)
    service = MessageHTTPService(
        message_dao=message_dao,
        auth_dao=auth_dao,
        encryption_service=encryption_service,
        logger=logging.getLogger(__name__),
    )
    service.token = "access-token"

    sender_id = uuid4()
    successful_message_id = uuid4()
    failed_message_id = uuid4()
    message_dao.get_undelivered_messages.return_value = {
        "has_messages": True,
        "messages": [
            {
                "id": str(successful_message_id),
                "sender_id": str(sender_id),
                "message": "successful-ciphertext",
                "ephemeral_public_key": "ephemeral-key",
                "ephemeral_signature": "ephemeral-signature",
            },
            {
                "id": str(failed_message_id),
                "sender_id": str(sender_id),
                "message": "failed-ciphertext",
                "ephemeral_public_key": "ephemeral-key",
                "ephemeral_signature": "ephemeral-signature",
            },
        ],
    }
    encryption_service.decrypt_message.side_effect = [
        "plaintext",
        DecryptionError("Invalid authentication tag"),
    ]

    messages = await service.get_undelivered_messages(
        ed_dict={sender_id: "sender-ed-public-key"},
        recipient_ecdh_private_key="recipient-ecdh-private-key",
    )

    assert [message["id"] for message in messages] == [str(successful_message_id)]
    results = message_dao.ack_messages.await_args.kwargs["results"]
    assert {(result.message_id, result.failed) for result in results} == {
        (successful_message_id, False),
        (failed_message_id, True),
    }


@pytest.mark.asyncio
async def test_message_processing_does_not_ack_an_invalid_message_id() -> None:
    message_dao = AsyncMock(spec=MessageHTTPDAO)
    service = MessageHTTPService(
        message_dao=message_dao,
        auth_dao=AsyncMock(spec=AuthHTTPDAO),
        encryption_service=AsyncMock(spec=EncryptionService),
        logger=logging.getLogger(__name__),
    )
    service.token = "access-token"
    message_dao.get_undelivered_messages.return_value = {
        "has_messages": True,
        "messages": [{"id": "invalid-message-id"}],
    }

    messages = await service.get_undelivered_messages(
        ed_dict={},
        recipient_ecdh_private_key="recipient-ecdh-private-key",
    )

    assert messages == []
    message_dao.ack_messages.assert_not_awaited()


@pytest.mark.asyncio
async def test_message_synchronization_persists_sender_failures() -> None:
    local_user_id = uuid4()
    failed_message_id = uuid4()
    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id
    app_state.master_key = b"master-key"
    app_state.ecdh_private_key = "recipient-ecdh-private-key"

    message_http_service = MagicMock(spec=MessageHTTPService)
    message_http_service.get_undelivered_messages = AsyncMock(return_value=[])
    message_http_service.get_failed_messages = AsyncMock(
        return_value=[
            FailedMessageDTO(
                id=failed_message_id,
                recipient_id=uuid4(),
                chat_id=None,
                timestamp=datetime.now(UTC),
                is_delivered=True,
                failed=True,
            )
        ]
    )
    file_http_service = MagicMock(spec=FileHTTPService)
    file_http_service.get_undelivered_message_files = AsyncMock(return_value=[])
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contacts = AsyncMock(return_value=[])
    chat_service = MagicMock(spec=ChatService)
    chat_service.get_chats = AsyncMock(return_value=[])
    message_service = MagicMock(spec=MessageService)
    message_service.mark_messages_failed = AsyncMock(return_value=1)
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: app_state,
                MessageHTTPService: message_http_service,
                FileHTTPService: file_http_service,
                ContactService: contact_service,
                ChatService: chat_service,
                MessageService: message_service,
            }
        ),
    )

    success, message, counts = await SyncMessageHistoryInteractor()(container)

    assert success, message
    assert counts == {"text_count": 0, "file_count": 0, "failed_count": 1}
    message_service.mark_messages_failed.assert_awaited_once_with(
        local_user_id,
        [failed_message_id],
    )
