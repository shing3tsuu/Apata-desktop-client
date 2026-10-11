"""System-tray lifecycle and background notification controller."""

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from PyQt6.QtGui import QAction, QIcon
from PyQt6.QtWidgets import QApplication, QMainWindow, QMenu, QSystemTrayIcon

from src.presentation.interactors.login import RealtimeInteractor
from src.providers.state import AppState

from .icon import create_apata_icon
from .notifications import MessageNotificationTracker, TrayNotification


class TrayController:
    _NOTIFICATION_TIMEOUT_MS = 5_000

    def __init__(
        self,
        window: QMainWindow,
        app_state: AppState,
        realtime_interactor: RealtimeInteractor,
        logger: logging.Logger | None = None,
    ) -> None:
        self._window = window
        self._app_state = app_state
        self._realtime_interactor = realtime_interactor
        self._logger = logger or logging.getLogger(__name__)
        self._tracker = MessageNotificationTracker(app_state)
        self._background_tasks: set[asyncio.Task[Any]] = set()
        self._presence_lock = asyncio.Lock()
        self._exit_requested = False

        self._available = QSystemTrayIcon.isSystemTrayAvailable()
        self._tray_icon = QSystemTrayIcon(self._tray_icon_image(), window)
        self._tray_icon.setToolTip("APATA")

        self._menu = QMenu(window)
        self._open_action = QAction("OPEN APATA", window)
        self._exit_action = QAction("EXIT", window)
        self._menu.addAction(self._open_action)
        self._menu.addSeparator()
        self._menu.addAction(self._exit_action)
        self._tray_icon.setContextMenu(self._menu)

        self._open_action.triggered.connect(self.restore_window)
        self._exit_action.triggered.connect(self.request_exit)
        self._tray_icon.messageClicked.connect(self.restore_window)
        self._tray_icon.activated.connect(self._handle_activation)

        if self._available:
            self._tray_icon.show()
        else:
            self._logger.warning("System tray is unavailable")

    @property
    def available(self) -> bool:
        return self._available

    @property
    def exit_requested(self) -> bool:
        return self._exit_requested

    def arm_notifications(self) -> None:
        self._tracker.arm_from_state()

    def refresh_from_state(self) -> None:
        notifications = self._tracker.collect_new()
        if self._window.isVisible() and self._window.isActiveWindow():
            return
        for notification in notifications:
            self._show_notification(notification)

    def hide_window(self) -> bool:
        if (
            not self._available
            or self._exit_requested
            or self._app_state.token is None
        ):
            return False
        self._window.hide()
        self._schedule(self._set_presence(False))
        return True

    def restore_window(self) -> None:
        was_hidden = self._window.isHidden()
        self._window.showNormal()
        self._window.raise_()
        self._window.activateWindow()
        if was_hidden and self._app_state.token is not None:
            self._schedule(self._set_presence(True))

    def request_exit(self) -> None:
        if self._exit_requested:
            return
        self._exit_requested = True
        self._schedule(self._exit_application())

    def _handle_activation(
        self,
        reason: QSystemTrayIcon.ActivationReason,
    ) -> None:
        if reason in {
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        }:
            self.restore_window()

    def _show_notification(self, notification: TrayNotification) -> None:
        if not self._available or not QSystemTrayIcon.supportsMessages():
            return
        self._tray_icon.showMessage(
            notification.title,
            notification.body,
            QSystemTrayIcon.MessageIcon.Information,
            self._NOTIFICATION_TIMEOUT_MS,
        )

    async def _set_presence(self, online: bool) -> None:
        async with self._presence_lock:
            await self._realtime_interactor.set_presence(online)

    async def _exit_application(self) -> None:
        await self._set_presence(False)
        application = QApplication.instance()
        if application is not None:
            application.quit()

    def _schedule(self, coroutine: Coroutine[Any, Any, Any]) -> None:
        task = asyncio.create_task(coroutine)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_task_finished)

    def _background_task_finished(self, task: asyncio.Task[Any]) -> None:
        self._background_tasks.discard(task)
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            self._logger.exception("Tray background task failed")

    def _tray_icon_image(self) -> QIcon:
        window_icon = self._window.windowIcon()
        if not window_icon.isNull():
            return window_icon

        icon = create_apata_icon()
        self._window.setWindowIcon(icon)
        return icon
