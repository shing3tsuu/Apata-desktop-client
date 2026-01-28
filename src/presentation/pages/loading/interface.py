# presentation/pages/loading.py
import asyncio
import logging
from typing import Optional, List, Dict
from random import randint
from datetime import datetime

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFrame, QSizePolicy, QScrollArea,
    QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint, QParallelAnimationGroup, \
    QSequentialAnimationGroup
from PyQt6.QtGui import QFont, QPainter, QPen, QColor, QFontDatabase, QLinearGradient

from .manager import LoadingManager

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


class MinimalisticProgressBar(QFrame):
    """Custom progress bar with futuristic styling"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._max_value = 100
        self._glow_phase = 0
        self.setFixedHeight(4)
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_BORDER};
                border-radius: 2px;
            }}
        """)

        # Progress fill
        self._fill = QFrame(self)
        self._fill.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_ACCENT};
                border-radius: 2px;
            }}
        """)
        self._fill.setGeometry(0, 0, 0, 4)

        # Glow timer
        self._glow_timer = QTimer()
        self._glow_timer.timeout.connect(self._update_glow)
        self._glow_timer.start(50)

    def _update_glow(self):
        """Update subtle glow animation"""
        self._glow_phase = (self._glow_phase + 0.03) % (2 * 3.14159)
        self.update()

    def setValue(self, value: int):
        """Set progress value (0-100)"""
        self._value = max(0, min(value, self._max_value))
        width = int((self._value / self._max_value) * self.width())

        animation = QPropertyAnimation(self._fill, b"minimumWidth")
        animation.setDuration(400)
        animation.setStartValue(self._fill.width())
        animation.setEndValue(width)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start()

    def paintEvent(self, event):
        """Draw subtle glow effect"""
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self._value > 0 and self._value < self._max_value:
            # Subtle pulsing glow at progress end
            glow_intensity = 0.3 + 0.2 * (1 + (self._glow_phase / 3.14159))
            glow_width = 20

            gradient = QLinearGradient(
                self._fill.width() - glow_width, 0,
                self._fill.width(), 0
            )
            gradient.setColorAt(0, QColor(255, 255, 255, int(255 * glow_intensity * 0.3)))
            gradient.setColorAt(1, Qt.GlobalColor.transparent)

            painter.fillRect(
                self._fill.width() - glow_width, 0,
                glow_width, self.height(),
                gradient
            )


class StatusIndicator(QFrame):
    """Animated status indicator"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(12, 12)
        self._color = COLOR_WARNING
        self._pulse_phase = 0
        self._is_error = False

        # Pulse animation timer
        self._pulse_timer = QTimer()
        self._pulse_timer.timeout.connect(self._update_pulse)
        self._pulse_timer.start(100)

    def _update_pulse(self):
        """Update pulse animation"""
        if not self._is_error:
            self._pulse_phase = (self._pulse_phase + 0.1) % (2 * 3.14159)
        self.update()

    def setColor(self, color: str):
        """Set indicator color"""
        self._color = color
        self.update()

    def setError(self, is_error: bool):
        """Set error state"""
        self._is_error = is_error
        if is_error:
            self._color = COLOR_ERROR
        self.update()

    def paintEvent(self, event):
        """Draw animated indicator"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)

        # Main circle
        if self._is_error:
            # Error state - solid color
            painter.setBrush(QColor(self._color))
        else:
            # Normal state - pulsating
            pulse_intensity = 0.6 + 0.4 * (1 + (self._pulse_phase / 3.14159))
            color = QColor(self._color)
            color.setAlphaF(pulse_intensity)
            painter.setBrush(color)

        painter.drawEllipse(0, 0, 12, 12)

        # Outer glow
        if not self._is_error:
            glow_intensity = 0.2 + 0.1 * (1 + (self._pulse_phase / 3.14159))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            pen = QPen(QColor(self._color))
            pen.setWidth(2)
            pen.setColor(QColor(self._color))
            pen.setColor(QColor(pen.color().red(), pen.color().green(),
                                pen.color().blue(), int(255 * glow_intensity)))
            painter.setPen(pen)
            painter.drawEllipse(-2, -2, 16, 16)


class LoadingInterface(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.loading_manager = None
        self.steps: List[Dict] = []
        self.current_step = 0
        self.completed_steps: List[str] = []
        self.session_id = str(randint(100000, 999999))

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
        """Setup the futuristic loading UI"""
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLOR_BG_PRIMARY};
                color: {COLOR_TEXT_PRIMARY};
            }}
        """)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(40, 30, 40, 30)
        main_layout.setSpacing(0)

        # Header area
        header_layout = QHBoxLayout()

        # App branding
        brand_container = QVBoxLayout()

        app_name = QLabel("APATA")
        app_name.setStyleSheet(f"""
            color: {COLOR_ACCENT};
            font-size: 24px;
            font-weight: 300;
            letter-spacing: 3px;
            margin-bottom: 2px;
        """)

        app_subtitle = QLabel("SYSTEM INITIALIZATION")
        app_subtitle.setStyleSheet(f"""
            color: {COLOR_TEXT_MUTED};
            font-size: 10px;
            font-weight: 300;
            letter-spacing: 1.5px;
            font-family: '{FONT_MONO}', monospace;
        """)

        brand_container.addWidget(app_name)
        brand_container.addWidget(app_subtitle)

        header_layout.addLayout(brand_container)
        header_layout.addStretch()

        # Status indicator
        self.status_indicator = StatusIndicator()
        self.status_indicator.setColor(COLOR_WARNING)

        main_layout.addLayout(header_layout)

        # Main content area
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        content_layout.setSpacing(20)

        # Progress section
        progress_container = QVBoxLayout()
        progress_container.setSpacing(10)
        progress_container.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Percentage display
        self.percentage_label = QLabel("0%")
        self.percentage_label.setStyleSheet(f"""
            color: {COLOR_ACCENT};
            font-size: 18px;
            font-family: '{FONT_MONO}', monospace;
            font-weight: bold;
        """)
        self.percentage_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Progress bar
        self.progress_bar = MinimalisticProgressBar()
        self.progress_bar.setFixedWidth(400)

        progress_container.addWidget(self.percentage_label)
        progress_container.addWidget(self.progress_bar)

        content_layout.addLayout(progress_container)

        # Status logs container
        logs_container = QFrame()
        logs_container.setFixedSize(460, 120)
        logs_container.setStyleSheet(f"""
            QFrame {{
                background-color: transparent;
                border: 1px solid {COLOR_BORDER};
                border-radius: 4px;
            }}
        """)

        logs_layout = QVBoxLayout(logs_container)
        logs_layout.setContentsMargins(12, 8, 12, 8)
        logs_layout.setSpacing(6)

        # Create scroll area for logs
        self.logs_scroll_area = QScrollArea()
        self.logs_scroll_area.setStyleSheet("""
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
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)
        self.logs_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.logs_scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.logs_scroll_area.setWidgetResizable(True)

        # Container widget for logs
        self.logs_widget = QWidget()
        self.logs_widget.setStyleSheet("background-color: transparent;")
        self.logs_layout = QVBoxLayout(self.logs_widget)
        self.logs_layout.setContentsMargins(0, 0, 0, 0)
        self.logs_layout.setSpacing(4)

        # Set logs widget to scroll area
        self.logs_scroll_area.setWidget(self.logs_widget)

        logs_layout.addWidget(self.logs_scroll_area)

        content_layout.addWidget(logs_container)

        main_layout.addWidget(content_widget, stretch=1)

        # Footer
        footer_widget = QFrame()
        footer_widget.setFixedHeight(36)
        footer_widget.setStyleSheet(f"""
            QFrame {{
                border-top: 1px solid {COLOR_BORDER};
                background-color: transparent;
            }}
        """)

        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 8, 0, 0)

        # System info
        system_info = QLabel("SYNCHRONIZING • ENCRYPTING • ESTABLISHING SECURE CHANNELS")
        system_info.setStyleSheet(f"""
            color: {COLOR_TEXT_MUTED};
            font-size: 10px;
            font-family: '{FONT_MONO}', monospace;
            font-weight: 300;
            letter-spacing: 1px;
        """)

        footer_layout.addWidget(system_info)
        footer_layout.addStretch()

        # Session info
        session_label = QLabel(f"SESSION: {self.session_id}")
        session_label.setStyleSheet(f"""
            color: {COLOR_TEXT_SECONDARY};
            font-size: 10px;
            font-family: '{FONT_MONO}', monospace;
            font-weight: 300;
            letter-spacing: 1px;
        """)

        footer_layout.addWidget(session_label)

        # Error container (hidden by default)
        self.error_container = QFrame()
        self.error_container.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_SURFACE};
                border: 1px solid {COLOR_ERROR};
                border-radius: 6px;
                padding: 16px;
            }}
        """)
        self.error_container.setVisible(False)

        error_layout = QVBoxLayout(self.error_container)
        error_layout.setSpacing(8)

        error_title = QLabel("SYSTEM ERROR")
        error_title.setStyleSheet(f"""
            color: {COLOR_ERROR};
            font-size: 14px;
            font-weight: 500;
            font-family: '{FONT_MONO}', monospace;
        """)

        self.error_message = QLabel("")
        self.error_message.setStyleSheet(f"""
            color: {COLOR_TEXT_SECONDARY};
            font-size: 12px;
            font-family: '{FONT_PRIMARY}', sans-serif;
        """)
        self.error_message.setWordWrap(True)

        retry_button = QPushButton("RETRY INITIALIZATION")
        retry_button.setFixedHeight(32)
        retry_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_ERROR};
                color: {COLOR_ACCENT};
                border: none;
                border-radius: 4px;
                font-size: 12px;
                font-family: '{FONT_MONO}', monospace;
                font-weight: 400;
                letter-spacing: 1px;
            }}
            QPushButton:hover {{
                background-color: #FF5588;
            }}
        """)
        retry_button.clicked.connect(self.on_retry_clicked)

        error_layout.addWidget(error_title)
        error_layout.addWidget(self.error_message)
        error_layout.addWidget(retry_button, 0, Qt.AlignmentFlag.AlignCenter)

        content_layout.addWidget(self.error_container)

        main_layout.addWidget(footer_widget)
        self.setLayout(main_layout)

    def paintEvent(self, event):
        """Draw animated background elements"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw subtle grid (как в login интерфейсе)
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
        self.current_step = 0
        self.completed_steps = []

        # Clear logs
        for i in reversed(range(self.logs_layout.count())):
            widget = self.logs_layout.itemAt(i).widget()
            if widget is not None:
                widget.deleteLater()

        # Reset progress
        self.percentage_label.setText("0%")
        self.progress_bar.setValue(0)

        # Reset progress bar color
        self.progress_bar._fill.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_ACCENT};
                border-radius: 2px;
            }}
        """)

        # Show normal status
        self.status_indicator.setColor(COLOR_WARNING)
        self.status_indicator.setError(False)
        self.error_container.setVisible(False)

        # Define initialization steps in EXACT SEQUENCE
        self.steps = [
            {
                "name": "SYNCHRONIZING CONTACTS DATABASE",
                "method": self.synchronize_contacts,
                "params": {}
            },
            {
                "name": "LOADING MESSAGE HISTORY",
                "method": self.load_message_history,
                "params": {}
            },
            {
                "name": "ROTATING ENCRYPTION KEYS",
                "method": self.rotate_keys,
                "params": {}
            }
        ]

        # Start loading process
        asyncio.create_task(self.execute_loading_process())

    async def execute_loading_process(self):
        """Execute loading steps in sequence"""
        try:
            # Initialize LoadingManager
            if not self.loading_manager:
                self.loading_manager = LoadingManager(
                    self.main_window.app_state,
                    self.main_window.container
                )

            # Initial progress animation
            for i in range(0, 10, 1):
                self.percentage_label.setText(f"{i}%")
                self.progress_bar.setValue(i)
                await asyncio.sleep(0.04)

            # Execute each step in sequence
            total_steps = len(self.steps)

            for step_index, step_config in enumerate(self.steps):
                self.current_step = step_index
                step_name = step_config["name"]
                step_method = step_config["method"]

                # Update progress
                progress = min(100, int((step_index / total_steps) * 100))
                self.percentage_label.setText(f"{progress}%")
                self.progress_bar.setValue(progress)

                # Add step with "executing" status
                await self.add_step_status(step_name, "executing")

                try:
                    # Execute step method
                    success, message = await step_method()

                    if success:
                        await self.add_step_status(step_name, "completed")
                        self.completed_steps.append(step_name)
                    else:
                        await self.add_step_status(step_name, "error")
                        await self.show_error(f"Failed to execute: {step_name}\n{message}")
                        return  # Stop on error

                except Exception as e:
                    await self.add_step_status(step_name, "error")
                    await self.show_error(f"Error in {step_name}: {str(e)}")
                    return  # Stop on error

            # Final progress animation
            self.percentage_label.setText("100%")
            self.progress_bar.setValue(100)

            # Change status to success
            self.status_indicator.setColor(COLOR_SUCCESS)

            # Add final system messages
            final_steps = [
                "ENCRYPTED_SESSION_ACTIVE",
                "CONTACTS_SYNC_COMPLETE",
                "MESSAGE_DECRYPTION_READY",
                "SECURE_CHANNELS_ESTABLISHED",
                "MESSENGER_INTERFACE_LOADED"
            ]

            for step in final_steps:
                await asyncio.sleep(0.3)
                await self.add_step_status(step, "completed")

            # Final delay and transition to messenger
            await asyncio.sleep(0.5)

            # Check if messenger screen exists in main window
            if hasattr(self.main_window, 'screens') and "messenger" in self.main_window.screens:
                await self.main_window.show_screen("messenger")
            else:
                logging.warning("Messenger screen not found, staying on loading screen")

        except Exception as e:
            logging.error(f"Loading process failed: {e}")
            await self.show_error(f"System initialization failed: {str(e)}")

    async def synchronize_contacts(self) -> tuple[bool, str]:
        """Step 1: Synchronize contacts database"""
        try:
            success, message = await self.loading_manager.synchronize_contacts()
            return success, message
        except Exception as e:
            logging.error(f"Contact sync error: {e}")
            return False, str(e)

    async def load_message_history(self) -> tuple[bool, str]:
        """Step 2: Load message history"""
        try:
            success, message = await self.loading_manager.sync_message_history()
            return success, message
        except Exception as e:
            logging.error(f"Message history sync error: {e}")
            return False, str(e)

    async def rotate_keys(self) -> tuple[bool, str]:
        """Step 3: Rotate encryption keys"""
        try:
            success, message = await self.loading_manager.rotate_keys()
            return success, message
        except Exception as e:
            logging.error(f"Key rotation error: {e}")
            return False, str(e)

    async def add_step_status(self, step: str, status: str = "executing"):
        """Add step status to logs"""
        # Choose color and prefix based on status
        if status == "executing":
            color = COLOR_TEXT_PRIMARY
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

        # Create step row
        step_row = QWidget()
        step_row.setFixedHeight(18)
        row_layout = QHBoxLayout(step_row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(6)

        prefix_label = QLabel(prefix)
        prefix_label.setStyleSheet(f"color: {color}; font-size: 10px;")
        prefix_label.setFixedWidth(10)

        status_label = QLabel(status_text)
        status_label.setStyleSheet(f"""
            color: {COLOR_TEXT_MUTED};
            font-size: 9px;
            font-family: '{FONT_MONO}', monospace;
        """)
        status_label.setFixedWidth(70)

        step_label = QLabel(step)
        step_label.setStyleSheet(f"""
            color: {color};
            font-size: 10px;
            font-family: '{FONT_MONO}', monospace;
            font-weight: 300;
        """)

        row_layout.addWidget(prefix_label)
        row_layout.addWidget(status_label)
        row_layout.addWidget(step_label)
        row_layout.addStretch()

        # Add to logs with animation
        if status == "executing":
            step_row.setProperty("opacity", 0)
            self.logs_layout.addWidget(step_row)

            # Add spacer to push content up
            spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
            self.logs_layout.addItem(spacer)

            # Fade in animation
            animation = QPropertyAnimation(step_row, b"windowOpacity")
            animation.setDuration(200)
            animation.setStartValue(0)
            animation.setEndValue(1)
            animation.start()

        else:
            # Replace the last step (excluding spacer)
            count = self.logs_layout.count()
            if count > 1:  # At least one widget and spacer
                # Remove the second-to-last item (the step before spacer)
                old_widget = self.logs_layout.itemAt(count - 2).widget()
                if old_widget:
                    self.logs_layout.removeWidget(old_widget)
                    old_widget.deleteLater()

            # Remove spacer temporarily
            if count > 0:
                spacer = self.logs_layout.takeAt(self.logs_layout.count() - 1)

            # Add updated step
            self.logs_layout.addWidget(step_row)

            # Add spacer back
            spacer = QSpacerItem(0, 0, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Expanding)
            self.logs_layout.addItem(spacer)

        # Scroll to bottom
        self.logs_scroll_area.verticalScrollBar().setValue(
            self.logs_scroll_area.verticalScrollBar().maximum()
        )

    async def show_error(self, message: str):
        """Show error message"""
        self.error_message.setText(message)
        self.error_container.setVisible(True)

        # Set error state
        self.status_indicator.setError(True)

        # Change progress bar color to error
        self.progress_bar._fill.setStyleSheet(f"""
            QFrame {{
                background-color: {COLOR_ERROR};
                border-radius: 2px;
            }}
        """)

    async def hide_error(self):
        """Hide error message"""
        self.error_container.setVisible(False)

    @pyqtSlot()
    def on_retry_clicked(self):
        """Handle retry button click"""
        asyncio.create_task(self.retry_initialization())

    async def retry_initialization(self):
        """Retry initialization process"""
        await self.hide_error()
        await self.prepare_screen()