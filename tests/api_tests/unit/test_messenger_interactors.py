from datetime import datetime, timezone
from typing import cast
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID, uuid4

import pytest
from dishka import AsyncContainer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519

from src.adapters.api.dto import ContactPageDTO, ContactPublicDTO
from src.adapters.api.dao import ContactHTTPDAO
from src.adapters.api.service import ContactHTTPService, MessageHTTPService
from src.adapters.database.dto import ContactDTO, MessageDTO
from src.adapters.database.service import ContactService, MessageService
from src.adapters.database.structures import (
    ContactStatusEnum,
    MessageContentTypeEnum,
)
from src.presentation.interactors.messenger import (
    AcceptContactRequestInteractor,
    BlacklistContactInteractor,
    SearchContactsGlobalInteractor,
    SendContactRequestInteractor,
    SendContactTextMessageInteractor,
)
from src.providers.cache import ContactCache
from src.providers.state import AppState


class FakeRequestContainer:
    def __init__(self, services: dict[type, object]):
        self._services = services

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    async def get(self, dependency_type: type):
        return self._services[dependency_type]


class FakeContainer:
    def __init__(self, services: dict[type, object]):
        self._request_container = FakeRequestContainer(services)

    def __call__(self):
        return self._request_container


class FakeContactHTTPService:
    def __init__(self, page: ContactPageDTO):
        self.token: str | None = None
        self.page = page
        self.queries: list[str] = []

    async def search_all_contacts(self, username: str) -> list[ContactPublicDTO]:
        self.queries.append(username)
        return self.page.items


def make_contact(user_id: str, username: str) -> ContactPublicDTO:
    return ContactPublicDTO(
        contact_id=None,
        user_id=user_id,
        username=username,
        ed_public_key="ed-public-key",
        ecdh_public_key="ecdh-public-key",
        status="blank",
        online=False,
        last_seen=None,
    )


def make_cached_contact(
    server_user_id: UUID | None = None,
    local_contact_id: UUID | None = None,
    *,
    valid_public_keys: bool = False,
) -> ContactCache:
    server_user_id = server_user_id or uuid4()
    if valid_public_keys:
        ed_public_key = (
            ed25519.Ed25519PrivateKey.generate()
            .public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
        ecdh_public_key = (
            x25519.X25519PrivateKey.generate()
            .public_key()
            .public_bytes(
                serialization.Encoding.PEM,
                serialization.PublicFormat.SubjectPublicKeyInfo,
            )
            .decode()
        )
    else:
        ed_public_key = "contact-ed-public-key"
        ecdh_public_key = "contact-ecdh-public-key"
    return ContactCache(
        id=local_contact_id or server_user_id,
        server_user_id=server_user_id,
        username="ghost_user",
        status=ContactStatusEnum.ACCEPTED,
        last_seen=None,
        online=True,
        ed_public_key=ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )


def make_contact_response(
    contact: ContactCache,
    status: ContactStatusEnum,
    *,
    contact_id: UUID | None = None,
    online: bool | None = None,
    last_seen: str | None = None,
) -> ContactPublicDTO:
    assert contact.ed_public_key is not None
    assert contact.ecdh_public_key is not None
    return ContactPublicDTO(
        contact_id=str(contact_id) if contact_id is not None else None,
        user_id=str(contact.server_user_id),
        username=contact.username,
        ed_public_key=contact.ed_public_key,
        ecdh_public_key=contact.ecdh_public_key,
        status=status.value,
        online=online,
        last_seen=last_seen,
    )


def make_local_contact(
    contact: ContactCache,
    local_user_id: UUID,
    status: ContactStatusEnum,
) -> ContactDTO:
    return ContactDTO.model_construct(
        id=contact.id,
        local_user_id=local_user_id,
        server_user_id=contact.server_user_id,
        status=status,
        username=contact.username,
        ed_public_key=contact.ed_public_key,
        ecdh_public_key=contact.ecdh_public_key,
        last_seen=None,
        online=False,
    )


@pytest.mark.asyncio
async def test_search_contacts_global_interactor() -> None:
    current_user_id = uuid4()
    found_user_id = uuid4()
    contact_http_service = FakeContactHTTPService(
        ContactPageDTO(
            items=[
                make_contact(str(current_user_id), "ghost_self"),
                make_contact(str(found_user_id), "ghost_user"),
            ]
        )
    )
    app_state = AppState()
    app_state.token = "access-token"
    app_state.server_user_id = current_user_id
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                ContactHTTPService: contact_http_service,
                AppState: app_state,
            }
        ),
    )

    result = await SearchContactsGlobalInteractor()(container, "  ghost  ")

    assert contact_http_service.token == "access-token"
    assert contact_http_service.queries == ["ghost"]
    assert [contact.user_id for contact in result] == [str(found_user_id)]

    assert await SearchContactsGlobalInteractor()(container, "g") == []
    assert contact_http_service.queries == ["ghost"]


@pytest.mark.asyncio
async def test_search_contacts_global_interactor_requires_token() -> None:
    contact_http_service = FakeContactHTTPService(ContactPageDTO(items=[]))
    app_state = AppState()
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                ContactHTTPService: contact_http_service,
                AppState: app_state,
            }
        ),
    )

    assert await SearchContactsGlobalInteractor()(container, "ghost") == []
    assert contact_http_service.queries == []


@pytest.mark.asyncio
async def test_contact_http_service_follows_search_and_list_cursors() -> None:
    first_contact = make_contact(str(uuid4()), "ghost_one")
    second_contact = make_contact(str(uuid4()), "ghost_two")
    contact_dao = MagicMock(spec=ContactHTTPDAO)
    contact_dao.search_contacts = AsyncMock(
        side_effect=[
            ContactPageDTO(items=[first_contact], next_after_id="search-cursor"),
            ContactPageDTO(items=[second_contact]),
        ]
    )
    contact_dao.list_contacts = AsyncMock(
        side_effect=[
            ContactPageDTO(items=[first_contact], next_after_id="list-cursor"),
            ContactPageDTO(items=[second_contact]),
        ]
    )
    service = ContactHTTPService(
        contact_dao=contact_dao,
        auth_dao=MagicMock(),
        encryption_service=MagicMock(),
    )
    service.token = "access-token"

    search_results = await service.search_all_contacts("ghost")
    list_results = await service.list_all_contacts()

    assert search_results == [first_contact, second_contact]
    assert list_results == [first_contact, second_contact]
    assert contact_dao.search_contacts.await_args_list == [
        call(username="ghost", token="access-token", after_id=None),
        call(username="ghost", token="access-token", after_id="search-cursor"),
    ]
    assert contact_dao.list_contacts.await_args_list == [
        call(token="access-token", after_id=None),
        call(token="access-token", after_id="list-cursor"),
    ]


@pytest.mark.asyncio
async def test_send_contact_request_interactor_updates_database_and_cache() -> None:
    local_user_id = uuid4()
    contact = make_cached_contact(valid_public_keys=True)
    contact.status = ContactStatusEnum.BLANK
    response = make_contact_response(contact, ContactStatusEnum.PENDING_OUTGOING)
    saved_contact = make_local_contact(
        contact,
        local_user_id,
        ContactStatusEnum.PENDING_OUTGOING,
    )
    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id

    contact_http_service = MagicMock(spec=ContactHTTPService)
    contact_http_service.create_contact_request = AsyncMock(return_value=response)
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contact_by_server_user_id = AsyncMock(return_value=None)
    contact_service.add_contact = AsyncMock(return_value=saved_contact)
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: app_state,
                ContactHTTPService: contact_http_service,
                ContactService: contact_service,
            }
        ),
    )

    result = await SendContactRequestInteractor()(container, contact)

    assert result == (True, "SUCCESS", saved_contact)
    assert contact_http_service.token == "access-token"
    contact_http_service.create_contact_request.assert_awaited_once_with(
        str(contact.server_user_id)
    )
    contact_service.add_contact.assert_awaited_once()
    assert contact.status is ContactStatusEnum.PENDING_OUTGOING
    assert app_state.contacts_cache == [contact]


@pytest.mark.asyncio
async def test_accept_contact_request_interactor_updates_database_and_cache() -> None:
    local_user_id = uuid4()
    server_contact_id = uuid4()
    contact = make_cached_contact(valid_public_keys=True)
    contact.status = ContactStatusEnum.PENDING_INCOMING
    incoming = make_contact_response(
        contact,
        ContactStatusEnum.PENDING_INCOMING,
        contact_id=server_contact_id,
    )
    accepted = make_contact_response(
        contact,
        ContactStatusEnum.ACCEPTED,
        contact_id=server_contact_id,
        online=True,
        last_seen=datetime.now(timezone.utc).isoformat(),
    )
    existing = make_local_contact(
        contact,
        local_user_id,
        ContactStatusEnum.PENDING_INCOMING,
    )
    saved_contact = existing.model_copy(
        update={"status": ContactStatusEnum.ACCEPTED, "online": True}
    )
    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id
    app_state.contacts_cache = [contact]

    contact_http_service = MagicMock(spec=ContactHTTPService)
    contact_http_service.list_all_contacts = AsyncMock(return_value=[incoming])
    contact_http_service.accept_contact_request_dto = AsyncMock(
        return_value=accepted
    )
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contact_by_server_user_id = AsyncMock(
        return_value=existing
    )
    contact_service.update_contact = AsyncMock(return_value=saved_contact)
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: app_state,
                ContactHTTPService: contact_http_service,
                ContactService: contact_service,
            }
        ),
    )

    result = await AcceptContactRequestInteractor()(container, contact)

    assert result == (True, "SUCCESS", saved_contact)
    contact_http_service.accept_contact_request_dto.assert_awaited_once_with(
        str(server_contact_id)
    )
    contact_service.update_contact.assert_awaited_once()
    assert contact.status is ContactStatusEnum.ACCEPTED
    assert contact.online is True
    assert contact.last_seen is not None


@pytest.mark.asyncio
async def test_blacklist_contact_interactor_updates_database_and_cache() -> None:
    local_user_id = uuid4()
    contact = make_cached_contact(valid_public_keys=True)
    response = make_contact_response(contact, ContactStatusEnum.BLACKLIST)
    existing = make_local_contact(
        contact,
        local_user_id,
        ContactStatusEnum.ACCEPTED,
    )
    saved_contact = existing.model_copy(
        update={"status": ContactStatusEnum.BLACKLIST, "online": False}
    )
    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id
    app_state.contacts_cache = [contact]

    contact_http_service = MagicMock(spec=ContactHTTPService)
    contact_http_service.blacklist_contact = AsyncMock(return_value=response)
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contact_by_server_user_id = AsyncMock(
        return_value=existing
    )
    contact_service.update_contact = AsyncMock(return_value=saved_contact)
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: app_state,
                ContactHTTPService: contact_http_service,
                ContactService: contact_service,
            }
        ),
    )

    result = await BlacklistContactInteractor()(container, contact)

    assert result == (True, "SUCCESS", saved_contact)
    contact_http_service.blacklist_contact.assert_awaited_once_with(
        str(contact.server_user_id)
    )
    contact_service.update_contact.assert_awaited_once()
    assert contact.status is ContactStatusEnum.BLACKLIST
    assert contact.online is None
    assert contact.last_seen is None


@pytest.mark.asyncio
async def test_send_contact_text_message_interactor() -> None:
    local_user_id = uuid4()
    local_contact_id = uuid4()
    server_contact_id = uuid4()
    server_message_id = uuid4()
    local_message_id = uuid4()
    timestamp = datetime.now(timezone.utc)
    contact = ContactDTO.model_construct(
        id=local_contact_id,
        local_user_id=local_user_id,
        server_user_id=server_contact_id,
        status=ContactStatusEnum.ACCEPTED,
        username="ghost_user",
        ed_public_key="contact-ed-public-key",
        ecdh_public_key="contact-ecdh-public-key",
        last_seen=None,
        online=True,
    )
    saved_message = MessageDTO(
        id=local_message_id,
        local_user_id=local_user_id,
        server_message_id=server_message_id,
        contact_id=local_contact_id,
        chat_id=None,
        content_type=MessageContentTypeEnum.TEXT,
        content="encrypted-at-rest",
        timestamp=timestamp,
        is_outgoing=True,
        is_delivered=True,
    )

    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id
    app_state.master_key = b"master-key"
    app_state.ed_private_key = "sender-ed-private-key"
    app_state.ecdh_private_key = "sender-ecdh-private-key"
    app_state.ecdh_public_key = "sender-ecdh-public-key"
    cached_contact = make_cached_contact(
        server_user_id=server_contact_id,
        local_contact_id=local_contact_id,
    )
    app_state.contacts_cache = [cached_contact]

    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contact_by_server_user_id = AsyncMock(
        return_value=contact
    )
    message_http_service = MagicMock(spec=MessageHTTPService)
    message_http_service.send_encrypted_message_text = AsyncMock(
        return_value=server_message_id
    )
    message_service = MagicMock(spec=MessageService)
    message_service.add_message_text = AsyncMock(return_value=saved_message)
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: app_state,
                ContactService: contact_service,
                MessageHTTPService: message_http_service,
                MessageService: message_service,
            }
        ),
    )

    result = await SendContactTextMessageInteractor()(
        container,
        cached_contact,
        "  hello there  ",
    )

    assert result == (True, "SUCCESS", saved_message)
    assert message_http_service.token == "access-token"
    message_http_service.send_encrypted_message_text.assert_awaited_once_with(
        recipient_id=server_contact_id,
        chat_id=None,
        message="hello there",
        recipient_ed_public_key="contact-ed-public-key",
        sender_ed_private_key="sender-ed-private-key",
        sender_ecdh_private_key="sender-ecdh-private-key",
        ephemeral_ecdh_public_key="sender-ecdh-public-key",
    )
    message_service.add_message_text.assert_awaited_once()
    stored_dto = message_service.add_message_text.await_args.args[0]
    assert stored_dto.local_user_id == local_user_id
    assert stored_dto.server_message_id == server_message_id
    assert stored_dto.contact_id == local_contact_id
    assert stored_dto.chat_id is None
    assert stored_dto.content == "hello there"
    assert stored_dto.content_type == MessageContentTypeEnum.TEXT
    assert stored_dto.is_outgoing is True
    assert stored_dto.is_delivered is True
    assert message_service.master_key == b"master-key"
    assert len(cached_contact.messages) == 1
    assert cached_contact.messages[0].content == "hello there"
    assert cached_contact.messages[0].server_message_id == server_message_id


@pytest.mark.asyncio
async def test_send_contact_text_message_interactor_maps_global_result() -> None:
    local_user_id = uuid4()
    local_contact_id = uuid4()
    server_contact_id = uuid4()
    server_message_id = uuid4()
    global_contact = make_cached_contact(
        server_user_id=server_contact_id,
        valid_public_keys=True,
    )
    global_contact.status = ContactStatusEnum.BLANK
    local_contact = ContactDTO.model_construct(
        id=local_contact_id,
        local_user_id=local_user_id,
        server_user_id=server_contact_id,
        status=ContactStatusEnum.BLANK,
        username=global_contact.username,
        ed_public_key=global_contact.ed_public_key,
        ecdh_public_key=global_contact.ecdh_public_key,
        last_seen=None,
        online=True,
    )
    saved_message = MessageDTO(
        id=uuid4(),
        local_user_id=local_user_id,
        server_message_id=server_message_id,
        contact_id=local_contact_id,
        chat_id=None,
        content_type=MessageContentTypeEnum.TEXT,
        content="encrypted-at-rest",
        timestamp=datetime.now(timezone.utc),
        is_outgoing=True,
        is_delivered=True,
    )
    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id
    app_state.master_key = b"master-key"
    app_state.ed_private_key = "sender-ed-private-key"
    app_state.ecdh_private_key = "sender-ecdh-private-key"
    app_state.ecdh_public_key = "sender-ecdh-public-key"
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contact_by_server_user_id = AsyncMock(return_value=None)
    contact_service.add_contact = AsyncMock(return_value=local_contact)
    message_http_service = MagicMock(spec=MessageHTTPService)
    message_http_service.send_encrypted_message_text = AsyncMock(
        return_value=server_message_id
    )
    message_service = MagicMock(spec=MessageService)
    message_service.add_message_text = AsyncMock(return_value=saved_message)
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: app_state,
                ContactService: contact_service,
                MessageHTTPService: message_http_service,
                MessageService: message_service,
            }
        ),
    )

    result = await SendContactTextMessageInteractor()(
        container,
        global_contact,
        "hello from search",
    )

    assert result == (True, "SUCCESS", saved_message)
    contact_service.add_contact.assert_awaited_once()
    add_contact_dto = contact_service.add_contact.await_args.args[0]
    assert add_contact_dto.local_user_id == local_user_id
    assert add_contact_dto.server_user_id == server_contact_id
    assert add_contact_dto.status == ContactStatusEnum.BLANK
    assert add_contact_dto.ed_public_key == global_contact.ed_public_key
    assert add_contact_dto.ecdh_public_key == global_contact.ecdh_public_key
    assert global_contact.id == local_contact_id
    assert global_contact.status == ContactStatusEnum.BLANK
    assert app_state.contacts_cache == [global_contact]
    assert global_contact.messages[0].content == "hello from search"


@pytest.mark.asyncio
async def test_send_contact_text_message_interactor_requires_state() -> None:
    app_state = AppState()
    container = cast(
        AsyncContainer,
        FakeContainer({AppState: app_state}),
    )

    result = await SendContactTextMessageInteractor()(
        container,
        make_cached_contact(),
        "hello",
    )

    assert result == (False, "MESSAGE SENDING PREREQUISITES MISSING", None)


@pytest.mark.asyncio
async def test_send_contact_text_message_interactor_rejects_empty_text() -> None:
    container_mock = MagicMock()
    container = cast(AsyncContainer, container_mock)

    result = await SendContactTextMessageInteractor()(
        container,
        make_cached_contact(),
        "   ",
    )

    assert result == (False, "MESSAGE CANNOT BE EMPTY", None)
    container_mock.assert_not_called()


@pytest.mark.asyncio
async def test_send_contact_text_message_interactor_handles_server_failure() -> None:
    local_user_id = uuid4()
    local_contact_id = uuid4()
    server_contact_id = uuid4()
    contact = ContactDTO.model_construct(
        id=local_contact_id,
        local_user_id=local_user_id,
        server_user_id=server_contact_id,
        status=ContactStatusEnum.ACCEPTED,
        username="ghost_user",
        ed_public_key="contact-ed-public-key",
        ecdh_public_key="contact-ecdh-public-key",
        last_seen=None,
        online=True,
    )
    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id
    app_state.master_key = b"master-key"
    app_state.ed_private_key = "sender-ed-private-key"
    app_state.ecdh_private_key = "sender-ecdh-private-key"
    app_state.ecdh_public_key = "sender-ecdh-public-key"
    cached_contact = make_cached_contact(
        server_user_id=server_contact_id,
        local_contact_id=local_contact_id,
    )
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contact_by_server_user_id = AsyncMock(
        return_value=contact
    )
    message_http_service = MagicMock(spec=MessageHTTPService)
    message_http_service.send_encrypted_message_text = AsyncMock(return_value=None)
    message_service = MagicMock(spec=MessageService)
    message_service.add_message_text = AsyncMock()
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: app_state,
                ContactService: contact_service,
                MessageHTTPService: message_http_service,
                MessageService: message_service,
            }
        ),
    )

    result = await SendContactTextMessageInteractor()(
        container,
        cached_contact,
        "hello",
    )

    assert result == (False, "FAILED TO SEND MESSAGE", None)
    message_service.add_message_text.assert_not_awaited()
