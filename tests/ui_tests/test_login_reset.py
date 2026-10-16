import os
from types import SimpleNamespace
from unittest.mock import MagicMock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from src.presentation.pages.login.interface import LoginInterface


def _application() -> QApplication:
    application = QApplication.instance() or QApplication([])
    application.setQuitOnLastWindowClosed(False)
    return application


@pytest.mark.asyncio
async def test_prepare_screen_clears_previous_login_ui_state() -> None:
    application = _application()
    interface = LoginInterface(SimpleNamespace(container=object()))
    interface._start_local_usernames_loading = MagicMock()
    interface.mode = "login"
    interface.username = "previous-user"
    interface.password = "previous-password"
    interface.username_field.setText("previous-user")
    interface.password_field.setText("previous-password")
    interface.logs_container.add_log("PREVIOUS LOGIN")
    interface.choose_button.set_active_side("right", animated=False)
    interface.button.current_bg_color = interface.button.color_inactive
    interface.account_toggle_button.set_expanded(True, animated=False)
    interface.account_toggle_button.show()
    interface.accounts_panel.show()
    interface.local_usernames = ["previous-user"]
    interface.local_usernames_ready = True

    await interface.prepare_screen()
    application.processEvents()

    assert interface.mode == "register"
    assert interface.username == ""
    assert interface.password == ""
    assert interface.username_field.text() == ""
    assert interface.password_field.text() == ""
    assert interface.logs_container.logs == []
    assert interface.logs_container.blocks == []
    assert interface.choose_button.active_side == "left"
    assert interface.choose_button.left_color == interface.choose_button.color_primary
    assert interface.button.current_bg_color == interface.button.color_primary
    assert interface.account_toggle_button.expanded is False
    assert interface.account_toggle_button.isHidden()
    assert interface.accounts_panel.isHidden()
    assert interface.local_usernames == []
    assert interface.local_usernames_ready is False
    interface._start_local_usernames_loading.assert_called_once_with()

    interface.close()
    application.processEvents()
