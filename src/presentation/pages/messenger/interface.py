import flet as ft
import asyncio
from typing import List, Optional
from random import randint
from datetime import datetime, date, time, timedelta

from src.presentation.pages import AppState, Contact, Message

from .manager import MessengerManager

# Style configuration
COLOR_ACCENT = "#FFFFFF"
COLOR_TEXT = "#FFFFFF"
COLOR_SUCCESS = "#00FF00"
COLOR_WARNING = "#FFFF00"
COLOR_ERROR = "#FF4444"
COLOR_SECONDARY = "#666666"
COLOR_BG_DARK = "#0A0A0A"
COLOR_BG_CARD = "#1A1A1A"
COLOR_BG_HOVER = "#2A2A2A"
FONT_FAMILY = "RobotoSlab"


async def messenger_interface(page, change_screen, app_state, **kwargs):
    page.title = "APATA - SECURE MESSENGER"
    page.bgcolor = COLOR_BG_DARK

    # Initialize stub managers
    messenger_manager = MessengerManager(app_state)

    # State variables
    selected_contact = None
    contacts = []

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

    # UI Elements
    # Header
    header = ft.Container(
        content=ft.Row([
            ft.Text(
                "APATA SECURE MESSENGER",
                color=COLOR_ACCENT,
                size=16,
                font_family=FONT_FAMILY,
                weight=ft.FontWeight.BOLD
            ),
            ft.Container(expand=True),
            ft.IconButton(
                icon=ft.Icons.REFRESH,
                icon_color=COLOR_ACCENT,
                on_click=lambda _: load_contacts()
            ),
            ft.IconButton(
                icon=ft.Icons.SETTINGS,
                icon_color=COLOR_ACCENT,
                on_click=lambda _: print("Settings clicked")
            ),
            ft.IconButton(
                icon=ft.Icons.LOGOUT,
                icon_color=COLOR_ERROR,
                on_click=lambda _: asyncio.create_task(logout())
            ),
        ]),
        padding=15,
        bgcolor=ft.Colors.with_opacity(0.1, COLOR_ACCENT),
        border_radius=0
    )

    # Contacts list
    contacts_column = ft.Column([], scroll=ft.ScrollMode.ADAPTIVE)

    contacts_container = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Text("CONTACTS", color=COLOR_SECONDARY, size=12),
                    ft.Container(expand=True),
                    ft.Text(f"{len(contacts)} ONLINE", color=COLOR_SUCCESS, size=10)
                ]),
                padding=ft.padding.symmetric(horizontal=15, vertical=10)
            ),
            ft.Divider(color=ft.Colors.with_opacity(0.2, COLOR_ACCENT), height=1),
            contacts_column
        ]),
        blur=ft.Blur(3, 3, ft.BlurTileMode.REPEATED),
        width=300,
        border_radius=0
    )

    # Chat area
    chat_messages_column = ft.Column(
        [],
        scroll=ft.ScrollMode.ADAPTIVE,
        auto_scroll=True
    )

    chat_messages_container = ft.Container(
        content=chat_messages_column,
        expand=True,
        padding=20
    )

    # Message input
    message_input = ft.TextField(
        hint_text="TYPE ENCRYPTED MESSAGE...",
        hint_style=ft.TextStyle(color=COLOR_SECONDARY, font_family=FONT_FAMILY),
        text_style=ft.TextStyle(color=COLOR_TEXT, font_family=FONT_FAMILY),
        bgcolor=ft.Colors.with_opacity(0.05, COLOR_ACCENT),
        border=ft.InputBorder.NONE,
        border_radius=20,
        multiline=True,
        min_lines=1,
        max_lines=3,
        expand=True,
        on_submit=lambda e: page.run_task(send_message_handler)
    )

    send_button = ft.IconButton(
        icon=ft.Icons.SEND,
        icon_color=COLOR_ACCENT,
        on_click=lambda e: page.run_task(send_message_handler)
    )

    input_row = ft.Container(
        content=ft.Row([
            message_input,
            send_button
        ]),
        padding=15,
        bgcolor=COLOR_BG_CARD
    )

    # Empty state for chat
    empty_chat = ft.Container(
        content=ft.Column([
            ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE, size=64, color=COLOR_SECONDARY),
            ft.Text("SELECT A CONTACT TO START CHATTING",
                    color=COLOR_SECONDARY,
                    size=16,
                    font_family=FONT_FAMILY)
        ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
        expand=True,
        alignment=ft.Alignment(0, 0)
    )

    # Main chat container
    chat_container = ft.Column([
        ft.Container(
            content=ft.Row([
                ft.Text("NO CONTACT SELECTED", color=COLOR_SECONDARY, size=14),
                ft.Container(expand=True),
                ft.Text("ENCRYPTION: ECDH-AES256", color=COLOR_SUCCESS, size=10)
            ]),
            padding=15,
            blur=ft.Blur(2, 2, ft.BlurTileMode.REPEATED),
        ),
        ft.Divider(color=ft.Colors.with_opacity(0.2, COLOR_ACCENT), height=1),
        empty_chat
    ], expand=True)

    # Main layout
    main_content = ft.Row([
        # Contacts sidebar
        contacts_container,
        # Vertical divider
        ft.Container(width=1, bgcolor=ft.Colors.with_opacity(0.1, COLOR_ACCENT)),
        # Chat area
        ft.Column([
            chat_container,
            input_row
        ], expand=True)
    ], expand=True)

    # Footer
    footer = ft.Container(
        content=ft.Row([
            ft.Text("APATA TERMINAL", color=ft.Colors.with_opacity(0.5, COLOR_ACCENT), size=10),
            ft.Container(width=20),
            ft.Text("END-TO-END ENCRYPTION ACTIVE", color=COLOR_SUCCESS, size=12),
            ft.Container(width=20),
            ft.Text(f"SESSION: {randint(100000, 999999)}", color=ft.Colors.with_opacity(0.5, COLOR_ACCENT), size=10),
            ft.Container(expand=True),
            ft.Text(f"USER: {app_state.username}", color=COLOR_ACCENT, size=10)
        ]),
        padding=10,
        bgcolor=ft.Colors.with_opacity(0.1, COLOR_ACCENT)
    )

    # Final layout
    final_layout = ft.Container(
        content=ft.Stack(
            [
                background,
                ft.Container(
                    content=ft.Column([
                        header,
                        main_content,
                        footer
                    ], expand=True),
                    expand=True
                )
            ],
            expand=True
        ),
        expand=True
    )

    # Event handlers
    async def load_contacts():
        nonlocal contacts
        if not await messenger_manager.setup_services():
            raise Exception("Service initialization failed")
        contacts = await messenger_manager.get_contacts()
        contacts_column.controls.clear()

        for contact in contacts:
            contact_card = create_contact_card(contact)
            contacts_column.controls.append(contact_card)

        page.update()

    def create_contact_card(contact):
        now = datetime.utcnow()
        if contact.last_seen:
            time_diff = now - contact.last_seen
            if time_diff < timedelta(minutes=5):
                status_color = COLOR_SUCCESS
            else:
                status_color = COLOR_SECONDARY
        else:
            status_color = COLOR_SECONDARY

        if hasattr(contact, 'status') and contact.status == "rejected":
            status_color = COLOR_WARNING

        return ft.Container(
            content=ft.Row([
                ft.Container(
                    width=8,
                    height=8,
                    shape=ft.BoxShape.CIRCLE,
                    bgcolor=status_color
                ),
                ft.Column([
                    ft.Text(contact.username, color=COLOR_TEXT, size=14, font_family=FONT_FAMILY),
                    ft.Text(
                        format_last_seen(contact.last_seen),
                        color=COLOR_SECONDARY,
                        size=10
                    ) if contact.last_seen else ft.Text("never", color=COLOR_SECONDARY, size=10)
                ], spacing=2, expand=True),
                ft.Icon(ft.Icons.LOCK, size=12, color=COLOR_SUCCESS)
            ]),
            padding=15,
            blur=ft.Blur(10, 10, ft.BlurTileMode.REPEATED),
            border=ft.border.all(1.5, ft.Colors.with_opacity(0.3, COLOR_ACCENT)),
            on_click=lambda e, cid=contact.server_user_id: page.run_task(select_contact, cid),
            border_radius=15,
            data=contact.server_user_id
        )

    def format_last_seen(last_seen):
        now = datetime.utcnow()
        diff = now - last_seen

        if diff < timedelta(minutes=1):
            return "just now"
        elif diff < timedelta(hours=1):
            minutes = int(diff.total_seconds() / 60)
            return f"{minutes} min ago"
        elif diff < timedelta(days=1):
            hours = int(diff.total_seconds() / 3600)
            return f"{hours} hour ago" if hours == 1 else f"{hours} hours ago"
        else:
            days = diff.days
            return f"{days} day ago" if days == 1 else f"{days} days ago"

    async def select_contact(contact_id):
        nonlocal selected_contact
        selected_contact = contact_id

        # Update UI to show selected state
        for control in contacts_column.controls:
            if control.data == contact_id:
                control.bgcolor = COLOR_BG_HOVER
            else:
                control.bgcolor = COLOR_BG_CARD

        # Load messages for selected contact
        await load_messages(contact_id)

        # Update chat header
        contact = next((c for c in contacts if c.server_user_id == contact_id), None)
        if contact:
            chat_container.controls[0] = ft.Container(
                content=ft.Row([
                    ft.Text(contact.username, color=COLOR_ACCENT, size=16, font_family=FONT_FAMILY),
                    ft.Container(expand=True),
                    ft.Text("ENCRYPTION: ECDH-AES256", color=COLOR_SUCCESS, size=10)
                ]),
                padding=15,
                bgcolor=ft.Colors.with_opacity(0.05, COLOR_ACCENT)
            )

            # Replace empty chat with messages
            chat_container.controls[2] = chat_messages_container

        page.update()

    async def load_messages(contact_id):
        try:
            messages_list = await messenger_manager.get_messages(contact_id)
            chat_messages_column.controls.clear()

            for msg in messages_list:
                message_bubble = create_message_bubble(msg)
                chat_messages_column.controls.append(message_bubble)

            # Auto scroll to bottom
            await asyncio.sleep(0.1)
            chat_messages_column.scroll_to(offset=-1, duration=300)

        except Exception as e:
            print(f"Error loading messages: {e}")

    def create_message_bubble(message):
        if hasattr(message, 'is_outgoing'):
            message_data = {
                "id": message.server_message_id or id(message),
                "text": message.content.decode() if isinstance(message.content, bytes) else message.content,
                "is_outgoing": message.is_outgoing,
                "timestamp": format_timestamp(message.timestamp)
            }
        else:
            message_data = message

        alignment = ft.MainAxisAlignment.END if message_data["is_outgoing"] else ft.MainAxisAlignment.START
        bg_color = ft.Colors.with_opacity(0.2, COLOR_SUCCESS) if message_data["is_outgoing"] else COLOR_BG_CARD

        return ft.Container(
            content=ft.Row([
                ft.Column([
                    ft.Container(
                        content=ft.Text(
                            message_data["text"],
                            color=COLOR_TEXT,
                            size=14,
                            font_family=FONT_FAMILY
                        ),
                        padding=12,
                        bgcolor=bg_color,
                        border_radius=15
                    ),
                    ft.Text(
                        message_data["timestamp"],
                        color=COLOR_SECONDARY,
                        size=10
                    )
                ], spacing=5)
            ], alignment=alignment),
            padding=ft.padding.symmetric(vertical=5, horizontal=10)
        )

    async def send_message_handler():
        if not selected_contact or not message_input.value.strip():
            return

        text = message_input.value.strip()
        message_input.value = ""

        # Get the number of messages for the selected contact
        # Filter messages by contact_id
        contact_messages = [msg for msg in messages if msg.contact_id == selected_contact]
        temp_id = len(contact_messages) + 1

        new_message = Message(
            server_message_id=None,  # временный ID
            contact_id=selected_contact,
            content=text.encode() if isinstance(text, str) else text,
            timestamp=datetime.utcnow(),
            type="text",
            is_outgoing=True,
            is_delivered=False
        )

        # Create and add a bubble to the UI
        message_bubble = create_message_bubble({
            "id": temp_id,
            "text": text,
            "is_outgoing": True,
            "timestamp": "just now"
        })

        chat_messages_column.controls.append(message_bubble)
        page.update()

        # Scroll to the bottom
        await asyncio.sleep(0.1)
        chat_messages_column.scroll_to(offset=-1, duration=300)

        # Send a message via the manager
        try:
            success = await messenger_manager.send_message(selected_contact, text)
            if success:
                new_message.is_delivered = True
                # TODO: update server_message_id if manager returns it
            else:
                # TODO: показать сообщение об ошибке
                print("Failed to send message")
        except Exception as e:
            print(f"Error sending message: {e}")

    async def logout():
        # TODO: Implement proper logout logic
        await change_screen("login")

    # Initialize the interface
    page.clean()
    page.add(final_layout)

    # Load initial data
    await load_contacts()