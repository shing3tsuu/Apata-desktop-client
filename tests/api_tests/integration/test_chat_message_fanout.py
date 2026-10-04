import asyncio
from uuid import UUID, uuid4

import pytest

from src.adapters.api.service import (
    ChatHTTPService,
    ContactHTTPService,
    MessageHTTPService,
)
from src.adapters.database.service import ChatService, MessageService
from src.adapters.database.structures import ContactStatusEnum
from src.adapters.encryption.storage import keyring_storage
from src.presentation.interactors.login import (
    CacheConversationsInteractor,
    SynchronizeChatsInteractor,
    SynchronizeContactsInteractor,
)
from src.presentation.interactors.messenger import SendChatTextMessageInteractor
from src.providers.state import AppState
from tests.api_tests.integration.test_login_synchronization import (
    InMemoryKeyring,
    _login_and_synchronize_with_login_interactors,
    _make_container,
    _register_with_login_interactors,
)
from tests.timing_wrapper import timer


@pytest.fixture
def chat_keyring(monkeypatch):
    storage = InMemoryKeyring()
    monkeypatch.setattr(keyring_storage, "keyring", storage)
    return storage


async def _clear_state(container) -> None:
    async with container() as request_container:
        app_state = await request_container.get(AppState)
        app_state.clear_state()


async def _assert_contact_status(
    container,
    other_user_id: UUID,
    expected_status: ContactStatusEnum,
) -> None:
    async with container() as request_container:
        app_state = await request_container.get(AppState)
        contact_http_service = await request_container.get(ContactHTTPService)
        assert app_state.token is not None
        contact_http_service.token = app_state.token
        contacts = await contact_http_service.list_all_contacts()
    matching = [
        contact for contact in contacts if UUID(contact.user_id) == other_user_id
    ]
    assert len(matching) == 1
    assert matching[0].status == expected_status.value


async def _read_chat_messages(container, server_chat_id: UUID):
    async with container() as request_container:
        app_state = await request_container.get(AppState)
        chat_service = await request_container.get(ChatService)
        message_service = await request_container.get(MessageService)
        assert app_state.local_user_id is not None
        assert app_state.master_key is not None
        local_chat = await chat_service.get_chat_by_server_id(
            app_state.local_user_id,
            server_chat_id,
        )
        message_service.master_key = app_state.master_key
        return await message_service.get_recent_messages(
            app_state.local_user_id,
            chat_id=local_chat.id,
            limit=10,
        )


@timer()
def test_chat_message_fanout_survives_recipients_next_login(chat_keyring) -> None:
    async def scenario() -> None:
        owner_container = _make_container()
        first_recipient_container = _make_container()
        second_recipient_container = _make_container()
        containers = [
            owner_container,
            first_recipient_container,
            second_recipient_container,
        ]
        suffix = uuid4().hex[:12]
        owner_username = f"chat_owner_{suffix}"
        first_recipient_username = f"chat_first_{suffix}"
        second_recipient_username = f"chat_second_{suffix}"
        password = "integration-password"
        plaintext = "fan-out message before recipient login synchronization"

        try:
            owner = await _register_with_login_interactors(
                owner_container,
                owner_username,
                password,
            )
            first_recipient = await _register_with_login_interactors(
                first_recipient_container,
                first_recipient_username,
                password,
            )
            second_recipient = await _register_with_login_interactors(
                second_recipient_container,
                second_recipient_username,
                password,
            )
            owner_id = owner["server_user_id"]
            first_recipient_id = first_recipient["server_user_id"]
            second_recipient_id = second_recipient["server_user_id"]
            assert isinstance(owner_id, UUID)
            assert isinstance(first_recipient_id, UUID)
            assert isinstance(second_recipient_id, UUID)

            async with owner_container() as request_container:
                owner_state = await request_container.get(AppState)
                owner_contacts = await request_container.get(ContactHTTPService)
                assert owner_state.token is not None
                owner_contacts.token = owner_state.token
                await owner_contacts.create_contact_request(str(first_recipient_id))

            async with first_recipient_container() as request_container:
                recipient_state = await request_container.get(AppState)
                recipient_contacts = await request_container.get(ContactHTTPService)
                assert recipient_state.token is not None
                recipient_contacts.token = recipient_state.token
                incoming = [
                    contact
                    for contact in await recipient_contacts.list_all_contacts()
                    if UUID(contact.user_id) == owner_id
                ]
                assert len(incoming) == 1
                assert incoming[0].contact_id is not None
                await recipient_contacts.accept_contact_request_dto(
                    incoming[0].contact_id
                )

            async with owner_container() as request_container:
                owner_state = await request_container.get(AppState)
                chat_http_service = await request_container.get(ChatHTTPService)
                assert owner_state.token is not None
                chat_http_service.token = owner_state.token
                chat = await chat_http_service.create_chat("Fan-out integration chat")
                await chat_http_service.add_participant(chat.id, first_recipient_id)
                await chat_http_service.add_participant(chat.id, second_recipient_id)

            await _assert_contact_status(
                owner_container,
                first_recipient_id,
                ContactStatusEnum.ACCEPTED,
            )
            await _assert_contact_status(
                owner_container,
                second_recipient_id,
                ContactStatusEnum.BLANK,
            )

            await _clear_state(first_recipient_container)
            await _clear_state(second_recipient_container)

            (
                contacts_success,
                contacts_message,
                _,
            ) = await SynchronizeContactsInteractor()(owner_container)
            assert contacts_success, contacts_message
            chats_success, chats_message, _ = await SynchronizeChatsInteractor()(
                owner_container
            )
            assert chats_success, chats_message
            cache_success, cache_message, _ = await CacheConversationsInteractor()(
                owner_container
            )
            assert cache_success, cache_message

            async with owner_container() as request_container:
                owner_state = await request_container.get(AppState)
                owner_chat_cache = next(
                    cached_chat
                    for cached_chat in owner_state.chats_cache
                    if cached_chat.server_chat_id == chat.id
                )

            (
                send_success,
                send_message,
                sender_message,
            ) = await SendChatTextMessageInteractor()(
                owner_container,
                owner_chat_cache,
                plaintext,
            )
            assert send_success, send_message
            assert sender_message is not None
            assert sender_message.logical_message_id is not None

            sender_messages = await _read_chat_messages(owner_container, chat.id)
            assert len(sender_messages) == 1
            assert sender_messages[0].content == plaintext
            assert sender_messages[0].logical_message_id == (
                sender_message.logical_message_id
            )

            async with owner_container() as request_container:
                owner_state = await request_container.get(AppState)
                message_http_service = await request_container.get(MessageHTTPService)
                assert owner_state.token is not None
                message_http_service.token = owner_state.token
                assert await message_http_service.get_failed_messages() == []

            (
                _,
                _,
                first_sync_messages,
            ) = await _login_and_synchronize_with_login_interactors(
                first_recipient_container,
                first_recipient_username,
                password,
            )
            (
                _,
                _,
                second_sync_messages,
            ) = await _login_and_synchronize_with_login_interactors(
                second_recipient_container,
                second_recipient_username,
                password,
            )
            assert first_sync_messages == {
                "text_count": 1,
                "file_count": 0,
                "failed_count": 0,
            }
            assert second_sync_messages == {
                "text_count": 1,
                "file_count": 0,
                "failed_count": 0,
            }

            first_messages = await _read_chat_messages(
                first_recipient_container,
                chat.id,
            )
            second_messages = await _read_chat_messages(
                second_recipient_container,
                chat.id,
            )
            assert len(first_messages) == 1
            assert len(second_messages) == 1
            assert first_messages[0].content == plaintext
            assert second_messages[0].content == plaintext
            assert first_messages[0].server_message_id != (
                second_messages[0].server_message_id
            )
            assert first_messages[0].logical_message_id == (
                second_messages[0].logical_message_id
            )
            assert first_messages[0].logical_message_id == (
                sender_message.logical_message_id
            )
            assert first_messages[0].timestamp == second_messages[0].timestamp

            await _assert_contact_status(
                first_recipient_container,
                owner_id,
                ContactStatusEnum.ACCEPTED,
            )
            await _assert_contact_status(
                second_recipient_container,
                owner_id,
                ContactStatusEnum.BLANK,
            )
        finally:
            await asyncio.gather(*(container.close() for container in containers))

    asyncio.run(scenario())
