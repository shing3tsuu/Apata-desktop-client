import logging
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from dishka import Scope, make_async_container

from src.adapters.database.dto import (
    AddChatDTO,
    AddChatParticipantDTO,
    AddContactDTO,
    AddLocalUserDTO,
    AddMessageFileDTO,
    AddMessageTextDTO,
)
from src.adapters.database.service import (
    ChatService,
    ContactService,
    LocalUserService,
    MessageService,
)
from src.adapters.database.structures import (
    ContactStatusEnum,
    MessageContentMimeTypeEnum,
)
from src.adapters.encryption.dao import (
    AbstractECDHCipher,
    AbstractEDSignature,
    AbstractPasswordHasher,
)
from src.presentation.interactors.login import CacheConversationsInteractor
from src.providers import AppProvider, StateProvider
from src.providers.state import AppState
from tests.providers import MockDBProvider
from tests.timing_wrapper import timer


@pytest.fixture
async def container():
    container = make_async_container(
        StateProvider(),
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
async def message_service(container):
    async with container() as request_container:
        service = await request_container.get(MessageService)
        yield service
        # очищаем мастер-ключ после теста
        del service.master_key


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
async def ecdh_public_key(container):
    async with container() as request_container:
        ecdh_cipher = await request_container.get(AbstractECDHCipher)
        _, public_key = await ecdh_cipher.generate_key_pair()
        return public_key


@pytest.fixture
async def test_user(local_user_service, ed_signer, password_hasher):
    ed_public_key = (await ed_signer.generate_key_pair())[1]
    hashed_password = await password_hasher.hashing("testpass")
    user_data = AddLocalUserDTO(
        server_user_id=uuid4(),
        username="testuser",
        ed_public_key=ed_public_key,
        hashed_password=hashed_password,
        timezone=0,
    )
    user = await local_user_service.add_user(user_data)
    return user


@pytest.fixture
async def test_contact_user(local_user_service, ed_signer, password_hasher):
    ed_public_key = (await ed_signer.generate_key_pair())[1]
    hashed_password = await password_hasher.hashing("testpass")
    user_data = AddLocalUserDTO(
        server_user_id=uuid4(),
        username="contactuser",
        ed_public_key=ed_public_key,
        hashed_password=hashed_password,
        timezone=0,
    )
    user = await local_user_service.add_user(user_data)
    return user


@pytest.fixture
async def test_contact(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.ACCEPTED,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    contact = await contact_service.add_contact(add_dto)
    return contact


@pytest.fixture
def master_key():
    return os.urandom(32)


@pytest.mark.asyncio
async def test_conversation_cache_loads_recent_messages_without_file_payload(
    container, message_service, test_user, test_contact, master_key
):
    message_service.master_key = master_key
    async with container() as request_container:
        chat_service = await request_container.get(ChatService)
        app_state = await request_container.get(AppState)
        app_state.local_user_id = test_user.id
        app_state.master_key = master_key
        chat = await chat_service.add_chat(
            AddChatDTO(
                local_user_id=test_user.id,
                server_chat_id=uuid4(),
                name="Example group",
            )
        )
        await chat_service.add_participant(
            AddChatParticipantDTO(
                chat_id=chat.id,
                contact_id=test_contact.id,
            ),
            create_join_event=False,
        )

    started_at = datetime(2026, 9, 21, tzinfo=timezone.utc)
    for index in range(12):
        await message_service.add_message_text(
            AddMessageTextDTO(
                local_user_id=test_user.id,
                server_message_id=uuid.uuid7(),
                contact_id=test_contact.id,
                content=f"Text {index}",
                timestamp=started_at + timedelta(minutes=index),
                is_outgoing=index % 2 == 0,
                failed=index == 10,
            )
        )

    await message_service.add_message_text(
        AddMessageTextDTO(
            local_user_id=test_user.id,
            server_message_id=uuid.uuid7(),
            contact_id=test_contact.id,
            chat_id=chat.id,
            content="Group text",
            timestamp=started_at + timedelta(minutes=20),
            is_outgoing=False,
        )
    )
    await message_service.add_message_file(
        AddMessageFileDTO(
            local_user_id=test_user.id,
            server_message_id=uuid.uuid7(),
            chat_id=chat.id,
            file_name="attachment",
            file_content=b"file payload",
            file_size=12,
            file_mime_type=MessageContentMimeTypeEnum.BINARY,
            timestamp=started_at + timedelta(minutes=21),
            is_outgoing=True,
        )
    )

    success, message, counts = await CacheConversationsInteractor()(container)

    assert success, message
    assert counts == {"contacts": 1, "chats": 1, "messages": 12}
    assert [item.content for item in app_state.contacts_cache[0].messages] == [
        f"Text {index}" for index in range(2, 12)
    ]
    assert [item.content for item in app_state.chats_cache[0].messages] == [
        "Group text",
        None,
    ]
    assert app_state.chats_cache[0].messages[-1].file_name == "attachment"
    assert not hasattr(app_state.chats_cache[0].messages[-1], "file_content")
    assert app_state.chats_cache[0].participants == [app_state.contacts_cache[0]]
    assert app_state.chats_cache[0].participants[0] is app_state.contacts_cache[0]
    assert [
        item.content
        for item in app_state.contacts_cache[0].messages
        if item.failed is True
    ] == ["Text 10"]


@pytest.mark.asyncio
async def test_mark_messages_failed_updates_outgoing_messages(
    message_service,
    test_user,
    test_contact,
    master_key,
):
    message_service.master_key = master_key
    server_message_id = uuid.uuid7()
    saved = await message_service.add_message_text(
        AddMessageTextDTO(
            local_user_id=test_user.id,
            server_message_id=server_message_id,
            contact_id=test_contact.id,
            content="Failed delivery",
            is_outgoing=True,
            is_delivered=True,
        )
    )

    updated = await message_service.mark_messages_failed(
        test_user.id,
        [server_message_id],
    )
    messages = await message_service.get_messages(
        test_user.id,
        test_contact.id,
    )

    assert updated == 1
    assert messages[0].id == saved.id
    assert messages[0].failed is True


@pytest.mark.asyncio
@timer()
async def test_add_messages(message_service, test_user, test_contact, master_key):
    message_service.master_key = master_key

    texts = [
        AddMessageTextDTO(
            local_user_id=test_user.id,
            server_message_id=uuid.uuid7(),
            contact_id=test_contact.id,
            content=f"Text {i}",
            is_outgoing=True,
        )
        for i in range(3)
    ]
    files = [
        AddMessageFileDTO(
            local_user_id=test_user.id,
            server_message_id=uuid.uuid7(),
            contact_id=test_contact.id,
            file_name=f"file{i}",
            file_content=os.urandom(100),
            file_size=100,
            file_mime_type=MessageContentMimeTypeEnum.BINARY,
            is_outgoing=False,
        )
        for i in range(2)
    ]
    text_results, file_results = await message_service.add_messages(
        texts=texts, files=files
    )
    assert len(text_results) == 3
    assert len(file_results) == 2
    for msg in text_results:
        assert msg.content is not None and msg.content != ""
    for msg in file_results:
        assert msg.file_content is not None


@pytest.mark.asyncio
@timer()
async def test_get_messages(message_service, test_user, test_contact, master_key):
    message_service.master_key = master_key

    texts = [
        AddMessageTextDTO(
            local_user_id=test_user.id,
            server_message_id=uuid.uuid7(),
            contact_id=test_contact.id,
            content=f"Text {i}",
            is_outgoing=i % 2 == 0,
        )
        for i in range(5)
    ]
    for dto in texts:
        await message_service.add_message_text(dto)

    retrieved = await message_service.get_messages(
        local_user_id=test_user.id,
        contact_id=test_contact.id,
        limit=10,
    )
    assert len(retrieved) == 5
    for msg in retrieved:
        assert msg.content is not None
        assert msg.content.startswith("Text ")
        expected_outgoing = int(msg.content.split()[1]) % 2 == 0
        assert msg.is_outgoing == expected_outgoing


@pytest.mark.asyncio
@timer()
async def test_get_messages_limit(message_service, test_user, test_contact, master_key):
    message_service.master_key = master_key
    for i in range(10):
        dto = AddMessageTextDTO(
            local_user_id=test_user.id,
            server_message_id=uuid.uuid7(),
            contact_id=test_contact.id,
            content=f"Message {i}",
            is_outgoing=True,
        )
        await message_service.add_message_text(dto)

    retrieved = await message_service.get_messages(
        local_user_id=test_user.id,
        contact_id=test_contact.id,
        limit=3,
    )
    assert len(retrieved) == 3


@pytest.mark.asyncio
@timer()
async def test_get_messages_no_messages(
    message_service, test_user, test_contact, master_key
):
    message_service.master_key = master_key
    retrieved = await message_service.get_messages(
        local_user_id=test_user.id,
        contact_id=test_contact.id,
    )
    assert retrieved == []


@pytest.mark.asyncio
@timer()
async def test_delete_message(message_service, test_user, test_contact, master_key):
    message_service.master_key = master_key
    dto = AddMessageTextDTO(
        local_user_id=test_user.id,
        server_message_id=uuid.uuid7(),
        contact_id=test_contact.id,
        content="to delete",
        is_outgoing=True,
    )
    created = await message_service.add_message_text(dto)
    deleted = await message_service.delete_message(created.id)
    assert deleted is True

    retrieved = await message_service.get_messages(
        local_user_id=test_user.id,
        contact_id=test_contact.id,
    )
    assert len(retrieved) == 0


@pytest.mark.asyncio
@timer()
async def test_delete_message_not_found(message_service):
    result = await message_service.delete_message(uuid.uuid4())
    assert result is False


@pytest.mark.asyncio
@timer()
async def test_master_key_not_set(message_service, test_user, test_contact):
    assert message_service.master_key is None

    with pytest.raises(ValueError, match="Master key is not set"):
        await message_service.add_message_text(
            AddMessageTextDTO(
                local_user_id=test_user.id,
                server_message_id=uuid.uuid7(),
                contact_id=test_contact.id,
                content="test",
                is_outgoing=True,
            )
        )

    with pytest.raises(ValueError, match="Master key is not set"):
        await message_service.add_message_file(
            AddMessageFileDTO(
                local_user_id=test_user.id,
                server_message_id=uuid.uuid7(),
                contact_id=test_contact.id,
                file_name="test",
                file_content=b"test",
                file_size=4,
                file_mime_type=MessageContentMimeTypeEnum.TEXT,
                is_outgoing=True,
            )
        )

    with pytest.raises(ValueError, match="Master key is not set"):
        await message_service.get_messages(test_user.id, test_contact.id)


@pytest.mark.asyncio
@timer()
async def test_add_messages_empty_lists(message_service, master_key):
    message_service.master_key = master_key
    with pytest.raises(ValueError, match="No texts and no files"):
        await message_service.add_messages()


@pytest.mark.asyncio
@timer()
async def test_add_messages_with_none_lists(message_service, master_key):
    message_service.master_key = master_key
    with pytest.raises(ValueError, match="No texts and no files"):
        await message_service.add_messages(texts=None, files=None)


@pytest.mark.asyncio
@timer()
async def test_message_text_encryption_decryption(
    message_service, test_user, test_contact, master_key
):
    message_service.master_key = master_key
    original_text = "Secret message"
    dto = AddMessageTextDTO(
        local_user_id=test_user.id,
        server_message_id=uuid.uuid7(),
        contact_id=test_contact.id,
        content=original_text,
        is_outgoing=True,
    )
    await message_service.add_message_text(dto)
    retrieved = await message_service.get_messages(
        local_user_id=test_user.id,
        contact_id=test_contact.id,
    )
    assert len(retrieved) == 1
    assert retrieved[0].content == original_text


@pytest.mark.asyncio
@timer()
async def test_message_file_encryption_decryption(
    message_service, test_user, test_contact, master_key
):
    message_service.master_key = master_key
    original_data = b"binary file content"
    dto = AddMessageFileDTO(
        local_user_id=test_user.id,
        server_message_id=uuid.uuid7(),
        contact_id=test_contact.id,
        file_name="secret",
        file_content=original_data,
        file_size=len(original_data),
        file_mime_type=MessageContentMimeTypeEnum.BINARY,
        is_outgoing=True,
    )
    await message_service.add_message_file(dto)
    retrieved = await message_service.get_messages(
        local_user_id=test_user.id,
        contact_id=test_contact.id,
    )
    assert len(retrieved) == 1
    assert retrieved[0].file_content == original_data


@pytest.mark.asyncio
@timer()
async def test_add_message_file_real_image(
    message_service, test_user, test_contact, master_key
):
    message_service.master_key = master_key

    test_image_path = Path("tests/test_data/images/image_1.png")
    if not test_image_path.exists():
        pytest.skip("Test image not found")

    with open(test_image_path, "rb") as f:
        original_bytes = f.read()

    server_message_id = uuid.uuid7()
    dto = AddMessageFileDTO(
        local_user_id=test_user.id,
        server_message_id=server_message_id,
        contact_id=test_contact.id,
        file_name="image_1",
        file_content=original_bytes,
        file_size=len(original_bytes),
        file_mime_type=MessageContentMimeTypeEnum.PNG,
        is_outgoing=True,
    )

    saved = await message_service.add_message_file(dto)
    assert saved.id is not None
    assert saved.file_content != original_bytes  # зашифровано в БД

    # Получаем и расшифровываем
    retrieved = await message_service.get_messages(
        local_user_id=test_user.id,
        contact_id=test_contact.id,
        limit=10,
    )
    assert len(retrieved) == 1
    assert retrieved[0].file_content == original_bytes

    # Опционально сохраняем расшифрованный файл для визуальной проверки
    output_path = Path("tests/test_data/output/decrypted_from_db_image.png")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(retrieved[0].file_content)


@pytest.mark.asyncio
@timer()
async def test_add_message_file_real_video(
    message_service, test_user, test_contact, master_key
):
    message_service.master_key = master_key

    test_video_path = Path("tests/test_data/video/video_1.mp4")
    if not test_video_path.exists():
        pytest.skip("Test video not found")

    with open(test_video_path, "rb") as f:
        original_bytes = f.read()

    server_message_id = uuid.uuid7()
    dto = AddMessageFileDTO(
        local_user_id=test_user.id,
        server_message_id=server_message_id,
        contact_id=test_contact.id,
        file_name="video_1",
        file_content=original_bytes,
        file_size=len(original_bytes),
        file_mime_type=MessageContentMimeTypeEnum.MP4,
        is_outgoing=True,
    )

    saved = await message_service.add_message_file(dto)
    assert saved.id is not None
    assert saved.file_content != original_bytes

    retrieved = await message_service.get_messages(
        local_user_id=test_user.id,
        contact_id=test_contact.id,
        limit=10,
    )
    assert len(retrieved) == 1
    assert retrieved[0].file_content == original_bytes

    output_path = Path("tests/test_data/output/decrypted_from_db_video.mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(retrieved[0].file_content)
