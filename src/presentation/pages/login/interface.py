import flet as ft
from random import randint
import asyncio

from .manager import AuthManager
from src.presentation.pages import AppState

# Style configuration
COLOR_ACCENT = "#FFFFFF"
COLOR_TEXT = "#00FFFF"
COLOR_INPUT_BG = "#282F32"
COLOR_SUCCESS = "#00FF00"
COLOR_ERROR = "#FF4444"
FONT_FAMILY = "RobotoSlab"

async def login_interface(page, change_screen, app_state: AppState, **kwargs):
    page.title = "APATA"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.bgcolor = "#000000"

    # Initializing the authentication manager
    auth_manager = AuthManager(app_state)

    # UI State Elements
    status_text = ft.Text("", color=COLOR_TEXT, size=14, font_family=FONT_FAMILY)
    progress_indicator = ft.Container(
        height=2, width=0, bgcolor=COLOR_ACCENT,
        animate_size=ft.Animation(1000, "easeOut")
    )

    # Loading animation
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

    # Start the cursor animation
    asyncio.create_task(blink_cursor())

    # System Title
    title = ft.Container(
        content=ft.Column([
            ft.Text("APATA ENCRYPTED SYSTEMS VER 0.1.1 BETA", color=COLOR_ACCENT, size=15, font_family=FONT_FAMILY),
            ft.Text(
                f"TEMPORARILY ACCESS POINT VER: {randint(0, 10000)}.{randint(0, 10000)}."
                f"{randint(0, 10000)}.{randint(0, 10000)}",
                color=COLOR_ACCENT, size=12, font_family=FONT_FAMILY, text_align=ft.TextAlign.CENTER
            ),
            ft.Container(content=progress_indicator, margin=ft.margin.only(top=5)),
        ]), margin=ft.margin.only(bottom=30)
    )

    # Input fields
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
        """
        Generic authentication handler
        :param e:
        :return:
        """
        username = username_field.value.strip()
        password = password_field.value.strip()

        if not username or not password:
            await update_status("ERROR: CREDENTIALS REQUIRED", COLOR_ERROR)
            return

        # Block the UI
        await set_ui_loading(True)
        await update_status("INITIATING SECURE HANDSHAKE...", COLOR_TEXT)
        progress_indicator.width = 200
        page.update()

        try:
            # Configure services if necessary
            if not await auth_manager.setup_services():
                raise Exception("Service initialization failed")

            # Perform authentication
            success, message = await auth_manager.authenticate_user(username, password)

            if success:
                await update_status("ACCESS GRANTED - WELCOME TO APATA NETWORK", COLOR_SUCCESS)
                progress_indicator.bgcolor = COLOR_SUCCESS
                progress_indicator.width = 400
                page.update()

                # Delay before transition
                await asyncio.sleep(1.5)
                await change_screen("loading")
            else:
                raise Exception(message)

        except Exception as ex:
            await update_status(f"AUTHENTICATION FAILURE: {str(ex)}", COLOR_ERROR)
            progress_indicator.bgcolor = COLOR_ERROR
            await set_ui_loading(False)

    async def update_status(message: str, color: str):
        """
        Updating the status message
        :param message:
        :param color:
        :return:
        """

        status_text.value = message
        status_text.color = color
        page.update()

    async def set_ui_loading(loading: bool):
        """
        Setting the UI loading state
        :param loading:
        :return:
        """
        login_button.disabled = loading
        username_field.disabled = loading
        password_field.disabled = loading

    # Authentication button
    login_button = ft.ElevatedButton(
        "[ ACCESS GRANT ]",
        on_click=on_auth_click,
        bgcolor=COLOR_ACCENT, color="#000000",
        style=ft.ButtonStyle(
            shape=ft.RoundedRectangleBorder(radius=3),
            padding=ft.padding.symmetric(horizontal=30, vertical=15)
        )
    )

    # Main container
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

    footer = ft.Container(
        content=ft.Row([
            ft.Text("APATA TERMINAL", color=ft.Colors.with_opacity(0.5, COLOR_ACCENT), size=10),
            ft.Container(width=20),
            ft.Text("A SECURE CONNECTION WAS NOT ESTABLISHED", color=COLOR_ERROR, size=12),
            ft.Container(width=20),
            ft.Text(f"SESSION: {randint(100000, 999999)}", color=ft.Colors.with_opacity(0.5, COLOR_ACCENT), size=10),
        ], alignment=ft.MainAxisAlignment.CENTER),
        padding=10,
        bgcolor=ft.Colors.with_opacity(0.1, COLOR_ACCENT)
    )

    # Main layout
    main_layout = ft.Container(
        content=ft.Column([title, login_menu_container, footer],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0),
        padding=20
    )

    # Clean and add to the page
    page.clean()
    page.add(main_layout)
    username_field.focus()