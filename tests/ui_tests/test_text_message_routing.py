import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from src.adapters.database.structures import (
    ContactStatusEnum,
    MessageContentMimeTypeEnum,
    MessageContentTypeEnum,
)
from src.presentation.pages.messenger import interface as interface_module
from src.presentation.pages.messenger import messages as messages_module
from src.presentation.pages.messenger.fields import ReplySelection
from src.presentation.pages.messenger.interface import MessengerInterface
from src.presentation.pages.messenger.messages import (
    ImageBubble,
    MessageBubble,
    VideoBubble,
)
from src.presentation.pages.messenger.panels import MessagesPanel
from src.presentation.pages.messenger.theme import COLOR_PANEL_BACKGROUND
from src.providers.cache import ChatCache, ContactCache, MessageCache


def _application() -> QApplication:
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


def _contact() -> ContactCache:
    return ContactCache(
        id=uuid4(),
        server_user_id=uuid4(),
        username="contact",
        status=ContactStatusEnum.ACCEPTED,
        last_seen=None,
        online=False,
    )


def _chat() -> ChatCache:
    return ChatCache(
        id=uuid4(),
        server_chat_id=uuid4(),
        server_owner_id=uuid4(),
        name="chat",
        created_at=datetime.now(timezone.utc),
    )


def _messages_panel() -> MessagesPanel:
    return MessagesPanel(
        "MESSAGES",
        "#D91414",
        "#C53A3A",
        "#373636",
        "#A92B2B",
        "#373636",
        "#D91414",
        "#959292",
        "#F4F1EC",
    )


def test_messages_panel_renders_loaded_image_bytes() -> None:
    application = _application()
    panel = _messages_panel()
    contact = _contact()
    message_id = uuid4()
    contact.messages.append(
        MessageCache(
            id=message_id,
            server_message_id=uuid4(),
            contact_id=contact.id,
            chat_id=None,
            content_type=MessageContentTypeEnum.IMAGE,
            content=None,
            file_name="photo",
            file_size=68,
            file_mime_type=MessageContentMimeTypeEnum.PNG,
            timestamp=datetime.now(timezone.utc),
            is_outgoing=False,
            is_delivered=True,
        )
    )
    image_data = (
        Path(__file__).parents[1] / "test_data" / "images" / "image_1.png"
    ).read_bytes()

    panel.show_conversation(contact)
    panel.set_loaded_file_contents(contact, {message_id: image_data})

    image_bubbles = [
        panel.messages_view.message_list._layout.itemAt(index).widget()
        for index in range(panel.messages_view.message_list._layout.count())
        if isinstance(
            panel.messages_view.message_list._layout.itemAt(index).widget(),
            ImageBubble,
        )
    ]
    assert len(image_bubbles) == 1
    assert image_bubbles[0].has_image is True
    panel.close()
    application.processEvents()


def test_loaded_image_save_action_emits_local_message_and_file_name() -> None:
    application = _application()
    panel = _messages_panel()
    contact = _contact()
    message_id = uuid4()
    contact.messages.append(
        MessageCache(
            id=message_id,
            server_message_id=uuid4(),
            contact_id=contact.id,
            chat_id=None,
            content_type=MessageContentTypeEnum.IMAGE,
            content=None,
            file_name="photo.10.10.2026",
            file_size=68,
            file_mime_type=MessageContentMimeTypeEnum.PNG,
            timestamp=datetime.now(timezone.utc),
            is_outgoing=False,
            is_delivered=True,
        )
    )
    image_data = (
        Path(__file__).parents[1] / "test_data" / "images" / "image_1.png"
    ).read_bytes()
    save_requests: list[tuple[object, str]] = []
    panel.file_save_requested.connect(
        lambda saved_message_id, name: save_requests.append((saved_message_id, name))
    )

    panel.show_conversation(contact)
    panel.set_loaded_file_contents(contact, {message_id: image_data})
    bubble = next(iter(panel._file_message_ids))
    bubble.context_action.emit("save_to_disk")

    assert save_requests == [(message_id, "photo.10.10.2026.png")]
    panel.close()
    application.processEvents()


def test_image_bubble_opens_viewer_only_inside_message_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application()
    image_data = (
        Path(__file__).parents[1] / "test_data" / "images" / "image_1.png"
    ).read_bytes()
    viewer_calls: list[tuple[object, ...]] = []

    class ViewerStub:
        def __init__(self, *args: object) -> None:
            viewer_calls.append(args)

        def setFocus(self) -> None:
            return None

    monkeypatch.setattr(messages_module, "ImageViewer", ViewerStub)
    bubble = ImageBubble(
        None,
        False,
        "#D91414",
        "#C53A3A",
        "#373636",
        "#A92B2B",
        "#373636",
        image_data=image_data,
    )
    bubble.resize(800, bubble.height())
    bubble.show()
    application.processEvents()

    QTest.mouseClick(
        bubble,
        Qt.MouseButton.LeftButton,
        pos=QPoint(700, bubble.height() // 2),
    )
    assert viewer_calls == []

    QTest.mouseClick(
        bubble,
        Qt.MouseButton.LeftButton,
        pos=QPoint(
            bubble._bubble_x() + bubble._bubble_w // 2,
            bubble._bubble_h // 2,
        ),
    )
    assert len(viewer_calls) == 1
    bubble.close()
    application.processEvents()


def test_media_context_menu_contains_file_actions() -> None:
    application = _application()
    parent = _messages_panel()

    menu = messages_module._create_media_context_menu(parent, "#D91414")

    assert [action.text() for action in menu.actions()] == [
        "⌫ DELETE",
        "↹ FORWARD",
        "↪ REPLY",
        "⇩ SAVE TO DISK",
    ]
    assert [action.data() for action in menu.actions()] == [
        "delete",
        "forward",
        "reply",
        "save_to_disk",
    ]
    assert messages_module.COLOR_CONTEXT_MENU_BACKGROUND == COLOR_PANEL_BACKGROUND
    assert f"background-color: {COLOR_PANEL_BACKGROUND}" in menu.styleSheet()
    assert f"color: {COLOR_PANEL_BACKGROUND}" in menu.styleSheet()
    menu.close()
    parent.close()
    application.processEvents()


@pytest.mark.parametrize("media_type", ["image", "video"])
def test_media_bubble_emits_context_action_inside_message_shape(
    media_type: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application()
    monkeypatch.setattr(
        messages_module,
        "_exec_media_context_menu",
        lambda *_args: "save_to_disk",
    )
    if media_type == "image":
        image_data = (
            Path(__file__).parents[1] / "test_data" / "images" / "image_1.png"
        ).read_bytes()
        bubble: ImageBubble | VideoBubble = ImageBubble(
            None,
            False,
            "#D91414",
            "#C53A3A",
            "#373636",
            "#A92B2B",
            "#373636",
            image_data=image_data,
        )
    else:
        bubble = VideoBubble(
            "missing-video.mp4",
            False,
            "#D91414",
            "#C53A3A",
            "#373636",
            "#A92B2B",
            "#373636",
        )
    bubble.resize(800, bubble.height())
    bubble.show()
    application.processEvents()
    actions: list[str] = []
    bubble.context_action.connect(actions.append)

    QTest.mouseClick(
        bubble,
        Qt.MouseButton.RightButton,
        pos=QPoint(
            bubble._bubble_x() + bubble._bubble_w // 2,
            bubble._bubble_h // 2,
        ),
    )

    assert actions == ["save_to_disk"]
    bubble.close()
    application.processEvents()


def test_reply_action_opens_and_closes_input_preview() -> None:
    application = _application()
    panel = _messages_panel()
    contact = _contact()
    contact.messages.append(
        MessageCache(
            id=uuid4(),
            server_message_id=uuid4(),
            contact_id=contact.id,
            chat_id=None,
            content_type=MessageContentTypeEnum.TEXT,
            content="Source message for the reply preview",
            file_name=None,
            file_size=None,
            file_mime_type=None,
            timestamp=datetime.now(timezone.utc),
            is_outgoing=False,
            is_delivered=True,
        )
    )

    panel.show_conversation(contact)
    bubble = next(
        panel.messages_view.message_list._layout.itemAt(index).widget()
        for index in range(panel.messages_view.message_list._layout.count())
        if isinstance(
            panel.messages_view.message_list._layout.itemAt(index).widget(),
            MessageBubble,
        )
    )
    bubble.context_action.emit("reply")

    reply = panel.message_field.current_reply()
    assert reply is not None
    assert reply.author == contact.username
    assert reply.preview == "Source message for the reply preview"
    assert reply.local_message_id == contact.messages[0].id
    assert reply.server_message_id == contact.messages[0].server_message_id
    assert panel.message_field.reply_preview.isVisibleTo(panel.message_field)
    assert panel.message_field.height() == 88

    panel.message_field.reply_preview.removed.emit()

    assert panel.message_field.current_reply() is None
    assert panel.message_field.reply_preview.isHidden()
    assert panel.message_field.height() == 50
    panel.close()
    application.processEvents()


def test_reply_preview_uses_current_username_for_outgoing_message() -> None:
    application = _application()
    panel = _messages_panel()
    panel.set_current_user("local_user")
    contact = _contact()
    contact.messages.append(
        MessageCache(
            id=uuid4(),
            server_message_id=uuid4(),
            contact_id=contact.id,
            chat_id=None,
            content_type=MessageContentTypeEnum.TEXT,
            content="My source message",
            file_name=None,
            file_size=None,
            file_mime_type=None,
            timestamp=datetime.now(timezone.utc),
            is_outgoing=True,
            is_delivered=True,
        )
    )

    panel.show_conversation(contact)
    bubble = next(
        panel.messages_view.message_list._layout.itemAt(index).widget()
        for index in range(panel.messages_view.message_list._layout.count())
        if isinstance(
            panel.messages_view.message_list._layout.itemAt(index).widget(),
            MessageBubble,
        )
    )
    bubble.context_action.emit("reply")

    reply = panel.message_field.current_reply()
    assert reply is not None
    assert reply.author == "local_user"
    panel.close()
    application.processEvents()


def test_chat_reply_action_keeps_general_message_identity() -> None:
    application = _application()
    panel = _messages_panel()
    author = _contact()
    chat = _chat()
    chat.participants = [author]
    general_message_uuid = uuid4()
    source = MessageCache(
        id=uuid4(),
        server_message_id=uuid4(),
        general_message_uuid=general_message_uuid,
        contact_id=author.id,
        chat_id=chat.id,
        content_type=MessageContentTypeEnum.TEXT,
        content="Chat source message",
        file_name=None,
        file_size=None,
        file_mime_type=None,
        timestamp=datetime.now(timezone.utc),
        is_outgoing=False,
        is_delivered=True,
    )
    chat.messages.append(source)

    panel.show_conversation(chat)
    bubble = next(
        panel.messages_view.message_list._layout.itemAt(index).widget()
        for index in range(panel.messages_view.message_list._layout.count())
        if isinstance(
            panel.messages_view.message_list._layout.itemAt(index).widget(),
            MessageBubble,
        )
    )
    bubble.context_action.emit("reply")

    reply = panel.message_field.current_reply()
    assert reply is not None
    assert reply.author == author.username
    assert reply.general_message_uuid == general_message_uuid
    panel.close()
    application.processEvents()


def test_sending_reply_renders_quote_without_changing_request_text() -> None:
    application = _application()
    panel = _messages_panel()
    contact = _contact()
    source_local_id = uuid4()
    source_server_id = uuid4()
    requests: list[tuple[object, object, str, object]] = []
    panel.text_message_send_requested.connect(
        lambda request_id, conversation, text, reply: requests.append(
            (request_id, conversation, text, reply)
        )
    )
    panel.show_conversation(contact)
    panel.message_field.set_reply(
        contact.username,
        "Quoted source message",
        local_message_id=source_local_id,
        server_message_id=source_server_id,
    )
    panel.message_field.input_field.setText("Reply body")

    panel.message_field._on_send()

    assert len(requests) == 1
    assert requests[0][1:3] == (contact, "Reply body")
    reply = requests[0][3]
    assert reply.local_message_id == source_local_id
    assert reply.server_message_id == source_server_id
    bubble = next(iter(panel._pending_text_bubbles.values()))
    assert bubble.reply_author == contact.username
    assert bubble.reply_text == "Quoted source message"
    assert panel.message_field.current_reply() == reply
    assert panel.message_field.reply_preview.isVisibleTo(panel.message_field)

    panel.finish_text_message(
        requests[0][0],
        True,
        server_message_id=uuid4(),
        local_message_id=uuid4(),
    )

    assert panel.message_field.current_reply() is None
    assert panel.message_field.reply_preview.isHidden()
    panel.close()
    application.processEvents()


def test_failed_reply_send_preserves_reply_selection() -> None:
    application = _application()
    panel = _messages_panel()
    contact = _contact()
    panel.show_conversation(contact)
    panel.message_field.set_reply(
        contact.username,
        "Quoted source message",
        local_message_id=uuid4(),
        server_message_id=uuid4(),
    )
    expected_reply = panel.message_field.current_reply()

    panel._on_message_sent("Reply body")
    request_id = next(iter(panel._pending_text_bubbles))
    panel.finish_text_message(request_id, False, failure_message="SEND FAILED")

    assert panel.message_field.current_reply() == expected_reply
    assert panel.message_field.reply_preview.isVisibleTo(panel.message_field)
    panel.close()
    application.processEvents()


@pytest.mark.asyncio
async def test_interface_loads_cached_image_when_contact_is_opened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application()
    contact = _contact()
    message_id = uuid4()
    contact.messages.append(
        MessageCache(
            id=message_id,
            server_message_id=uuid4(),
            contact_id=contact.id,
            chat_id=None,
            content_type=MessageContentTypeEnum.IMAGE,
            content=None,
            file_name="photo",
            file_size=1,
            file_mime_type=MessageContentMimeTypeEnum.PNG,
            timestamp=datetime.now(timezone.utc),
            is_outgoing=False,
            is_delivered=True,
        )
    )
    image_data = (
        Path(__file__).parents[1] / "test_data" / "images" / "image_1.png"
    ).read_bytes()
    loader = AsyncMock(return_value=(True, "SUCCESS", {message_id: image_data}))
    monkeypatch.setattr(
        interface_module,
        "LoadConversationFileMessagesInteractor",
        lambda: loader,
    )
    container = object()
    messenger = MessengerInterface(SimpleNamespace(container=container))

    messenger._show_conversation(contact)
    task = messenger._file_loading_task
    assert task is not None
    await task

    loader.assert_awaited_once_with(container, [message_id])
    assert any(
        isinstance(
            messenger.messages_panel.messages_view.message_list._layout.itemAt(
                index
            ).widget(),
            ImageBubble,
        )
        for index in range(
            messenger.messages_panel.messages_view.message_list._layout.count()
        )
    )
    messenger.close()
    application.processEvents()


def test_messages_panel_emits_text_request_for_selected_chat() -> None:
    application = _application()
    panel = _messages_panel()
    chat = _chat()
    requests: list[tuple[object, object, str, object]] = []
    panel.text_message_send_requested.connect(
        lambda request_id, conversation, text, reply: requests.append(
            (request_id, conversation, text, reply)
        )
    )

    panel.show_conversation(chat)
    panel._on_message_sent("hello chat")

    assert len(requests) == 1
    assert requests[0][1:] == (chat, "hello chat", None)
    assert len(panel._pending_text_bubbles) == 1
    assert next(iter(panel._pending_text_bubbles.values())).author is None
    panel.close()
    application.processEvents()


def test_file_sending_is_available_only_for_direct_conversations() -> None:
    application = _application()
    panel = _messages_panel()

    assert panel.message_field.attach_button.isHidden()

    panel.show_conversation(_contact())
    assert not panel.message_field.attach_button.isHidden()

    panel.message_field.attached_file = "pending.txt"
    panel.show_conversation(_chat())
    assert panel.message_field.attach_button.isHidden()
    assert panel.message_field.attached_file is None

    panel.show_conversation(None)
    assert panel.message_field.attach_button.isHidden()
    panel.close()
    application.processEvents()


def test_common_send_action_routes_attachment_instead_of_text() -> None:
    application = _application()
    panel = _messages_panel()
    contact = _contact()
    text_requests: list[tuple[object, object, str, object]] = []
    file_requests: list[tuple[object, object, str]] = []
    panel.text_message_send_requested.connect(
        lambda request_id, conversation, text, reply: text_requests.append(
            (request_id, conversation, text, reply)
        )
    )
    panel.file_message_send_requested.connect(
        lambda request_id, conversation, path: file_requests.append(
            (request_id, conversation, path)
        )
    )
    panel.show_conversation(contact)
    panel.message_field.input_field.setText("send this later")
    panel.message_field.attached_file = "document.pdf"

    panel.message_field._on_send()

    assert text_requests == []
    assert len(file_requests) == 1
    assert file_requests[0][1:] == (contact, "document.pdf")
    assert panel.message_field.input_field.text() == "send this later"
    assert panel.message_field.attached_file is None
    assert len(panel._pending_file_bubbles) == 1
    bubble = next(iter(panel._pending_file_bubbles.values()))
    assert bubble.status == ""

    server_message_id = uuid4()
    panel.finish_file_message(file_requests[0][0], True, server_message_id)

    assert bubble.status == "sent"
    assert bubble.server_message_id == server_message_id
    assert panel._pending_file_bubbles == {}
    panel.close()
    application.processEvents()


def test_file_bubble_marks_failed_when_sending_fails() -> None:
    application = _application()
    panel = _messages_panel()
    panel.show_conversation(_contact())
    panel._on_file_sent("document.pdf")
    request_id, bubble = next(iter(panel._pending_file_bubbles.items()))

    panel.finish_file_message(
        request_id,
        False,
        failure_message="FAILED TO SEND FILE",
    )

    assert bubble.status == "failed"
    assert bubble.toolTip() == "FAILED TO SEND FILE"
    assert panel._pending_file_bubbles == {}
    panel.close()
    application.processEvents()


def test_chat_bubbles_show_sender_name_and_use_extra_height() -> None:
    application = _application()
    panel = _messages_panel()
    participant = _contact()
    chat = _chat()
    chat.participants.append(participant)
    now = datetime.now(timezone.utc)
    chat.messages.extend(
        [
            MessageCache(
                id=uuid4(),
                server_message_id=uuid4(),
                contact_id=participant.id,
                chat_id=chat.id,
                content_type=MessageContentTypeEnum.TEXT,
                content="incoming",
                file_name=None,
                file_size=None,
                file_mime_type=None,
                timestamp=now,
                is_outgoing=False,
                is_delivered=True,
            ),
            MessageCache(
                id=uuid4(),
                server_message_id=uuid4(),
                contact_id=None,
                chat_id=chat.id,
                content_type=MessageContentTypeEnum.TEXT,
                content="outgoing",
                file_name=None,
                file_size=None,
                file_mime_type=None,
                timestamp=now,
                is_outgoing=True,
                is_delivered=True,
            ),
        ]
    )
    panel.set_available_contacts([participant])
    panel.show_conversation(chat)
    bubbles = [
        panel.messages_view.message_list._layout.itemAt(index).widget()
        for index in range(panel.messages_view.message_list._layout.count())
    ]
    message_bubbles = [
        bubble for bubble in bubbles if isinstance(bubble, MessageBubble)
    ]
    plain_bubble = MessageBubble(
        None,
        "incoming",
        False,
        "#D91414",
        "#C53A3A",
        "#373636",
        "#A92B2B",
        "#373636",
        now,
    )

    assert [bubble.author for bubble in message_bubbles] == ["contact", None]
    assert message_bubbles[0].height() > plain_bubble.height()
    assert message_bubbles[1].height() == plain_bubble.height()
    plain_bubble.deleteLater()
    panel.close()
    application.processEvents()


@pytest.mark.asyncio
async def test_interface_routes_text_messages_by_conversation_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application()
    container = object()
    contact = _contact()
    chat = _chat()
    contact_message_id = uuid4()
    chat_message_id = uuid4()
    contact_interactor = AsyncMock(
        return_value=(
            True,
            "SUCCESS",
            SimpleNamespace(id=uuid4(), server_message_id=contact_message_id),
        )
    )
    chat_interactor = AsyncMock(
        return_value=(
            True,
            "SUCCESS",
            SimpleNamespace(id=uuid4(), server_message_id=chat_message_id),
        )
    )
    monkeypatch.setattr(
        interface_module,
        "SendContactTextMessageInteractor",
        lambda: contact_interactor,
    )
    monkeypatch.setattr(
        interface_module,
        "SendChatTextMessageInteractor",
        lambda: chat_interactor,
    )
    messenger = MessengerInterface(SimpleNamespace(container=container))

    await messenger._send_text_message(uuid4(), contact, "direct", None)
    await messenger._send_text_message(uuid4(), chat, "group", None)

    contact_interactor.assert_awaited_once_with(container, contact, "direct", None)
    chat_interactor.assert_awaited_once_with(
        container,
        chat,
        "group",
        None,
        None,
    )
    messenger.close()
    application.processEvents()


@pytest.mark.asyncio
async def test_interface_routes_direct_reply_with_local_message_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application()
    container = object()
    contact = _contact()
    source = MessageCache(
        id=uuid4(),
        server_message_id=uuid4(),
        contact_id=contact.id,
        chat_id=None,
        content_type=MessageContentTypeEnum.TEXT,
        content="Quoted source",
        file_name=None,
        file_size=None,
        file_mime_type=None,
        timestamp=datetime.now(timezone.utc),
        is_outgoing=False,
        is_delivered=True,
    )
    contact.messages.append(source)
    saved = SimpleNamespace(id=uuid4(), server_message_id=uuid4())
    contact_interactor = AsyncMock(return_value=(True, "SUCCESS", saved))
    monkeypatch.setattr(
        interface_module,
        "SendContactTextMessageInteractor",
        lambda: contact_interactor,
    )
    messenger = MessengerInterface(SimpleNamespace(container=container))
    reply = ReplySelection(
        author=contact.username,
        preview="Quoted source",
        local_message_id=source.id,
        server_message_id=source.server_message_id,
    )

    await messenger._send_text_message(uuid4(), contact, "Reply body", reply)

    contact_interactor.assert_awaited_once_with(
        container,
        contact,
        "Reply body",
        source,
    )
    messenger.close()
    application.processEvents()


@pytest.mark.asyncio
async def test_interface_resolves_and_routes_chat_reply_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application()
    container = object()
    chat = _chat()
    source = MessageCache(
        id=uuid4(),
        server_message_id=uuid4(),
        general_message_uuid=uuid4(),
        contact_id=uuid4(),
        chat_id=chat.id,
        content_type=MessageContentTypeEnum.TEXT,
        content="Quoted group message",
        file_name=None,
        file_size=None,
        file_mime_type=None,
        timestamp=datetime.now(timezone.utc),
        is_outgoing=False,
        is_delivered=True,
    )
    chat.messages.append(source)
    reply_targets = {uuid4(): uuid4()}
    targets_interactor = AsyncMock(
        return_value=(True, "SUCCESS", reply_targets)
    )
    saved = SimpleNamespace(id=uuid4(), server_message_id=uuid4())
    chat_interactor = AsyncMock(return_value=(True, "SUCCESS", saved))
    monkeypatch.setattr(
        interface_module,
        "GetChatReplyTargetsInteractor",
        lambda: targets_interactor,
    )
    monkeypatch.setattr(
        interface_module,
        "SendChatTextMessageInteractor",
        lambda: chat_interactor,
    )
    messenger = MessengerInterface(SimpleNamespace(container=container))
    reply = ReplySelection(
        author="quoted_user",
        preview="Quoted group message",
        local_message_id=source.id,
        server_message_id=source.server_message_id,
        general_message_uuid=source.general_message_uuid,
    )

    await messenger._send_text_message(uuid4(), chat, "Reply body", reply)

    targets_interactor.assert_awaited_once_with(
        container,
        chat,
        source.general_message_uuid,
    )
    chat_interactor.assert_awaited_once_with(
        container,
        chat,
        "Reply body",
        source,
        reply_targets,
    )
    messenger.close()
    application.processEvents()


@pytest.mark.asyncio
async def test_interface_routes_file_messages_to_contact_interactor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application()
    container = object()
    contact = _contact()
    local_message_id = uuid4()
    server_message_id = uuid4()
    file_interactor = AsyncMock(
        return_value=(
            True,
            "SUCCESS",
            SimpleNamespace(
                id=local_message_id,
                server_message_id=server_message_id,
            ),
        )
    )
    monkeypatch.setattr(
        interface_module,
        "SendContactFileMessageInteractor",
        lambda: file_interactor,
    )
    messenger = MessengerInterface(SimpleNamespace(container=container))
    messenger.messages_panel.show_conversation(contact)
    messenger.messages_panel.message_field.attached_file = "document.pdf"

    messenger.messages_panel.message_field._on_send()
    pending_bubble = next(iter(messenger.messages_panel._pending_file_bubbles.values()))
    tasks = list(messenger._message_tasks)
    await asyncio.gather(*tasks)

    file_interactor.assert_awaited_once_with(container, contact, "document.pdf")
    assert pending_bubble.status == "sent"
    assert pending_bubble.server_message_id == server_message_id
    assert messenger.messages_panel._pending_file_bubbles == {}
    messenger.close()
    application.processEvents()


@pytest.mark.asyncio
async def test_interface_routes_save_action_to_file_interactor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    application = _application()
    container = object()
    message_id = uuid4()
    destination = tmp_path / "saved-photo.png"
    save_interactor = AsyncMock(return_value=(True, "SUCCESS", destination))
    monkeypatch.setattr(
        interface_module,
        "SaveMessageFileToDiskInteractor",
        lambda: save_interactor,
    )
    monkeypatch.setattr(
        interface_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(destination), "ALL FILES (*)"),
    )
    messenger = MessengerInterface(SimpleNamespace(container=container))

    messenger._schedule_file_save(message_id, "photo.png")
    tasks = list(messenger._message_tasks)
    await asyncio.gather(*tasks)

    save_interactor.assert_awaited_once_with(
        container,
        message_id,
        str(destination),
    )
    messenger.close()
    application.processEvents()


def test_interface_does_not_save_when_dialog_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application()
    save_interactor = AsyncMock()
    monkeypatch.setattr(
        interface_module,
        "SaveMessageFileToDiskInteractor",
        lambda: save_interactor,
    )
    monkeypatch.setattr(
        interface_module.QFileDialog,
        "getSaveFileName",
        lambda *_args: ("", ""),
    )
    messenger = MessengerInterface(SimpleNamespace(container=object()))

    messenger._schedule_file_save(uuid4(), "photo.png")

    save_interactor.assert_not_awaited()
    assert messenger._message_tasks == set()
    messenger.close()
    application.processEvents()
