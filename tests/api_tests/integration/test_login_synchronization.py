import asyncio
import logging
import os
from uuid import UUID, uuid4

import pytest
from dishka import Scope, make_async_container

from src.adapters.api.service import (
    AuthHTTPService,
    ChatHTTPService,
    ContactHTTPService,
    MessageHTTPService,
)
from src.adapters.database.service import ChatService, ContactService, MessageService
from src.adapters.database.structures import ChatEventTypeEnum, ContactStatusEnum
from src.adapters.encryption.service import EncryptionService
from src.adapters.encryption.storage import keyring_storage
from src.presentation.interactors.login import (
    AddUserToDatabaseInteractor,
    CheckLocalUserLoginInteractor,
    CheckLocalUserRegisterInteractor,
    ComparePasswordInteractor,
    ContainKeysInteractor,
    GetPrivateKeysInteractor,
    HashingPasswordInteractor,
    LoginUserInteractor,
    RegisterUserOnServerInteractor,
    RotateKeysInteractor,
    SynchronizeChatsInteractor,
    SynchronizeContactsInteractor,
    SyncMessageHistoryInteractor,
)
from src.providers import AppProvider, StateProvider
from src.providers.state import AppState
from tests.providers import MockDBProvider
from tests.timing_wrapper import timer

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"


def api_base_url() -> str:
    return (
        os.getenv("APATA_API_BASE_URL")
        or os.getenv("API_BASE_URL")
        or DEFAULT_API_BASE_URL
    ).rstrip("/")


class InMemoryKeyring:
    def __init__(self):
        self._values: dict[tuple[str, str], str] = {}

    def get_password(self, service_name: str, username: str) -> str | None:
        return self._values.get((service_name, username))

    def set_password(self, service_name: str, username: str, value: str) -> None:
        self._values[(service_name, username)] = value

    def delete_password(self, service_name: str, username: str) -> None:
        self._values.pop((service_name, username), None)


@pytest.fixture
def in_memory_keyring(monkeypatch):
    storage = InMemoryKeyring()
    monkeypatch.setattr(keyring_storage, "keyring", storage)
    return storage


def _make_container():
    return make_async_container(
        StateProvider(),
        AppProvider(
            scope=Scope.APP,
            logger=logging.getLogger(__name__),
            symmetric_cipher="AESGCMSIV",
            asymmetric_cipher="X25519",
            signature_cipher="ED-25519",
            password_cipher="ARGON2",
            base_url=api_base_url(),
            verify_ssl=False,
            base_ws_url="ws://127.0.0.1:8000",
        ),
        MockDBProvider(),
    )


def _assert_success(result: tuple[bool, str]) -> None:
    success, message = result
    assert success, message


async def _register_with_login_interactors(
    container,
    username: str,
    password: str,
) -> dict[str, UUID | str]:
    _assert_success(
        await CheckLocalUserRegisterInteractor()(container, username, password)
    )
    _assert_success(await RegisterUserOnServerInteractor()(container))
    _assert_success(await ContainKeysInteractor()(container))
    _assert_success(await LoginUserInteractor()(container))
    _assert_success(await HashingPasswordInteractor()(container))
    _assert_success(await AddUserToDatabaseInteractor()(container))

    async with container() as request_container:
        app_state = await request_container.get(AppState)
        assert app_state.local_user_id is not None
        assert app_state.server_user_id is not None
        assert app_state.ed_public_key is not None
        return {
            "local_user_id": app_state.local_user_id,
            "server_user_id": app_state.server_user_id,
            "ed_public_key": app_state.ed_public_key,
        }


async def _send_data_to_registered_user(
    container,
    receiver: dict[str, UUID | str],
) -> dict[str, UUID | str]:
    async with container() as request_container:
        auth_service = await request_container.get(AuthHTTPService)
        contact_service = await request_container.get(ContactHTTPService)
        chat_service = await request_container.get(ChatHTTPService)
        message_service = await request_container.get(MessageHTTPService)
        encryption_service = await request_container.get(EncryptionService)

        sender_username = f"sync_sender_{uuid4().hex[:12]}"
        sender_registration = await auth_service.register(sender_username)
        sender_login = await auth_service.login(
            username=sender_username,
            ed_private_key=sender_registration.ed_private_key,
        )
        sender_id = UUID(sender_registration.id)
        receiver_server_user_id = receiver["server_user_id"]
        receiver_ed_public_key = receiver["ed_public_key"]
        assert isinstance(receiver_server_user_id, UUID)
        assert isinstance(receiver_ed_public_key, str)

        contact_service.token = sender_login.access_token
        request = await contact_service.create_contact_request(
            str(receiver_server_user_id)
        )

        message_service.token = sender_login.access_token
        ephemeral_keys = await encryption_service.generate_key_pairs()
        message_id = await message_service.send_encrypted_message_text(
            recipient_id=receiver_server_user_id,
            chat_id=None,
            message="message waiting for synchronization",
            recipient_ed_public_key=receiver_ed_public_key,
            sender_ed_private_key=sender_registration.ed_private_key,
            sender_ecdh_private_key=ephemeral_keys.ecdh_private_key,
            ephemeral_ecdh_public_key=ephemeral_keys.ecdh_public_key,
        )
        assert message_id is not None

        chat_service.token = sender_login.access_token
        chat = await chat_service.create_chat("synchronization chat")
        invitation = await chat_service.add_participant(
            chat_id=chat.id,
            user_id=receiver_server_user_id,
        )

        assert request.status == "pending(outgoing)"
        assert invitation.participant.user_id == receiver_server_user_id
        return {
            "sender_id": sender_id,
            "chat_id": chat.id,
            "message_id": message_id,
        }


async def _send_direct_message_without_contact_request(
    container,
    receiver: dict[str, UUID | str],
) -> dict[str, UUID]:
    async with container() as request_container:
        auth_service = await request_container.get(AuthHTTPService)
        message_service = await request_container.get(MessageHTTPService)
        encryption_service = await request_container.get(EncryptionService)

        sender_username = f"blank_sender_{uuid4().hex[:12]}"
        sender_registration = await auth_service.register(sender_username)
        sender_login = await auth_service.login(
            username=sender_username,
            ed_private_key=sender_registration.ed_private_key,
        )
        receiver_server_user_id = receiver["server_user_id"]
        receiver_ed_public_key = receiver["ed_public_key"]
        assert isinstance(receiver_server_user_id, UUID)
        assert isinstance(receiver_ed_public_key, str)

        ephemeral_keys = await encryption_service.generate_key_pairs()
        message_service.token = sender_login.access_token
        message_id = await message_service.send_encrypted_message_text(
            recipient_id=receiver_server_user_id,
            chat_id=None,
            message="first message creates blank contact",
            recipient_ed_public_key=receiver_ed_public_key,
            sender_ed_private_key=sender_registration.ed_private_key,
            sender_ecdh_private_key=ephemeral_keys.ecdh_private_key,
            ephemeral_ecdh_public_key=ephemeral_keys.ecdh_public_key,
        )
        assert message_id is not None
        return {
            "sender_id": UUID(sender_registration.id),
            "message_id": message_id,
        }


async def _login_and_synchronize_with_login_interactors(
    container,
    username: str,
    password: str,
) -> tuple[dict[str, int], dict[str, int], dict[str, int]]:
    _assert_success(
        await CheckLocalUserLoginInteractor()(container, username, password)
    )
    _assert_success(await ComparePasswordInteractor()(container))
    _assert_success(await GetPrivateKeysInteractor()(container))
    _assert_success(await LoginUserInteractor()(container))

    contacts_success, contacts_message, contacts_count = (
        await SynchronizeContactsInteractor()(container)
    )
    assert contacts_success, contacts_message

    chats_success, chats_message, chats_count = await SynchronizeChatsInteractor()(
        container
    )
    assert chats_success, chats_message

    messages_success, messages_message, messages_count = (
        await SyncMessageHistoryInteractor()(container)
    )
    assert messages_success, messages_message
    _assert_success(await RotateKeysInteractor()(container))

    return contacts_count, chats_count, messages_count


@timer()
def test_registered_user_login_synchronizes_contact_message_and_chat_invitation(
    in_memory_keyring,
) -> None:
    async def scenario() -> None:
        container = _make_container()
        username = f"sync_receiver_{uuid4().hex[:12]}"
        password = "integration-password"
        try:
            receiver = await _register_with_login_interactors(
                container,
                username,
                password,
            )

            async with container() as request_container:
                app_state = await request_container.get(AppState)
                app_state.clear_state()

            server_data = await _send_data_to_registered_user(container, receiver)
            contacts_count, chats_count, messages_count = (
                await _login_and_synchronize_with_login_interactors(
                    container,
                    username,
                    password,
                )
            )

            async with container() as request_container:
                app_state = await request_container.get(AppState)
                contact_service = await request_container.get(ContactService)
                chat_service = await request_container.get(ChatService)
                message_service = await request_container.get(MessageService)

                assert app_state.local_user_id == receiver["local_user_id"]
                assert app_state.master_key is not None
                message_service.master_key = app_state.master_key

                sender_contact = await contact_service.get_contact_by_server_user_id(
                    app_state.local_user_id,
                    server_data["sender_id"],
                )
                local_chat = await chat_service.get_chat_by_server_id(
                    app_state.local_user_id,
                    server_data["chat_id"],
                )
                participants = await chat_service.get_chat_participants(local_chat.id)
                events = await chat_service.get_chat_events(local_chat.id)
                messages = await message_service.get_messages(
                    app_state.local_user_id,
                    sender_contact.id,
                )

            assert contacts_count["added"] == 1
            assert chats_count["added"] == 1
            assert chats_count["participants_added"] == 1
            assert chats_count["events_added"] >= 1
            assert messages_count == {
                "text_count": 1,
                "file_count": 0,
                "failed_count": 0,
            }
            assert sender_contact.status == ContactStatusEnum.PENDING_INCOMING
            assert {participant.id for participant in participants} == {
                sender_contact.id
            }
            assert any(
                event.event_type == ChatEventTypeEnum.MEMBER_ADDED
                for event in events
            )
            assert [message.server_message_id for message in messages] == [
                server_data["message_id"]
            ]
            assert messages[0].content == "message waiting for synchronization"

            repeat_contacts_success, repeat_contacts_message, repeat_contacts = (
                await SynchronizeContactsInteractor()(container)
            )
            repeat_chats_success, repeat_chats_message, repeat_chats = (
                await SynchronizeChatsInteractor()(container)
            )
            repeat_messages_success, repeat_messages_message, repeat_messages = (
                await SyncMessageHistoryInteractor()(container)
            )

            assert repeat_contacts_success, repeat_contacts_message
            assert repeat_chats_success, repeat_chats_message
            assert repeat_messages_success, repeat_messages_message
            assert repeat_contacts["added"] == 0
            assert repeat_chats == {
                "added": 0,
                "updated": 0,
                "participants_added": 0,
                "participants_left": 0,
                "events_added": 0,
                "unmapped_participants": 0,
            }
            assert repeat_messages == {
                "text_count": 0,
                "file_count": 0,
                "failed_count": 0,
            }
        finally:
            await container.close()

    asyncio.run(scenario())


@timer()
def test_first_direct_message_creates_and_synchronizes_blank_contact(
    in_memory_keyring,
) -> None:
    async def scenario() -> None:
        container = _make_container()
        username = f"blank_receiver_{uuid4().hex[:12]}"
        password = "integration-password"
        try:
            receiver = await _register_with_login_interactors(
                container,
                username,
                password,
            )
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                app_state.clear_state()

            server_data = await _send_direct_message_without_contact_request(
                container,
                receiver,
            )
            contacts_count, _, messages_count = (
                await _login_and_synchronize_with_login_interactors(
                    container,
                    username,
                    password,
                )
            )

            async with container() as request_container:
                app_state = await request_container.get(AppState)
                contact_service = await request_container.get(ContactService)
                message_service = await request_container.get(MessageService)
                assert app_state.local_user_id is not None
                assert app_state.master_key is not None
                message_service.master_key = app_state.master_key
                sender_contact = await contact_service.get_contact_by_server_user_id(
                    app_state.local_user_id,
                    server_data["sender_id"],
                )
                assert sender_contact is not None
                messages = await message_service.get_messages(
                    app_state.local_user_id,
                    sender_contact.id,
                )

            assert contacts_count["added"] == 1
            assert messages_count == {
                "text_count": 1,
                "file_count": 0,
                "failed_count": 0,
            }
            assert sender_contact.status == ContactStatusEnum.BLANK
            assert [message.server_message_id for message in messages] == [
                server_data["message_id"]
            ]
            assert messages[0].content == "first message creates blank contact"
        finally:
            await container.close()

    asyncio.run(scenario())
