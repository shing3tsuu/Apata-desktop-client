from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)


class LocalAccountsPanel(QFrame):
    account_selected = pyqtSignal(str)

    def __init__(
        self,
        color_primary: str,
        color_background: str,
        color_text: str,
        parent=None,
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_background = color_background
        self.color_text = color_text

        self.setFixedSize(230, 166)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setStyleSheet(
            f"""
            LocalAccountsPanel {{
                background-color: {self.color_background};
                border: 1px solid {self.color_primary};
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                width: 7px;
                background: transparent;
                margin: 4px 1px 4px 0;
            }}
            QScrollBar::handle:vertical {{
                background: {self.color_primary};
                min-height: 20px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{
                height: 0;
            }}
            """
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 3, 6)
        layout.setSpacing(0)

        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.scroll_area.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )

        self.content = QWidget()
        self.content.setStyleSheet("background: transparent;")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(2)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self.scroll_area.setWidget(self.content)
        layout.addWidget(self.scroll_area)

    def set_accounts(self, usernames: list[str]):
        self._clear_accounts()

        if not usernames:
            self._set_message("NO LOCAL ACCOUNTS")
            return

        for username in usernames:
            account_button = QPushButton(username)
            account_button.setCursor(Qt.CursorShape.PointingHandCursor)
            account_button.setFixedHeight(34)
            account_button.setFont(QFont("Roboto", 11))
            account_button.setStyleSheet(
                f"""
                QPushButton {{
                    background: transparent;
                    border: none;
                    color: {self.color_text};
                    padding: 0 10px;
                    text-align: left;
                }}
                QPushButton:hover {{
                    background: {self.color_primary};
                    color: {self.color_background};
                }}
                QPushButton:pressed {{
                    background: {self.color_primary};
                    color: {self.color_background};
                }}
                """
            )
            account_button.clicked.connect(
                lambda checked=False, value=username: self.account_selected.emit(value)
            )
            self.content_layout.addWidget(account_button)

        self.content_layout.addStretch()

    def set_loading(self):
        self._clear_accounts()
        self._set_message("LOADING LOCAL ACCOUNTS...")

    def _set_message(self, message: str):
        message_label = QLabel(message)
        message_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        message_label.setFont(QFont("Roboto", 10))
        message_label.setStyleSheet(
            f"color: {self.color_text}; background: transparent;"
        )
        self.content_layout.addWidget(message_label)

    def _clear_accounts(self):
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
