import flet as ft
from random import randint
import asyncio

from .auth_manager import AuthManager
from src.presentation.pages import AppState

# Конфигурация стилей
COLOR_ACCENT = "#FFFFFF"
COLOR_TEXT = "#00FFFF"
COLOR_INPUT_BG = "#282F32"
COLOR_SUCCESS = "#00FF00"
COLOR_ERROR = "#FF4444"
FONT_FAMILY = "RobotoSlab"


def login_interface(page, change_screen, app_state: AppState, **kwargs):
    page.title = "APATA"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.bgcolor = "#000000"

    # Инициализация менеджера аутентификации
    auth_manager = AuthManager(app_state)

    # Элементы состояния UI
    status_text = ft.Text("", color=COLOR_TEXT, size=14, font_family=FONT_FAMILY)
    progress_indicator = ft.Container(
        height=2, width=0, bgcolor=COLOR_ACCENT,
        animate_size=ft.Animation(1000, "easeOut")
    )

    # Анимация загрузки
    loading_animation = ft.Row([
        ft.Text(">", color=COLOR_ACCENT, size=16, font_family=FONT_FAMILY),
        ft.Text("_", color=COLOR_ACCENT, size=16, font_family=FONT_FAMILY,
                animate_opacity=ft.Animation(500, "easeInOut"))
    ], spacing=2)

    async def blink_cursor():
        while True:
            loading_animation.controls[1].opacity = 0
            page.update()
            await asyncio.sleep(0.5)
            loading_animation.controls[1].opacity = 1
            page.update()
            await asyncio.sleep(0.5)

    # Запускаем анимацию курсора
    asyncio.create_task(blink_cursor())

    # Заголовок системы
    title = ft.Container(
        content=ft.Column([
            ft.Text("APATA ENCRYPTED SYSTEMS VER 0.1", color=COLOR_ACCENT, size=15, font_family=FONT_FAMILY),
            ft.Text(
                f"TEMPORARILY ACCESS POINT VER: {randint(0, 10000)}.{randint(0, 10000)}."
                f"{randint(0, 10000)}.{randint(0, 10000)}",
                color=COLOR_ACCENT, size=12, font_family=FONT_FAMILY, text_align=ft.TextAlign.CENTER
            ),
            ft.Container(content=progress_indicator, margin=ft.margin.only(top=5)),
        ]), margin=ft.margin.only(bottom=30)
    )

    # Поля ввода
    username_field = ft.TextField(
        label="username", value="",
        text_style=ft.TextStyle(size=18, color=COLOR_TEXT, font_family=FONT_FAMILY),
        label_style=ft.TextStyle(color=COLOR_ACCENT, size=16, font_family=FONT_FAMILY),
        bgcolor=COLOR_INPUT_BG, border=ft.InputBorder.UNDERLINE, border_color=COLOR_ACCENT,
        height=60, cursor_color=COLOR_ACCENT, width=375,
        on_submit=lambda e: on_auth_click(e)
    )

    password_field = ft.TextField(
        label="password", value="", password=True, can_reveal_password=True,
        text_style=ft.TextStyle(size=18, color=COLOR_TEXT, font_family=FONT_FAMILY),
        label_style=ft.TextStyle(color=COLOR_ACCENT, size=16, font_family=FONT_FAMILY),
        bgcolor=COLOR_INPUT_BG, border=ft.InputBorder.UNDERLINE, border_color=COLOR_ACCENT,
        height=60, cursor_color=COLOR_ACCENT, width=375,
        on_submit=lambda e: on_auth_click(e)
    )

    async def on_auth_click(e):
        """Универсальный обработчик аутентификации"""
        username = username_field.value.strip()
        password = password_field.value.strip()

        if not username or not password:
            update_status("ERROR: CREDENTIALS REQUIRED", COLOR_ERROR)
            return

        # Блокируем UI
        set_ui_loading(True)
        update_status("INITIATING SECURE HANDSHAKE...", COLOR_TEXT)
        progress_indicator.width = 200
        page.update()

        try:
            # Настройка сервисов если необходимо
            if not await auth_manager.setup_services():
                raise Exception("Service initialization failed")

            # Выполняем аутентификацию
            success, message = await auth_manager.authenticate_user(username, password)

            if success:
                update_status("ACCESS GRANTED - WELCOME TO APATA NETWORK", COLOR_SUCCESS)
                progress_indicator.bgcolor = COLOR_SUCCESS
                progress_indicator.width = 400
                page.update()

                # Задержка перед переходом
                await asyncio.sleep(1.5)
                change_screen("messenger")
            else:
                raise Exception(message)

        except Exception as ex:
            update_status(f"AUTHENTICATION FAILURE: {str(ex)}", COLOR_ERROR)
            progress_indicator.bgcolor = COLOR_ERROR
            set_ui_loading(False)

    def update_status(message: str, color: str):
        """Обновление статусного сообщения"""
        status_text.value = message
        status_text.color = color
        page.update()

    def set_ui_loading(loading: bool):
        """Установка состояния загрузки UI"""
        login_button.disabled = loading
        username_field.disabled = loading
        password_field.disabled = loading
        progress_indicator.visible = loading
        if not loading:
            progress_indicator.width = 0

    # Кнопка аутентификации
    login_button = ft.ElevatedButton(
        "[ ACCESS GRANT ]",
        on_click=on_auth_click,
        bgcolor=COLOR_ACCENT, color="#000000",
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=3),
            padding=ft.padding.symmetric(horizontal=30, vertical=15)
        )
    )

    # Основной контейнер
    login_menu_container = ft.Container(
        content=ft.Column([
            ft.Text("PLEASE, ENTER YOUR CREDENTIALS", color=COLOR_ACCENT, size=18,
                    font_family=FONT_FAMILY, text_align=ft.TextAlign.CENTER),
            ft.Container(height=20),
            username_field, ft.Container(height=10), password_field,
            ft.Container(height=25), login_button, ft.Container(height=20),
            loading_animation, status_text,
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
        padding=ft.padding.symmetric(vertical=30, horizontal=25),
        bgcolor="#0A0A0A", border=ft.border.all(1.5, COLOR_ACCENT),
        border_radius=ft.border_radius.all(3), width=450,
    )

    # Главный layout
    main_layout = ft.Container(
        content=ft.Column([title, login_menu_container],
                          horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
        padding=20
    )

    # Очищаем и добавляем на страницу
    page.clean()
    page.add(main_layout)
    username_field.focus()