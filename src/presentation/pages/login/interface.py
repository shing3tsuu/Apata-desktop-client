# interface.py
import asyncio
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, pyqtSlot, QTimer, QPropertyAnimation, QEasingCurve, QRect, QPoint
from PyQt6.QtGui import QFont, QPainter, QPen, QColor, QFontDatabase, QRadialGradient, QBrush
import qasync

from .manager import AuthManager

# Futuristic minimalist color palette
COLOR_BG_PRIMARY = "#000000"  # Deep black
COLOR_BG_SECONDARY = "#0A0A0A"  # Slightly lighter black
COLOR_SURFACE = "#121212"  # Dark surface
COLOR_SURFACE_HOVER = "#1A1A1A"  # Hover state
COLOR_BORDER = "#2A2A2A"  # Border gray
COLOR_ACCENT = "#FFFFFF"  # White accent
COLOR_ACCENT_GLOW = "rgba(255, 255, 255, 0.1)"  # Soft white glow
COLOR_TEXT_PRIMARY = "#FFFFFF"  # White text
COLOR_TEXT_SECONDARY = "#AAAAAA"  # Gray text
COLOR_TEXT_MUTED = "#666666"  # Muted text
COLOR_SUCCESS = "#7FFFD4"  # Soft green success
COLOR_ERROR = "#FF3366"  # Soft pink error
COLOR_DISABLED = "#333333"  # Disabled state

# Font settings
FONT_PRIMARY = "SF Pro Display"
FONT_MONO = "SF Mono"


class GlowFrame(QFrame):
    """Frame with soft glow effect and chamfered corners"""

    def __init__(self, parent=None, glow_color=COLOR_ACCENT_GLOW):
        super().__init__(parent)
        self.glow_color = glow_color
        self.setFrameStyle(QFrame.Shape.NoFrame)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Draw main surface with chamfered corners
        pen = QPen(QColor(COLOR_BORDER))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.setBrush(QColor(COLOR_SURFACE))

        # Chamfered corners (8px radius)
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 8, 8)

        # Inner subtle highlight
        painter.setPen(QPen(QColor(255, 255, 255, 20)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(1, 1, self.width() - 2, self.height() - 2, 8, 8)


class FuturisticInput(QLineEdit):
    """Custom input field with futuristic styling"""

    def __init__(self, placeholder="", is_password=False, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self._is_focused = False

        # Устанавливаем placeholder в пустую строку - это важно!
        self.setPlaceholderText("")

        # Basic styling
        self.setStyleSheet(f"""
            QLineEdit {{
                background-color: {COLOR_SURFACE};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                padding: 12px 16px;
                font-size: 14px;
                font-family: '{FONT_PRIMARY}', sans-serif;
                font-weight: 300;
                selection-background-color: {COLOR_TEXT_MUTED};
            }}
            QLineEdit:hover {{
                border-color: {COLOR_TEXT_SECONDARY};
                background-color: {COLOR_SURFACE_HOVER};
            }}
            QLineEdit:focus {{
                border: 2px solid {COLOR_ACCENT};
                background-color: {COLOR_BG_SECONDARY};
                padding: 11px 15px;
            }}
            QLineEdit:disabled {{
                color: {COLOR_TEXT_MUTED};
                background-color: {COLOR_DISABLED};
            }}
        """)

        if is_password:
            self.setEchoMode(QLineEdit.EchoMode.Password)

        # Создаем кастомный label для placeholder
        self._placeholder_label = QLabel(placeholder, self)
        self._placeholder_label.setStyleSheet(f"""
            color: {COLOR_TEXT_MUTED};
            font-size: 14px;
            font-family: '{FONT_PRIMARY}', sans-serif;
            font-weight: 300;
            background: transparent;
        """)
        self._placeholder_label.move(16, 14)

        # Изначально обновляем видимость
        self._update_placeholder_visibility()

        # Подключаем сигнал изменения текста
        self.textChanged.connect(self._update_placeholder_visibility)

    def _update_placeholder_visibility(self):
        """Скрываем label если есть текст"""
        text = self.text()
        self._placeholder_label.setVisible(not text)

    def focusInEvent(self, event):
        """Обработка фокуса"""
        self._is_focused = True
        super().focusInEvent(event)

        # Анимируем только если текст пустой
        if not self.text():
            animation = QPropertyAnimation(self._placeholder_label, b"pos")
            animation.setDuration(150)
            animation.setStartValue(self._placeholder_label.pos())
            animation.setEndValue(QPoint(16, 4))
            animation.start()

        # Обновляем стиль независимо от наличия текста
        self._placeholder_label.setStyleSheet(f"""
            color: {COLOR_ACCENT};
            font-size: 11px;
            font-family: '{FONT_PRIMARY}', sans-serif;
            font-weight: 300;
            background: transparent;
        """)

    def focusOutEvent(self, event):
        """Обработка потери фокуса"""
        self._is_focused = False
        super().focusOutEvent(event)

        # Анимируем только если текст пустой
        if not self.text():
            animation = QPropertyAnimation(self._placeholder_label, b"pos")
            animation.setDuration(150)
            animation.setStartValue(self._placeholder_label.pos())
            animation.setEndValue(QPoint(16, 14))
            animation.start()

        # Возвращаем обычный стиль
        self._placeholder_label.setStyleSheet(f"""
            color: {COLOR_TEXT_MUTED};
            font-size: 14px;
            font-family: '{FONT_PRIMARY}', sans-serif;
            font-weight: 300;
            background: transparent;
        """)


class LoginInterface(QWidget):
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.auth_manager = None
        self._glow_timer = QTimer()
        self._glow_phase = 0

        self.setup_ui()
        self.load_fonts()
        self.setup_background()

    def load_fonts(self):
        """Load modern minimalist fonts"""
        modern_fonts = ["SF Pro Display", "Inter", "Helvetica Neue", "Segoe UI"]

        for font_name in modern_fonts:
            font_id = QFontDatabase.addApplicationFont(font_name)
            if font_id != -1:
                global FONT_PRIMARY
                FONT_PRIMARY = QFontDatabase.applicationFontFamilies(font_id)[0]
                break

    def setup_background(self):
        """Setup subtle animated background"""
        self._glow_timer.timeout.connect(self._update_glow)
        self._glow_timer.start(50)

    def _update_glow(self):
        """Animate subtle background glow"""
        self._glow_phase = (self._glow_phase + 0.02) % (2 * 3.14159)
        self.update()

    def paintEvent(self, event):
        """Draw animated background elements"""
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

    def setup_ui(self):
        """Setup the futuristic minimalist UI"""
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {COLOR_BG_PRIMARY};
                color: {COLOR_TEXT_PRIMARY};
            }}
        """)

        # Main layout
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(60, 40, 60, 40)
        main_layout.setSpacing(0)

        # Header area
        header_layout = QHBoxLayout()

        # App branding
        brand_container = QVBoxLayout()

        app_name = QLabel("APATA")
        app_name.setStyleSheet(f"""
            color: {COLOR_ACCENT};
            font-size: 28px;
            font-weight: 300;
            letter-spacing: 4px;
            margin-bottom: 2px;
        """)

        app_subtitle = QLabel("SECURE COMMUNICATION PLATFORM")
        app_subtitle.setStyleSheet(f"""
            color: {COLOR_TEXT_MUTED};
            font-size: 11px;
            font-weight: 300;
            letter-spacing: 2px;
            font-family: '{FONT_MONO}', monospace;
        """)

        brand_container.addWidget(app_name)
        brand_container.addWidget(app_subtitle)

        header_layout.addLayout(brand_container)
        header_layout.addStretch()

        main_layout.addLayout(header_layout)

        # Center content area
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Login form container with glow
        self.form_container = GlowFrame()
        self.form_container.setFixedSize(420, 380)

        form_layout = QVBoxLayout(self.form_container)
        form_layout.setContentsMargins(40, 40, 40, 40)

        # Form title (moved down with more spacing)
        form_title = QLabel("ACCESS TERMINAL")
        form_title.setStyleSheet(f"""
            color: {COLOR_ACCENT};
            font-size: 20px;
            font-weight: 300;
            letter-spacing: 2px;
            padding-bottom: 4px;
            border-bottom: 1px solid {COLOR_BORDER};
        """)
        form_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Input fields
        input_container = QVBoxLayout()
        input_container.setSpacing(16)

        self.username_field = FuturisticInput("USERNAME")
        self.password_field = FuturisticInput("PASSWORD", is_password=True)

        self.username_field.returnPressed.connect(self.on_login_clicked)
        self.password_field.returnPressed.connect(self.on_login_clicked)

        input_container.addWidget(self.username_field)
        input_container.addWidget(self.password_field)

        # Login button
        self.login_button = QPushButton("AUTHENTICATE")
        self.login_button.setFixedHeight(52)
        self.login_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {COLOR_SURFACE};
                color: {COLOR_TEXT_PRIMARY};
                border: 1px solid {COLOR_BORDER};
                border-radius: 6px;
                font-size: 14px;
                font-weight: 400;
                letter-spacing: 1px;
                text-transform: uppercase;
                font-family: '{FONT_MONO}', monospace;
                padding: 16px;
            }}
            QPushButton:hover {{
                background-color: {COLOR_SURFACE_HOVER};
                border-color: {COLOR_TEXT_SECONDARY};
                color: {COLOR_ACCENT};
            }}
            QPushButton:pressed {{
                background-color: {COLOR_ACCENT};
                color: {COLOR_BG_PRIMARY};
                border-color: {COLOR_ACCENT};
            }}
            QPushButton:disabled {{
                background-color: {COLOR_DISABLED};
                color: {COLOR_TEXT_MUTED};
                border-color: {COLOR_BORDER};
            }}
        """)
        self.login_button.clicked.connect(self.on_login_clicked)

        # Status and progress area (simplified)
        status_area = QFrame()
        status_area.setFixedHeight(40)
        status_layout = QVBoxLayout(status_area)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(8)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet(f"""
            color: {COLOR_TEXT_SECONDARY};
            font-size: 12px;
            font-family: '{FONT_MONO}', monospace;
            font-weight: 300;
        """)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # Progress bar
        self.progress_bar = QFrame()
        self.progress_bar.setFixedHeight(2)
        self.progress_bar.setStyleSheet(f"""
            background-color: {COLOR_BORDER};
            border-radius: 1px;
        """)
        self.progress_bar.setMaximumWidth(340)
        self.progress_bar.setMinimumWidth(0)

        self.progress_fill = QFrame(self.progress_bar)
        self.progress_fill.setFixedHeight(2)
        self.progress_fill.setStyleSheet(f"""
            background-color: {COLOR_ACCENT};
            border-radius: 1px;
        """)
        self.progress_fill.setGeometry(0, 0, 0, 2)

        status_layout.addWidget(self.status_label)
        status_layout.addWidget(self.progress_bar)

        # Assemble form
        form_layout.addWidget(form_title)
        form_layout.addSpacing(16)  # Adjusted spacing
        form_layout.addLayout(input_container)
        form_layout.addWidget(self.login_button)
        form_layout.addSpacing(16)  # Adjusted spacing
        form_layout.addWidget(status_area)

        center_layout.addWidget(self.form_container)
        main_layout.addWidget(center_widget, stretch=1)

        # Footer
        footer_widget = QFrame()
        footer_widget.setFixedHeight(40)
        footer_widget.setStyleSheet(f"""
            QFrame {{
                border-top: 1px solid {COLOR_BORDER};
                background-color: transparent;
            }}
        """)

        footer_layout = QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 12, 0, 0)

        # System info
        system_info = QLabel("ENCRYPTION • AES-256-GCM • ECDH-X25519 • ECDSA-SECP256R1")
        system_info.setStyleSheet(f"""
            color: {COLOR_TEXT_MUTED};
            font-size: 11px;
            font-family: '{FONT_MONO}', monospace;
            font-weight: 300;
            letter-spacing: 1px;
        """)

        footer_layout.addWidget(system_info)
        footer_layout.addStretch()

        # Session info
        session_label = QLabel(f"SESSION: {self.generate_session_id()}")
        session_label.setStyleSheet(f"""
            color: {COLOR_TEXT_SECONDARY};
            font-size: 11px;
            font-family: '{FONT_MONO}', monospace;
            font-weight: 300;
            letter-spacing: 1px;
        """)

        footer_layout.addWidget(session_label)

        main_layout.addWidget(footer_widget)
        self.setLayout(main_layout)

        # Start entry animation
        QTimer.singleShot(100, self.play_entry_animation)

    def generate_session_id(self):
        """Generate session identifier"""
        import random
        return f"{random.randint(100000, 999999)}"

    def play_entry_animation(self):
        """Play form entry animation"""
        # Fade in form
        animation = QPropertyAnimation(self.form_container, b"windowOpacity")
        animation.setDuration(400)
        animation.setStartValue(0)
        animation.setEndValue(1)
        animation.start()

        # Slide up slightly
        pos_animation = QPropertyAnimation(self.form_container, b"pos")
        pos_animation.setDuration(400)
        pos_animation.setStartValue(self.form_container.pos() + QPoint(0, 20))
        pos_animation.setEndValue(self.form_container.pos())
        pos_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        pos_animation.start()

    @pyqtSlot()
    def on_login_clicked(self):
        """Handle login button click"""
        asyncio.create_task(self.login_async())

    async def login_async(self):
        """Async login handler"""
        username = self.username_field.text().strip()
        password = self.password_field.text().strip()

        if not username or not password:
            await self.update_status("CREDENTIALS REQUIRED", COLOR_ERROR)
            self.play_error_animation()
            return

        await self.set_ui_loading(True)
        await self.update_status("INITIALIZING SECURE HANDSHAKE...", COLOR_TEXT_SECONDARY)

        # Animate progress
        self.animate_progress(170)  # 50%

        try:
            if not self.auth_manager:
                self.auth_manager = AuthManager(
                    self.main_window.app_state,
                    self.main_window.container
                )

            success, message = await self.auth_manager.authenticate_user(
                username, password
            )

            if success:
                await self.update_status("ACCESS GRANTED", COLOR_SUCCESS)
                self.animate_progress(340)  # 100%
                self.play_success_animation()

                await asyncio.sleep(1.2)
                await self.main_window.show_screen("loading")
            else:
                raise Exception(message)

        except Exception as ex:
            await self.update_status(f"AUTHENTICATION FAILED: {str(ex)}", COLOR_ERROR)
            self.play_error_animation()

        finally:
            await self.set_ui_loading(False)

    async def update_status(self, message: str, color: str):
        """Update status label"""
        self.status_label.setText(message)
        self.status_label.setStyleSheet(f"""
            color: {color};
            font-size: 12px;
            font-family: '{FONT_MONO}', monospace;
            font-weight: 300;
        """)

        # Fade animation
        fade = QPropertyAnimation(self.status_label, b"windowOpacity")
        fade.setDuration(150)
        fade.setStartValue(0)
        fade.setEndValue(1)
        fade.start()

    async def set_ui_loading(self, loading: bool):
        """Set UI loading state"""
        self.login_button.setDisabled(loading)
        self.username_field.setDisabled(loading)
        self.password_field.setDisabled(loading)

        if loading:
            self.login_button.setText("AUTHENTICATING...")
        else:
            self.login_button.setText("AUTHENTICATE")

    def animate_progress(self, width: int):
        """Animate progress bar"""
        animation = QPropertyAnimation(self.progress_fill, b"minimumWidth")
        animation.setDuration(600)
        animation.setStartValue(self.progress_fill.width())
        animation.setEndValue(width)
        animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        animation.start()

    def play_error_animation(self):
        """Play error animation"""
        # Pulse animation
        pulse = QPropertyAnimation(self.form_container, b"geometry")
        pulse.setDuration(100)
        pulse.setStartValue(self.form_container.geometry())
        pulse.setKeyValueAt(0.33, QRect(
            self.form_container.x() - 3,
            self.form_container.y(),
            self.form_container.width(),
            self.form_container.height()
        ))
        pulse.setKeyValueAt(0.66, QRect(
            self.form_container.x() + 3,
            self.form_container.y(),
            self.form_container.width(),
            self.form_container.height()
        ))
        pulse.setEndValue(self.form_container.geometry())
        pulse.start()

        # Progress bar error color
        self.progress_fill.setStyleSheet(f"""
            background-color: {COLOR_ERROR};
            border-radius: 1px;
        """)

    def play_success_animation(self):
        """Play success animation"""
        # Glow pulse
        glow = QPropertyAnimation(self.form_container, b"windowOpacity")
        glow.setDuration(300)
        glow.setStartValue(1)
        glow.setKeyValueAt(0.5, 1.2)
        glow.setEndValue(1)
        glow.start()

        # Progress bar success color
        self.progress_fill.setStyleSheet(f"""
            background-color: {COLOR_SUCCESS};
            border-radius: 1px;
        """)

    async def prepare_screen(self, **kwargs):
        """Prepare screen for display"""
        self.username_field.clear()
        self.password_field.clear()
        self.status_label.setText("")
        self.progress_fill.setFixedWidth(0)
        self.progress_fill.setStyleSheet(f"""
            background-color: {COLOR_ACCENT};
            border-radius: 1px;
        """)
        await self.set_ui_loading(False)
        self.username_field.setFocus()

        # Restart background animation
        self._glow_timer.start()