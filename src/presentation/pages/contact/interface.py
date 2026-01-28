# presentation/pages/contact.py
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QScrollArea, QLineEdit,
    QStackedWidget, QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer, pyqtSignal
from PyQt6.QtGui import QFont, QPainter, QPen, QColor, QFontDatabase

from .manager import ContactManager

# Consistent color palette with other interfaces
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


class ContactCard(QFrame):
    """Contact card for displaying contact information"""

    clicked = pyqtSignal(int)  # Emits contact_id when clicked
    action_requested = pyqtSignal(str, int)  # Emits (action, contact_id)

    def __init__(self, contact, section="contacts", parent=None):
        super().__init__(parent)
        self.contact = contact
        self.contact_id = contact.server_user_id
        self.section = section
        self.setup_ui()

    def setup_ui(self):
        self.setFixedHeight(80)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(15, 10, 15, 10)
        layout.setSpacing(12)

        # Status indicator
        status_indicator = QFrame()
        status_indicator.setFixedSize(10, 10)

        if self.section == "pending":
            status_color = COLOR_WARNING
        elif self.section == "blacklist":
            status_color = COLOR_ERROR
        elif self.contact.online:
            status_color = COLOR_SUCCESS
        else:
            status_color = COLOR_TEXT_MUTED

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

        # Status text based on section and contact status
        if self.section == "pending":
            status_text = "pending request"
            status_color = COLOR_WARNING
        elif self.section == "blacklist":
            status_text = "blocked"
            status_color = COLOR_ERROR
        elif self.contact.online:
            status_text = "online"
            status_color = COLOR_SUCCESS
        else:
            status_text = self._format_last_seen(self.contact.last_seen, self.contact.online)
            status_color = COLOR_TEXT_MUTED

        status_label = QLabel(status_text)
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

        # Action buttons based on section
        if self.section == "search":
            # Add contact button
            add_btn = QPushButton("ADD")
            add_btn.setFixedSize(60, 30)
            add_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_SUCCESS};
                    color: {COLOR_BG_PRIMARY};
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                    font-family: '{FONT_MONO}', monospace;
                    font-weight: 400;
                }}
                QPushButton:hover {{
                    background-color: #90EE90;
                }}
            """)
            add_btn.clicked.connect(lambda: self.action_requested.emit("add", self.contact_id))
            layout.addWidget(add_btn)

        elif self.section == "pending":
            # Accept and reject buttons
            accept_btn = QPushButton("✓")
            accept_btn.setFixedSize(30, 30)
            accept_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_SUCCESS};
                    color: {COLOR_BG_PRIMARY};
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #90EE90;
                }}
            """)
            accept_btn.clicked.connect(lambda: self.action_requested.emit("accept", self.contact_id))

            reject_btn = QPushButton("✗")
            reject_btn.setFixedSize(30, 30)
            reject_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_ERROR};
                    color: {COLOR_BG_PRIMARY};
                    border: none;
                    border-radius: 4px;
                    font-size: 14px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: #FF6B6B;
                }}
            """)
            reject_btn.clicked.connect(lambda: self.action_requested.emit("reject", self.contact_id))

            layout.addWidget(accept_btn)
            layout.addWidget(reject_btn)

        elif self.section == "blacklist":
            # Restore button
            restore_btn = QPushButton("RESTORE")
            restore_btn.setFixedSize(80, 30)
            restore_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_SUCCESS};
                    color: {COLOR_BG_PRIMARY};
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                    font-family: '{FONT_MONO}', monospace;
                    font-weight: 400;
                }}
                QPushButton:hover {{
                    background-color: #90EE90;
                }}
            """)
            restore_btn.clicked.connect(lambda: self.action_requested.emit("restore", self.contact_id))
            layout.addWidget(restore_btn)

        elif self.section == "contacts":
            # Block button
            block_btn = QPushButton("BLOCK")
            block_btn.setFixedSize(70, 30)
            block_btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {COLOR_ERROR};
                    color: {COLOR_BG_PRIMARY};
                    border: none;
                    border-radius: 4px;
                    font-size: 11px;
                    font-family: '{FONT_MONO}', monospace;
                    font-weight: 400;
                }}
                QPushButton:hover {{
                    background-color: #FF6B6B;
                }}
            """)
            block_btn.clicked.connect(lambda: self.action_requested.emit("block", self.contact_id))
            layout.addWidget(block_btn)

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
        """Handle click event - only for contacts section"""
        if event.button() == Qt.MouseButton.LeftButton and self.section == "contacts":
            self.clicked.emit(self.contact_id)
            self.setStyleSheet(f"""
                QFrame {{
                    background-color: {COLOR_SURFACE};
                    border-radius: 8px;
                    border: 1px solid {COLOR_ACCENT};
                }}
            """)
        super().mousePressEvent(event)


class FuturisticSearchBar(QLineEdit):
    """Custom search bar with futuristic styling"""

    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setPlaceholderText(placeholder)
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLOR_SURFACE};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                font-family: '{FONT_PRIMARY}', sans-serif;
                font-weight: 300;
            }}
            QLineEdit:hover {{
                border-color: {COLOR_TEXT_SECONDARY};
                background-color: {COLOR_SURFACE_HOVER};
            }}
            QLineEdit:focus {{
                border: 2px solid {COLOR_ACCENT};
                background-color: {COLOR_BG_SECONDARY};
                padding: 7px 11px;
            }}
        """)

        # Add search icon using a label (since QLineEdit doesn't support icons directly)
        self.search_icon = QLabel("🔍", self)
        self.search_icon.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_MUTED};
                font-size: 14px;
                background: transparent;
            }}
        """)
        self.search_icon.setGeometry(10, 10, 20, 20)

        # Adjust text margins to make room for icon
        self.setTextMargins(35, 0, 0, 0)


class ContactInterface(QWidget):
    """Contact management interface with futuristic design"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.contact_manager = None
        self.contacts = []
        self.search_results = []
        self.pending_requests = []
        self.blacklist = []

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
        """Setup the futuristic contact management UI"""
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

        # Main content area with tabs
        content_area = self.create_content_area()
        main_layout.addWidget(content_area)

        # Footer
        footer = self.create_footer()
        main_layout.addWidget(footer)

    def create_header(self) -> QFrame:
        """Create header with navigation and controls"""
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

        # Back button
        back_btn = QPushButton("← BACK")
        back_btn.setFixedSize(80, 32)
        back_btn.setStyleSheet(f"""
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
        back_btn.clicked.connect(lambda: asyncio.create_task(self.go_back()))

        # Title
        title = QLabel("CONTACTS MANAGEMENT")
        title.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_ACCENT};
                font-size: 18px;
                font-weight: 300;
                letter-spacing: 1px;
            }}
        """)

        layout.addWidget(back_btn)
        layout.addWidget(title)
        layout.addStretch()

        # Sync button
        sync_btn = QPushButton("SYNC")
        sync_btn.setFixedSize(60, 32)
        sync_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_SURFACE};
                color: {COLOR_SUCCESS};
                border: 1px solid {COLOR_SUCCESS};
                border-radius: 4px;
                font-size: 11px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 400;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_SUCCESS};
                color: {COLOR_BG_PRIMARY};
            }}
        """)
        sync_btn.clicked.connect(lambda: asyncio.create_task(self.synchronize_contacts()))

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

        layout.addWidget(sync_btn)
        layout.addWidget(logout_btn)

        return header

    def create_content_area(self) -> QFrame:
        """Create main content area with tabs"""
        content_area = QFrame()
        content_area.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(content_area)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab buttons
        tabs_frame = QFrame()
        tabs_frame.setFixedHeight(50)
        tabs_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_SECONDARY};
                border-bottom: 1px solid {COLOR_BORDER};
            }}
        """)

        tabs_layout = QHBoxLayout(tabs_frame)
        tabs_layout.setContentsMargins(20, 0, 20, 0)
        tabs_layout.setSpacing(0)

        # Tab buttons
        self.contacts_tab = QPushButton("MY CONTACTS")
        self.search_tab = QPushButton("FIND CONTACTS")
        self.pending_tab = QPushButton("PENDING")
        self.blacklist_tab = QPushButton("BLACKLIST")

        for tab in [self.contacts_tab, self.search_tab, self.pending_tab, self.blacklist_tab]:
            tab.setFixedHeight(50)
            tab.setCheckable(True)
            tab.setStyleSheet(f"""
                QPushButton {{
                    background-color: transparent;
                    color: {COLOR_TEXT_SECONDARY};
                    border: none;
                    font-size: 12px;
                    font-family: '{FONT_MONO}', monospace;
                    font-weight: 400;
                    letter-spacing: 1px;
                    padding: 0 20px;
                }}
                QPushButton:hover {{
                    color: {COLOR_TEXT_PRIMARY};
                    background-color: {COLOR_SURFACE_HOVER};
                }}
                QPushButton:checked {{
                    color: {COLOR_ACCENT};
                    border-bottom: 2px solid {COLOR_ACCENT};
                }}
            """)
            tabs_layout.addWidget(tab)

        tabs_layout.addStretch()

        layout.addWidget(tabs_frame)

        # Stacked widget for tab content
        self.stacked_widget = QStackedWidget()

        # Contacts tab
        self.contacts_widget = self.create_contacts_widget()
        self.stacked_widget.addWidget(self.contacts_widget)

        # Search tab
        self.search_widget = self.create_search_widget()
        self.stacked_widget.addWidget(self.search_widget)

        # Pending tab
        self.pending_widget = self.create_pending_widget()
        self.stacked_widget.addWidget(self.pending_widget)

        # Blacklist tab
        self.blacklist_widget = self.create_blacklist_widget()
        self.stacked_widget.addWidget(self.blacklist_widget)

        layout.addWidget(self.stacked_widget)

        # Connect tab buttons
        self.contacts_tab.clicked.connect(lambda: self.switch_tab(0))
        self.search_tab.clicked.connect(lambda: self.switch_tab(1))
        self.pending_tab.clicked.connect(lambda: self.switch_tab(2))
        self.blacklist_tab.clicked.connect(lambda: self.switch_tab(3))

        # Set default tab
        self.contacts_tab.setChecked(True)

        return content_area

    def create_contacts_widget(self) -> QWidget:
        """Create widget for displaying existing contacts"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border-bottom: 1px solid {COLOR_BORDER};
            }}
        """)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("MY CONTACTS")
        title.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_MUTED};
                font-size: 11px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
                letter-spacing: 1px;
            }}
        """)

        self.contacts_count_label = QLabel("0 TOTAL")
        self.contacts_count_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_SUCCESS};
                font-size: 10px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
            }}
        """)

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.contacts_count_label)

        layout.addWidget(header)

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
        self.contacts_container = QWidget()
        self.contacts_container.setStyleSheet("background-color: transparent;")
        self.contacts_layout = QVBoxLayout(self.contacts_container)
        self.contacts_layout.setContentsMargins(20, 20, 20, 20)
        self.contacts_layout.setSpacing(10)

        # Add spacer
        self.contacts_layout.addStretch()

        self.contacts_scroll_area.setWidget(self.contacts_container)
        layout.addWidget(self.contacts_scroll_area)

        return widget

    def create_search_widget(self) -> QWidget:
        """Create widget for searching contacts"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border-bottom: 1px solid {COLOR_BORDER};
            }}
        """)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("FIND CONTACTS")
        title.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_MUTED};
                font-size: 11px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
                letter-spacing: 1px;
            }}
        """)

        header_layout.addWidget(title)
        header_layout.addStretch()

        layout.addWidget(header)

        # Search bar
        search_bar_frame = QFrame()
        search_bar_frame.setFixedHeight(70)
        search_bar_frame.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
            }}
        """)

        search_layout = QHBoxLayout(search_bar_frame)
        search_layout.setContentsMargins(20, 15, 20, 15)

        self.search_input = FuturisticSearchBar("SEARCH USERNAME...")
        self.search_input.returnPressed.connect(lambda: asyncio.create_task(self.search_contacts()))

        search_btn = QPushButton("SEARCH")
        search_btn.setFixedSize(80, 40)
        search_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_SURFACE};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                font-size: 11px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 400;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_SURFACE_HOVER};
                border-color: {COLOR_TEXT_SECONDARY};
                color: {COLOR_ACCENT};
            }}
        """)
        search_btn.clicked.connect(lambda: asyncio.create_task(self.search_contacts()))

        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_btn)

        layout.addWidget(search_bar_frame)

        # Search results scroll area
        self.search_scroll_area = QScrollArea()
        self.search_scroll_area.setStyleSheet("""
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
        self.search_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.search_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.search_scroll_area.setWidgetResizable(True)

        # Search results container
        self.search_container = QWidget()
        self.search_container.setStyleSheet("background-color: transparent;")
        self.search_layout = QVBoxLayout(self.search_container)
        self.search_layout.setContentsMargins(20, 0, 20, 20)
        self.search_layout.setSpacing(10)

        # Add spacer
        self.search_layout.addStretch()

        self.search_scroll_area.setWidget(self.search_container)
        layout.addWidget(self.search_scroll_area)

        return widget

    def create_pending_widget(self) -> QWidget:
        """Create widget for displaying pending contact requests"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border-bottom: 1px solid {COLOR_BORDER};
            }}
        """)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("PENDING REQUESTS")
        title.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_MUTED};
                font-size: 11px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
                letter-spacing: 1px;
            }}
        """)

        self.pending_count_label = QLabel("0 PENDING")
        self.pending_count_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_WARNING};
                font-size: 10px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
            }}
        """)

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.pending_count_label)

        layout.addWidget(header)

        # Pending requests scroll area
        self.pending_scroll_area = QScrollArea()
        self.pending_scroll_area.setStyleSheet("""
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
        self.pending_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.pending_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.pending_scroll_area.setWidgetResizable(True)

        # Pending requests container
        self.pending_container = QWidget()
        self.pending_container.setStyleSheet("background-color: transparent;")
        self.pending_layout = QVBoxLayout(self.pending_container)
        self.pending_layout.setContentsMargins(20, 20, 20, 20)
        self.pending_layout.setSpacing(10)

        # Add spacer
        self.pending_layout.addStretch()

        self.pending_scroll_area.setWidget(self.pending_container)
        layout.addWidget(self.pending_scroll_area)

        return widget

    def create_blacklist_widget(self) -> QWidget:
        """Create widget for displaying blacklisted contacts"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)

        # Header
        header = QFrame()
        header.setFixedHeight(50)
        header.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border-bottom: 1px solid {COLOR_BORDER};
            }}
        """)

        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("BLACKLIST")
        title.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_MUTED};
                font-size: 11px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
                letter-spacing: 1px;
            }}
        """)

        self.blacklist_count_label = QLabel("0 BLOCKED")
        self.blacklist_count_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_ERROR};
                font-size: 10px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
            }}
        """)

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.blacklist_count_label)

        layout.addWidget(header)

        # Blacklist scroll area
        self.blacklist_scroll_area = QScrollArea()
        self.blacklist_scroll_area.setStyleSheet("""
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
        self.blacklist_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.blacklist_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.blacklist_scroll_area.setWidgetResizable(True)

        # Blacklist container
        self.blacklist_container = QWidget()
        self.blacklist_container.setStyleSheet("background-color: transparent;")
        self.blacklist_layout = QVBoxLayout(self.blacklist_container)
        self.blacklist_layout.setContentsMargins(20, 20, 20, 20)
        self.blacklist_layout.setSpacing(10)

        # Add spacer
        self.blacklist_layout.addStretch()

        self.blacklist_scroll_area.setWidget(self.blacklist_container)
        layout.addWidget(self.blacklist_scroll_area)

        return widget

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

        # User info
        user_label = QLabel(f"USER: {self.main_window.app_state.username}")
        user_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_SECONDARY};
                font-size: 10px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
            }}
        """)

        layout.addWidget(user_label)

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
        # Initialize contact manager
        if not self.contact_manager:
            self.contact_manager = ContactManager(
                self.main_window.app_state,
                self.main_window.container
            )

        # Load all data
        await self.load_all_data()

        # Switch to contacts tab by default
        self.switch_tab(0)

    def switch_tab(self, index: int):
        """Switch between tabs"""
        self.stacked_widget.setCurrentIndex(index)

        # Update button states
        self.contacts_tab.setChecked(index == 0)
        self.search_tab.setChecked(index == 1)
        self.pending_tab.setChecked(index == 2)
        self.blacklist_tab.setChecked(index == 3)

    async def load_all_data(self):
        """Load all contact data"""
        await self.load_existing_contacts()
        await self.load_pending_requests()
        await self.load_blacklist()

    async def load_existing_contacts(self):
        """Load existing contacts from app state"""
        # Clear existing contacts
        for i in reversed(range(self.contacts_layout.count())):
            widget = self.contacts_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()

        # Add contacts
        for contact in self.main_window.app_state.accepted_contacts:
            contact_card = ContactCard(contact, section="contacts")
            contact_card.clicked.connect(self.on_contact_clicked)
            contact_card.action_requested.connect(self.on_contact_action)
            self.contacts_layout.insertWidget(self.contacts_layout.count() - 1, contact_card)

        # Update count
        count = len(self.main_window.app_state.accepted_contacts)
        self.contacts_count_label.setText(f"{count} TOTAL")

        # If no contacts, show empty state
        if count == 0:
            empty_label = QLabel("No contacts yet")
            empty_label.setStyleSheet(f"""
                QLabel {{
                    color: {COLOR_TEXT_MUTED};
                    font-size: 14px;
                    font-family: '{FONT_PRIMARY}', sans-serif;
                    font-weight: 300;
                }}
            """)
            empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.contacts_layout.insertWidget(self.contacts_layout.count() - 1, empty_label)

    async def load_pending_requests(self):
        """Load pending contact requests"""
        try:
            if not self.contact_manager:
                return

            self.pending_requests = await self.contact_manager.get_pending_requests()

            # Clear existing pending requests
            for i in reversed(range(self.pending_layout.count())):
                widget = self.pending_layout.itemAt(i).widget()
                if widget is not None:
                    widget.deleteLater()

            # Add pending requests
            for contact in self.pending_requests:
                contact_card = ContactCard(contact, section="pending")
                contact_card.action_requested.connect(self.on_contact_action)
                self.pending_layout.insertWidget(self.pending_layout.count() - 1, contact_card)

            # Update count
            count = len(self.pending_requests)
            self.pending_count_label.setText(f"{count} PENDING")

            # If no pending requests, show empty state
            if count == 0:
                empty_label = QLabel("No pending requests")
                empty_label.setStyleSheet(f"""
                    QLabel {{
                        color: {COLOR_TEXT_MUTED};
                        font-size: 14px;
                        font-family: '{FONT_PRIMARY}', sans-serif;
                        font-weight: 300;
                    }}
                """)
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.pending_layout.insertWidget(self.pending_layout.count() - 1, empty_label)

        except Exception as e:
            logging.error(f"Error loading pending requests: {e}")

    async def load_blacklist(self):
        """Load blacklisted contacts"""
        try:
            if not self.contact_manager:
                return

            self.blacklist = await self.contact_manager.get_blacklist()

            # Clear existing blacklist
            for i in reversed(range(self.blacklist_layout.count())):
                widget = self.blacklist_layout.itemAt(i).widget()
                if widget is not None:
                    widget.deleteLater()

            # Add blacklisted contacts
            for contact in self.blacklist:
                contact_card = ContactCard(contact, section="blacklist")
                contact_card.action_requested.connect(self.on_contact_action)
                self.blacklist_layout.insertWidget(self.blacklist_layout.count() - 1, contact_card)

            # Update count
            count = len(self.blacklist)
            self.blacklist_count_label.setText(f"{count} BLOCKED")

            # If no blacklisted contacts, show empty state
            if count == 0:
                empty_label = QLabel("Blacklist is empty")
                empty_label.setStyleSheet(f"""
                    QLabel {{
                        color: {COLOR_TEXT_MUTED};
                        font-size: 14px;
                        font-family: '{FONT_PRIMARY}', sans-serif;
                        font-weight: 300;
                    }}
                """)
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.blacklist_layout.insertWidget(self.blacklist_layout.count() - 1, empty_label)

        except Exception as e:
            logging.error(f"Error loading blacklist: {e}")

    async def search_contacts(self):
        """Search for contacts by username"""
        search_term = self.search_input.text().strip()
        if not search_term:
            return

        try:
            if not self.contact_manager:
                return

            # Clear previous search results
            for i in reversed(range(self.search_layout.count())):
                widget = self.search_layout.itemAt(i).widget()
                if widget is not None:
                    widget.deleteLater()

            # Show loading indicator
            loading_label = QLabel("Searching...")
            loading_label.setStyleSheet(f"""
                QLabel {{
                    color: {COLOR_TEXT_MUTED};
                    font-size: 14px;
                    font-family: '{FONT_PRIMARY}', sans-serif;
                    font-weight: 300;
                }}
            """)
            loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.search_layout.insertWidget(self.search_layout.count() - 1, loading_label)

            # Perform search
            self.search_results = await self.contact_manager.find_contacts(search_term)

            # Clear loading indicator
            loading_label.deleteLater()

            # Display results
            if not self.search_results:
                empty_label = QLabel("No contacts found")
                empty_label.setStyleSheet(f"""
                    QLabel {{
                        color: {COLOR_TEXT_MUTED};
                        font-size: 14px;
                        font-family: '{FONT_PRIMARY}', sans-serif;
                        font-weight: 300;
                    }}
                """)
                empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                self.search_layout.insertWidget(self.search_layout.count() - 1, empty_label)
            else:
                for contact in self.search_results:
                    contact_card = ContactCard(contact, section="search")
                    contact_card.action_requested.connect(self.on_contact_action)
                    self.search_layout.insertWidget(self.search_layout.count() - 1, contact_card)

        except Exception as e:
            logging.error(f"Error searching contacts: {e}")

            # Clear loading indicator
            for i in reversed(range(self.search_layout.count())):
                widget = self.search_layout.itemAt(i).widget()
                if widget is not None:
                    widget.deleteLater()

            # Show error
            error_label = QLabel(f"Search error: {str(e)}")
            error_label.setStyleSheet(f"""
                QLabel {{
                    color: {COLOR_ERROR};
                    font-size: 14px;
                    font-family: '{FONT_PRIMARY}', sans-serif;
                    font-weight: 300;
                }}
            """)
            error_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.search_layout.insertWidget(self.search_layout.count() - 1, error_label)

    @pyqtSlot(int)
    def on_contact_clicked(self, contact_id: int):
        """Handle contact selection - navigate to messenger"""
        asyncio.create_task(self.select_contact(contact_id))

    async def select_contact(self, contact_id: int):
        """Select a contact and navigate to messenger"""
        await self.main_window.show_screen("messenger", selected_contact=contact_id)

    @pyqtSlot(str, int)
    def on_contact_action(self, action: str, contact_id: int):
        """Handle contact card action"""
        asyncio.create_task(self.handle_contact_action(action, contact_id))

    async def handle_contact_action(self, action: str, contact_id: int):
        """Handle contact action based on button clicked"""
        try:
            if not self.contact_manager:
                return

            success = False

            if action == "add":
                success = await self.contact_manager.send_request(contact_id)
                message = "Contact request sent" if success else "Failed to send request"
                color = COLOR_SUCCESS if success else COLOR_ERROR

            elif action == "accept":
                success = await self.contact_manager.accept_request(contact_id)
                message = "Contact request accepted" if success else "Failed to accept request"
                color = COLOR_SUCCESS if success else COLOR_ERROR

            elif action == "reject":
                success = await self.contact_manager.reject_request(contact_id)
                message = "Contact request rejected" if success else "Failed to reject request"
                color = COLOR_SUCCESS if success else COLOR_ERROR

            elif action == "restore":
                success = await self.contact_manager.accept_request(contact_id)  # Same as accept for restoration
                message = "Contact restored from blacklist" if success else "Failed to restore contact"
                color = COLOR_SUCCESS if success else COLOR_ERROR

            elif action == "block":
                success = await self.contact_manager.remove_contact(contact_id)
                message = "Contact moved to blacklist" if success else "Failed to block contact"
                color = COLOR_SUCCESS if success else COLOR_ERROR

            # Show status message
            self.show_status_message(message, color)

            # Reload data if action was successful
            if success:
                await self.load_all_data()

        except Exception as e:
            logging.error(f"Error handling contact action {action}: {e}")
            self.show_status_message(f"Error: {str(e)}", COLOR_ERROR)

    async def synchronize_contacts(self):
        """Synchronize contacts with server"""
        try:
            if not self.contact_manager:
                return

            self.show_status_message("Synchronizing contacts...", COLOR_TEXT_SECONDARY)

            success = await self.contact_manager.synchronize_contacts()

            if success:
                self.show_status_message("Contacts synchronized successfully", COLOR_SUCCESS)
                await self.load_all_data()
            else:
                self.show_status_message("Failed to synchronize contacts", COLOR_ERROR)

        except Exception as e:
            logging.error(f"Error synchronizing contacts: {e}")
            self.show_status_message(f"Sync error: {str(e)}", COLOR_ERROR)

    async def go_back(self):
        """Go back to messenger screen"""
        await self.main_window.show_screen("messenger")

    async def logout(self):
        """Logout and return to login screen"""
        await self.main_window.show_screen("login")

    def show_status_message(self, message: str, color: str):
        """Show a status message (implement as needed)"""
        # You can implement a status bar or temporary message display here
        logging.info(f"Status: {message}")