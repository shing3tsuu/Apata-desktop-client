import flet as ft
import asyncio
from typing import List, Optional
from datetime import datetime, timedelta

from src.presentation.pages import AppState, Contact
from .manager import ContactManager

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


async def contact_interface(page, change_screen, app_state, container, **kwargs):
    page.title = "APATA - CONTACTS"
    page.bgcolor = COLOR_BG_DARK

    # Initialize contact manager
    contact_manager = ContactManager(app_state, container)

    # State variables
    search_results = []
    pending_requests = []

    # UI Elements
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

    # Header
    header = ft.Container(
        content=ft.Row([
            ft.IconButton(
                icon=ft.Icons.ARROW_BACK,
                icon_color=COLOR_ACCENT,
                on_click=lambda _: asyncio.create_task(change_screen("messenger"))
            ),
            ft.Text(
                "CONTACTS MANAGEMENT",
                color=COLOR_ACCENT,
                size=16,
                font_family=FONT_FAMILY,
                weight=ft.FontWeight.BOLD
            ),
            ft.Container(expand=True),
            ft.IconButton(
                icon=ft.Icons.PERSON_ADD,
                icon_color=COLOR_ACCENT,
                tooltip="Add new contact",
                on_click=lambda _: show_search_section()
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

    # Search section
    search_field = ft.TextField(
        hint_text="SEARCH USERNAME...",
        hint_style=ft.TextStyle(color=COLOR_SECONDARY, font_family=FONT_FAMILY),
        text_style=ft.TextStyle(color=COLOR_TEXT, font_family=FONT_FAMILY),
        bgcolor=ft.Colors.with_opacity(0.05, COLOR_ACCENT),
        border=ft.InputBorder.NONE,
        border_radius=20,
        expand=True,
        on_submit=lambda e: asyncio.create_task(search_contacts())
    )

    search_button = ft.IconButton(
        icon=ft.Icons.SEARCH,
        icon_color=COLOR_ACCENT,
        on_click=lambda e: asyncio.create_task(search_contacts())
    )

    search_row = ft.Row([
        search_field,
        search_button
    ])

    # Search results
    search_results_column = ft.Column([], scroll=ft.ScrollMode.ADAPTIVE)

    search_results_container = ft.Container(
        content=search_results_column,
        margin=10,
        expand=True
    )

    search_section = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Text("FIND CONTACTS", color=COLOR_SECONDARY, size=12),
                    ft.Container(expand=True),
                ]),
                padding=ft.padding.symmetric(horizontal=15, vertical=10)
            ),
            ft.Divider(color=ft.Colors.with_opacity(0.2, COLOR_ACCENT), height=1),
            ft.Container(
                content=search_row,
                padding=15
            ),
            search_results_container
        ]),
        blur=ft.Blur(3, 3, ft.BlurTileMode.REPEATED),
        border_radius=15,
        margin=10,
        visible=False,
        expand=True
    )

    # Existing contacts
    contacts_column = ft.Column([], scroll=ft.ScrollMode.ADAPTIVE)

    contacts_container = ft.Container(
        content=contacts_column,
        margin=10,
        expand=True
    )

    contacts_section = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Text("MY CONTACTS", color=COLOR_SECONDARY, size=12),
                    ft.Container(expand=True),
                    ft.Text(f"{len(app_state.contacts_cache)} TOTAL", color=COLOR_SUCCESS, size=10)
                ]),
                padding=ft.padding.symmetric(horizontal=15, vertical=10)
            ),
            ft.Divider(color=ft.Colors.with_opacity(0.2, COLOR_ACCENT), height=1),
            contacts_container  # Заменен contacts_column на contacts_container
        ]),
        blur=ft.Blur(3, 3, ft.BlurTileMode.REPEATED),
        border_radius=15,
        margin=10,
        expand=True
    )

    # Pending requests
    pending_column = ft.Column([], scroll=ft.ScrollMode.ADAPTIVE)

    pending_container = ft.Container(
        content=pending_column,
        margin=10,
        expand=True  # Добавлено для растягивания
    )

    pending_section = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.Text("PENDING REQUESTS", color=COLOR_SECONDARY, size=12),
                    ft.Container(expand=True),
                    ft.Icon(ft.Icons.PENDING, size=16, color=COLOR_WARNING)
                ]),
                padding=ft.padding.symmetric(horizontal=15, vertical=10)
            ),
            ft.Divider(color=ft.Colors.with_opacity(0.2, COLOR_ACCENT), height=1),
            pending_container
        ]),
        blur=ft.Blur(3, 3, ft.BlurTileMode.REPEATED),
        border_radius=15,
        margin=10,
        visible=False,
        expand=True
    )

    # Main content area with tabs
    content_area = ft.Container(
        content=ft.Column([
            ft.Container(
                content=ft.Row([
                    ft.TextButton(
                        "MY CONTACTS",
                        style=ft.ButtonStyle(
                            color=COLOR_ACCENT,
                            bgcolor=COLOR_BG_CARD if len(app_state.contacts_cache) > 0 else ft.Colors.TRANSPARENT
                        ),
                        on_click=lambda e: show_contacts_section()
                    ),
                    ft.TextButton(
                        "FIND CONTACTS",
                        style=ft.ButtonStyle(color=COLOR_ACCENT),
                        on_click=lambda e: show_search_section()
                    ),
                    ft.TextButton(
                        "PENDING",
                        style=ft.ButtonStyle(color=COLOR_ACCENT),
                        on_click=lambda e: show_pending_section()
                    ),
                ]),
                padding=10
            ),
            ft.Divider(color=ft.Colors.with_opacity(0.2, COLOR_ACCENT), height=1),
            ft.Container(
                content=ft.Stack([
                    contacts_section,
                    search_section,
                    pending_section
                ]),
                expand=True
            )
        ]),
        expand=True
    )

    # Footer
    footer = ft.Container(
        content=ft.Row([
            ft.Text("APATA CONTACTS TERMINAL", color=ft.Colors.with_opacity(0.5, COLOR_ACCENT), size=10),
            ft.Container(width=20),
            ft.Text("SECURE CONTACT MANAGEMENT", color=COLOR_SUCCESS, size=12),
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
                        content_area,
                        footer
                    ], expand=True),
                    expand=True
                )
            ],
            expand=True
        ),
        expand=True
    )

    # Contact card creation
    def create_contact_card(contact, show_actions=True, is_pending=False):
        status_color = COLOR_SECONDARY
        status_text = "offline"

        if hasattr(contact, 'status') and contact.status == "pending":
            status_color = COLOR_WARNING
            status_text = "pending"
        elif hasattr(contact, 'status') and contact.status == "rejected":
            status_color = COLOR_ERROR
            status_text = "rejected"
        elif contact.last_seen:
            try:
                if isinstance(contact.last_seen, str):
                    last_seen_dt = parse_datetime(contact.last_seen)
                else:
                    last_seen_dt = contact.last_seen

                if last_seen_dt:
                    time_diff = datetime.utcnow() - last_seen_dt
                    if time_diff <= timedelta(minutes=5):
                        status_color = COLOR_SUCCESS
                        status_text = "online"
                    else:
                        status_color = COLOR_SECONDARY
                        status_text = f"last seen {format_last_seen(last_seen_dt)}"
                else:
                    status_color = COLOR_SECONDARY
                    status_text = "offline"

            except Exception as e:
                print(f"Error parsing last_seen: {e}")
                status_color = COLOR_SECONDARY
                status_text = "offline"
        else:
            status_color = COLOR_SECONDARY
            status_text = "offline"

        card_content = [
            ft.Row([
                ft.Container(
                    width=8,
                    height=8,
                    shape=ft.BoxShape.CIRCLE,
                    bgcolor=status_color
                ),
                ft.Column([
                    ft.Text(contact.username, color=COLOR_TEXT, size=14, font_family=FONT_FAMILY),
                    ft.Text(status_text, color=COLOR_SECONDARY, size=10)
                ], spacing=2, expand=True),
                ft.Icon(ft.Icons.LOCK, size=12, color=COLOR_SUCCESS)
            ])
        ]

        # Add action buttons if needed
        if show_actions:
            if is_pending:
                # For pending requests - accept/reject buttons
                action_buttons = ft.Row([
                    ft.IconButton(
                        icon=ft.Icons.CHECK,
                        icon_color=COLOR_SUCCESS,
                        icon_size=20,
                        tooltip="Accept request",
                        on_click=lambda e, cid=contact.server_user_id: asyncio.create_task(accept_request(cid))
                    ),
                    ft.IconButton(
                        icon=ft.Icons.CLOSE,
                        icon_color=COLOR_ERROR,
                        icon_size=20,
                        tooltip="Reject request",
                        on_click=lambda e, cid=contact.server_user_id: asyncio.create_task(reject_request(cid))
                    )
                ])
            else:
                # For search results - add contact button
                action_buttons = ft.Row([
                    ft.IconButton(
                        icon=ft.Icons.ADD,
                        icon_color=COLOR_SUCCESS,
                        icon_size=20,
                        tooltip="Send contact request",
                        on_click=lambda e, cid=contact.server_user_id: asyncio.create_task(send_contact_request(cid))
                    )
                ])

            card_content.append(action_buttons)

        return ft.Container(
            content=ft.Column(card_content),
            padding=15,
            blur=ft.Blur(10, 10, ft.BlurTileMode.REPEATED),
            border=ft.border.all(1.5, ft.Colors.with_opacity(0.3, COLOR_ACCENT)),
            on_click=lambda e, cid=contact.server_user_id: select_contact(cid) if not show_actions else None,
            border_radius=15,
            data=contact.server_user_id
        )

    def parse_datetime(datetime_str):
        from datetime import datetime
        formats = [
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f%z",
            "%Y-%m-%dT%H:%M:%S%z"
        ]

        for fmt in formats:
            try:
                return datetime.strptime(datetime_str, fmt)
            except ValueError:
                continue

        return None

    def format_last_seen(last_seen):
        """Форматирует datetime для отображения"""
        if not last_seen or not isinstance(last_seen, datetime):
            return "unknown"

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

    # Section visibility management
    def show_contacts_section():
        contacts_section.visible = True
        search_section.visible = False
        pending_section.visible = False
        page.update()

    def show_search_section():
        contacts_section.visible = False
        search_section.visible = True
        pending_section.visible = False
        page.update()

    def show_pending_section():
        contacts_section.visible = False
        search_section.visible = False
        pending_section.visible = True
        asyncio.create_task(load_pending_requests())
        page.update()

    # Event handlers
    async def search_contacts():
        if not search_field.value.strip():
            return

        search_results_column.controls.clear()
        search_results_column.controls.append(
            ft.Container(
                content=ft.ProgressRing(color=COLOR_ACCENT),
                alignment=ft.Alignment(0, 0),
                padding=20
            )
        )
        page.update()

        try:
            results = await contact_manager.find_contacts(search_field.value.strip())
            search_results_column.controls.clear()

            if not results:
                search_results_column.controls.append(
                    ft.Container(
                        content=ft.Text("No contacts found", color=COLOR_SECONDARY),
                        alignment=ft.Alignment(0, 0),
                        padding=20
                    )
                )
            else:
                for contact in results:
                    contact_card = create_contact_card(contact, show_actions=True)
                    search_results_column.controls.append(contact_card)

            page.update()

        except Exception as e:
            search_results_column.controls.clear()
            search_results_column.controls.append(
                ft.Container(
                    content=ft.Text(f"Search error: {str(e)}", color=COLOR_ERROR),
                    alignment=ft.Alignment(0, 0),
                    padding=20
                )
            )
            page.update()

    async def send_contact_request(contact_id):
        try:
            success = await contact_manager.send_request(contact_id)
            if success:
                # Update UI to show success
                for card in search_results_column.controls:
                    if card.data == contact_id:
                        card.content.controls[1] = ft.Text("Request sent", color=COLOR_SUCCESS, size=12)
                        break
                page.update()
            else:
                # Show error
                show_snackbar("Failed to send contact request")
        except Exception as e:
            show_snackbar(f"Error: {str(e)}")

    async def accept_request(contact_id):
        # TODO: Implement accept logic in manager
        show_snackbar(f"Contact request {contact_id} accepted")
        await load_pending_requests()

    async def reject_request(contact_id):
        # TODO: Implement reject logic in manager
        show_snackbar(f"Contact request {contact_id} rejected")
        await load_pending_requests()

    async def load_pending_requests():
        # TODO: Load actual pending requests from manager
        # This is a placeholder - implement based on your data structure
        pending_column.controls.clear()

        # Example placeholder - replace with actual data
        if hasattr(app_state, 'pending_requests_cache'):
            for request in app_state.pending_requests_cache:
                contact_card = create_contact_card(request, show_actions=True, is_pending=True)
                pending_column.controls.append(contact_card)

        if not pending_column.controls:
            pending_column.controls.append(
                ft.Container(
                    content=ft.Text("No pending requests", color=COLOR_SECONDARY),
                    alignment=ft.Alignment(0, 0),
                    padding=20
                )
            )

        page.update()

    async def load_existing_contacts():
        contacts_column.controls.clear()

        for contact in app_state.contacts_cache:
            contact_card = create_contact_card(contact, show_actions=False)
            contacts_column.controls.append(contact_card)

        if not contacts_column.controls:
            contacts_column.controls.append(
                ft.Container(
                    content=ft.Column([
                        ft.Icon(ft.Icons.PEOPLE_OUTLINE, size=48, color=COLOR_SECONDARY),
                        ft.Text("No contacts yet", color=COLOR_SECONDARY, size=16)
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER),
                    alignment=ft.Alignment(0, 0),
                    padding=40
                )
            )

        page.update()

    def select_contact(contact_id):
        # Navigate to messenger with selected contact
        change_screen("messenger", selected_contact=contact_id)

    def show_snackbar(message, color=COLOR_ACCENT):
        page.snack_bar = ft.SnackBar(
            content=ft.Text(message, color=COLOR_TEXT),
            bgcolor=color,
            behavior=ft.SnackBarBehavior.FLOATING
        )
        page.snack_bar.open = True
        page.update()

    async def logout():
        # TODO: Implement proper logout logic
        await change_screen("login")

    async def initialize_manager():
        if not await contact_manager.setup_services():
            raise Exception("Contact service initialization failed")
        await load_existing_contacts()

    # Initialize the interface
    page.clean()
    page.add(final_layout)

    # Load initial data
    await initialize_manager()
    show_contacts_section()  # Show contacts by default