import logging
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from dishka import Scope, make_async_container

from src.adapters.database.dto import (
    AddChatDTO,
    AddChatEventDTO,
    AddChatParticipantDTO,
    AddContactDTO,
    AddLocalUserDTO,
    RequestChatEventDTO,
)
from src.adapters.database.service import ChatService, ContactService, LocalUserService
from src.adapters.database.structures import ChatEventTypeEnum, ContactStatusEnum
from src.adapters.encryption.dao import (
    AbstractECDHCipher,
    AbstractEDSignature,
    AbstractPasswordHasher,
)
from src.exceptions import ChatAlreadyExistsError
from src.providers import AppProvider
from tests.providers import MockDBProvider
from tests.timing_wrapper import timer


@pytest.fixture
async def container():
    container = make_async_container(
        AppProvider(
            scope=Scope.APP,
            logger=logging.getLogger(__name__),
            symmetric_cipher="AESGCMSIV",
            asymmetric_cipher="X25519",
            signature_cipher="ED-25519",
            password_cipher="BCRYPT",
            base_url="https://test.com",
            verify_ssl=False,
            base_ws_url="wss://test.com",
        ),
        MockDBProvider(),
    )
    yield container
    await container.close()


@pytest.fixture
async def local_user_service(container):
    async with container() as request_container:
        service = await request_container.get(LocalUserService)
        yield service


@pytest.fixture
async def contact_service(container):
    async with container() as request_container:
        service = await request_container.get(ContactService)
        yield service


@pytest.fixture
async def chat_service(container):
    async with container() as request_container:
        service = await request_container.get(ChatService)
        yield service


@pytest.fixture
async def ed_signer(container):
    async with container() as request_container:
        signer = await request_container.get(AbstractEDSignature)
        yield signer


@pytest.fixture
async def password_hasher(container):
    async with container() as request_container:
        hasher = await request_container.get(AbstractPasswordHasher)
        yield hasher


@pytest.fixture
async def ecdh_cipher(container):
    async with container() as request_container:
        cipher = await request_container.get(AbstractECDHCipher)
        yield cipher


@pytest.fixture
async def test_user(local_user_service, ed_signer, password_hasher):
    ed_public_key = (await ed_signer.generate_key_pair())[1]
    hashed_password = await password_hasher.hashing("testpass")
    return await local_user_service.add_user(
        AddLocalUserDTO(
            server_user_id=uuid4(),
            username="testuser",
            ed_public_key=ed_public_key,
            hashed_password=hashed_password,
            timezone=0,
        )
    )


async def create_contact(
    contact_service,
    local_user_id,
    username,
    ed_signer,
    ecdh_cipher,
):
    ed_public_key = (await ed_signer.generate_key_pair())[1]
    ecdh_public_key = (await ecdh_cipher.generate_key_pair())[1]
    return await contact_service.add_contact(
        AddContactDTO(
            local_user_id=local_user_id,
            server_user_id=uuid4(),
            status=ContactStatusEnum.ACCEPTED,
            username=username,
            ed_public_key=ed_public_key,
            ecdh_public_key=ecdh_public_key,
        )
    )


async def create_chat(chat_service, local_user_id, name):
    return await chat_service.add_chat(
        AddChatDTO(
            local_user_id=local_user_id,
            server_chat_id=uuid4(),
            name=name,
        )
    )


@pytest.mark.asyncio
@timer()
async def test_add_chat_and_duplicate_server_chat_id_raises(
    chat_service,
    test_user,
):
    server_chat_id = uuid4()
    server_owner_id = uuid4()
    created_at = datetime.now(timezone.utc)
    created = await chat_service.add_chat(
        AddChatDTO(
            local_user_id=test_user.id,
            server_chat_id=server_chat_id,
            server_owner_id=server_owner_id,
            name="project-chat",
            created_at=created_at,
        )
    )

    by_id = await chat_service.get_chat_by_id(created.id)
    by_server_id = await chat_service.get_chat_by_server_id(
        test_user.id,
        server_chat_id,
    )
    by_name = await chat_service.get_chat_by_name(test_user.id, "project")

    assert by_id.id == created.id
    assert by_server_id.id == created.id
    assert by_name.id == created.id
    assert created.server_owner_id == server_owner_id
    assert created.created_at == created_at

    with pytest.raises(ChatAlreadyExistsError):
        await chat_service.add_chat(
            AddChatDTO(
                local_user_id=test_user.id,
                server_chat_id=server_chat_id,
                name="same-server-chat",
            )
        )


@pytest.mark.asyncio
@timer()
async def test_add_participant_creates_join_event_only_for_new_joiner(
    chat_service,
    contact_service,
    test_user,
    ed_signer,
    ecdh_cipher,
):
    chat = await create_chat(chat_service, test_user.id, "team-chat")
    existing_contact = await create_contact(
        contact_service,
        test_user.id,
        "existing-member",
        ed_signer,
        ecdh_cipher,
    )
    joiner = await create_contact(
        contact_service,
        test_user.id,
        "new-member",
        ed_signer,
        ecdh_cipher,
    )

    await chat_service.add_participant(
        AddChatParticipantDTO(chat_id=chat.id, contact_id=existing_contact.id),
        create_join_event=False,
    )
    await chat_service.add_participant(
        AddChatParticipantDTO(chat_id=chat.id, contact_id=joiner.id),
    )

    events = await chat_service.get_chat_events(chat.id)
    participants = await chat_service.get_chat_participants(chat.id)

    assert {participant.id for participant in participants} == {
        existing_contact.id,
        joiner.id,
    }
    assert len(events) == 1
    assert events[0].contact_id == joiner.id
    assert events[0].event_type == ChatEventTypeEnum.MEMBER_ADDED


@pytest.mark.asyncio
@timer()
async def test_readding_existing_participant_does_not_duplicate_join_event(
    chat_service,
    contact_service,
    test_user,
    ed_signer,
    ecdh_cipher,
):
    chat = await create_chat(chat_service, test_user.id, "stable-chat")
    contact = await create_contact(
        contact_service,
        test_user.id,
        "stable-member",
        ed_signer,
        ecdh_cipher,
    )
    participant = AddChatParticipantDTO(chat_id=chat.id, contact_id=contact.id)

    first_result = await chat_service.add_participant(participant)
    second_result = await chat_service.add_participant(participant)
    events = await chat_service.get_chat_events(chat.id)
    participants = await chat_service.get_chat_participants(chat.id)

    assert first_result.chat_id == second_result.chat_id
    assert first_result.contact_id == second_result.contact_id
    assert [participant.id for participant in participants] == [contact.id]
    assert len(events) == 1
    assert events[0].event_type == ChatEventTypeEnum.MEMBER_ADDED


@pytest.mark.asyncio
@timer()
async def test_delete_participant_creates_left_event_only_when_member_existed(
    chat_service,
    contact_service,
    test_user,
    ed_signer,
    ecdh_cipher,
):
    chat = await create_chat(chat_service, test_user.id, "leave-chat")
    contact = await create_contact(
        contact_service,
        test_user.id,
        "leaving-member",
        ed_signer,
        ecdh_cipher,
    )
    await chat_service.add_participant(
        AddChatParticipantDTO(chat_id=chat.id, contact_id=contact.id)
    )

    first_delete = await chat_service.delete_participant(chat.id, contact.id)
    second_delete = await chat_service.delete_participant(chat.id, contact.id)
    events = await chat_service.get_chat_events(chat.id)
    participants = await chat_service.get_chat_participants(chat.id)
    removed_participant = await chat_service.get_participant(chat.id, contact.id)

    assert first_delete is True
    assert second_delete is False
    assert participants == []
    assert removed_participant is not None
    assert removed_participant.left_at is not None
    assert [event.event_type for event in events] == [
        ChatEventTypeEnum.MEMBER_ADDED,
        ChatEventTypeEnum.MEMBER_REMOVED,
    ]
    assert [event.contact_id for event in events] == [contact.id, contact.id]


@pytest.mark.asyncio
@timer()
async def test_sync_add_and_remove_participant_can_skip_events(
    chat_service,
    contact_service,
    test_user,
    ed_signer,
    ecdh_cipher,
):
    chat = await create_chat(chat_service, test_user.id, "sync-chat")
    contact = await create_contact(
        contact_service,
        test_user.id,
        "synced-member",
        ed_signer,
        ecdh_cipher,
    )

    added = await chat_service.add_participant(
        AddChatParticipantDTO(chat_id=chat.id, contact_id=contact.id),
        create_join_event=False,
    )
    deleted = await chat_service.delete_participant(
        chat.id,
        contact.id,
        create_left_event=False,
    )
    events = await chat_service.get_chat_events(chat.id)

    assert added.contact_id == contact.id
    assert deleted is True
    assert events == []


@pytest.mark.asyncio
@timer()
async def test_explicit_chat_event_crud(
    chat_service,
    contact_service,
    test_user,
    ed_signer,
    ecdh_cipher,
):
    chat = await create_chat(chat_service, test_user.id, "event-admin-chat")
    contact = await create_contact(
        contact_service,
        test_user.id,
        "event-member",
        ed_signer,
        ecdh_cipher,
    )

    created = await chat_service.add_chat_event(
        AddChatEventDTO(
            chat_id=chat.id,
            contact_id=contact.id,
            event_type=ChatEventTypeEnum.MEMBER_JOINED,
        )
    )
    updated = await chat_service.update_chat_event(
        RequestChatEventDTO(
            id=created.id,
            event_type=ChatEventTypeEnum.MEMBER_LEFT,
        )
    )
    found = await chat_service.get_chat_event_by_id(created.id)
    deleted = await chat_service.delete_chat_event(created.id)
    missing = await chat_service.get_chat_event_by_id(created.id)

    assert updated is not None
    assert updated.event_type == ChatEventTypeEnum.MEMBER_LEFT
    assert found is not None
    assert found.event_type == ChatEventTypeEnum.MEMBER_LEFT
    assert deleted is True
    assert missing is None


@pytest.mark.asyncio
@timer()
async def test_server_chat_events_are_idempotent_and_keep_server_context(
    chat_service,
    test_user,
):
    chat = await create_chat(chat_service, test_user.id, "event-sync-chat")
    server_event_id = uuid4()
    actor_server_user_id = uuid4()
    target_server_user_id = uuid4()
    timestamp = datetime.now(timezone.utc)

    first_event = await chat_service.add_chat_event(
        AddChatEventDTO(
            chat_id=chat.id,
            server_event_id=server_event_id,
            actor_server_user_id=actor_server_user_id,
            target_server_user_id=target_server_user_id,
            event_type=ChatEventTypeEnum.MEMBER_REMOVED,
            timestamp=timestamp,
        )
    )
    duplicate_event = await chat_service.add_chat_event(
        AddChatEventDTO(
            chat_id=chat.id,
            server_event_id=server_event_id,
            actor_server_user_id=actor_server_user_id,
            target_server_user_id=target_server_user_id,
            event_type=ChatEventTypeEnum.MEMBER_REMOVED,
            timestamp=timestamp,
        )
    )
    latest_timestamp = await chat_service.get_latest_server_event_timestamp(chat.id)
    events = await chat_service.get_chat_events(chat.id)

    assert duplicate_event.id == first_event.id
    assert len(events) == 1
    assert first_event.contact_id is None
    assert first_event.actor_server_user_id == actor_server_user_id
    assert first_event.target_server_user_id == target_server_user_id
    assert latest_timestamp == timestamp
