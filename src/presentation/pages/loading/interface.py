import flet as ft
import asyncio
from random import randint, uniform
from typing import List

from .manager import LoadingManager

# Style configuration
COLOR_ACCENT = "#FFFFFF"
COLOR_TEXT = "#00FFFF"
COLOR_SUCCESS = "#00FF00"
COLOR_WARNING = "#FFFFFF"
COLOR_ERROR = "#FF4444"
COLOR_SECONDARY = "#FFFFFF"
FONT_FAMILY = "RobotoSlab"


async def loading_interface(page, change_screen, app_state, **kwargs):
    page.title = "APATA - SYSTEM INITIALIZATION"
    page.vertical_alignment = ft.MainAxisAlignment.CENTER
    page.horizontal_alignment = ft.CrossAxisAlignment.CENTER
    page.bgcolor = "#000000"

    loading_manager = LoadingManager(app_state)

    # System initialization steps with real methods
    initialization_steps = [
        {
            "name": "INITIALIZING SECURITY SERVICES",
            "method": loading_manager.setup_services,
            "params": {}
        },
        {
            "name": "SYNCHRONIZING CONTACTS DATABASE",
            "method": loading_manager.synchronize_contacts,
            "params": {}
        },
        {
            "name": "LOADING MESSAGE HISTORY",
            "method": loading_manager.sync_message_history,
            "params": {}
        },
        {
            "name": "ROTATING ENCRYPTION KEYS",
            "method": loading_manager.rotate_keys,
            "params": {}
        }
    ]

    completed_steps: list[str] = []
    current_step = 0

    # UI Elements
    status_container = ft.Column([], spacing=3)
    progress_percentage = ft.Text("0%", color=COLOR_ACCENT, size=18, font_family=FONT_FAMILY, weight=ft.FontWeight.BOLD)

    # Animated connection lines
    connection_lines = ft.Container(
        content=ft.Stack([
            ft.Container(
                width=100,
                height=2,
                bgcolor=ft.Colors.with_opacity(0.4, COLOR_WARNING),
                top=40,
                left=150,
                animate_opacity=ft.Animation(800, "easeInOut")
            )
        ]),
        width=500,
        height=100
    )

    # Main progress bar with glow effect
    progress_bar_background = ft.Container(
        height=8,
        width=400,
        bgcolor=ft.Colors.with_opacity(0.2, COLOR_ACCENT),
        border_radius=4
    )

    progress_bar_fill = ft.Container(
        height=8,
        width=0,
        bgcolor=COLOR_TEXT,
        border_radius=4,
        animate_size=ft.Animation(800, "easeOut"),
        shadow=ft.BoxShadow(
            spread_radius=2,
            blur_radius=8,
            color=ft.Colors.with_opacity(0.6, COLOR_TEXT),
        )
    )

    # Status indicator with pulsating effect
    status_indicator = ft.Container(
        width=12,
        height=12,
        shape=ft.BoxShape.CIRCLE,
        bgcolor=COLOR_WARNING,
        shadow=ft.BoxShadow(
            spread_radius=2,
            blur_radius=10,
            color=ft.Colors.with_opacity(0.8, COLOR_WARNING),
        )
    )

    # Create error message text element
    error_message_text = ft.Text("", color=COLOR_TEXT, size=12)

    # Error display container (hidden by default)
    error_container = ft.Container(
        content=ft.Column([
            ft.Text("SYSTEM ERROR", color=COLOR_ERROR, size=16, weight=ft.FontWeight.BOLD),
            error_message_text,
            ft.Container(height=10),
            ft.ElevatedButton(
                "RETRY INITIALIZATION",
                on_click=lambda _: asyncio.create_task(retry_initialization()),
                color=COLOR_ACCENT,
                bgcolor=COLOR_ERROR
            )
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=20,
        bgcolor=ft.Colors.with_opacity(0.1, COLOR_ERROR),
        border=ft.border.all(1, COLOR_ERROR),
        border_radius=8,
        visible=False
    )

    # Main loading container
    loading_container = ft.Container(
        content=ft.Column([
            ft.Container(height=30),
            # Status header
            ft.Row([
                status_indicator,
                ft.Text("SYSTEM INITIALIZATION ACTIVE",
                        color=COLOR_WARNING, size=14, font_family=FONT_FAMILY),
            ], spacing=10, alignment=ft.MainAxisAlignment.CENTER),
            ft.Container(height=25),
            # Progress section
            ft.Column([
                progress_percentage,
                ft.Container(height=15),
                ft.Stack([
                    progress_bar_background,
                    progress_bar_fill
                ]),
            ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
            ft.Container(height=30),
            # Connection visualization
            connection_lines,
            ft.Container(height=25),
            # Status logs
            ft.Container(
                content=status_container,
                height=120,
                width=450,
                padding=ft.padding.all(10),
                bgcolor=ft.Colors.with_opacity(0.05, COLOR_ACCENT),
                border=ft.border.all(1, ft.Colors.with_opacity(0.1, COLOR_ACCENT)),
                border_radius=5
            ),
            # Error container (initially hidden)
            error_container
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        padding=ft.padding.symmetric(vertical=40, horizontal=25),
        bgcolor="#0A0A0A",
        border=ft.border.all(1.5, ft.Colors.with_opacity(0.3, COLOR_ACCENT)),
        border_radius=8,
        width=550,
        height=550
    )

    # Terminal-style footer
    footer = ft.Container(
        content=ft.Row([
            ft.Text("APATA TERMINAL", color=ft.Colors.with_opacity(0.5, COLOR_ACCENT), size=10),
            ft.Container(width=20),
            ft.Text("SECURE CONNECTION ESTABLISHED", color=COLOR_SUCCESS, size=12),
            ft.Container(width=20),
            ft.Text(f"SESSION: {randint(100000, 999999)}", color=ft.Colors.with_opacity(0.5, COLOR_ACCENT), size=10),
        ], alignment=ft.MainAxisAlignment.CENTER),
        padding=10,
        bgcolor=ft.Colors.with_opacity(0.1, COLOR_ACCENT)
    )

    # Clean and add to page
    page.clean()
    main_column = ft.Column([
        loading_container,
        ft.Container(height=10),
        footer
    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=0)

    page.add(main_column)

    async def animate_connection():
        """
        Animation of connection lines
        :return:
        """
        while True:
            connection_lines.content.controls[0].opacity = 0.3
            page.update()
            await asyncio.sleep(0.8)
            connection_lines.content.controls[0].opacity = 1.0
            page.update()
            await asyncio.sleep(0.8)

    async def animate_status_indicator():
        """
        Status indicator animation
        :return:
        """
        colors = [COLOR_WARNING, COLOR_SUCCESS, COLOR_TEXT]
        color_index = 0
        while True:
            status_indicator.bgcolor = colors[color_index]
            status_indicator.shadow.color = ft.Colors.with_opacity(0.8, colors[color_index])
            color_index = (color_index + 1) % len(colors)
            page.update()
            await asyncio.sleep(1.5)

    async def add_step_status(step: str, status: str = "executing"):
        """
        Adding a step status with animation
        :param step:
        :param status:
        :return:
        """
        await asyncio.sleep(uniform(0.1, 0.3))

        if status == "executing":
            color = COLOR_TEXT
            prefix = "▶"
            status_text = "EXECUTING:"
        elif status == "completed":
            color = COLOR_SUCCESS
            prefix = "✓"
            status_text = "COMPLETED:"
        elif status == "error":
            color = COLOR_ERROR
            prefix = "✗"
            status_text = "FAILED:"
        else:
            color = COLOR_WARNING
            prefix = "▶"
            status_text = "EXECUTING:"

        step_row = ft.Row([
            ft.Text(prefix, color=color, size=10),
            ft.Text(status_text, color=ft.Colors.with_opacity(0.7, COLOR_ACCENT), size=10),
            ft.Text(step, color=color, size=11, font_family=FONT_FAMILY, weight=ft.FontWeight.W_400),
        ], spacing=6)

        if status == "executing":
            step_row.opacity = 0
            status_container.controls.append(step_row)

            # Appearance animation
            for i in range(0, 11):
                step_row.opacity = i / 10
                if i % 2 == 0:
                    page.update()
                await asyncio.sleep(0.02)
        else:
            # Replace the last step
            if status_container.controls:
                status_container.controls[-1] = step_row

        page.update()

    async def show_error(message: str):
        """
        Show error message
        :param message:
        :return:
        """
        error_message_text.value = message
        error_container.visible = True
        status_indicator.bgcolor = COLOR_ERROR
        status_indicator.shadow.color = ft.Colors.with_opacity(0.8, COLOR_ERROR)

        # Update status header
        status_header = ft.Row([
            status_indicator,
            ft.Text("SYSTEM ERROR - INITIALIZATION FAILED",
                    color=COLOR_ERROR, size=14, font_family=FONT_FAMILY),
        ], spacing=10, alignment=ft.MainAxisAlignment.CENTER)

        # Updating the status title
        loading_container.content.controls[1] = status_header
        page.update()

    async def hide_error():
        """
        Hide error message
        :return:
        """
        error_container.visible = False
        page.update()

    async def retry_initialization():
        """
        Retry initialization on error
        :return:
        """
        await hide_error()
        await simulate_loading_process()

    async def simulate_loading_process():
        """
        System boot process
        :return:
        """
        nonlocal current_step

        # Reset state
        current_step = 0
        status_container.controls.clear()
        progress_bar_fill.width = 0
        progress_percentage.value = "0%"
        progress_bar_fill.bgcolor = COLOR_TEXT

        # Restoring normal status
        status_header = ft.Row([
            status_indicator,
            ft.Text("SYSTEM INITIALIZATION ACTIVE",
                    color=COLOR_WARNING, size=14, font_family=FONT_FAMILY),
        ], spacing=10, alignment=ft.MainAxisAlignment.CENTER)
        loading_container.content.controls[1] = status_header

        # Initial progress animation
        for i in range(0, 10, 1):
            progress_percentage.value = f"{i}%"
            progress_bar_fill.width = (i / 100) * 400
            await asyncio.sleep(0.1)
            page.update()

        # Sequential execution of real steps
        for step_index, step_config in enumerate(initialization_steps):
            current_step = step_index
            step_name = step_config["name"]
            step_method = step_config["method"]
            step_params = step_config["params"]

            # Progress update
            progress = min(100, int((current_step / len(initialization_steps)) * 100))
            progress_percentage.value = f"{progress}%"
            progress_bar_fill.width = (progress / 100) * 400

            # Adding a step with the "running" status
            await add_step_status(step_name, "executing")
            page.update()

            try:
                # Executing a method
                success, message = await step_method(**step_params)

                if success:
                    await add_step_status(step_name, "completed")
                else:
                    await add_step_status(step_name, "error")
                    await show_error(f"Failed to execute: {step_name}")
                    raise Exception(message)

            except Exception as e:
                await add_step_status(step_name, "error")
                await show_error(f"Error in {step_name}: {str(e)}")
                return  # Terminate the process on error

            # Delay between steps
            await asyncio.sleep(uniform(0.3, 0.8))

        # Final animation
        await asyncio.sleep(0.5)

        # Smooth filling up to 100%
        final_progress = 100
        progress_percentage.value = f"{final_progress}%"
        progress_bar_fill.width = (final_progress / 100) * 400
        page.update()

        progress_bar_fill.bgcolor = COLOR_SUCCESS
        progress_bar_fill.shadow.color = ft.Colors.with_opacity(0.6, COLOR_SUCCESS)

        # Status update
        status_indicator.bgcolor = COLOR_SUCCESS
        status_header = ft.Row([
            status_indicator,
            ft.Text("SYSTEM READY - ALL MODULES OPERATIONAL",
                    color=COLOR_SUCCESS, size=14, font_family=FONT_FAMILY),
        ], spacing=10, alignment=ft.MainAxisAlignment.CENTER)

        loading_container.content.controls[1] = status_header

        # Final system messages
        final_steps = [
            "ENCRYPTED_SESSION_ACTIVE",
            "CONTACTS_SYNC_COMPLETE",
            "MESSAGE_DECRYPTION_READY",
            "SECURE_CHANNELS_ESTABLISHED",
            "MESSENGER_INTERFACE_LOADED"
        ]

        for step in final_steps:
            await asyncio.sleep(0.4)
            await add_step_status(step, "completed")

        # Final delay and transition
        await asyncio.sleep(1.5)
        await change_screen("messenger")

    # Launching animations
    asyncio.create_task(animate_connection())
    asyncio.create_task(animate_status_indicator())
    asyncio.create_task(simulate_loading_process())