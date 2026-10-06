import asyncio
import os
from typing import cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QWidget

from src.presentation.pages.messenger.interface import MessengerInterface
from src.presentation.pages.messenger.panels import ContactsPanel


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _panel() -> ContactsPanel:
    panel = ContactsPanel(
        contacts_title="CONTACTS",
        chats_title="CHATS",
        color_primary="#D91414",
        color_third="#373636",
        color_divider="#F4F1EC",
    )
    panel.resize(480, 720)
    panel.show()
    _application().processEvents()
    return panel


def _click(widget: object) -> None:
    QTest.mouseClick(  # type: ignore[call-overload]
        cast(QWidget, widget),
        Qt.MouseButton.LeftButton,
    )


def test_chat_creation_panel_opens_submits_and_closes_outside() -> None:
    application = _application()
    panel = _panel()
    created_names: list[str] = []
    panel.create_chat_requested.connect(created_names.append)

    assert panel.search_panel.create_chat_button.isVisible() is False
    _click(panel.chats_tab)
    application.processEvents()
    assert panel.search_panel.create_chat_button.isVisible() is True

    _click(panel.search_panel.create_chat_button)
    application.processEvents()
    assert panel.chat_creation_panel.isVisible() is True
    assert panel.chat_creation_panel.name_field.alignment() == (
        Qt.AlignmentFlag.AlignCenter
    )
    block_widths = {
        panel.chat_creation_panel.title.width(),
        panel.chat_creation_panel.name_field.width(),
        panel.chat_creation_panel.create_button.width(),
    }
    assert len(block_widths) == 1

    panel.chat_creation_panel.name_field.setText("Night shift")
    _click(panel.chat_creation_panel.create_button)
    assert created_names == ["Night shift"]

    _click(panel.chats_tab)
    application.processEvents()
    assert panel.chat_creation_panel.isVisible() is False
    panel.close()


def test_switching_to_contacts_closes_chat_creation_panel() -> None:
    application = _application()
    panel = _panel()

    _click(panel.chats_tab)
    _click(panel.search_panel.create_chat_button)
    application.processEvents()
    assert panel.chat_creation_panel.isVisible() is True

    _click(panel.contacts_tab)
    application.processEvents()
    assert panel.chat_creation_panel.isVisible() is False
    assert panel.search_panel.create_chat_button.isVisible() is False
    panel.close()


class _PendingTask:
    def done(self) -> bool:
        return False


def test_chat_creation_ignores_submission_while_request_is_in_flight() -> None:
    application = _application()
    interface = MessengerInterface()
    pending_task = cast(asyncio.Task[None], _PendingTask())
    interface._chat_creation_task = pending_task

    interface._schedule_chat_creation("Second chat")

    assert interface._chat_creation_task is pending_task
    interface.close()
    application.processEvents()
