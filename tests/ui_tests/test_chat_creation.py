import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

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


def test_chat_creation_panel_opens_submits_and_closes_outside() -> None:
    application = _application()
    panel = _panel()
    created_names: list[str] = []
    panel.create_chat_requested.connect(created_names.append)

    assert panel.search_panel.create_chat_button.isVisible() is False
    QTest.mouseClick(panel.chats_tab, Qt.MouseButton.LeftButton)
    application.processEvents()
    assert panel.search_panel.create_chat_button.isVisible() is True

    QTest.mouseClick(
        panel.search_panel.create_chat_button,
        Qt.MouseButton.LeftButton,
    )
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
    QTest.mouseClick(
        panel.chat_creation_panel.create_button,
        Qt.MouseButton.LeftButton,
    )
    assert created_names == ["Night shift"]

    QTest.mouseClick(panel.chats_tab, Qt.MouseButton.LeftButton)
    application.processEvents()
    assert panel.chat_creation_panel.isVisible() is False
    panel.close()


def test_switching_to_contacts_closes_chat_creation_panel() -> None:
    application = _application()
    panel = _panel()

    QTest.mouseClick(panel.chats_tab, Qt.MouseButton.LeftButton)
    QTest.mouseClick(
        panel.search_panel.create_chat_button,
        Qt.MouseButton.LeftButton,
    )
    application.processEvents()
    assert panel.chat_creation_panel.isVisible() is True

    QTest.mouseClick(panel.contacts_tab, Qt.MouseButton.LeftButton)
    application.processEvents()
    assert panel.chat_creation_panel.isVisible() is False
    assert panel.search_panel.create_chat_button.isVisible() is False
    panel.close()
