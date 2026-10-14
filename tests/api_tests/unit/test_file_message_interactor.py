from datetime import datetime, timezone
from pathlib import Path
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from dishka import AsyncContainer
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519

from src.adapters.api.service import FileHTTPService
from src.adapters.database.dto import ContactDTO, MessageDTO
from src.adapters.database.service import ContactService, MessageService
from src.adapters.database.structures import (
    ContactStatusEnum,
    MessageContentMimeTypeEnum,
    MessageContentTypeEnum,
)
from src.presentation.interactors.messenger import (
    LoadConversationFileMessagesInteractor,
    SaveMessageFileToDiskInteractor,
    SendContactFileMessageInteractor,
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


def _app_state(local_user_id=None) -> AppState:
    state = AppState()
    state.token = "access-token"
    state.local_user_id = local_user_id or uuid4()
    state.master_key = b"master-key"
    state.ed_private_key = "sender-ed-private-key"
    state.ecdh_private_key = "sender-ecdh-private-key"
    state.ecdh_public_key = "sender-ecdh-public-key"
    return state


def _cached_contact() -> ContactCache:
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
    return ContactCache(
        id=uuid4(),
        server_user_id=uuid4(),
        username="recipient",
        status=ContactStatusEnum.ACCEPTED,
        last_seen=None,
        online=False,
        ed_public_key=ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )


def _local_contact(state: AppState, cached: ContactCache) -> ContactDTO:
    return ContactDTO.model_construct(
        id=cached.id,
        local_user_id=state.local_user_id,
        server_user_id=cached.server_user_id,
        status=cached.status,
        username=cached.username,
        ed_public_key=cached.ed_public_key,
        ecdh_public_key=cached.ecdh_public_key,
        last_seen=cached.last_seen,
        online=cached.online,
    )


def _saved_file_message(
    state: AppState,
    cached: ContactCache,
    server_message_id,
    file_content: bytes,
    file_name: str = "photo",
) -> MessageDTO:
    return MessageDTO(
        id=uuid4(),
        local_user_id=state.local_user_id,
        server_message_id=server_message_id,
        contact_id=cached.id,
        chat_id=None,
        content_type=MessageContentTypeEnum.IMAGE,
        content=None,
        file_name=file_name,
        file_content=b"encrypted-at-rest",
        file_size=len(file_content),
        file_mime_type=MessageContentMimeTypeEnum.PNG,
        timestamp=datetime.now(timezone.utc),
        is_outgoing=True,
        is_delivered=True,
    )


@pytest.mark.asyncio
async def test_load_conversation_file_messages_returns_decrypted_bytes() -> None:
    state = _app_state()
    cached = _cached_contact()
    first = _saved_file_message(
        state,
        cached,
        uuid4(),
        b"first-image",
    ).model_copy(update={"file_content": b"first-image"})
    second = _saved_file_message(
        state,
        cached,
        uuid4(),
        b"second-image",
    ).model_copy(update={"file_content": b"second-image"})
    message_service = MagicMock(spec=MessageService)
    message_service.get_file_messages = AsyncMock(return_value=[first, second])
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: state,
                MessageService: message_service,
            }
        ),
    )

    success, status_message, contents = await LoadConversationFileMessagesInteractor()(
        container,
        [first.id, first.id, second.id],
    )

    assert success is True
    assert status_message == "SUCCESS"
    assert contents == {
        first.id: b"first-image",
        second.id: b"second-image",
    }
    assert message_service.master_key == b"master-key"
    message_service.get_file_messages.assert_awaited_once_with(
        state.local_user_id,
        [first.id, second.id],
    )


@pytest.mark.asyncio
async def test_save_message_file_to_destination_directory(tmp_path: Path) -> None:
    state = _app_state()
    cached = _cached_contact()
    content = b"decrypted-image-content"
    message = _saved_file_message(
        state,
        cached,
        uuid4(),
        content,
        "photo.09.10.2026",
    ).model_copy(update={"file_content": content})
    message_service = MagicMock(spec=MessageService)
    message_service.get_file_messages = AsyncMock(return_value=[message])
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: state,
                MessageService: message_service,
            }
        ),
    )

    result = await SaveMessageFileToDiskInteractor()(
        container,
        message.id,
        str(tmp_path),
    )

    destination = tmp_path / "photo.09.10.2026.png"
    assert result == (True, "SUCCESS", destination)
    assert destination.read_bytes() == content
    assert message_service.master_key == b"master-key"
    message_service.get_file_messages.assert_awaited_once_with(
        state.local_user_id,
        [message.id],
    )


@pytest.mark.asyncio
async def test_save_message_file_appends_original_extension(
    tmp_path: Path,
) -> None:
    state = _app_state()
    cached = _cached_contact()
    content = b"decrypted-image-content"
    message = _saved_file_message(
        state,
        cached,
        uuid4(),
        content,
    ).model_copy(update={"file_content": content})
    message_service = MagicMock(spec=MessageService)
    message_service.get_file_messages = AsyncMock(return_value=[message])
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: state,
                MessageService: message_service,
            }
        ),
    )

    selected_path = tmp_path / "renamed.10.10.2026"
    result = await SaveMessageFileToDiskInteractor()(
        container,
        message.id,
        str(selected_path),
    )

    destination = tmp_path / "renamed.10.10.2026.png"
    assert result == (True, "SUCCESS", destination)
    assert destination.read_bytes() == content


@pytest.mark.asyncio
async def test_save_message_file_rejects_missing_message(tmp_path: Path) -> None:
    state = _app_state()
    message_id = uuid4()
    message_service = MagicMock(spec=MessageService)
    message_service.get_file_messages = AsyncMock(return_value=[])
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: state,
                MessageService: message_service,
            }
        ),
    )

    result = await SaveMessageFileToDiskInteractor()(
        container,
        message_id,
        str(tmp_path),
    )

    assert result == (False, "FILE MESSAGE NOT FOUND", None)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.asyncio
async def test_save_message_file_rejects_invalid_decrypted_size(
    tmp_path: Path,
) -> None:
    state = _app_state()
    cached = _cached_contact()
    message = _saved_file_message(
        state,
        cached,
        uuid4(),
        b"expected-content",
    ).model_copy(update={"file_content": b"truncated"})
    message_service = MagicMock(spec=MessageService)
    message_service.get_file_messages = AsyncMock(return_value=[message])
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: state,
                MessageService: message_service,
            }
        ),
    )

    result = await SaveMessageFileToDiskInteractor()(
        container,
        message.id,
        str(tmp_path),
    )

    assert result == (
        False,
        "FILE CONTENT SIZE DOES NOT MATCH METADATA",
        None,
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    ("file_name", "expected"),
    [
        ("image.jpg", MessageContentMimeTypeEnum.JPG),
        ("image.jpeg", MessageContentMimeTypeEnum.JPEG),
        ("image.png", MessageContentMimeTypeEnum.PNG),
        ("document.pdf", MessageContentMimeTypeEnum.PDF),
        ("document.docx", MessageContentMimeTypeEnum.DOCX),
        ("notes.txt", MessageContentMimeTypeEnum.TEXT),
    ],
)
def test_file_mime_parser_supports_attachment_dialog_extensions(
    file_name: str,
    expected: MessageContentMimeTypeEnum,
) -> None:
    assert (
        SendContactFileMessageInteractor._parse_file_mime_type(Path(file_name))
        is expected
    )


@pytest.mark.asyncio
async def test_send_contact_file_message_persists_and_updates_cache(
    tmp_path: Path,
) -> None:
    source = tmp_path / "photo.09.10.2026.png"
    file_content = b"image-content"
    source.write_bytes(file_content)
    state = _app_state()
    cached = _cached_contact()
    state.contacts_cache = [cached]
    local_contact = _local_contact(state, cached)
    server_message_id = uuid4()
    saved_message = _saved_file_message(
        state,
        cached,
        server_message_id,
        file_content,
        "photo.09.10.2026",
    )
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contact_by_server_user_id = AsyncMock(
        return_value=local_contact
    )
    file_http_service = MagicMock(spec=FileHTTPService)
    file_http_service.send_encrypted_message_file = AsyncMock(
        return_value=server_message_id
    )
    message_service = MagicMock(spec=MessageService)
    message_service.add_message_file = AsyncMock(return_value=saved_message)
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: state,
                ContactService: contact_service,
                FileHTTPService: file_http_service,
                MessageService: message_service,
            }
        ),
    )

    result = await SendContactFileMessageInteractor()(
        container,
        cached,
        str(source),
    )

    assert result == (True, "SUCCESS", saved_message)
    assert file_http_service.token == "access-token"
    file_http_service.send_encrypted_message_file.assert_awaited_once_with(
        chat_id=None,
        recipient_id=cached.server_user_id,
        recipient_ed_public_key=cached.ed_public_key,
        sender_ed_private_key="sender-ed-private-key",
        sender_ecdh_private_key="sender-ecdh-private-key",
        ephemeral_ecdh_public_key="sender-ecdh-public-key",
        file_name="photo.09.10.2026",
        file_mime_type=".png",
        file_content=file_content,
    )
    message_service.add_message_file.assert_awaited_once()
    stored = message_service.add_message_file.await_args.args[0]
    assert stored.file_content == file_content
    assert stored.file_name == "photo.09.10.2026"
    assert stored.file_mime_type is MessageContentMimeTypeEnum.PNG
    assert stored.content_type is MessageContentTypeEnum.IMAGE
    assert message_service.master_key == b"master-key"
    assert len(cached.messages) == 1
    assert cached.messages[0].file_name == "photo.09.10.2026"
    assert cached.messages[0].content is None
    assert cached.messages[0].file_content == file_content


@pytest.mark.asyncio
async def test_send_contact_file_message_maps_new_local_contact_after_upload(
    tmp_path: Path,
) -> None:
    source = tmp_path / "photo.png"
    file_content = b"image-content"
    source.write_bytes(file_content)
    state = _app_state()
    cached = _cached_contact()
    cached.status = ContactStatusEnum.BLANK
    local_contact = _local_contact(state, cached).model_copy(update={"id": uuid4()})
    server_message_id = uuid4()
    saved_message = _saved_file_message(
        state,
        cached,
        server_message_id,
        file_content,
    ).model_copy(update={"contact_id": local_contact.id})
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contact_by_server_user_id = AsyncMock(return_value=None)
    contact_service.add_contact = AsyncMock(return_value=local_contact)
    file_http_service = MagicMock(spec=FileHTTPService)
    file_http_service.send_encrypted_message_file = AsyncMock(
        return_value=server_message_id
    )
    message_service = MagicMock(spec=MessageService)
    message_service.add_message_file = AsyncMock(return_value=saved_message)
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: state,
                ContactService: contact_service,
                FileHTTPService: file_http_service,
                MessageService: message_service,
            }
        ),
    )

    result = await SendContactFileMessageInteractor()(
        container,
        cached,
        str(source),
    )

    assert result == (True, "SUCCESS", saved_message)
    contact_service.add_contact.assert_awaited_once()
    assert cached.id == local_contact.id
    assert state.contacts_cache == [cached]
    assert cached.messages[0].server_message_id == server_message_id


@pytest.mark.asyncio
async def test_send_contact_file_message_upload_failure_has_no_local_mutation(
    tmp_path: Path,
) -> None:
    source = tmp_path / "document.pdf"
    source.write_bytes(b"document-content")
    state = _app_state()
    cached = _cached_contact()
    original_contact_id = cached.id
    contact_service = MagicMock(spec=ContactService)
    contact_service.get_contact_by_server_user_id = AsyncMock(return_value=None)
    contact_service.add_contact = AsyncMock()
    file_http_service = MagicMock(spec=FileHTTPService)
    file_http_service.send_encrypted_message_file = AsyncMock(return_value=None)
    message_service = MagicMock(spec=MessageService)
    message_service.add_message_file = AsyncMock()
    container = cast(
        AsyncContainer,
        FakeContainer(
            {
                AppState: state,
                ContactService: contact_service,
                FileHTTPService: file_http_service,
                MessageService: message_service,
            }
        ),
    )

    result = await SendContactFileMessageInteractor()(
        container,
        cached,
        str(source),
    )

    assert result == (False, "FAILED TO SEND FILE", None)
    contact_service.add_contact.assert_not_awaited()
    message_service.add_message_file.assert_not_awaited()
    assert state.contacts_cache == []
    assert cached.id == original_contact_id
    assert cached.messages == []


@pytest.mark.asyncio
async def test_send_contact_file_message_validates_before_reading(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    oversized = tmp_path / "large.bin"
    oversized.write_bytes(b"1234")
    unsupported = tmp_path / "program.exe"
    unsupported.write_bytes(b"123")
    monkeypatch.setattr(FileHTTPService, "MAX_PLAINTEXT_FILE_SIZE", 3)
    container_mock = MagicMock()
    container = cast(AsyncContainer, container_mock)
    interactor = SendContactFileMessageInteractor()

    assert await interactor(container, _cached_contact(), str(oversized)) == (
        False,
        "FILE EXCEEDS 100 MIB LIMIT",
        None,
    )
    assert await interactor(container, _cached_contact(), str(unsupported)) == (
        False,
        "FILE TYPE IS NOT SUPPORTED",
        None,
    )
    container_mock.assert_not_called()


@pytest.mark.asyncio
async def test_send_contact_file_message_requires_application_state(
    tmp_path: Path,
) -> None:
    source = tmp_path / "document.pdf"
    source.write_bytes(b"document-content")
    state = AppState()
    container = cast(
        AsyncContainer,
        FakeContainer({AppState: state}),
    )

    result = await SendContactFileMessageInteractor()(
        container,
        _cached_contact(),
        str(source),
    )

    assert result == (False, "FILE SENDING PREREQUISITES MISSING", None)
