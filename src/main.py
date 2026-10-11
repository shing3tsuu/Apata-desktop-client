import asyncio
import logging
import sys

import qasync
from dishka import Scope, make_async_container
from PyQt6.QtGui import QCloseEvent
from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget

from src.presentation.interactors.login import RealtimeInteractor
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
        self.realtime_interactor.add_listener(
            self.screens["messenger"].refresh_from_state
        )

        async with self.container() as request_container:
            app_state = await request_container.get(AppState)
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
        if self.realtime_interactor is not None:
            await self.realtime_interactor.stop()
        if self.container:
            await self.container.close()

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
