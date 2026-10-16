import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QEvent, QPointF, Qt
from PyQt6.QtGui import QEnterEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
import pytest

from src.presentation.pages.messenger.buttons import LogoutButton
from src.presentation.pages.messenger.interface import MessengerInterface


def _application() -> QApplication:
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


def test_logout_button_hover_changes_state_and_scale() -> None:
    application = _application()
    button = LogoutButton("#373636", "#D91414")
    button.show()
    clicks: list[bool] = []
    button.clicked.connect(lambda: clicks.append(True))

    enter = QEnterEvent(QPointF(10, 10), QPointF(10, 10), QPointF(10, 10))
    application.sendEvent(button, enter)
    QTest.qWait(180)

    assert button._hovered is True
    assert button._scale == pytest.approx(1.16)

    QTest.mouseClick(button, Qt.MouseButton.LeftButton)
    assert clicks == [True]

    application.sendEvent(button, QEvent(QEvent.Type.Leave))
    QTest.qWait(180)
    assert button._hovered is False
    assert button._scale == pytest.approx(1.0)
    button.close()


def test_logout_button_stays_in_the_top_right_corner() -> None:
    application = _application()
    interface = MessengerInterface()
    interface.resize(1200, 800)
    interface.show()
    application.processEvents()

    assert interface.logout_button.pos().x() == (
        interface.width() - interface.logout_button.width() - 16
    )
    assert interface.logout_button.pos().y() == 9

    interface.close()
    application.processEvents()


def test_logout_confirmation_is_centered_and_emits_only_after_yes() -> None:
    application = _application()
    interface = MessengerInterface()
    interface.resize(1200, 800)
    interface.show()
    application.processEvents()
    confirmations: list[bool] = []
    interface.logout_requested.connect(lambda: confirmations.append(True))

    QTest.mouseClick(interface.logout_button, Qt.MouseButton.LeftButton)
    application.processEvents()

    overlay = interface.logout_confirmation
    assert overlay.isVisible()
    assert overlay.card.size().width() == 520
    assert overlay.card.size().height() == 180
    assert (
        overlay.card.question_label.text()
        == "A R E  Y O U  S U R E  T O  L O G O U T ?"
    )
    assert overlay.card.geometry().center() == overlay.rect().center()

    QTest.mouseClick(overlay.card.no_button, Qt.MouseButton.LeftButton)
    assert not overlay.isVisible()
    assert confirmations == []

    interface.logout_button.clicked.emit()
    application.processEvents()
    QTest.mouseClick(overlay.card.yes_button, Qt.MouseButton.LeftButton)
    assert not overlay.isVisible()
    assert confirmations == [True]

    interface.close()
    application.processEvents()
