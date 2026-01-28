# presentation/pages/messenger.py
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from random import randint

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QTextEdit,
    QSplitter, QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer, QPropertyAnimation, QEasingCurve, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPen, QColor, QFontDatabase

from .manager import MessengerManager

# Consistent color palette with login interface
COLOR_BG_PRIMARY = "#000000"
COLOR_BG_SECONDARY = "#0A0A0A"
COLOR_SURFACE = "#121212"
COLOR_SURFACE_HOVER = "#1A1A1A"
COLOR_BORDER = "#2A2A2A"
COLOR_ACCENT = "#FFFFFF"
COLOR_ACCENT_GLOW = "rgba(255, 255, 255, 0.1)"
COLOR_TEXT_PRIMARY = "#FFFFFF"
COLOR_TEXT_SECONDARY = "#AAAAAA"
COLOR_TEXT_MUTED = "#666666"
COLOR_SUCCESS = "#7FFFD4"
COLOR_WARNING = "#FFFF00"
COLOR_ERROR = "#FF3366"
COLOR_DISABLED = "#333333"

FONT_PRIMARY = "SF Pro Display"
FONT_MONO = "SF Mono"


class MessageBubble(QFrame):
    """Custom message bubble with futuristic styling"""

    def __init__(self, message: dict, timezone: int = 0, parent=None):
        super().__init__(parent)
        self.message = message
        self.timezone = timezone if timezone is not None else 0  # Защита от None
        self.is_outgoing = message.get("is_outgoing", False)
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("background: transparent;")

        # Main layout
        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 8, 20, 8)

        # Spacer for outgoing messages (right side)
        if self.is_outgoing:
            layout.addStretch()

        # Message container
        message_container = QFrame()
        message_container.setObjectName("messageContainer")
        if self.is_outgoing:
            bg_color = "#5F9EA0"  # Синий цвет для исходящих
            text_color = COLOR_TEXT_PRIMARY
            border_color = "#1565C0"
        else:
            bg_color = COLOR_SURFACE
            text_color = COLOR_TEXT_PRIMARY
            border_color = COLOR_BORDER

        message_container.setStyleSheet(f"""
            QFrame#messageContainer {{
                background-color: {bg_color};
                border-radius: 12px;
                border: 1px solid {border_color};
                padding: 12px;
                max-width: 400px;
            }}
            QFrame#messageContainer:hover {{
                border-color: {COLOR_TEXT_SECONDARY};
            }}
        """)

        message_layout = QVBoxLayout(message_container)
        message_layout.setContentsMargins(0, 0, 0, 0)
        message_layout.setSpacing(4)

        # Message content
        content_label = QLabel(self.message["content"])
        content_label.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                font-size: 13px;
                font-family: '{FONT_PRIMARY}', sans-serif;
                font-weight: 300;
                line-height: 1.4;
            }}
        """)
        content_label.setWordWrap(True)
        content_label.setTextFormat(Qt.TextFormat.RichText)

        # Message timestamp
        timestamp = self.message.get("timestamp", "")
        if isinstance(timestamp, datetime):
            timestamp = self._format_timestamp(timestamp, self.timezone)
        elif timestamp == "just now":
            # Если это временный маркер "just now", оставляем как есть
            pass
        elif isinstance(timestamp, str) and timestamp.endswith("Z"):
            # Если это строка в формате ISO с Z
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                timestamp = self._format_timestamp(dt, self.timezone)
            except:
                pass

        timestamp_label = QLabel(timestamp)
        timestamp_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_MUTED if not self.is_outgoing else '#BBBBBB'};
                font-size: 10px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
                opacity: 0.8;
            }}
        """)
        timestamp_label.setAlignment(Qt.AlignmentFlag.AlignRight if self.is_outgoing else Qt.AlignmentFlag.AlignLeft)

        message_layout.addWidget(content_label)
        message_layout.addWidget(timestamp_label)

        layout.addWidget(message_container)

        # Spacer for incoming messages (left side)
        if not self.is_outgoing:
            layout.addStretch()

    def _format_timestamp(self, timestamp: datetime, tz_offset: int = 0) -> str:
        """Format timestamp for display"""
        # Защита от None
        if tz_offset is None:
            tz_offset = 0

        try:
            timestamp_local = timestamp + timedelta(hours=tz_offset)
            now_local = datetime.utcnow() + timedelta(hours=tz_offset)

            diff = now_local - timestamp_local
            if diff.total_seconds() < 60:
                return "just now"
            elif diff.total_seconds() < 3600:
                minutes = int(diff.total_seconds() / 60)
                return f"{minutes}m ago"
            elif diff.total_seconds() < 86400:
                hours = int(diff.total_seconds() / 3600)
                return f"{hours}h ago"
            else:
                return timestamp_local.strftime("%b %d, %H:%M")
        except Exception as e:
            logging.error(f"Error formatting timestamp: {e}")
            return timestamp.strftime("%H:%M")


class ContactCard(QFrame):
    """Contact card for contacts list"""

    clicked = pyqtSignal(int)  # Emits contact_id when clicked

    def __init__(self, contact, parent=None):  # contact is Contact object, not dict
        super().__init__(parent)
        self.contact = contact
        self.contact_id = contact.server_user_id
        self.setup_ui()

    def setup_ui(self):
        self.setFixedHeight(70)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border-radius: 8px;
                border: 1px solid transparent;
            }}
            QFrame:hover {{
                background-color: {COLOR_SURFACE_HOVER};
                border-color: {COLOR_BORDER};
            }}
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(12)

        # Status indicator
        status_indicator = QFrame()
        status_indicator.setFixedSize(10, 10)
        status_color = COLOR_SUCCESS if self.contact.online else COLOR_TEXT_MUTED
        status_indicator.setStyleSheet(f"""
            QFrame {{
                background-color: {status_color};
                border-radius: 5px;
                border: 2px solid {COLOR_BG_PRIMARY};
            }}
        """)

        # Contact info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)

        username_label = QLabel(self.contact.username)
        username_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_PRIMARY};
                font-size: 14px;
                font-family: '{FONT_PRIMARY}', sans-serif;
                font-weight: 400;
            }}
        """)

        status_text = "online" if self.contact.online else self._format_last_seen(
            self.contact.last_seen,
            self.contact.online
        )

        status_label = QLabel(status_text)
        status_color = COLOR_SUCCESS if self.contact.online else COLOR_TEXT_MUTED
        status_label.setStyleSheet(f"""
            QLabel {{
                color: {status_color};
                font-size: 11px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
            }}
        """)

        info_layout.addWidget(username_label)
        info_layout.addWidget(status_label)

        layout.addWidget(status_indicator)
        layout.addLayout(info_layout)
        layout.addStretch()

    def _format_last_seen(self, last_seen, online: bool) -> str:
        """Format last seen time"""
        if online:
            return "online"

        if not last_seen:
            return "never"

        if isinstance(last_seen, str):
            try:
                last_seen = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
            except:
                return "unknown"

        now = datetime.utcnow()
        diff = now - last_seen

        if diff.total_seconds() < 60:
            return "just now"
        elif diff.total_seconds() < 3600:
            minutes = int(diff.total_seconds() / 60)
            return f"{minutes}m ago"
        elif diff.total_seconds() < 86400:
            hours = int(diff.total_seconds() / 3600)
            return f"{hours}h ago"
        else:
            days = diff.days
            return f"{days}d ago"

    def mousePressEvent(self, event):
        """Handle click event"""
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self.contact_id)
            # Highlight selected contact
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {COLOR_SURFACE};
                    border-radius: 8px;
                    border: 1px solid {COLOR_ACCENT};
                }}
            """)
        super().mousePressEvent(event)


class FuturisticTextEdit(QTextEdit):
    """Custom text input with futuristic styling"""

    returnPressed = pyqtSignal()

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self._placeholder = placeholder
        self.setup_ui()

    def setup_ui(self):
        self.setFixedHeight(80)
        self.setPlaceholderText(self._placeholder)
        self.setStyleSheet(f"""
            QTextEdit {{
                background-color: {COLOR_SURFACE};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 8px;
                padding: 12px;
                font-size: 13px;
                font-family: '{FONT_PRIMARY}', sans-serif;
                font-weight: 300;
                selection-background-color: {COLOR_TEXT_MUTED};
            }}
            QTextEdit:hover {{
                border-color: {COLOR_TEXT_SECONDARY};
                background-color: {COLOR_SURFACE_HOVER};
            }}
            QTextEdit:focus {{
                border: 2px solid {COLOR_ACCENT};
                background-color: {COLOR_BG_SECONDARY};
                padding: 11px;
            }}
        """)

    def keyPressEvent(self, event):
        """Handle Enter key for sending messages"""
        if event.key() == Qt.Key.Key_Return and not event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.returnPressed.emit()
            event.accept()
        elif event.key() == Qt.Key.Key_Return and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            # Insert new line with Shift+Enter
            self.insertPlainText("\n")
        else:
            super().keyPressEvent(event)


class MessengerInterface(QWidget):
    """Main messenger interface with black futuristic HUD design"""

    new_message_received = pyqtSignal(dict)  # Сигнал для нового сообщения
    user_status_updated = pyqtSignal(dict)  # Сигнал для обновления статуса

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.messenger_manager = None
        self.selected_contact = None
        self.contacts = []
        self.timezone = 0  # Значение по умолчанию
        self.session_id = str(randint(100000, 999999))

        # Timer for periodic updates
        self.update_timer = QTimer()
        # FIX: Connect to a slot that creates an async task
        self.update_timer.timeout.connect(lambda: asyncio.create_task(self.update_contacts_periodically()))
        self.update_timer.start(30000)  # Update every 30 seconds

        # Подключаем сигналы
        self.new_message_received.connect(self._on_new_message_received)
        self.user_status_updated.connect(self._on_user_status_updated)

        self.setup_ui()
        self.load_fonts()

    def load_fonts(self):
        """Load modern minimalist fonts"""
        modern_fonts = ["SF Pro Display", "Inter", "Helvetica Neue", "Segoe UI"]

        for font_name in modern_fonts:
            font_id = QFontDatabase.addApplicationFont(font_name)
            if font_id != -1:
                global FONT_PRIMARY
                FONT_PRIMARY = QFontDatabase.applicationFontFamilies(font_id)[0]
                break

    def setup_ui(self):
        """Setup the futuristic messenger UI"""
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLOR_BG_PRIMARY};
                color: {COLOR_TEXT_PRIMARY};
            }}
        """)

        # Main layout
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Header
        header = self.create_header()
        main_layout.addWidget(header)

        # Main content area with splitter
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        content_splitter.setHandleWidth(1)
        content_splitter.setStyleSheet(f"""
            QSplitter::handle {{
                background-color: {COLOR_BORDER};
            }}
        """)

        # Contacts sidebar
        self.contacts_sidebar = self.create_contacts_sidebar()
        content_splitter.addWidget(self.contacts_sidebar)

        # Chat area
        self.chat_area = self.create_chat_area()
        content_splitter.addWidget(self.chat_area)

        # Set initial splitter sizes
        content_splitter.setSizes([300, 700])

        main_layout.addWidget(content_splitter)

        # Footer
        footer = self.create_footer()
        main_layout.addWidget(footer)

    def create_header(self) -> QFrame:
        """Create header with app branding and controls"""
        header = QFrame()
        header.setFixedHeight(60)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SECONDARY};
                border-bottom: 1px solid {COLOR_BORDER};
            }}
        """)

        layout = QHBoxLayout(header)
        layout.setContentsMargins(20, 0, 20, 0)

        # App branding
        brand_layout = QVBoxLayout()
        brand_layout.setSpacing(2)

        app_name = QLabel("APATA MESSENGER")
        app_name.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_ACCENT};
                font-size: 18px;
                font-weight: 300;
                letter-spacing: 2px;
            }}
        """)

        app_subtitle = QLabel("SECURE COMMUNICATION PLATFORM")
        app_subtitle.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_MUTED};
                font-size: 9px;
                font-weight: 300;
                letter-spacing: 1px;
                font-family: '{FONT_MONO}', monospace;
            }}
        """)

        brand_layout.addWidget(app_name)
        brand_layout.addWidget(app_subtitle)

        layout.addLayout(brand_layout)
        layout.addStretch()

        # Controls
        controls_layout = QHBoxLayout()
        controls_layout.setSpacing(10)

        # Add contact button - ИСПРАВЛЕНО: добавлен обработчик
        add_contact_btn = QPushButton("+ CONTACT")
        add_contact_btn.setFixedSize(100, 32)
        add_contact_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_SURFACE};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                font-size: 11px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 400;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_SURFACE_HOVER};
                border-color: {COLOR_TEXT_SECONDARY};
            }}
        """)

        add_contact_btn.clicked.connect(lambda: asyncio.create_task(self.show_contact_interface()))

        # Refresh button
        refresh_btn = QPushButton("🔄")
        refresh_btn.setFixedSize(32, 32)
        refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_SURFACE};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_SURFACE_HOVER};
                border-color: {COLOR_TEXT_SECONDARY};
            }}
        """)
        refresh_btn.clicked.connect(lambda: asyncio.create_task(self.load_contacts()))

        # Settings button
        settings_btn = QPushButton("⚙")
        settings_btn.setFixedSize(32, 32)
        settings_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_SURFACE};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
                font-size: 14px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_SURFACE_HOVER};
                border-color: {COLOR_TEXT_SECONDARY};
            }}
        """)

        settings_btn.clicked.connect(lambda: asyncio.create_task(self.show_settings_interface()))

        # Logout button
        logout_btn = QPushButton("LOGOUT")
        logout_btn.setFixedSize(80, 32)
        logout_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_SURFACE};
                color: {COLOR_ERROR};
                border: 1px solid {COLOR_ERROR};
                border-radius: 4px;
                font-size: 11px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 400;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_ERROR};
                color: {COLOR_BG_PRIMARY};
            }}
        """)
        logout_btn.clicked.connect(lambda: asyncio.create_task(self.logout()))

        controls_layout.addWidget(add_contact_btn)
        controls_layout.addWidget(refresh_btn)
        controls_layout.addWidget(settings_btn)
        controls_layout.addWidget(logout_btn)

        layout.addLayout(controls_layout)

        return header

    def create_contacts_sidebar(self) -> QFrame:
        """Create contacts sidebar"""
        sidebar = QFrame()
        sidebar.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SECONDARY};
                border-right: 1px solid {COLOR_BORDER};
            }}
        """)

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Contacts header
        contacts_header = QFrame()
        contacts_header.setFixedHeight(50)
        contacts_header.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border-bottom: 1px solid {COLOR_BORDER};
            }}
        """)

        header_layout = QHBoxLayout(contacts_header)
        header_layout.setContentsMargins(15, 0, 15, 0)

        contacts_title = QLabel("CONTACTS")
        contacts_title.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_MUTED};
                font-size: 11px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
                letter-spacing: 1px;
            }}
        """)

        self.online_count_label = QLabel("0 ONLINE")
        self.online_count_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_SUCCESS};
                font-size: 10px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
            }}
        """)

        header_layout.addWidget(contacts_title)
        header_layout.addStretch()
        header_layout.addWidget(self.online_count_label)

        layout.addWidget(contacts_header)

        # Contacts list scroll area
        self.contacts_scroll_area = QScrollArea()
        self.contacts_scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: transparent;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background-color: #444444;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #555555;
            }
        """)
        self.contacts_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.contacts_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.contacts_scroll_area.setWidgetResizable(True)

        # Contacts list container
        self.contacts_widget = QWidget()
        self.contacts_widget.setStyleSheet("background-color: transparent;")
        self.contacts_layout = QVBoxLayout(self.contacts_widget)
        self.contacts_layout.setContentsMargins(0, 0, 0, 0)
        self.contacts_layout.setSpacing(0)

        # Add spacer to push contacts to top
        self.contacts_layout.addStretch()

        self.contacts_scroll_area.setWidget(self.contacts_widget)
        layout.addWidget(self.contacts_scroll_area)

        return sidebar

    def create_chat_area(self) -> QFrame:
        """Create main chat area"""
        chat_area = QFrame()
        chat_area.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(chat_area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Chat header (initially empty)
        self.chat_header = QFrame()
        self.chat_header.setFixedHeight(60)
        self.chat_header.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SECONDARY};
                border-bottom: 1px solid {COLOR_BORDER};
            }}
        """)
        self.chat_header.setVisible(False)

        header_layout = QHBoxLayout(self.chat_header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        self.contact_info_layout = QVBoxLayout()
        self.contact_info_layout.setSpacing(2)

        self.contact_name_label = QLabel("SELECT A CONTACT")
        self.contact_name_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_ACCENT};
                font-size: 16px;
                font-family: '{FONT_PRIMARY}', sans-serif;
                font-weight: 400;
            }}
        """)

        self.contact_status_label = QLabel("")
        self.contact_status_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_MUTED};
                font-size: 11px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
            }}
        """)

        self.contact_info_layout.addWidget(self.contact_name_label)
        self.contact_info_layout.addWidget(self.contact_status_label)

        header_layout.addLayout(self.contact_info_layout)
        header_layout.addStretch()

        layout.addWidget(self.chat_header)

        # Messages scroll area
        self.messages_scroll_area = QScrollArea()
        self.messages_scroll_area.setStyleSheet("""
            QScrollArea {
                background-color: transparent;
                border: none;
            }
            QScrollBar:vertical {
                background-color: transparent;
                width: 6px;
                border-radius: 3px;
            }
            QScrollBar::handle:vertical {
                background-color: #444444;
                border-radius: 3px;
                min-height: 20px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #555555;
            }
        """)
        self.messages_scroll_area.setWidgetResizable(True)

        # Messages container
        self.messages_widget = QWidget()
        self.messages_widget.setStyleSheet("background-color: transparent;")
        self.messages_layout = QVBoxLayout(self.messages_widget)
        self.messages_layout.setContentsMargins(20, 20, 20, 20)
        self.messages_layout.setSpacing(8)

        # Add spacer to push messages to bottom
        self.messages_layout.addStretch()

        self.messages_scroll_area.setWidget(self.messages_widget)
        layout.addWidget(self.messages_scroll_area)

        # Empty state
        self.empty_state = self.create_empty_state()
        layout.addWidget(self.empty_state)

        # Message input area
        input_area = QFrame()
        input_area.setFixedHeight(100)
        input_area.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SECONDARY};
                border-top: 1px solid {COLOR_BORDER};
            }}
        """)

        input_layout = QHBoxLayout(input_area)
        input_layout.setContentsMargins(20, 10, 20, 10)
        input_layout.setSpacing(12)

        # Message input
        self.message_input = FuturisticTextEdit("TYPE MESSAGE...")
        self.message_input.returnPressed.connect(lambda: asyncio.create_task(self.send_message()))

        # Send button
        self.send_button = QPushButton("SEND")
        self.send_button.setFixedSize(80, 40)
        self.send_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_SURFACE};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                font-size: 12px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 400;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_SURFACE_HOVER};
                border-color: {COLOR_TEXT_SECONDARY};
                color: {COLOR_ACCENT};
            }}
            QPushButton:disabled {{
                background-color: {COLOR_DISABLED};
                color: {COLOR_TEXT_MUTED};
                border-color: {COLOR_BORDER};
            }}
        """)
        self.send_button.clicked.connect(lambda: asyncio.create_task(self.send_message()))
        self.send_button.setEnabled(False)

        input_layout.addWidget(self.message_input)
        input_layout.addWidget(self.send_button)

        layout.addWidget(input_area)

        return chat_area

    def create_empty_state(self) -> QFrame:
        """Create empty state for chat area"""
        empty_state = QFrame()
        empty_state.setStyleSheet("background-color: transparent;")

        layout = QVBoxLayout(empty_state)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        empty_label = QLabel("SELECT A CONTACT TO START CHATTING")
        empty_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_MUTED};
                font-size: 14px;
                font-family: '{FONT_PRIMARY}', sans-serif;
                font-weight: 300;
            }}
        """)

        layout.addWidget(empty_label)

        return empty_state

    def create_footer(self) -> QFrame:
        """Create footer with system info"""
        footer = QFrame()
        footer.setFixedHeight(40)
        footer.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SECONDARY};
                border-top: 1px solid {COLOR_BORDER};
            }}
        """)

        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 0, 20, 0)

        # System info
        system_info = QLabel("ENCRYPTION • AES-256-GCM • ECDH-X25519 • ECDSA-SECP256R1")
        system_info.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_MUTED};
                font-size: 10px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
                letter-spacing: 0.5px;
            }}
        """)

        layout.addWidget(system_info)
        layout.addStretch()

        # Session info
        session_label = QLabel(f"SESSION: {self.session_id} • USER: {self.main_window.app_state.username}")
        session_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_SECONDARY};
                font-size: 10px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
            }}
        """)

        layout.addWidget(session_label)

        return footer

    def paintEvent(self, event):
        """Draw subtle background grid"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw subtle grid
        grid_size = 40
        pen = QPen(QColor(255, 255, 255, 8))
        pen.setWidth(1)
        painter.setPen(pen)

        # Vertical lines
        for x in range(0, self.width(), grid_size):
            painter.drawLine(x, 0, x, self.height())

        # Horizontal lines
        for y in range(0, self.height(), grid_size):
            painter.drawLine(0, y, self.width(), y)

    async def prepare_screen(self, **kwargs):
        """Prepare screen for display"""
        # Clear previous state
        self.selected_contact = None
        self.clear_chat()

        # Initialize messenger manager
        if not self.messenger_manager:
            self.messenger_manager = MessengerManager(
                self.main_window.app_state,
                self.main_window.container
            )

        # Load timezone с обработкой ошибок
        try:
            tz = await self.messenger_manager.get_timezone()
            if tz is not None:
                self.timezone = tz
            else:
                self.timezone = 0
                logging.warning("Timezone returned None, using default 0")
        except Exception as e:
            logging.error(f"Error getting timezone: {e}")
            self.timezone = 0

        # Load contacts
        await self.load_contacts()

        # Start WebSocket connection if not already started
        if not self.main_window.app_state.is_ws_connected:
            success = await self.messenger_manager.start_ws()
            if success:
                logging.info("WebSocket connection started")

        # Set message callback for real-time updates - исправляем
        self.messenger_manager.set_message_callback(self._handle_manager_callback_safe)

    async def _handle_manager_callback_safe(self, event_data: dict):
        """Безопасный обработчик callback из менеджера"""
        try:
            # Логируем получение события
            logging.info(f"Received callback from manager: {event_data.get('type')}")

            event_type = event_data.get("type")

            if event_type == "new_message":
                # Используем сигнал для передачи в основной поток
                self.new_message_received.emit(event_data)
            elif event_type == "user_status":
                self.user_status_updated.emit(event_data)
            elif event_type == "error":
                logging.error(f"Manager error: {event_data}")
        except Exception as e:
            logging.error(f"Error in manager callback: {e}")

    @pyqtSlot(dict)
    def _on_new_message_received(self, message_data: dict):
        """Обработка нового сообщения в основном потоке"""
        try:
            logging.info(f"Processing new message in UI thread: {message_data}")

            contact_id = message_data.get("contact_id")
            message_text = message_data.get("message")
            timestamp = message_data.get("timestamp")

            if not contact_id or not message_text:
                logging.warning(f"Invalid message data: {message_data}")
                return

            # Приводим contact_id к int
            try:
                contact_id = int(contact_id)
            except (ValueError, TypeError):
                logging.error(f"Invalid contact_id: {contact_id}")
                return

            logging.info(f"Message from contact {contact_id}, selected contact: {self.selected_contact}")

            # Если сообщение от выбранного контакта, отображаем сразу
            if contact_id == self.selected_contact:
                # Парсим timestamp
                if timestamp:
                    try:
                        if isinstance(timestamp, str):
                            if timestamp.endswith('Z'):
                                timestamp_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            else:
                                timestamp_dt = datetime.fromisoformat(timestamp)
                        else:
                            timestamp_dt = timestamp
                    except Exception as e:
                        logging.error(f"Error parsing timestamp {timestamp}: {e}")
                        timestamp_dt = datetime.utcnow()
                else:
                    timestamp_dt = datetime.utcnow()

                message_dict = {
                    "id": len(self.messages_layout.children()),
                    "content": message_text,
                    "is_outgoing": False,  # Входящие сообщения
                    "timestamp": timestamp_dt
                }

                # Добавляем в интерфейс
                asyncio.create_task(self.add_message_to_chat(message_dict))
                logging.info(f"Message added to chat UI")

            else:
                logging.info(f"Message not for selected contact, will show notification")
                # TODO: Показать уведомление

        except Exception as e:
            logging.error(f"Error in _on_new_message_received: {e}")

    @pyqtSlot(dict)
    def _on_user_status_updated(self, status_data: dict):
        """Обработка обновления статуса в основном потоке"""
        try:
            asyncio.create_task(self.handle_user_status(status_data))
        except Exception as e:
            logging.error(f"Error in _on_user_status_updated: {e}")

    async def handle_manager_callback(self, event_data: dict):
        """Handle callbacks from messenger manager"""
        try:
            logging.info(f"Handling manager callback: {event_data.get('type')}")

            event_type = event_data.get("type")

            if event_type == "new_message":
                await self.handle_incoming_message(event_data)
            elif event_type == "user_status":
                await self.handle_user_status(event_data)
            elif event_type == "error":
                logging.error(f"Manager error: {event_data}")
        except Exception as e:
            logging.error(f"Error in handle_manager_callback: {e}")

    async def handle_incoming_message(self, message_data: dict):
        """Handle incoming message from manager"""
        try:
            logging.info(f"Handling incoming message: {message_data}")

            contact_id = message_data.get("contact_id")
            message_text = message_data.get("message")
            timestamp = message_data.get("timestamp")

            if not contact_id or not message_text:
                logging.warning(f"Invalid message data: {message_data}")
                return

            # Приводим contact_id к int
            try:
                contact_id = int(contact_id)
            except (ValueError, TypeError):
                logging.error(f"Invalid contact_id: {contact_id}")
                return

            logging.info(f"Message from contact {contact_id}, selected contact: {self.selected_contact}")

            # Если сообщение от выбранного контакта, отображаем сразу
            if contact_id == self.selected_contact:
                # Парсим timestamp
                if timestamp:
                    try:
                        if isinstance(timestamp, str):
                            if timestamp.endswith('Z'):
                                timestamp_dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                            else:
                                timestamp_dt = datetime.fromisoformat(timestamp)
                        else:
                            timestamp_dt = timestamp
                    except Exception as e:
                        logging.error(f"Error parsing timestamp {timestamp}: {e}")
                        timestamp_dt = datetime.utcnow()
                else:
                    timestamp_dt = datetime.utcnow()

                message_dict = {
                    "id": len(self.messages_layout.children()),
                    "content": message_text,
                    "is_outgoing": False,  # Входящие сообщения
                    "timestamp": timestamp_dt
                }

                await self.add_message_to_chat(message_dict)
                logging.info(f"Message added to chat UI")

            else:
                logging.info(f"Message not for selected contact, will show notification")
                # TODO: Показать уведомление

        except Exception as e:
            logging.error(f"Error in handle_incoming_message: {e}")

    async def handle_user_status(self, status_data: dict):
        """Handle user status update"""
        try:
            user_id = status_data.get("user_id")
            online = status_data.get("online")
            timestamp = status_data.get("timestamp")

            logging.info(f"User status update: user_{user_id} -> {'online' if online else 'offline'}")

            # Update contact in list
            for i in range(self.contacts_layout.count() - 1):  # Exclude spacer
                widget = self.contacts_layout.itemAt(i).widget()
                if isinstance(widget, ContactCard) and widget.contact_id == user_id:
                    # Update the contact object
                    widget.contact.online = online
                    if timestamp:
                        try:
                            widget.contact.last_seen = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                        except:
                            widget.contact.last_seen = datetime.utcnow()

                    # Update the contact card
                    new_card = ContactCard(widget.contact)
                    new_card.clicked.connect(self.on_contact_clicked)
                    self.contacts_layout.replaceWidget(widget, new_card)
                    widget.deleteLater()
                    break

            # Update online count
            await self.update_online_count()

            # If this is the selected contact, update chat header
            if user_id == self.selected_contact:
                await self.update_chat_header()

        except Exception as e:
            logging.error(f"Error handling user status: {e}")

    async def load_contacts(self):
        """Load contacts from manager"""
        try:
            self.contacts = await self.messenger_manager.get_contacts()

            # Clear existing contacts (except spacer)
            for i in reversed(range(self.contacts_layout.count())):
                widget = self.contacts_layout.itemAt(i).widget()
                if widget is not None:
                    widget.deleteLater()

            # Add contacts
            for contact in self.contacts:
                contact_card = ContactCard(contact)
                contact_card.clicked.connect(self.on_contact_clicked)
                self.contacts_layout.insertWidget(self.contacts_layout.count() - 1, contact_card)

            # Update online count
            await self.update_online_count()

        except Exception as e:
            logging.error(f"Error loading contacts: {e}")

    async def update_online_count(self):
        """Update online contacts count"""
        online_count = sum(1 for contact in self.contacts if contact.online)
        self.online_count_label.setText(f"{online_count} ONLINE")

    async def update_contacts_periodically(self):
        """Periodically update contacts list"""
        await self.load_contacts()

    @pyqtSlot(int)
    def on_contact_clicked(self, contact_id: int):
        """Handle contact selection"""
        asyncio.create_task(self.select_contact(contact_id))

    async def select_contact(self, contact_id: int):
        """Select a contact and load their messages"""
        self.selected_contact = contact_id
        self.send_button.setEnabled(True)

        # Highlight selected contact
        for i in range(self.contacts_layout.count() - 1):  # Exclude spacer
            widget = self.contacts_layout.itemAt(i).widget()
            if isinstance(widget, ContactCard):
                if widget.contact_id == contact_id:
                    widget.setStyleSheet(f"""
                        QFrame {{
                            background-color: {COLOR_SURFACE};
                            border-radius: 8px;
                            border: 1px solid {COLOR_ACCENT};
                        }}
                    """)
                else:
                    widget.setStyleSheet(f"""
                        QFrame {{
                            background-color: transparent;
                            border-radius: 8px;
                            border: 1px solid transparent;
                        }}
                        QFrame:hover {{
                            background-color: {COLOR_SURFACE_HOVER};
                            border-color: {COLOR_BORDER};
                        }}
                    """)

        # Show chat header
        self.chat_header.setVisible(True)
        self.empty_state.setVisible(False)

        # Update chat header
        await self.update_chat_header()

        # Load messages
        await self.load_messages(contact_id)

    async def update_chat_header(self):
        """Update chat header with contact info"""
        if not self.selected_contact:
            return

        contact = next((c for c in self.contacts if c.server_user_id == self.selected_contact), None)
        if contact:
            self.contact_name_label.setText(contact.username)

            if contact.online:
                self.contact_status_label.setText("online")
                self.contact_status_label.setStyleSheet(f"""
                    QLabel {{
                        color: {COLOR_SUCCESS};
                        font-size: 11px;
                        font-family: '{FONT_MONO}', monospace;
                        font-weight: 300;
                    }}
                """)
            else:
                last_seen = contact.last_seen
                if last_seen:
                    if isinstance(last_seen, str):
                        try:
                            last_seen = datetime.fromisoformat(last_seen.replace('Z', '+00:00'))
                        except:
                            last_seen = None

                    if last_seen:
                        now = datetime.utcnow()
                        diff = now - last_seen

                        if diff.total_seconds() < 60:
                            status = "just now"
                        elif diff.total_seconds() < 3600:
                            minutes = int(diff.total_seconds() / 60)
                            status = f"{minutes}m ago"
                        elif diff.total_seconds() < 86400:
                            hours = int(diff.total_seconds() / 3600)
                            status = f"{hours}h ago"
                        else:
                            days = diff.days
                            status = f"{days}d ago"
                    else:
                        status = "unknown"
                else:
                    status = "never"

                self.contact_status_label.setText(f"last seen {status}")
                self.contact_status_label.setStyleSheet(f"""
                    QLabel {{
                        color: {COLOR_TEXT_MUTED};
                        font-size: 11px;
                        font-family: '{FONT_MONO}', monospace;
                        font-weight: 300;
                    }}
                """)

    async def load_messages(self, contact_id: int):
        """Load messages for selected contact"""
        try:
            # Clear existing messages
            self.clear_chat()

            # Load messages from manager
            messages = await self.messenger_manager.get_messages(contact_id)

            # Add messages to chat
            for message in messages:
                await self.add_message_to_chat(message)

            # Scroll to bottom
            self.scroll_to_bottom()

        except Exception as e:
            logging.error(f"Error loading messages: {e}")

    async def add_message_to_chat(self, message: dict):
        """Add a message to the chat display"""
        try:
            # Добавляем защиту от None для timezone
            timezone = self.timezone if self.timezone is not None else 0
            message_bubble = MessageBubble(message, timezone)
            self.messages_layout.insertWidget(self.messages_layout.count() - 1, message_bubble)

            # Scroll to new message
            QTimer.singleShot(100, self.scroll_to_bottom)

            # Force update
            self.messages_widget.update()

        except Exception as e:
            logging.error(f"Error adding message to chat: {e}")

    def scroll_to_bottom(self):
        """Scroll chat to bottom"""
        try:
            scrollbar = self.messages_scroll_area.verticalScrollBar()
            if scrollbar:
                scrollbar.setValue(scrollbar.maximum())
        except Exception as e:
            logging.error(f"Error scrolling to bottom: {e}")

    def clear_chat(self):
        """Clear all messages from chat"""
        for i in reversed(range(self.messages_layout.count())):
            widget = self.messages_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()

        # Add spacer back
        self.messages_layout.addStretch()

    async def send_message(self):
        """Send a message to selected contact"""
        if not self.selected_contact or not self.message_input.toPlainText().strip():
            return

        message_text = self.message_input.toPlainText().strip()
        self.message_input.clear()

        # Create temporary message in UI
        temp_message = {
            "id": len(self.messages_layout.children()),
            "content": message_text,
            "is_outgoing": True,  # Исходящие сообщения (отправленные мной)
            "timestamp": "just now"  # Временно используем строку
        }

        # Сразу добавляем сообщение в UI
        await self.add_message_to_chat(temp_message)

        try:
            # Send via manager
            success = await self.messenger_manager.send_message(
                self.selected_contact,
                message_text,
                content_type="text"
            )

            if not success:
                # Show error message
                error_message = {
                    "id": len(self.messages_layout.children()),
                    "content": "Failed to send message",
                    "is_outgoing": True,
                    "timestamp": "just now"
                }
                await self.add_message_to_chat(error_message)

        except Exception as e:
            logging.error(f"Error sending message: {e}")

    async def show_contact_interface(self):
        """Navigate to contact management interface"""
        await self.main_window.show_screen("contact")

    async def show_settings_interface(self):
        """Navigate to settings interface"""
        await self.main_window.show_screen("settings")

    async def logout(self):
        """Logout and return to login screen"""
        try:
            # Stop WebSocket connection
            if self.messenger_manager and self.main_window.app_state.is_ws_connected:
                await self.messenger_manager.stop_ws()

            # Logout via manager
            if self.messenger_manager:
                await self.messenger_manager.logout()

            # Return to login screen
            await self.main_window.show_screen("login")

        except Exception as e:
            logging.error(f"Error during logout: {e}")
            await self.main_window.show_screen("login")