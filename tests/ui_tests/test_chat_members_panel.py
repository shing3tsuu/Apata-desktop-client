import os
from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from src.adapters.database.structures import ContactStatusEnum
from src.presentation.pages.messenger.contacts import ContactCard, ContactList
from src.presentation.pages.messenger.panels import MessagesPanel
from src.providers.cache import ChatCache, ContactCache


def _application() -> QApplication:
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


def _contact(
    username: str,
    *,
    status: ContactStatusEnum = ContactStatusEnum.ACCEPTED,
) -> ContactCache:
    return ContactCache(
        id=uuid4(),
        server_user_id=uuid4(),
        username=username,
        status=status,
        last_seen=None,
        online=False,
    )


def _chat(participants: list[ContactCache] | None = None) -> ChatCache:
    return ChatCache(
        id=uuid4(),
        server_chat_id=uuid4(),
        server_owner_id=uuid4(),
        name="Night shift",
        created_at=datetime.now(timezone.utc),
        participants=participants or [],
    )


def _panel() -> MessagesPanel:
    panel = MessagesPanel(
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
    panel.resize(960, 720)
    panel.show()
    _application().processEvents()
    return panel


def _contact_list(chat: ChatCache, panel: MessagesPanel) -> ContactList:
    contact_list = ContactList(
        color_primary="#D91414",
        color_inactive="#959292",
    )
    contact_list.resize(480, 720)
    contact_list.contact_selected.connect(panel.show_conversation)
    contact_list.chat_members_requested.connect(panel.toggle_chat_members_panel)
    contact_list.set_conversations([], [chat])
    contact_list.show()
    _application().processEvents()
    return contact_list


def _click(widget: object) -> None:
    QTest.mouseClick(  # type: ignore[call-overload]
        cast(QWidget, widget),
        Qt.MouseButton.LeftButton,
    )


def test_add_button_is_inside_chat_card_only() -> None:
    application = _application()
    contact_card = ContactCard(
        _contact("contact"),
        color_primary="#D91414",
        color_inactive="#959292",
    )
    chat_card = ContactCard(
        _chat(),
        color_primary="#D91414",
        color_inactive="#959292",
    )
    chat_card.resize(480, 78)
    chat_card.show()
    application.processEvents()

    assert contact_card.add_chat_participant_button is None
    assert chat_card.add_chat_participant_button is not None
    assert chat_card.add_chat_participant_button.isVisible() is False
    chat_card.set_selected(True)
    application.processEvents()
    assert chat_card.add_chat_participant_button.isVisible() is True
    assert chat_card.add_chat_participant_button.geometry().right() < chat_card.width()
    chat_card.set_selected(False)
    application.processEvents()
    assert chat_card.add_chat_participant_button.isVisible() is False
    contact_card.close()
    chat_card.close()
    application.processEvents()


def test_panel_filters_candidates_and_blocks_repeated_in_flight_clicks() -> None:
    application = _application()
    panel = _panel()
    participant = _contact("participant")
    candidate = _contact("accepted")
    blank = _contact("blank", status=ContactStatusEnum.BLANK)
    current_user = _contact("current_user")
    chat = _chat([participant])
    contact_list = _contact_list(chat, panel)
    additions: list[tuple[ChatCache, ContactCache]] = []
    panel.chat_participant_add_requested.connect(
        lambda selected_chat, contact: additions.append((selected_chat, contact))
    )

    panel.set_available_contacts(
        [participant, candidate, blank, current_user],
        current_user.server_user_id,
    )
    chat_card = contact_list._cards[0]
    button = chat_card.add_chat_participant_button
    assert button is not None
    assert button.isVisible() is False
    _click(chat_card)
    application.processEvents()
    assert button.isVisible() is True
    _click(button)
    application.processEvents()

    assert panel.chat_members_panel.isVisible() is True
    assert panel.chat_members_panel.x() == 0
    assert panel.chat_members_panel.candidate_contacts == [candidate]
    participant_card = contact_list._chat_participant_cards[chat_card][0]
    assert participant_card.isVisible() is False
    assert contact_list._expanded_chat_card is None

    candidate_row = panel.chat_members_panel._rows[candidate.server_user_id]
    _click(candidate_row)
    _click(candidate_row)
    application.processEvents()
    assert additions == [(chat, candidate)]

    chat.participants.append(candidate)
    panel.finish_chat_participant_addition(candidate, True)
    application.processEvents()
    assert panel.chat_members_panel.isVisible() is True
    assert panel.chat_members_panel.candidate_contacts == []
    contact_list.close()
    panel.close()
    application.processEvents()


def test_panel_scrolls_and_closes_outside_or_on_conversation_change() -> None:
    application = _application()
    panel = _panel()
    contacts = [_contact(f"contact_{index:02}") for index in range(12)]
    chat = _chat()
    contact_list = _contact_list(chat, panel)

    panel.set_available_contacts(contacts)
    chat_card = contact_list._cards[0]
    button = chat_card.add_chat_participant_button
    assert button is not None
    _click(chat_card)
    application.processEvents()
    assert button.isVisible() is True
    _click(button)
    application.processEvents()

    assert panel.chat_members_panel.scroll.verticalScrollBar().maximum() > 0

    _click(panel.messages_view)
    application.processEvents()
    assert panel.chat_members_panel.isVisible() is False

    _click(button)
    application.processEvents()
    assert panel.chat_members_panel.isVisible() is True

    panel.show_conversation(contacts[0])
    application.processEvents()
    assert panel.chat_members_panel.isVisible() is False
    contact_list.close()
    panel.close()
    application.processEvents()
