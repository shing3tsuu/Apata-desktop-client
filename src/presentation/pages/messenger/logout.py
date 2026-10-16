from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from .buttons import LogoutConfirmationButton


class LogoutConfirmationCard(QWidget):
    confirmed = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(
        self,
        color_primary: str,
        color_inactive: str,
        color_background: str,
        color_text: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_inactive = color_inactive
        self.color_background = color_background
        self.color_text = color_text
        self.setFixedSize(520, 180)
        self.setStyleSheet("background: transparent;")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(38, 18, 38, 18)
        layout.setSpacing(12)

        self.question_label = QLabel(
            "A R E  Y O U  S U R E  T O  L O G O U T ?"
        )
        self.question_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.question_label.setFont(
            QFont("Roboto Condensed", 14, QFont.Weight.Normal)
        )
        self.question_label.setStyleSheet(
            f"background: transparent; border: none; color: {self.color_text};"
        )
        layout.addWidget(self.question_label, stretch=1)

        buttons = QWidget(self)
        buttons.setStyleSheet("background: transparent;")
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.setSpacing(18)

        self.yes_button = LogoutConfirmationButton(
            "Y E S",
            self.color_inactive,
            self.color_primary,
            self.color_background,
        )
        self.no_button = LogoutConfirmationButton(
            "N O",
            self.color_inactive,
            self.color_primary,
            self.color_background,
        )
        self.yes_button.clicked.connect(self.confirmed.emit)
        self.no_button.clicked.connect(self.cancelled.emit)
        buttons_layout.addWidget(self.yes_button)
        buttons_layout.addWidget(self.no_button)
        layout.addWidget(buttons, stretch=1)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        triangle_width = 38
        margin = 1
        path = QPainterPath()
        path.moveTo(margin + triangle_width, margin)
        path.lineTo(margin, self.height() / 2)
        path.lineTo(margin + triangle_width, self.height() - margin)
        path.lineTo(self.width() - margin - triangle_width, self.height() - margin)
        path.lineTo(self.width() - margin, self.height() / 2)
        path.lineTo(self.width() - margin - triangle_width, margin)
        path.closeSubpath()

        painter.fillPath(path, QColor(self.color_background))
        painter.setPen(QPen(QColor(self.color_text), 1))
        painter.drawPath(path)


class LogoutConfirmationOverlay(QWidget):
    confirmed = pyqtSignal()

    def __init__(
        self,
        color_primary: str,
        color_inactive: str,
        color_background: str,
        color_text: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.card = LogoutConfirmationCard(
            color_primary,
            color_inactive,
            color_background,
            color_text,
        )
        self.card.confirmed.connect(self._confirm)
        self.card.cancelled.connect(self.close_panel)
        layout.addWidget(self.card)
        self.hide()

    def open_panel(self) -> None:
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        self.show()
        self.raise_()

    def close_panel(self) -> None:
        self.hide()

    def _confirm(self) -> None:
        self.close_panel()
        self.confirmed.emit()
