import os
from datetime import datetime
from uuid import UUID, uuid4

from PyQt6.QtCore import QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.adapters.database.structures import ContactStatusEnum, MessageContentTypeEnum
from src.providers.cache import ChatCache, ContactCache

from .buttons import AddChatParticipantButton, ConversationTabButton
from .chat_members import ChatMembersPanel
from .contacts import ContactList, Conversation, conversation_name
from .creation import ChatCreationPanel
from .fields import MessageField
from .messages import MessageBubble, MessagesView
from .search import ConversationSearchPanel
from .theme import (
    COLOR_CONTACT_BORDER,
    COLOR_CONTACT_SECTION_ACTIVE,
    COLOR_CONTACT_SECTION_BACKGROUND,
    COLOR_CONTACT_SECTION_TEXT,
    COLOR_CONVERSATION_TITLE,
    COLOR_PANEL_BACKGROUND,
    COLOR_SCROLLBAR_HANDLE,
    COLOR_SCROLLBAR_TRACK,
    COLOR_TEXT,
)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
MONTH_NAMES = (
    "JANUARY",
    "FEBRUARY",
    "MARCH",
    "APRIL",
    "MAY",
    "JUNE",
    "JULY",
    "AUGUST",
    "SEPTEMBER",
    "OCTOBER",
    "NOVEMBER",
    "DECEMBER",
)


def format_last_seen(value: datetime, now: datetime | None = None) -> str:
    if value.tzinfo is not None:
        value = value.astimezone()
        if now is None:
            current = datetime.now().astimezone()
        elif now.tzinfo is None:
            current = now.replace(tzinfo=value.tzinfo)
        else:
            current = now.astimezone(value.tzinfo)
    else:
        current = now.replace(tzinfo=None) if now is not None else datetime.now()

    days_ago = (current.date() - value.date()).days
    time_text = value.strftime("%H:%M")
    if days_ago <= 0:
        return f"TODAY AT {time_text}"
    if days_ago == 1:
        return f"YESTERDAY AT {time_text}"
    if days_ago == 2:
        return f"THE DAY BEFORE YESTERDAY AT {time_text}"

    date_text = f"{value.day} {MONTH_NAMES[value.month - 1]}"
    if value.year != current.year:
        date_text = f"{date_text} {value.year}"
    return f"{date_text} AT {time_text}"


class PanelDivider(QWidget):
    def __init__(self, color: str, parent=None):
        super().__init__(parent)
        self.color = color
        self.setFixedWidth(1)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event):
        painter = QPainter(self)
        pen = QPen(QColor(self.color))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(0, 0, 0, self.height())


class ContactsPanel(QWidget):
    conversation_selected = pyqtSignal(object)
    contact_action_requested = pyqtSignal(str, object)
    chat_members_requested = pyqtSignal(object, object)
    chat_members_panel_close_requested = pyqtSignal()
    search_requested = pyqtSignal(str, str, bool)
    search_cleared = pyqtSignal()
    create_chat_requested = pyqtSignal(str)

    def __init__(
        self,
        contacts_title: str,
        chats_title: str,
        color_primary: str,
        color_third: str,
        color_divider: str,
        parent=None,
    ):
        super().__init__(parent)
        self.contacts_title = contacts_title
        self.chats_title = chats_title
        self.color_primary = color_primary
        self.color_third = color_third
        self.color_divider = color_divider
        self._contacts: list[ContactCache] = []
        self._chats: list[ChatCache] = []
        self._active_section = "contacts"
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {COLOR_PANEL_BACKGROUND};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        tabs = QWidget()
        tabs.setFixedHeight(40)
        tabs.setStyleSheet("background: transparent;")
        tabs_layout = QHBoxLayout(tabs)
        tabs_layout.setContentsMargins(0, 0, 0, 0)
        tabs_layout.setSpacing(0)

        self.contacts_tab = ConversationTabButton(
            self.contacts_title,
            self.color_primary,
            self.color_third,
            self.color_divider,
            active=True,
        )
        self.chats_tab = ConversationTabButton(
            self.chats_title,
            self.color_primary,
            self.color_third,
            self.color_divider,
        )
        self.contacts_tab.clicked.connect(lambda: self._show_section("contacts"))
        self.chats_tab.clicked.connect(lambda: self._show_section("chats"))
        tabs_layout.addWidget(self.contacts_tab)
        tabs_layout.addWidget(self.chats_tab)
        layout.addWidget(tabs)

        self.search_panel = ConversationSearchPanel(
            self.color_primary,
            self.color_third,
        )
        self.search_panel.search_requested.connect(self._forward_search_request)
        self.search_panel.search_cleared.connect(self._clear_search)
        self.search_panel.create_chat_requested.connect(self._toggle_chat_creation)
        layout.addWidget(self.search_panel)

        self.chat_creation_panel = ChatCreationPanel(
            color_inactive=self.color_third,
            color_background=COLOR_PANEL_BACKGROUND,
            color_text=COLOR_TEXT,
        )
        self.chat_creation_panel.create_requested.connect(
            self.create_chat_requested.emit
        )
        layout.addWidget(self.chat_creation_panel)

        # Скролл-зона для списка контактов
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"""
            QScrollArea {{ border: none; background: {COLOR_PANEL_BACKGROUND}; }}
            QScrollBar:vertical {{ background: {COLOR_SCROLLBAR_TRACK}; width: 4px; }}
            QScrollBar::handle:vertical {{ background: {COLOR_SCROLLBAR_HANDLE}; border-radius: 2px; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
        """)

        self.contact_list = ContactList(
            self.color_primary,
            COLOR_CONTACT_BORDER,
            color_section_background=COLOR_CONTACT_SECTION_BACKGROUND,
            color_section_text=COLOR_CONTACT_SECTION_TEXT,
            color_section_active=COLOR_CONTACT_SECTION_ACTIVE,
        )
        self.contact_list.contact_selected.connect(self.conversation_selected.emit)
        self.contact_list.contact_action_requested.connect(
            self.contact_action_requested.emit
        )
        self.contact_list.chat_members_requested.connect(
            self.chat_members_requested.emit
        )
        scroll.setWidget(self.contact_list)

        layout.addWidget(scroll, stretch=1)
        self.setLayout(layout)

    def set_conversations(
        self, contacts: list[ContactCache], chats: list[ChatCache]
    ) -> None:
        self._contacts = contacts
        self._chats = chats
        self._render_active_section()

    def show_contact_search_results(self, contacts: list[ContactCache]) -> None:
        if self._active_section == "contacts":
            self.contact_list.set_conversations(
                contacts,
                [],
                expand_populated_sections=True,
                show_contact_sections=True,
            )

    def _show_section(self, section: str) -> None:
        if section not in {"contacts", "chats"}:
            return
        self._active_section = section
        self.contacts_tab.set_active(section == "contacts")
        self.chats_tab.set_active(section == "chats")
        self.search_panel.set_mode(section)
        if section != "chats":
            self.chat_creation_panel.close_panel()
            self.chat_members_panel_close_requested.emit()
        self._render_active_section()
        self.search_cleared.emit()

    def _toggle_chat_creation(self) -> None:
        if self._active_section != "chats":
            return
        if self.chat_creation_panel.isVisible():
            self.chat_creation_panel.close_panel()
            return
        self.chat_creation_panel.open_panel(self.search_panel.create_chat_button)

    def set_chat_creation_busy(self, busy: bool) -> None:
        self.chat_creation_panel.set_busy(busy)

    def finish_chat_creation(self, success: bool) -> None:
        if success:
            self.chat_creation_panel.complete_creation()
        else:
            self.chat_creation_panel.set_busy(False)

    def _forward_search_request(self, query: str, global_search: bool) -> None:
        self.search_requested.emit(self._active_section, query, global_search)

    def _clear_search(self) -> None:
        self._render_active_section()
        self.search_cleared.emit()

    def _render_active_section(self) -> None:
        if self._active_section == "contacts":
            self.contact_list.set_conversations(
                self._contacts,
                [],
                show_contact_sections=True,
            )
        else:
            self.contact_list.set_conversations([], self._chats)

    def select_first_conversation(self) -> None:
        self.contact_list.select_first()

    def select_conversation(self, conversation: Conversation) -> None:
        self.contact_list.select_conversation(conversation)

    def refresh_conversation(self, conversation: Conversation) -> None:
        self.contact_list.refresh_conversation(conversation)

    def chat_members_button(
        self,
        chat: ChatCache,
    ) -> AddChatParticipantButton | None:
        return self.contact_list.chat_members_button(chat)


class MessagesPanel(QWidget):
    text_message_send_requested = pyqtSignal(object, object, str)
    chat_participant_add_requested = pyqtSignal(object, object)

    def __init__(
        self,
        title: str,
        color_primary: str,
        color_outgoing: str,
        color_incoming: str,
        color_error: str,
        color_pending: str,
        color_input_focus: str,
        color_border: str,
        color_divider: str,
        parent=None,
    ):
        super().__init__(parent)
        self.title = title
        self.color_primary = color_primary
        self.color_outgoing = color_outgoing
        self.color_incoming = color_incoming
        self.color_error = color_error
        self.color_pending = color_pending
        self.color_input_focus = color_input_focus
        self.color_border = color_border
        self.color_divider = color_divider
        self.selected_conversation: Conversation | None = None
        self._available_contacts: list[ContactCache] = []
        self._current_user_id: UUID | None = None
        self._chat_members_anchor: AddChatParticipantButton | None = None
        self._pending_text_bubbles: dict[UUID, MessageBubble] = {}
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet(f"background-color: {COLOR_PANEL_BACKGROUND};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = PanelHeader(self.title, self.color_primary, self.color_divider)
        layout.addWidget(header)

        self.conversation_title = PanelHeader(
            "SELECT A CONVERSATION",
            COLOR_CONVERSATION_TITLE,
            self.color_divider,
            alignment=Qt.AlignmentFlag.AlignLeft,
            letter_spacing=4,
            leading_icon="",
        )
        self.conversation_title.setFixedHeight(36)
        layout.addWidget(self.conversation_title)

        self.messages_view = MessagesView(
            self.color_primary,
            self.color_outgoing,
            self.color_incoming,
            self.color_error,
            self.color_pending,
        )
        layout.addWidget(self.messages_view, stretch=1)

        self.message_field = MessageField(
            self.color_primary,
            self.color_border,
            self.color_divider,
            self.color_input_focus,
        )
        self.message_field.message_sent.connect(self._on_message_sent)
        self.message_field.file_sent.connect(self._on_file_sent)
        layout.addWidget(self.message_field)

        self.setLayout(layout)

        self.chat_members_panel = ChatMembersPanel(
            color_primary=self.color_primary,
            color_border=self.color_border,
            color_background=COLOR_PANEL_BACKGROUND,
            color_text=COLOR_TEXT,
            color_scrollbar=COLOR_SCROLLBAR_HANDLE,
            parent=self,
        )
        self.chat_members_panel.add_requested.connect(
            self.chat_participant_add_requested.emit
        )
        self.chat_members_panel.closed.connect(self._on_chat_members_panel_closed)

    def set_available_contacts(
        self,
        contacts: list[ContactCache],
        current_user_id: UUID | None = None,
    ) -> None:
        self._available_contacts = contacts
        self._current_user_id = current_user_id
        if isinstance(self.selected_conversation, ChatCache):
            self.chat_members_panel.update_context(
                self.selected_conversation,
                contacts,
                current_user_id,
            )

    def show_conversation(
        self,
        conversation: Conversation | None,
        *,
        preserve_chat_members_panel: bool = False,
    ) -> None:
        previous = self.selected_conversation
        same_chat = (
            isinstance(previous, ChatCache)
            and isinstance(conversation, ChatCache)
            and previous.server_chat_id == conversation.server_chat_id
        )
        keep_panel_open = (
            preserve_chat_members_panel
            and same_chat
            and self.chat_members_panel.isVisible()
        )
        if not keep_panel_open:
            self.chat_members_panel.close_panel()
        self.selected_conversation = conversation
        self._pending_text_bubbles.clear()
        if isinstance(conversation, ContactCache):
            leading_icon = "👤"
            title = conversation.username.upper()
            if conversation.status is ContactStatusEnum.ACCEPTED:
                if conversation.online:
                    title = f"{title} (ONLINE)"
                else:
                    offline_status = "OFFLINE"
                    if conversation.last_seen is not None:
                        offline_status = (
                            f"{offline_status} · LAST SEEN "
                            f"{format_last_seen(conversation.last_seen)}"
                        )
                    title = f"{title} ({offline_status})"
        elif isinstance(conversation, ChatCache):
            leading_icon = "🗨️"
            title = conversation_name(conversation).upper()
        else:
            leading_icon = ""
            title = "SELECT A CONVERSATION"
        self.conversation_title.set_leading_icon(leading_icon)
        self.conversation_title.set_title(title)
        if isinstance(conversation, ChatCache) and keep_panel_open:
            self.chat_members_panel.update_context(
                conversation,
                self._available_contacts,
                self._current_user_id,
            )
            self._position_chat_members_panel()
            self.chat_members_panel.raise_()
        message_list = self.messages_view.message_list
        message_list.clear_messages()
        if conversation is None:
            return
        for message in conversation.messages:
            if message.content_type == MessageContentTypeEnum.TEXT:
                text = message.content or ""
            else:
                text = f"⎙ {message.file_name or message.content_type.value}"
            bubble = message_list.add_message(
                server_message_id=message.server_message_id,
                text=text,
                is_mine=message.is_outgoing,
                timestamp=message.timestamp,
                status=(
                    "failed"
                    if message.failed is True
                    else "sent"
                    if message.is_outgoing
                    else ""
                ),
            )
            bubble.context_action.connect(self._handle_context_action)
            bubble.delete_requested.connect(self._delete_message)
        QTimer.singleShot(0, self.messages_view._smooth_scroll_to_bottom)

    def finish_chat_participant_addition(
        self,
        contact: ContactCache,
        success: bool,
        failure_message: str | None = None,
    ) -> None:
        self.chat_members_panel.finish_add(
            contact,
            success,
            failure_message,
        )

    def toggle_chat_members_panel(
        self,
        chat: ChatCache,
        anchor: AddChatParticipantButton,
    ) -> None:
        conversation = self.selected_conversation
        if (
            not isinstance(conversation, ChatCache)
            or conversation.server_chat_id != chat.server_chat_id
        ):
            return
        previous_anchor = self._chat_members_anchor
        if previous_anchor is not None and previous_anchor is not anchor:
            previous_anchor.set_active(False)
        self._chat_members_anchor = anchor
        self._position_chat_members_panel()
        self.chat_members_panel.toggle(
            chat,
            self._available_contacts,
            self._current_user_id,
            anchor,
        )
        anchor.set_active(self.chat_members_panel.isVisible())

    def reanchor_chat_members_panel(
        self,
        chat: ChatCache,
        anchor: AddChatParticipantButton,
    ) -> None:
        if (
            not self.chat_members_panel.isVisible()
            or not isinstance(self.selected_conversation, ChatCache)
            or self.selected_conversation.server_chat_id != chat.server_chat_id
        ):
            return
        self._chat_members_anchor = anchor
        self.chat_members_panel.set_anchor_widget(anchor)
        anchor.set_active(True)

    def close_chat_members_panel(self) -> None:
        self.chat_members_panel.close_panel()

    def _on_chat_members_panel_closed(self) -> None:
        anchor = self._chat_members_anchor
        self._chat_members_anchor = None
        if anchor is None:
            return
        try:
            anchor.set_active(False)
        except RuntimeError:
            pass

    def _position_chat_members_panel(self) -> None:
        panel_width = max(210, min(300, self.width() * 3 // 14))
        top = 84
        bottom_margin = max(68, self.message_field.height() + 8)
        panel_height = max(180, min(360, self.height() - top - bottom_margin))
        self.chat_members_panel.setGeometry(
            0,
            top,
            panel_width,
            panel_height,
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._position_chat_members_panel()

    def _on_message_sent(self, text: str) -> None:
        conversation = self.selected_conversation
        if not isinstance(conversation, ContactCache):
            return

        request_id = uuid4()
        bubble = self.messages_view.message_list.add_message(
            server_message_id=None,
            text=text,
            is_mine=True,
            status="",
        )
        bubble.context_action.connect(self._handle_context_action)
        bubble.delete_requested.connect(self._delete_message)
        self._pending_text_bubbles[request_id] = bubble
        QTimer.singleShot(10, self.messages_view._smooth_scroll_to_bottom)
        self.text_message_send_requested.emit(request_id, conversation, text)

    def finish_text_message(
        self,
        request_id: UUID,
        success: bool,
        server_message_id: UUID | None = None,
        failure_message: str | None = None,
    ) -> None:
        bubble = self._pending_text_bubbles.pop(request_id, None)
        if bubble is None:
            return
        if success and server_message_id is not None:
            bubble.server_message_id = server_message_id
            bubble.set_status("sent")
            return
        if failure_message:
            bubble.setToolTip(failure_message)
        bubble.set_status("failed")

    def _on_file_sent(self, path: str):
        ext = os.path.splitext(path)[1].lower()
        if ext in IMAGE_EXTENSIONS:
            bubble = self.messages_view.message_list.add_image(path, is_mine=True)
        elif ext in VIDEO_EXTENSIONS:
            bubble = self.messages_view.message_list.add_video(path, is_mine=True)
        else:
            bubble = self.messages_view.message_list.add_message(
                server_message_id=None,
                text=f"‹ ⎙ {os.path.basename(path)} ›",
                is_mine=True,
            )
        bubble.context_action.connect(self._handle_context_action)
        bubble.delete_requested.connect(self._delete_message)
        QTimer.singleShot(10, self.messages_view._smooth_scroll_to_bottom)

        bubble.set_status("failed")

    def _handle_context_action(self, action: str):
        if not self.sender():
            return
        if action == "delete":
            sender = self.sender()
            if isinstance(sender, QWidget):
                layout = self.messages_view.message_list._layout
                layout.removeWidget(sender)
                sender.hide()
                sender.deleteLater()

    def _delete_message(self, msg_id: UUID | None):
        # stub for delete business logic
        if msg_id is not None:
            print(f"[API CALL] Delete message {msg_id}")
        else:
            print("[API CALL] Delete message (no ID yet)")


class PanelHeader(QWidget):
    def __init__(
        self,
        title: str,
        color_primary: str,
        color_divider: str,
        parent=None,
        alignment: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft,
        letter_spacing: float = 0,
        leading_icon: str = "",
    ):
        super().__init__(parent)
        self.title = title
        self.color_primary = color_primary
        self.color_divider = color_divider
        self.alignment = alignment
        self.letter_spacing = letter_spacing
        self.leading_icon = leading_icon
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def set_title(self, title: str) -> None:
        self.title = title
        self.update()

    def set_leading_icon(self, icon: str) -> None:
        self.leading_icon = icon
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(self.color_divider))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        painter.setBrush(QColor(self.color_primary))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 12, 3, 16)

        text_left = 14
        painter.setPen(QColor(self.color_primary))
        if self.leading_icon and self.alignment == Qt.AlignmentFlag.AlignLeft:
            icon_font = QFont("Segoe UI Emoji", 13)
            painter.setFont(icon_font)
            painter.drawText(
                QRect(14, 0, 24, self.height()),
                Qt.AlignmentFlag.AlignCenter,
                self.leading_icon,
            )
            text_left = 44

        font = QFont("Roboto", 11)
        if self.letter_spacing:
            font.setLetterSpacing(
                QFont.SpacingType.AbsoluteSpacing, self.letter_spacing
            )
        painter.setFont(font)
        if self.alignment == Qt.AlignmentFlag.AlignCenter:
            text_rect = self.rect()
        elif self.alignment == Qt.AlignmentFlag.AlignRight:
            text_rect = QRect(0, 0, self.width() - 14, self.height())
        else:
            text_rect = QRect(text_left, 0, self.width() - text_left, self.height())
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter | self.alignment,
            self.title,
        )


class PanelPlaceholder(QWidget):
    def __init__(self, text: str, color: str, parent=None):
        super().__init__(parent)
        self.text = text
        self.color = color
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def paintEvent(self, event):
        painter = QPainter(self)
        font = QFont("Roboto", 11)
        painter.setFont(font)
        painter.setPen(QColor(self.color))
        painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.text)
