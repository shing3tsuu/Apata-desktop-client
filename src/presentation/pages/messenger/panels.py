from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QScrollArea,
)
from PyQt6.QtCore import Qt, QRect
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath

from .fields import MessageField
from .contacts import ContactList
from .messages import MessagesView

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.bmp'}

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
    def __init__(
        self,
        title: str,
        color_primary: str,
        color_third: str,
        color_fourth: str,
        parent=None,
    ):
        super().__init__(parent)
        self.title = title
        self.color_primary = color_primary
        self.color_third = color_third
        self.color_fourth = color_fourth
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background-color: #000000;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = PanelHeader(
            self.title, self.color_primary, self.color_third, self.color_fourth
        )
        layout.addWidget(header)

        # Скролл-зона для списка контактов
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet("""
            QScrollArea { border: none; background: #000000; }
            QScrollBar:vertical { background: #000000; width: 4px; }
            QScrollBar::handle:vertical { background: #45464C; border-radius: 2px; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
        """)

        self.contact_list = ContactList(self.color_primary, self.color_third)
        self.contact_list.contact_selected.connect(self._on_contact_selected)
        scroll.setWidget(self.contact_list)

        layout.addWidget(scroll, stretch=1)
        self.setLayout(layout)

    def _on_contact_selected(self, contact: dict):
        # Здесь потом подключишь переход к диалогу
        print(f"[ContactsPanel] selected: {contact['username']}")


class MessagesPanel(QWidget):
    def __init__(
        self,
        title: str,
        color_primary: str,
        color_third: str,
        color_fourth: str,
        parent=None,
    ):
        super().__init__(parent)
        self.title = title
        self.color_primary = color_primary
        self.color_third = color_third
        self.color_fourth = color_fourth
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self._setup_ui()

    def _setup_ui(self):
        self.setStyleSheet("background-color: #000000;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = PanelHeader(
            self.title, self.color_primary, self.color_third, self.color_fourth
        )
        layout.addWidget(header)

        self.messages_view = MessagesView(self.color_primary, self.color_fourth)
        layout.addWidget(self.messages_view, stretch=1)

        self.message_field = MessageField(
            self.color_primary, self.color_third, self.color_fourth
        )
        self.message_field.message_sent.connect(self._on_message_sent)
        self.message_field.file_sent.connect(self._on_file_sent)
        layout.addWidget(self.message_field)

        self.setLayout(layout)

    def _on_message_sent(self, text: str):
        self.messages_view.message_list.add_message(f"‹ {text.upper()} ›", is_mine=True)
        self.messages_view._scroll_to_bottom()

    def _on_file_sent(self, path: str):
        import os
        ext = os.path.splitext(path)[1].lower()

        if ext in IMAGE_EXTENSIONS:
            self.messages_view.message_list.add_image(path, is_mine=True)
        else:
            filename = path.split("/")[-1]
            self.messages_view.message_list.add_message(
                f"‹ ⎙ {filename.upper()} ›", is_mine=True
            )

        self.messages_view._scroll_to_bottom()


class PanelHeader(QWidget):
    def __init__(
        self,
        title: str,
        color_primary: str,
        color_third: str,
        color_fourth: str,
        parent=None,
    ):
        super().__init__(parent)
        self.title = title
        self.color_primary = color_primary
        self.color_third = color_third
        self.color_fourth = color_fourth
        self.setFixedHeight(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pen = QPen(QColor(self.color_third))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        painter.setBrush(QColor(self.color_primary))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRect(0, 12, 3, 16)

        font = QFont("Roboto", 11)
        painter.setFont(font)
        painter.setPen(QColor(self.color_primary))
        painter.drawText(
            QRect(14, 0, self.width() - 14, self.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
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
