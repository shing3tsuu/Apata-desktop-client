import os
from datetime import datetime, timezone
from typing import cast
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from src.adapters.database.structures import ContactStatusEnum
from src.presentation.pages.messenger.contacts import ContactList
from src.presentation.pages.messenger.context_menus import ContactContextMenu
from src.presentation.pages.messenger.theme import (
    COLOR_CONTACT_OFFLINE,
    COLOR_CONTACT_ONLINE,
)
from src.providers.cache import ChatCache, ContactCache


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _contact(
    username: str,
    *,
    status: ContactStatusEnum = ContactStatusEnum.ACCEPTED,
    online: bool = True,
) -> ContactCache:
    return ContactCache(
        id=uuid4(),
        server_user_id=uuid4(),
        username=username,
        status=status,
        last_seen=None,
        online=online,
    )


def _chat(name: str, participants: list[ContactCache]) -> ChatCache:
    return ChatCache(
        id=uuid4(),
        server_chat_id=uuid4(),
        server_owner_id=uuid4(),
        name=name,
        created_at=datetime.now(timezone.utc),
        participants=participants,
    )


def _contact_list(chats: list[ChatCache]) -> ContactList:
    contact_list = ContactList(
        color_primary="#D91414",
        color_inactive="#B8B5B0",
    )
    contact_list.resize(480, 720)
    contact_list.set_conversations([], chats)
    contact_list.show()
    _application().processEvents()
    return contact_list


def _click(widget: object, button: Qt.MouseButton = Qt.MouseButton.LeftButton) -> None:
    QTest.mouseClick(  # type: ignore[call-overload]
        cast(QWidget, widget),
        button,
    )


def _wait(milliseconds: int) -> None:
    QTest.qWait(milliseconds)  # type: ignore[call-arg, arg-type]


def test_repeated_chat_click_toggles_participants_without_reselection() -> None:
    application = _application()
    participant = _contact("ghost_user")
    chat = _chat("Night shift", [participant])
    contact_list = _contact_list([chat])
    selected: list[object] = []
    contact_list.contact_selected.connect(selected.append)
    chat_card = contact_list._cards[0]
    participant_card = contact_list._chat_participant_cards[chat_card][0]

    _click(chat_card)
    application.processEvents()

    assert selected == [chat]
    assert participant_card.isVisible() is False
    assert chat_card.triangle_rotation == 0.0

    _click(chat_card)
    _wait(350)

    assert selected == [chat]
    assert participant_card.isVisible() is True
    assert chat_card.triangle_rotation == pytest.approx(180.0)

    _click(chat_card)
    _wait(350)

    assert selected == [chat]
    assert participant_card.isVisible() is False
    assert chat_card.triangle_rotation == pytest.approx(0.0)
    contact_list.close()
    application.processEvents()


def test_only_one_chat_participant_list_stays_expanded() -> None:
    application = _application()
    first_chat = _chat("First", [_contact("first_user")])
    second_chat = _chat("Second", [_contact("second_user")])
    contact_list = _contact_list([first_chat, second_chat])
    first_card, second_card = contact_list._cards
    first_participant = contact_list._chat_participant_cards[first_card][0]
    second_participant = contact_list._chat_participant_cards[second_card][0]

    _click(first_card)
    _click(first_card)
    application.processEvents()
    assert first_participant.isVisible() is True

    _click(second_card)
    _click(second_card)
    _wait(350)

    assert first_participant.isVisible() is False
    assert first_card.triangle_rotation == pytest.approx(0.0)
    assert second_participant.isVisible() is True
    assert second_card.triangle_rotation == pytest.approx(180.0)
    contact_list.close()
    application.processEvents()


def test_expanded_chat_survives_sidebar_refresh() -> None:
    application = _application()
    participant = _contact("ghost_user")
    chat = _chat("Night shift", [participant])
    contact_list = _contact_list([chat])
    chat_card = contact_list._cards[0]

    _click(chat_card)
    _click(chat_card)
    application.processEvents()
    contact_list.set_conversations([], [chat])
    application.processEvents()

    restored_card = contact_list._cards[0]
    restored_participant = contact_list._chat_participant_cards[restored_card][0]
    assert contact_list._expanded_chat_card is restored_card
    assert restored_participant.isVisible() is True
    assert restored_card.triangle_rotation == pytest.approx(180.0)
    contact_list.close()
    application.processEvents()


def test_chat_participant_selection_and_context_action_are_forwarded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    application = _application()
    participant = _contact("ghost_user")
    chat = _chat("Night shift", [participant])
    contact_list = _contact_list([chat])
    selected: list[object] = []
    actions: list[tuple[str, object]] = []
    contact_list.contact_selected.connect(selected.append)
    contact_list.contact_action_requested.connect(
        lambda action, contact: actions.append((action, contact))
    )
    chat_card = contact_list._cards[0]
    participant_card = contact_list._chat_participant_cards[chat_card][0]
    monkeypatch.setattr(
        ContactContextMenu,
        "exec_action",
        lambda self, position: "block",
    )

    _click(chat_card)
    _click(chat_card)
    application.processEvents()
    _click(participant_card, Qt.MouseButton.RightButton)
    application.processEvents()
    participant_card._show_context_menu(QPoint(5, 5))

    assert selected[-1] is participant
    assert participant_card.is_selected is True
    assert actions == [("block", participant)]
    contact_list.close()
    application.processEvents()


def test_chat_without_cached_participants_can_still_toggle() -> None:
    application = _application()
    chat = _chat("Empty", [])
    contact_list = _contact_list([chat])
    chat_card = contact_list._cards[0]

    _click(chat_card)
    _click(chat_card)
    _wait(350)

    assert contact_list._expanded_chat_card is chat_card
    assert contact_list._chat_participant_cards[chat_card] == []
    contact_list.close()
    application.processEvents()


def test_participant_triangle_preserves_contact_privacy_rules() -> None:
    application = _application()
    accepted = _contact("accepted", online=True)
    blank = _contact(
        "unmapped",
        status=ContactStatusEnum.BLANK,
        online=True,
    )
    chat = _chat("Privacy", [accepted, blank])
    contact_list = _contact_list([chat])
    chat_card = contact_list._cards[0]
    accepted_card, blank_card = contact_list._chat_participant_cards[chat_card]

    assert accepted_card._triangle_color() == COLOR_CONTACT_ONLINE
    assert blank_card._triangle_color() == COLOR_CONTACT_OFFLINE
    contact_list.close()
    application.processEvents()
