# presentation/pages/settings.py
import asyncio
import logging
from typing import List, Optional

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QComboBox, QSizePolicy,
    QScrollArea
)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer
from PyQt6.QtGui import QFont, QPainter, QPen, QColor, QFontDatabase

from .manager import SettingsManager

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


class FuturisticComboBox(QComboBox):
    """Custom combobox with futuristic styling"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()

    def setup_ui(self):
        self.setFixedHeight(40)
        self.setStyleSheet(f"""
            QComboBox {{
                background-color: {COLOR_SURFACE};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
                font-family: '{FONT_PRIMARY}', sans-serif;
                font-weight: 300;
                selection-background-color: {COLOR_TEXT_MUTED};
            }}
            QComboBox:hover {{
                border-color: {COLOR_TEXT_SECONDARY};
                background-color: {COLOR_SURFACE_HOVER};
            }}
            QComboBox:focus {{
                border: 2px solid {COLOR_ACCENT};
                background-color: {COLOR_BG_SECONDARY};
                padding: 7px 11px;
            }}
            QComboBox::drop-down {{
                border: none;
                width: 30px;
            }}
            QComboBox::down-arrow {{
                image: none;
                border-left: 5px solid transparent;
                border-right: 5px solid transparent;
                border-top: 5px solid {COLOR_TEXT_PRIMARY};
                width: 0;
                height: 0;
                margin-right: 10px;
            }}
            QComboBox QAbstractItemView {{
                background-color: {COLOR_SURFACE};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                selection-background-color: {COLOR_SURFACE_HOVER};
                selection-color: {COLOR_ACCENT};
                outline: none;
            }}
        """)

        # Customize scrollbar for dropdown
        self.view().verticalScrollBar().setStyleSheet("""
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


class SettingsInterface(QWidget):
    """Settings interface with futuristic design"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.settings_manager = None

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
        """Setup the futuristic settings UI"""
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

        # Main content area
        content_area = self.create_content_area()
        main_layout.addWidget(content_area)

        # Footer
        footer = self.create_footer()
        main_layout.addWidget(footer)

    def create_header(self) -> QFrame:
        """Create header with navigation"""
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
        title = QLabel("SETTINGS")
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

        layout.addWidget(logout_btn)

        return header

    def create_content_area(self) -> QFrame:
        """Create main content area"""
        content_area = QFrame()
        content_area.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BG_PRIMARY};
            }}
        """)

        layout = QVBoxLayout(content_area)
        layout.setContentsMargins(0, 0, 0, 0)

        # Scroll area for settings
        scroll_area = QScrollArea()
        scroll_area.setStyleSheet("""
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
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setWidgetResizable(True)

        # Settings container
        settings_container = QWidget()
        settings_container.setStyleSheet("background-color: transparent;")
        settings_layout = QVBoxLayout(settings_container)
        settings_layout.setContentsMargins(40, 40, 40, 40)
        settings_layout.setSpacing(30)

        # Timezone settings card
        timezone_card = self.create_timezone_card()
        settings_layout.addWidget(timezone_card)

        # Add spacer
        settings_layout.addStretch()

        scroll_area.setWidget(settings_container)
        layout.addWidget(scroll_area)

        return content_area

    def create_timezone_card(self) -> QFrame:
        """Create timezone settings card"""
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_SURFACE};
                border: 1px solid {COLOR_BORDER};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(30, 30, 30, 30)
        layout.setSpacing(20)

        # Title
        title_label = QLabel("TIMEZONE SETTINGS")
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_ACCENT};
                font-size: 18px;
                font-family: '{FONT_PRIMARY}', sans-serif;
                font-weight: 400;
                padding-bottom: 10px;
                border-bottom: 1px solid {COLOR_BORDER};
            }}
        """)

        # Description
        desc_label = QLabel("Set your local timezone for correct message timestamps")
        desc_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_SECONDARY};
                font-size: 13px;
                font-family: '{FONT_PRIMARY}', sans-serif;
                font-weight: 300;
                line-height: 1.5;
            }}
        """)
        desc_label.setWordWrap(True)

        # Timezone selection
        timezone_layout = QVBoxLayout()
        timezone_layout.setSpacing(8)

        timezone_label = QLabel("Select Timezone")
        timezone_label.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_PRIMARY};
                font-size: 14px;
                font-family: '{FONT_PRIMARY}', sans-serif;
                font-weight: 300;
            }}
        """)

        self.timezone_combo = FuturisticComboBox()

        # Current timezone info
        current_info = QLabel("Current timezone: Not set")
        current_info.setStyleSheet(f"""
            QLabel {{
                color: {COLOR_TEXT_MUTED};
                font-size: 12px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
            }}
        """)
        self.current_timezone_label = current_info

        timezone_layout.addWidget(timezone_label)
        timezone_layout.addWidget(self.timezone_combo)
        timezone_layout.addWidget(current_info)

        # Save button
        save_btn = QPushButton("SAVE SETTINGS")
        save_btn.setFixedSize(150, 35)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_SUCCESS};
                color: {COLOR_BG_PRIMARY};
                border: none;
                border-radius: 6px;
                font-size: 12px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 400;
                letter-spacing: 1px;
                text-transform: uppercase;
                padding: 0px 5px;
            }}
            QPushButton:hover {{
                background-color: #90EE90;
            }}
            QPushButton:pressed {{
                background-color: {COLOR_SUCCESS};
            }}
            QPushButton:disabled {{
                background-color: {COLOR_DISABLED};
                color: {COLOR_TEXT_MUTED};
            }}
        """)
        save_btn.clicked.connect(lambda: asyncio.create_task(self.save_settings()))

        layout.addWidget(title_label)
        layout.addWidget(desc_label)
        layout.addLayout(timezone_layout)
        layout.addWidget(save_btn)

        return card

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
        # Initialize settings manager
        if not self.settings_manager:
            self.settings_manager = SettingsManager(
                self.main_window.app_state,
                self.main_window.container
            )

        # Load timezone settings
        await self.load_timezone_settings()

    async def load_timezone_settings(self):
        """Load timezone settings"""
        try:
            if not self.settings_manager:
                return

            # Get current timezone
            current_timezone = await self.settings_manager.get_timezone()

            # Get timezone options
            timezone_options = self.settings_manager.get_timezone_options()

            # Clear existing items
            self.timezone_combo.clear()

            # Add timezone options to combobox
            for tz_int, tz_str in timezone_options.items():
                display_text = f"UTC{tz_str}"
                self.timezone_combo.addItem(display_text, tz_int)

            # Set current timezone
            current_timezone_str = timezone_options.get(current_timezone, "+00:00")

            # Find and select the current timezone in combobox
            index = self.timezone_combo.findData(current_timezone)
            if index >= 0:
                self.timezone_combo.setCurrentIndex(index)

            # Update current timezone label
            self.current_timezone_label.setText(f"Current timezone: UTC{current_timezone_str}")

        except Exception as e:
            logging.error(f"Error loading timezone settings: {e}")

            # Set default values
            self.timezone_combo.clear()
            self.timezone_combo.addItem("UTC+00:00", 0)
            self.current_timezone_label.setText("Current timezone: UTC+00:00")

    async def save_settings(self):
        """Save settings"""
        try:
            if not self.settings_manager:
                return

            # Get selected timezone
            current_index = self.timezone_combo.currentIndex()
            if current_index < 0:
                self.show_status_message("Please select a timezone", COLOR_ERROR)
                return

            selected_timezone = self.timezone_combo.currentText()

            # Extract timezone string (e.g., "UTC+03:00" -> "+03:00")
            if selected_timezone.startswith("UTC"):
                timezone_str = selected_timezone[3:]  # Remove "UTC" prefix
            else:
                timezone_str = selected_timezone

            # Save timezone
            success, message = await self.settings_manager.update_timezone(timezone_str)

            if success:
                self.show_status_message("Settings saved successfully", COLOR_SUCCESS)

                # Update current timezone label
                self.current_timezone_label.setText(f"Current timezone: UTC{timezone_str}")

                # Refresh timezone in other screens if needed
                await self.refresh_other_screens()
            else:
                self.show_status_message(f"Error: {message}", COLOR_ERROR)

        except Exception as e:
            logging.error(f"Error saving settings: {e}")
            self.show_status_message(f"Error: {str(e)}", COLOR_ERROR)

    async def refresh_other_screens(self):
        """Refresh other screens that might use timezone data"""
        # Refresh messenger screen if it's active
        messenger_screen = self.main_window.screens.get("messenger")
        if messenger_screen and hasattr(messenger_screen, 'load_timezone'):
            await messenger_screen.load_timezone()

    async def go_back(self):
        """Go back to messenger screen"""
        await self.main_window.show_screen("messenger")

    async def logout(self):
        """Logout and return to login screen"""
        await self.main_window.show_screen("login")

    def show_status_message(self, message: str, color: str):
        """Show a status message"""
        # Create a temporary status label
        status_label = QLabel(message)
        status_label.setStyleSheet(f"""
            QLabel {{
                background-color: {color};
                color: {'#000000' if color == COLOR_SUCCESS else COLOR_TEXT_PRIMARY};
                padding: 10px;
                border-radius: 6px;
                font-size: 12px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 300;
            }}
        """)
        status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Add to layout temporarily
        layout = self.layout()
        if layout:
            # Remove previous status if exists
            if hasattr(self, '_status_widget') and self._status_widget:
                layout.removeWidget(self._status_widget)
                self._status_widget.deleteLater()

            # Add new status
            layout.insertWidget(1, status_label)  # Insert after header
            self._status_widget = status_label

            # Remove after 3 seconds
            QTimer.singleShot(3000, lambda: self.remove_status_message())

    def remove_status_message(self):
        """Remove status message"""
        if hasattr(self, '_status_widget') and self._status_widget:
            layout = self.layout()
            if layout:
                layout.removeWidget(self._status_widget)
                self._status_widget.deleteLater()
                self._status_widget = None