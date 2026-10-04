from datetime import datetime, timezone
from typing import cast
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID, uuid4

import pytest
from dishka import AsyncContainer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519

from src.adapters.api.dto import (
    ChatParticipantDTO,
    ContactPageDTO,
    ContactPublicDTO,
    SentChatMessageDeliveryDTO,
)
from src.adapters.api.dao import ContactHTTPDAO
from src.adapters.api.service import (
    ChatHTTPService,
    ContactHTTPService,
    MessageHTTPService,
)
from src.adapters.database.dto import ChatDTO, ContactDTO, MessageDTO, RequestContactDTO
from src.adapters.database.service import (
    ChatService,
    ContactService,
    MessageService,
)
from src.adapters.database.structures import (
    ContactStatusEnum,
    MessageContentTypeEnum,
)
from src.exceptions import APIError
from src.presentation.interactors.login import SynchronizeContactsInteractor
from src.presentation.interactors.messenger import (
    AcceptContactRequestInteractor,
    BlacklistContactInteractor,
    SearchContactsGlobalInteractor,
    SendChatTextMessageInteractor,
    SendContactRequestInteractor,
    SendContactTextMessageInteractor,
)
from src.providers.cache import ChatCache, ContactCache
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
    contact_http_service.accept_contact_request_dto = AsyncMock(return_value=accepted)
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contact_by_server_user_id = AsyncMock(return_value=existing)
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
    contact_service.get_contact_by_server_user_id = AsyncMock(return_value=existing)
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
    contact_service.get_contact_by_server_user_id = AsyncMock(return_value=contact)
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
    contact_service.get_contact_by_server_user_id = AsyncMock(return_value=contact)
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


@pytest.mark.asyncio
async def test_contact_mutation_preserves_the_pinned_ed_public_key() -> None:
    local_user_id = uuid4()
    cached_contact = make_cached_contact(valid_public_keys=True)
    replacement_keys = make_cached_contact(valid_public_keys=True)
    cached_contact.status = ContactStatusEnum.BLANK
    existing = make_local_contact(
        cached_contact,
        local_user_id,
        ContactStatusEnum.BLANK,
    )
    saved_contact = existing.model_copy(
        update={"status": ContactStatusEnum.PENDING_OUTGOING}
    )
    response = ContactPublicDTO(
        contact_id=str(uuid4()),
        user_id=str(cached_contact.server_user_id),
        username=cached_contact.username,
        ed_public_key=replacement_keys.ed_public_key,
        ecdh_public_key=replacement_keys.ecdh_public_key,
        status=ContactStatusEnum.PENDING_OUTGOING.value,
        online=False,
        last_seen=None,
    )
    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id
    app_state.contacts_cache = [cached_contact]
    contact_http_service = MagicMock(spec=ContactHTTPService)
    contact_http_service.create_contact_request = AsyncMock(return_value=response)
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contact_by_server_user_id = AsyncMock(return_value=existing)
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

    result = await SendContactRequestInteractor()(container, cached_contact)

    assert result == (True, "SUCCESS", saved_contact)
    update = contact_service.update_contact.await_args.args[0]
    assert update.ed_public_key is None
    assert cached_contact.ed_public_key == existing.ed_public_key
    assert cached_contact.ecdh_public_key == replacement_keys.ecdh_public_key


@pytest.mark.asyncio
async def test_contact_synchronization_never_overwrites_a_pinned_ed_key() -> None:
    local_user_id = uuid4()
    server_user_id = uuid4()
    cached_contact = make_cached_contact(valid_public_keys=True)
    replacement_keys = make_cached_contact(valid_public_keys=True)
    existing = make_local_contact(
        cached_contact,
        local_user_id,
        ContactStatusEnum.ACCEPTED,
    )
    server_contact = RequestContactDTO(
        local_user_id=local_user_id,
        server_user_id=cached_contact.server_user_id,
        status=ContactStatusEnum.ACCEPTED,
        username=cached_contact.username,
        ed_public_key=replacement_keys.ed_public_key,
        ecdh_public_key=replacement_keys.ecdh_public_key,
        last_seen=None,
        online=True,
    )
    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id
    app_state.server_user_id = server_user_id
    contact_http_service = MagicMock(spec=ContactHTTPService)
    contact_http_service.get_contacts = AsyncMock(return_value=[server_contact])
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contacts = AsyncMock(return_value=[existing])
    contact_service.update_contact = AsyncMock(return_value=existing)
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

    success, message, counts = await SynchronizeContactsInteractor()(container)

    assert success, message
    assert counts == {"edited": 1, "added": 0}
    update = contact_service.update_contact.await_args.args[0]
    assert update.ed_public_key is None
    assert existing.ed_public_key == cached_contact.ed_public_key


@pytest.mark.asyncio
async def test_send_chat_text_message_interactor_persists_one_logical_message() -> None:
    timestamp = datetime.now(timezone.utc)
    local_user_id = uuid4()
    sender_server_id = uuid4()
    first_recipient_id = uuid4()
    second_recipient_id = uuid4()
    local_chat_id = uuid4()
    server_chat_id = uuid4()
    logical_message_id = uuid4()
    local_chat = ChatDTO(
        id=local_chat_id,
        local_user_id=local_user_id,
        server_chat_id=server_chat_id,
        server_owner_id=sender_server_id,
        name="Group chat",
        created_at=timestamp,
    )
    chat_cache = ChatCache(
        id=local_chat_id,
        server_chat_id=server_chat_id,
        server_owner_id=sender_server_id,
        name="Group chat",
        created_at=timestamp,
    )
    contacts = [
        ContactDTO.model_construct(
            id=uuid4(),
            local_user_id=local_user_id,
            server_user_id=recipient_id,
            status=ContactStatusEnum.BLANK,
            username=f"user_{index}",
            ed_public_key=f"recipient-{index}-ed-key",
            ecdh_public_key=f"recipient-{index}-ecdh-key",
            last_seen=None,
            online=None,
        )
        for index, recipient_id in enumerate(
            [first_recipient_id, second_recipient_id],
            start=1,
        )
    ]
    deliveries = [
        SentChatMessageDeliveryDTO(
            id=uuid4(),
            logical_message_id=logical_message_id,
            recipient_id=recipient_id,
            timestamp=timestamp,
        )
        for recipient_id in [first_recipient_id, second_recipient_id]
    ]
    saved_message = MessageDTO(
        id=uuid4(),
        local_user_id=local_user_id,
        server_message_id=deliveries[0].id,
        logical_message_id=logical_message_id,
        contact_id=None,
        chat_id=local_chat_id,
        content_type=MessageContentTypeEnum.TEXT,
        content="encrypted-at-rest",
        timestamp=timestamp,
        is_outgoing=True,
        is_delivered=True,
    )
    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id
    app_state.server_user_id = sender_server_id
    app_state.master_key = b"master-key"
    app_state.ed_private_key = "sender-ed-private-key"
    app_state.ecdh_private_key = "sender-ecdh-private-key"
    app_state.ecdh_public_key = "sender-ecdh-public-key"
    app_state.chats_cache = [chat_cache]
    chat_http_service = MagicMock(spec=ChatHTTPService)
    chat_http_service.get_participants = AsyncMock(
        return_value=[
            ChatParticipantDTO(
                chat_id=server_chat_id,
                user_id=user_id,
                invited_by_user_id=None,
                joined_at=timestamp,
                left_at=None,
            )
            for user_id in [
                sender_server_id,
                first_recipient_id,
                second_recipient_id,
            ]
        ]
    )
    contact_http_service = MagicMock(spec=ContactHTTPService)
    chat_service = MagicMock(spec=ChatService)
    chat_service.get_chat_by_id = AsyncMock(return_value=local_chat)
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contacts = AsyncMock(return_value=contacts)
    message_http_service = MagicMock(spec=MessageHTTPService)
    message_http_service.send_encrypted_chat_message_text = AsyncMock(
        return_value=deliveries
    )
    message_service = MagicMock(spec=MessageService)
    message_service.add_message_text = AsyncMock(return_value=saved_message)
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: app_state,
                ChatHTTPService: chat_http_service,
                ContactHTTPService: contact_http_service,
                ChatService: chat_service,
                ContactService: contact_service,
                MessageHTTPService: message_http_service,
                MessageService: message_service,
            }
        ),
    )

    result = await SendChatTextMessageInteractor()(container, chat_cache, " hello ")

    assert result == (True, "SUCCESS", saved_message)
    message_http_service.send_encrypted_chat_message_text.assert_awaited_once_with(
        chat_id=server_chat_id,
        message="hello",
        recipient_ed_public_keys={
            first_recipient_id: "recipient-1-ed-key",
            second_recipient_id: "recipient-2-ed-key",
        },
        sender_ed_private_key="sender-ed-private-key",
        sender_ecdh_private_key="sender-ecdh-private-key",
        sender_ecdh_public_key="sender-ecdh-public-key",
    )
    message_service.add_message_text.assert_awaited_once()
    stored = message_service.add_message_text.await_args.args[0]
    assert stored.logical_message_id == logical_message_id
    assert stored.chat_id == local_chat_id
    assert len(chat_cache.messages) == 1
    assert chat_cache.messages[0].logical_message_id == logical_message_id


@pytest.mark.asyncio
async def test_send_chat_text_message_syncs_missing_contacts_once() -> None:
    timestamp = datetime.now(timezone.utc)
    local_user_id = uuid4()
    sender_server_id = uuid4()
    recipient_id = uuid4()
    local_chat_id = uuid4()
    server_chat_id = uuid4()
    local_chat = ChatDTO(
        id=local_chat_id,
        local_user_id=local_user_id,
        server_chat_id=server_chat_id,
        server_owner_id=sender_server_id,
        name="Group chat",
        created_at=timestamp,
    )
    chat_cache = ChatCache(
        id=local_chat_id,
        server_chat_id=server_chat_id,
        server_owner_id=sender_server_id,
        name="Group chat",
        created_at=timestamp,
    )
    contact_keys = make_cached_contact(valid_public_keys=True)
    server_contact = ContactPublicDTO(
        contact_id=str(uuid4()),
        user_id=str(recipient_id),
        username="new_member",
        ed_public_key=contact_keys.ed_public_key,
        ecdh_public_key=contact_keys.ecdh_public_key,
        status=ContactStatusEnum.BLANK.value,
        online=None,
        last_seen=None,
    )
    saved_contact = ContactDTO.model_construct(
        id=uuid4(),
        local_user_id=local_user_id,
        server_user_id=recipient_id,
        status=ContactStatusEnum.BLANK,
        username="new_member",
        ed_public_key=contact_keys.ed_public_key,
        ecdh_public_key=contact_keys.ecdh_public_key,
        last_seen=None,
        online=None,
    )
    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id
    app_state.server_user_id = sender_server_id
    app_state.master_key = b"master-key"
    app_state.ed_private_key = "sender-ed-private-key"
    app_state.ecdh_private_key = "sender-ecdh-private-key"
    app_state.ecdh_public_key = "sender-ecdh-public-key"
    chat_http_service = MagicMock(spec=ChatHTTPService)
    chat_http_service.get_participants = AsyncMock(
        return_value=[
            ChatParticipantDTO(
                chat_id=server_chat_id,
                user_id=user_id,
                invited_by_user_id=None,
                joined_at=timestamp,
                left_at=None,
            )
            for user_id in [sender_server_id, recipient_id]
        ]
    )
    contact_http_service = MagicMock(spec=ContactHTTPService)
    contact_http_service.list_all_contacts = AsyncMock(return_value=[server_contact])
    chat_service = MagicMock(spec=ChatService)
    chat_service.get_chat_by_id = AsyncMock(return_value=local_chat)
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contacts = AsyncMock(
        side_effect=[[], [saved_contact], [saved_contact]]
    )
    contact_service.add_contact = AsyncMock(return_value=saved_contact)
    message_http_service = MagicMock(spec=MessageHTTPService)
    message_http_service.send_encrypted_chat_message_text = AsyncMock(
        side_effect=APIError("membership changed", status_code=409)
    )
    message_service = MagicMock(spec=MessageService)
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: app_state,
                ChatHTTPService: chat_http_service,
                ContactHTTPService: contact_http_service,
                ChatService: chat_service,
                ContactService: contact_service,
                MessageHTTPService: message_http_service,
                MessageService: message_service,
            }
        ),
    )

    result = await SendChatTextMessageInteractor()(container, chat_cache, "hello")

    assert result == (False, "MEMBERSHIP CHANGED", None)
    contact_http_service.list_all_contacts.assert_awaited_once()
    contact_service.add_contact.assert_awaited_once()
    message_service.add_message_text.assert_not_awaited()
