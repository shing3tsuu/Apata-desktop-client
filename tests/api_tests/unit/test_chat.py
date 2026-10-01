import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID, uuid4, uuid7

import pytest
from dishka import Scope, make_async_container

from src.adapters.api.dao import ChatHTTPDAO, CommonHTTPClient, MessageHTTPDAO
from src.adapters.api.dto import (
    ChatDTO,
    ChatEventDTO,
    ChatParticipantChangeDTO,
    ChatParticipantDTO,
    MessageProcessingResultDTO,
)
from src.adapters.api.service import (
    AuthHTTPService,
    ChatHTTPService,
    ContactHTTPService,
)
from src.exceptions import AuthenticationError
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


async def _register_and_login(
    auth_service: AuthHTTPService,
) -> dict[str, Any]:
    username = f"chat{uuid4().hex[:12]}"
    registration = await auth_service.register(username)
    login = await auth_service.login(
        username=username,
        ed_private_key=registration.ed_private_key,
    )
    return {
        "id": UUID(registration.id),
        "access_token": login.access_token,
    }


async def _accept_contact(
    contact_service: ContactHTTPService,
    requester: dict[str, Any],
    receiver: dict[str, Any],
) -> None:
    contact_service.token = requester["access_token"]
    outgoing = await contact_service.create_contact_request(str(receiver["id"]))
    assert outgoing.contact_id is not None

    contact_service.token = receiver["access_token"]
    accepted = await contact_service.answer_contact_request(
        contact_id=outgoing.contact_id,
        action="accept",
    )
    assert accepted.status == "accepted"


async def _create_chat_with_participant(
    chat_service: ChatHTTPService,
    contact_service: ContactHTTPService,
    owner: dict[str, Any],
    participant: dict[str, Any],
) -> ChatDTO:
    await _accept_contact(
        contact_service=contact_service,
        requester=owner,
        receiver=participant,
    )
    chat_service.token = owner["access_token"]
    chat = await chat_service.create_chat("Live chat flow")
    change = await chat_service.add_participant(
        chat_id=chat.id,
        user_id=participant["id"],
    )

    assert change.participant.chat_id == chat.id
    assert change.participant.user_id == participant["id"]
    assert change.participant.left_at is None
    assert change.event.event_type == "member_added"
    return chat


def _message_ids(response: dict[str, Any]) -> set[UUID]:
    messages = response.get("messages")
    assert isinstance(messages, list)
    return {
        UUID(str(message["id"])) for message in messages if isinstance(message, dict)
    }


def test_chat_http_service_token_property() -> None:
    service = ChatHTTPService(chat_dao=MagicMock(spec=ChatHTTPDAO))

    assert service.token is None

    with pytest.raises(ValueError):
        service.token = ""

    service.token = "access-token"
    assert service.token == "access-token"

    del service.token
    assert service.token is None


@pytest.mark.asyncio
async def test_chat_http_dao_calls_chat_endpoints() -> None:
    chat_id = uuid4()
    user_id = uuid4()
    chat_response = {
        "id": str(chat_id),
        "owner_id": str(uuid4()),
        "name": "team-chat",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    participant_response = {
        "participant": {
            "chat_id": str(chat_id),
            "user_id": str(user_id),
            "invited_by_user_id": str(uuid4()),
            "joined_at": datetime.now(timezone.utc).isoformat(),
            "left_at": None,
        },
        "event": {
            "id": str(uuid4()),
            "chat_id": str(chat_id),
            "user_id": str(user_id),
            "event_type": "member_added",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "target_user_id": None,
        },
    }
    http_client = MagicMock(spec=CommonHTTPClient)
    http_client.post = AsyncMock(side_effect=[chat_response, participant_response])
    http_client.delete = AsyncMock(side_effect=[{}, participant_response])
    dao = ChatHTTPDAO(http_client=http_client)

    created = await dao.create_chat(name="team-chat", token="access-token")
    deleted = await dao.delete_chat(chat_id=chat_id, token="access-token")
    added = await dao.add_participant(
        chat_id=chat_id,
        user_id=user_id,
        token="access-token",
    )
    removed = await dao.remove_participant(
        chat_id=chat_id,
        user_id=user_id,
        token="access-token",
    )

    assert created is chat_response
    assert deleted == {}
    assert added is participant_response
    assert removed is participant_response
    assert http_client.set_auth_token.call_args_list == [
        call("access-token"),
        call("access-token"),
        call("access-token"),
        call("access-token"),
    ]
    assert http_client.post.await_args_list == [
        call("/chats", {"name": "team-chat"}),
        call(
            f"/chats/{chat_id}/participants",
            {"user_id": str(user_id)},
        ),
    ]
    assert http_client.delete.await_args_list == [
        call(f"/chats/{chat_id}"),
        call(f"/chats/{chat_id}/participants/{user_id}"),
    ]


@pytest.mark.asyncio
async def test_chat_http_dao_lists_chats_participants_and_incremental_events() -> None:
    chat_id = uuid4()
    user_id = uuid4()
    after = datetime.now(timezone.utc)
    chat_response = {
        "id": str(chat_id),
        "owner_id": str(user_id),
        "name": "team-chat",
        "created_at": after.isoformat(),
    }
    participant_response = {
        "chat_id": str(chat_id),
        "user_id": str(user_id),
        "invited_by_user_id": None,
        "joined_at": after.isoformat(),
        "left_at": None,
    }
    event_response = {
        "id": str(uuid4()),
        "chat_id": str(chat_id),
        "user_id": str(user_id),
        "event_type": "member_added",
        "timestamp": after.isoformat(),
        "target_user_id": None,
    }
    http_client = MagicMock(spec=CommonHTTPClient)
    http_client.get = AsyncMock(
        side_effect=[
            [chat_response],
            [participant_response],
            [event_response],
        ]
    )
    dao = ChatHTTPDAO(http_client=http_client)

    chats = await dao.get_chats(token="access-token")
    participants = await dao.get_participants(chat_id, token="access-token")
    events = await dao.get_events(
        chat_id,
        token="access-token",
        after=after,
    )

    assert chats == [chat_response]
    assert participants == [participant_response]
    assert events == [event_response]
    assert http_client.get.await_args_list == [
        call("/chats"),
        call(f"/chats/{chat_id}/participants"),
        call(f"/chats/{chat_id}/events", params={"after": after.isoformat()}),
    ]


@pytest.mark.asyncio
async def test_chat_http_service_returns_dtos_and_delete_result() -> None:
    chat_id = uuid4()
    owner_id = uuid4()
    user_id = uuid4()
    invited_by_user_id = uuid4()
    event_id = uuid4()
    created_at = datetime.now(timezone.utc)
    joined_at = datetime.now(timezone.utc)
    timestamp = datetime.now(timezone.utc)
    chat_dao = MagicMock(spec=ChatHTTPDAO)
    chat_dao.create_chat = AsyncMock(
        return_value={
            "id": str(chat_id),
            "owner_id": str(owner_id),
            "name": "team-chat",
            "created_at": created_at.isoformat(),
        }
    )
    chat_dao.delete_chat = AsyncMock(return_value={})
    participant_change = {
        "participant": {
            "chat_id": str(chat_id),
            "user_id": str(user_id),
            "invited_by_user_id": str(invited_by_user_id),
            "joined_at": joined_at.isoformat(),
            "left_at": None,
        },
        "event": {
            "id": str(event_id),
            "chat_id": str(chat_id),
            "user_id": str(owner_id),
            "event_type": "member_added",
            "timestamp": timestamp.isoformat(),
            "target_user_id": str(user_id),
        },
    }
    chat_dao.add_participant = AsyncMock(return_value=participant_change)
    chat_dao.remove_participant = AsyncMock(return_value=participant_change)
    service = ChatHTTPService(chat_dao=chat_dao)
    service.token = "access-token"

    created = await service.create_chat("team-chat")
    deleted = await service.delete_chat(chat_id)
    added = await service.add_participant(chat_id, user_id)
    removed = await service.remove_participant(chat_id, user_id)

    assert created == ChatDTO(
        id=chat_id,
        owner_id=owner_id,
        name="team-chat",
        created_at=created_at,
    )
    expected_change = ChatParticipantChangeDTO(
        participant=ChatParticipantDTO(
            chat_id=chat_id,
            user_id=user_id,
            invited_by_user_id=invited_by_user_id,
            joined_at=joined_at,
            left_at=None,
        ),
        event=ChatEventDTO(
            id=event_id,
            chat_id=chat_id,
            user_id=owner_id,
            event_type="member_added",
            timestamp=timestamp,
            target_user_id=user_id,
        ),
    )
    assert deleted is True
    assert added == expected_change
    assert removed == expected_change
    chat_dao.create_chat.assert_awaited_once_with(
        name="team-chat",
        token="access-token",
    )
    chat_dao.delete_chat.assert_awaited_once_with(
        chat_id=chat_id,
        token="access-token",
    )
    chat_dao.add_participant.assert_awaited_once_with(
        chat_id=chat_id,
        user_id=user_id,
        token="access-token",
    )
    chat_dao.remove_participant.assert_awaited_once_with(
        chat_id=chat_id,
        user_id=user_id,
        token="access-token",
    )


@pytest.mark.asyncio
async def test_chat_http_service_requires_authentication() -> None:
    chat_dao = MagicMock(spec=ChatHTTPDAO)
    service = ChatHTTPService(chat_dao=chat_dao)

    with pytest.raises(AuthenticationError):
        await service.create_chat("team-chat")

    with pytest.raises(AuthenticationError):
        await service.delete_chat(uuid4())

    with pytest.raises(AuthenticationError):
        await service.add_participant(uuid4(), uuid4())

    with pytest.raises(AuthenticationError):
        await service.remove_participant(uuid4(), uuid4())


@pytest.mark.asyncio
async def test_chat_http_service_clears_rejected_token() -> None:
    chat_dao = MagicMock(spec=ChatHTTPDAO)
    chat_dao.create_chat = AsyncMock(side_effect=AuthenticationError("Session expired"))
    service = ChatHTTPService(chat_dao=chat_dao)
    service.token = "expired-token"

    with pytest.raises(AuthenticationError):
        await service.create_chat("team-chat")

    with pytest.raises(AuthenticationError):
        await service.delete_chat(uuid4())


@timer()
def test_chat_service_live_creates_adds_participant_and_deletes_chat() -> None:
    async def scenario() -> None:
        container = _make_container()
        try:
            async with container() as request_container:
                auth_service = await request_container.get(AuthHTTPService)
                contact_service = await request_container.get(ContactHTTPService)
                chat_service = await request_container.get(ChatHTTPService)

                owner = await _register_and_login(auth_service)
                participant = await _register_and_login(auth_service)
                chat = await _create_chat_with_participant(
                    chat_service=chat_service,
                    contact_service=contact_service,
                    owner=owner,
                    participant=participant,
                )

                chat_service.token = owner["access_token"]
                deleted = await chat_service.delete_chat(chat.id)
        finally:
            await container.close()

        assert chat.owner_id == owner["id"]
        assert chat.name == "Live chat flow"
        assert deleted is True

    asyncio.run(scenario())


@timer()
def test_chat_service_live_removes_participant() -> None:
    async def scenario() -> None:
        container = _make_container()
        try:
            async with container() as request_container:
                auth_service = await request_container.get(AuthHTTPService)
                contact_service = await request_container.get(ContactHTTPService)
                chat_service = await request_container.get(ChatHTTPService)

                owner = await _register_and_login(auth_service)
                participant = await _register_and_login(auth_service)
                chat = await _create_chat_with_participant(
                    chat_service=chat_service,
                    contact_service=contact_service,
                    owner=owner,
                    participant=participant,
                )

                chat_service.token = owner["access_token"]
                removed = await chat_service.remove_participant(
                    chat_id=chat.id,
                    user_id=participant["id"],
                )
        finally:
            await container.close()

        assert removed.participant.chat_id == chat.id
        assert removed.participant.user_id == participant["id"]
        assert removed.participant.left_at is not None
        assert removed.event.event_type == "member_removed"
        assert removed.event.user_id == owner["id"]
        assert removed.event.target_user_id == participant["id"]

    asyncio.run(scenario())


@timer()
def test_message_dao_live_sends_with_chat_id_for_active_participants() -> None:
    async def scenario() -> None:
        container = _make_container()
        try:
            async with container() as request_container:
                auth_service = await request_container.get(AuthHTTPService)
                contact_service = await request_container.get(ContactHTTPService)
                chat_service = await request_container.get(ChatHTTPService)
                message_dao = await request_container.get(MessageHTTPDAO)

                owner = await _register_and_login(auth_service)
                participant = await _register_and_login(auth_service)
                chat = await _create_chat_with_participant(
                    chat_service=chat_service,
                    contact_service=contact_service,
                    owner=owner,
                    participant=participant,
                )
                owner_message_id = uuid7()
                participant_message_id = uuid7()

                await message_dao.send_message_text(
                    recipient_id=participant["id"],
                    chat_id=chat.id,
                    message="owner-chat-ciphertext",
                    message_id=owner_message_id,
                    content_type="text",
                    ephemeral_public_key="owner-ephemeral-public-key",
                    ephemeral_signature="owner-ephemeral-signature",
                    token=owner["access_token"],
                )
                await message_dao.send_message_text(
                    recipient_id=owner["id"],
                    chat_id=chat.id,
                    message="participant-chat-ciphertext",
                    message_id=participant_message_id,
                    content_type="text",
                    ephemeral_public_key="participant-ephemeral-public-key",
                    ephemeral_signature="participant-ephemeral-signature",
                    token=participant["access_token"],
                )
                participant_inbox = await message_dao.get_undelivered_messages(
                    participant["access_token"]
                )
                owner_inbox = await message_dao.get_undelivered_messages(
                    owner["access_token"]
                )

                await message_dao.ack_messages(
                    [
                        MessageProcessingResultDTO(
                            message_id=owner_message_id,
                            failed=False,
                        )
                    ],
                    participant["access_token"],
                )
                await message_dao.ack_messages(
                    [
                        MessageProcessingResultDTO(
                            message_id=participant_message_id,
                            failed=False,
                        )
                    ],
                    owner["access_token"],
                )
        finally:
            await container.close()

        assert participant_inbox.get("has_messages") is True
        assert owner_inbox.get("has_messages") is True
        assert _message_ids(participant_inbox) == {owner_message_id}
        assert _message_ids(owner_inbox) == {participant_message_id}
        assert participant_inbox["messages"][0]["message"] == ("owner-chat-ciphertext")
        assert owner_inbox["messages"][0]["message"] == ("participant-chat-ciphertext")

    asyncio.run(scenario())


@timer()
def test_message_dao_live_rejects_non_participant() -> None:
    async def scenario() -> None:
        container = _make_container()
        try:
            async with container() as request_container:
                auth_service = await request_container.get(AuthHTTPService)
                contact_service = await request_container.get(ContactHTTPService)
                chat_service = await request_container.get(ChatHTTPService)
                message_dao = await request_container.get(MessageHTTPDAO)

                owner = await _register_and_login(auth_service)
                participant = await _register_and_login(auth_service)
                non_participant = await _register_and_login(auth_service)
                chat = await _create_chat_with_participant(
                    chat_service=chat_service,
                    contact_service=contact_service,
                    owner=owner,
                    participant=participant,
                )

                with pytest.raises(AuthenticationError) as non_participant_error:
                    await message_dao.send_message_text(
                        recipient_id=owner["id"],
                        chat_id=chat.id,
                        message="non-participant-ciphertext",
                        message_id=uuid7(),
                        content_type="text",
                        ephemeral_public_key="non-participant-public-key",
                        ephemeral_signature="non-participant-signature",
                        token=non_participant["access_token"],
                    )

                owner_inbox = await message_dao.get_undelivered_messages(
                    owner["access_token"]
                )
        finally:
            await container.close()

        error = non_participant_error.value
        assert error.message == "Chat participant access is forbidden"
        assert error.context["status_code"] == 403
        response_data = error.context["response_data"]
        assert response_data["code"] == "chat_participant_forbidden"
        assert response_data["detail"] == "Chat participant access is forbidden"
        assert response_data["status_code"] == 403
        assert owner_inbox == {"has_messages": False, "messages": []}

    asyncio.run(scenario())


@timer()
def test_message_dao_live_rejects_removed_participant() -> None:
    async def scenario() -> None:
        container = _make_container()
        try:
            async with container() as request_container:
                auth_service = await request_container.get(AuthHTTPService)
                contact_service = await request_container.get(ContactHTTPService)
                chat_service = await request_container.get(ChatHTTPService)
                message_dao = await request_container.get(MessageHTTPDAO)

                owner = await _register_and_login(auth_service)
                participant = await _register_and_login(auth_service)
                chat = await _create_chat_with_participant(
                    chat_service=chat_service,
                    contact_service=contact_service,
                    owner=owner,
                    participant=participant,
                )

                chat_service.token = owner["access_token"]
                await chat_service.remove_participant(
                    chat_id=chat.id,
                    user_id=participant["id"],
                )

                with pytest.raises(AuthenticationError) as error_info:
                    await message_dao.send_message_text(
                        recipient_id=owner["id"],
                        chat_id=chat.id,
                        message="removed-participant-ciphertext",
                        message_id=uuid7(),
                        content_type="text",
                        ephemeral_public_key="removed-participant-public-key",
                        ephemeral_signature="removed-participant-signature",
                        token=participant["access_token"],
                    )

                owner_inbox = await message_dao.get_undelivered_messages(
                    owner["access_token"]
                )
        finally:
            await container.close()

        error = error_info.value
        assert error.message == "Chat participant access is forbidden"
        assert error.context["status_code"] == 403
        response_data = error.context["response_data"]
        assert response_data["code"] == "chat_participant_forbidden"
        assert response_data["detail"] == "Chat participant access is forbidden"
        assert response_data["status_code"] == 403
        assert owner_inbox == {"has_messages": False, "messages": []}

    asyncio.run(scenario())
