import asyncio
import logging
import sys

import qasync
from dishka import Scope, make_async_container
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from src.adapters.api.service import AuthHTTPService
from src.presentation.interactors.login import LogoutInteractor, RealtimeInteractor
from src.presentation.pages.login import LoginInterface
from src.presentation.pages.messenger import MessengerInterface
from src.presentation.pages.tray import TrayController, create_apata_icon
from src.providers import StateProvider, AppProvider
from src.providers.state import AppState


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.container = None
        self.current_screen = None
        self.screens = {}
        self.realtime_interactor = None
        self.logout_interactor = None
        self._logout_task: asyncio.Task[None] | None = None
        self.tray_controller = None
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("APATA")
        self.resize(1600, 900)
        self.screen_stack = QStackedWidget()
        self.setCentralWidget(self.screen_stack)
        self.setStyleSheet("""
            QMainWindow { background-color: #F4F1EC; }
            QStackedWidget { background-color: #F4F1EC; }
        """)

    async def initialize(self):
        logger = logging.getLogger(__name__)
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        )
        self.container = make_async_container(
            StateProvider(),
            AppProvider(
                scope=Scope.APP,
                logger=logger,
                symmetric_cipher="AESGCMSIV",
                asymmetric_cipher="X25519",
                signature_cipher="ED-25519",
                password_cipher="ARGON2",
                base_url="http://127.0.0.1:8000",
                verify_ssl=False,
                base_ws_url="ws://127.0.0.1:8000",
            )
        )

        self.screens = {
            "login": LoginInterface(self),
            "messenger": MessengerInterface(self),
        }
        self.realtime_interactor = RealtimeInteractor(self.container, logger)
        self.logout_interactor = LogoutInteractor(self.realtime_interactor, logger)
        self.realtime_interactor.add_listener(
            self.screens["messenger"].refresh_from_state
        )
        self.screens["messenger"].logout_requested.connect(
            self._schedule_logout
        )

        async with self.container() as request_container:
            app_state = await request_container.get(AppState)
            auth_http_service = await request_container.get(AuthHTTPService)
        auth_http_service.set_session_expired_callback(
            self._handle_expired_session
        )
        self.tray_controller = TrayController(
            window=self,
            app_state=app_state,
            realtime_interactor=self.realtime_interactor,
            logger=logger,
        )
        self.realtime_interactor.add_listener(
            self.tray_controller.refresh_from_state
        )
        application = QApplication.instance()
        if isinstance(application, QApplication) and self.tray_controller.available:
            application.setQuitOnLastWindowClosed(False)

        for name, screen in self.screens.items():
            self.screen_stack.addWidget(screen)

        await self.show_screen("login")

    async def show_screen(self, screen_name: str, **kwargs):
        if screen_name not in self.screens:
            logging.error(f"Screen '{screen_name}' not found")
            return
        screen = self.screens[screen_name]
        if hasattr(screen, "prepare_screen"):
            await screen.prepare_screen(**kwargs)
        self.screen_stack.setCurrentWidget(screen)
        self.current_screen = screen_name

    async def cleanup(self):
        logout_task = self._logout_task
        if logout_task is not None and not logout_task.done():
            logout_task.cancel()
            try:
                await logout_task
            except asyncio.CancelledError:
                pass
        if self.realtime_interactor is not None:
            await self.realtime_interactor.stop()
        if self.container:
            await self.container.close()

    async def _handle_expired_session(self) -> None:
        if self.realtime_interactor is not None:
            await self.realtime_interactor.stop()
        if self.tray_controller is not None:
            self.tray_controller.restore_window()
        self._reset_authenticated_ui()
        await self.show_screen("login")

    def _schedule_logout(self) -> None:
        if self._logout_task is not None and not self._logout_task.done():
            return
        self._logout_task = asyncio.create_task(self._logout())
        self._logout_task.add_done_callback(self._logout_finished)

    async def _logout(self) -> None:
        if self.container is None or self.logout_interactor is None:
            return

        _success, message = await self.logout_interactor(self.container)
        if message != "SUCCESS":
            logging.getLogger(__name__).warning(message)

        self._reset_authenticated_ui()
        await self.show_screen("login")

    def _logout_finished(self, task: asyncio.Task[None]) -> None:
        if self._logout_task is task:
            self._logout_task = None
        if task.cancelled():
            return
        try:
            task.result()
        except Exception:
            logging.getLogger(__name__).exception("Logout failed unexpectedly")

    def _reset_authenticated_ui(self) -> None:
        messenger = self.screens.get("messenger")
        if isinstance(messenger, MessengerInterface):
            messenger.reset_session()
        if self.tray_controller is not None:
            self.tray_controller.reset_session()

    def closeEvent(self, event: QCloseEvent) -> None:
        tray_controller = self.tray_controller
        if tray_controller is not None and tray_controller.hide_window():
            event.ignore()
            return

        application = QApplication.instance()
        if isinstance(application, QApplication):
            application.setQuitOnLastWindowClosed(True)
        super().closeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setApplicationName("APATA")
    app.setApplicationDisplayName("APATA")
    app.setOrganizationName("APATA")
    app.setWindowIcon(create_apata_icon())
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    asyncio.ensure_future(window.initialize(), loop=loop)

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        loop.run_until_complete(window.cleanup())
        loop.close()
