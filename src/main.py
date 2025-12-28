import flet as ft
import asyncio
import logging

from dishka import make_async_container

from presentation.pages.login import login_interface
from presentation.pages.loading import loading_interface
from presentation.pages.messenger import messenger_interface
from presentation.pages.contact import contact_interface
from presentation.pages.settings import settings_interface
from presentation.pages import AppState

from providers import AppProvider

# Dictionary for storing all interfaces
PAGES = {
    "login": login_interface,
    "loading": loading_interface,
    "messenger": messenger_interface,
    "contact": contact_interface,
    "settings": settings_interface,
}

async def main(page: ft.Page):
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
        force=True
    )
    # Initializing the application state
    container = make_async_container(
        AppProvider()
    )
    app_state = AppState()

    page.title = "APATA"
    page.window.width = 960
    page.window.height = 720

    async def change_screen(screen_name, **kwargs):
        page.controls.clear()

        if screen_name in PAGES:
            interface_func = PAGES[screen_name]
            if asyncio.iscoroutinefunction(interface_func):
                await interface_func(page, change_screen, app_state, container, **kwargs)
            else:
                interface_func(page, change_screen, app_state, container, **kwargs)

        page.update()
    try:
        await change_screen("login")
    finally:
        await container.close()


if __name__ == "__main__":
    ft.app(target=main, assets_dir="assets")