import sys
import asyncio
import logging

from PyQt6.QtWidgets import QApplication, QMainWindow, QStackedWidget
from PyQt6.QtCore import Qt
import qasync

from dishka import make_async_container

from src.presentation.pages.login import LoginInterface
from src.presentation.pages.loading import LoadingInterface
from src.presentation.pages.messenger import MessengerInterface
from src.presentation.pages.contact import ContactInterface
from src.presentation.pages.settings import SettingsInterface
from src.presentation.pages import AppState

from src.providers import AppProvider

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.container = None
        self.app_state = None
        self.current_screen = None
        self.setup_ui()

    def setup_ui(self):
        self.setWindowTitle("APATA")
        self.resize(1600, 900)

        self.screen_stack = QStackedWidget()
        self.setCentralWidget(self.screen_stack)

        self.setStyleSheet("""
            QMainWindow {
                background-color: #000000;
            }
        """)

    async def initialize(self):
        try:
            self.container = make_async_container(AppProvider())
            self.app_state = AppState()

            self.screens = {
                "login": LoginInterface(self),
                "loading": LoadingInterface(self),
                "messenger": MessengerInterface(self),
                "contact": ContactInterface(self),
                "settings": SettingsInterface(self),
            }

            for name, screen in self.screens.items():
                self.screen_stack.addWidget(screen)

            await self.show_screen("login")

        except Exception as e:
            logging.error(f"Initialization error: {e}")
            raise

    async def show_screen(self, screen_name: str, **kwargs):
        if screen_name not in self.screens:
            logging.error(f"Screen '{screen_name}' not found")
            return

        screen = self.screens[screen_name]

        if hasattr(screen, 'prepare_screen'):
            await screen.prepare_screen(**kwargs)

        self.screen_stack.setCurrentWidget(screen)
        self.current_screen = screen_name

    async def cleanup(self):
        if self.container:
            await self.container.close()


async def main():
    app = QApplication(sys.argv)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    await window.initialize()

    try:
        loop.run_forever()
    except KeyboardInterrupt:
        pass
    finally:
        await window.cleanup()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        force=True
    )

    try:
        asyncio.run(main())
    except Exception as e:
        logging.error(f"Application error: {e}")