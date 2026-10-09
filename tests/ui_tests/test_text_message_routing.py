import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from src.adapters.database.structures import (
    ContactStatusEnum,
    MessageContentTypeEnum,
)
from src.presentation.pages.messenger import interface as interface_module
from src.presentation.pages.messenger.interface import MessengerInterface
from src.presentation.pages.messenger.messages import MessageBubble
from src.presentation.pages.messenger.panels import MessagesPanel
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


def test_messages_panel_emits_text_request_for_selected_chat() -> None:
    application = _application()
    panel = _messages_panel()
    chat = _chat()
    requests: list[tuple[object, object, str]] = []
    panel.text_message_send_requested.connect(
        lambda request_id, conversation, text: requests.append(
            (request_id, conversation, text)
        )
    )

    panel.show_conversation(chat)
    panel._on_message_sent("hello chat")

    assert len(requests) == 1
    assert requests[0][1:] == (chat, "hello chat")
    assert len(panel._pending_text_bubbles) == 1
    assert next(iter(panel._pending_text_bubbles.values())).author is None
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
            SimpleNamespace(server_message_id=contact_message_id),
        )
    )
    chat_interactor = AsyncMock(
        return_value=(
            True,
            "SUCCESS",
            SimpleNamespace(server_message_id=chat_message_id),
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

    await messenger._send_text_message(uuid4(), contact, "direct")
    await messenger._send_text_message(uuid4(), chat, "group")

    contact_interactor.assert_awaited_once_with(container, contact, "direct")
    chat_interactor.assert_awaited_once_with(container, chat, "group")
    messenger.close()
    application.processEvents()
