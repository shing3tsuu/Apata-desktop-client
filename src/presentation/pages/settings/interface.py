import flet as ft
import asyncio
from typing import List, Optional
from random import randint
from datetime import datetime, date, time, timedelta

from src.presentation.pages import AppState, Contact, Message

from .manager import SettingsManager

COLOR_ACCENT = "#FFFFFF"
COLOR_TEXT = "#FFFFFF"
COLOR_SUCCESS = "#7FFFD4"
COLOR_WARNING = "#FFFF00"
COLOR_ERROR = "#FF4444"
COLOR_SECONDARY = "#666666"
COLOR_BG_DARK = "#0A0A0A"
COLOR_BG_CARD = "#1A1A1A"
COLOR_BG_HOVER = "#2A2A2A"
FONT_FAMILY = "RobotoSlab"

async def settings_interface(page, change_screen, app_state, container, **kwargs):
    page.title = "APATA - SETTINGS"
    page.bgcolor = COLOR_BG_DARK

    settings_manager = SettingsManager(app_state, container)

    # Get current timezone
    current_timezone_int = await settings_manager.get_timezone()
    timezone_options = settings_manager.get_timezone_options()  # Исправьте название метода
    current_timezone_str = timezone_options.get(current_timezone_int, "+00:00")

    background = ft.Container(
        content=ft.Image(
            src="messenger_background.gif",
            fit=ft.ImageFit.COVER,
            width=page.window.width,
            height=page.window.height,
            expand=True,
        ),
        expand=True,
    )

    # Timezone dropdown
    timezone_dropdown = ft.Dropdown(
        label="Timezone",
        hint_text="Select your timezone",
        options=[
            ft.DropdownOption(text=f"UTC{tz_str}", key=tz_str)
            for tz_int, tz_str in timezone_options.items()
        ],
        value=current_timezone_str,
        border_color=COLOR_ACCENT,
        text_style=ft.TextStyle(color=COLOR_TEXT, font_family=FONT_FAMILY),
        width=200
    )

    # Save button
    save_button = ft.ElevatedButton(
        "SAVE SETTINGS",
        bgcolor=COLOR_SUCCESS,
        color=COLOR_BG_DARK,
        on_click=lambda e: asyncio.create_task(save_settings())
    )

    # Back button
    back_button = ft.IconButton(
        icon=ft.Icons.ARROW_BACK,
        icon_color=COLOR_ACCENT,
        on_click=lambda _: asyncio.create_task(change_screen("messenger"))
    )

    # Main content
    content = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    back_button,
                    ft.Text("SETTINGS", color=COLOR_ACCENT, size=20, font_family=FONT_FAMILY),
                    ft.Container(expand=True),
                ]),
                padding=20
            ),
            ft.Divider(color=ft.Colors.with_opacity(0.2, COLOR_ACCENT)),
            ft.Container(
                content=ft.Column([
                    ft.Text("TIMEZONE SETTINGS", color=COLOR_ACCENT, size=16),
                    ft.Text("Set your local timezone for correct message timestamps", 
                           color=COLOR_SECONDARY, size=12),
                    timezone_dropdown,
                    ft.Container(height=20),
                    save_button
                ]),
                padding=30,
                bgcolor=ft.Colors.with_opacity(0.1, COLOR_ACCENT),
                border_radius=15,
                margin=20
            )
        ]),
        expand=True
    )

    async def save_settings():
        if timezone_dropdown.value:
            success, message = await settings_manager.update_timezone(timezone_dropdown.value)
            
            if success:
                # Show success message
                page.snack_bar = ft.SnackBar(
                    content=ft.Text("Settings saved successfully!", color=COLOR_TEXT),
                    bgcolor=COLOR_SUCCESS
                )
                page.snack_bar.open = True
                page.update()
            else:
                # Show error message
                page.snack_bar = ft.SnackBar(
                    content=ft.Text(f"Error: {message}", color=COLOR_TEXT),
                    bgcolor=COLOR_ERROR
                )
                page.snack_bar.open = True
                page.update()

    # Final layout
    final_layout = ft.Container(
        content=ft.Stack([
            background,
            content
        ]),
        expand=True
    )

    page.clean()
    page.add(final_layout)