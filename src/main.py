import flet as ft
from presentation.pages.login.interface import login_interface
# from presentation.pages.messenger.interface import messenger_interface
# from presentation.pages.contacts.interface import contacts_interface
from presentation.pages import AppState

# Словарь для хранения всех интерфейсов
PAGES = {
    "login": login_interface,
    # "messenger": messenger_interface,
    # "contacts": contacts_interface,
}


def main(page: ft.Page):
    # Инициализация состояния приложения
    app_state = AppState()

    page.title = "APATA"
    page.window.width = 960
    page.window.height = 720
    page.bgcolor = ft.Colors.BLACK

    # Функция для смены экрана
    def change_screen(screen_name, **kwargs):
        # Очищаем страницу
        page.controls.clear()

        # Получаем функцию интерфейса и вызываем её
        if screen_name in PAGES:
            interface_func = PAGES[screen_name]
            interface_func(page, change_screen, app_state, **kwargs)

        page.update()

    # Запускаем начальный экран
    change_screen("login")


if __name__ == "__main__":
    ft.app(target=main)
