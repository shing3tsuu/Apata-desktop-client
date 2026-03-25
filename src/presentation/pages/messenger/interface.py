from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QFrame,
)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath

from src.presentation.pages import AppState
from .manager import MessengerManager

from .panels import ContactsPanel, MessagesPanel, PanelDivider

COLOR_PRIMARY = "#b3ff15"
COLOR_SECONDARY = "#000000"
COLOR_THIRD = "#2b2b2b"
COLOR_FOURTH = "#6115ff"
COLOR_ERROR = "#ff153e"


class MessengerInterface(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("background-color: #000000;")

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.contacts_panel = ContactsPanel(
            "▙▚▜ C O N T Ʌ C T S ", COLOR_PRIMARY, COLOR_THIRD, COLOR_FOURTH
        )
        root_layout.addWidget(self.contacts_panel, stretch=3)

        divider = PanelDivider(COLOR_THIRD)
        root_layout.addWidget(divider)

        self.messages_panel = MessagesPanel(
            "▌▌▌ M Ξ S S Ʌ G Ξ S", COLOR_PRIMARY, COLOR_THIRD, COLOR_FOURTH
        )
        root_layout.addWidget(self.messages_panel, stretch=7)

        self.setLayout(root_layout)

    async def prepare_screen(self, **kwargs):
        pass
