from PyQt6.QtCore import QEvent, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QApplication, QSizePolicy, QVBoxLayout, QWidget

from .buttons import CreateChatSubmitButton
from .fields import ChatNameField


class ChatCreationTitle(QWidget):
    def __init__(
        self,
        color: str,
        color_background: str,
        parent=None,
    ):
        super().__init__(parent)
        self.color = color
        self.color_background = color_background
        self.setFixedHeight(38)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent;")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        triangle_width = 8
        path = QPainterPath()
        path.moveTo(triangle_width, 0)
        path.lineTo(0, self.height() / 2)
        path.lineTo(triangle_width, self.height())
        path.lineTo(self.width() - triangle_width, self.height())
        path.lineTo(self.width(), self.height() / 2)
        path.lineTo(self.width() - triangle_width, 0)
        path.closeSubpath()

        painter.fillPath(path, QColor(self.color_background))
        painter.setPen(QPen(QColor(self.color), 2))
        painter.drawPath(path)
        painter.setPen(QColor(self.color))
        painter.setFont(QFont("Roboto Condensed", 10, QFont.Weight.Normal))
        painter.drawText(
            self.rect(),
            Qt.AlignmentFlag.AlignCenter,
            "▛ C R E A T I N G   C H A T ▟",
        )


class ChatCreationPanel(QWidget):
    create_requested = pyqtSignal(str)

    def __init__(
        self,
        color_inactive: str,
        color_background: str,
        color_text: str,
        parent=None,
    ):
        super().__init__(parent)
        self._anchor_widget: QWidget | None = None
        self._application_filter_installed = False
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 2, 10, 8)
        layout.setSpacing(5)

        self.title = ChatCreationTitle(
            color=color_inactive,
            color_background=color_background,
        )
        layout.addWidget(self.title)

        self.name_field = ChatNameField(
            color_background=color_background,
            color_border=color_inactive,
            color_focus=color_inactive,
            color_text=color_inactive,
        )
        self.name_field.submitted.connect(self._submit)
        layout.addWidget(self.name_field)

        self.create_button = CreateChatSubmitButton(
            color=color_inactive,
            color_background=color_background,
        )
        self.create_button.clicked.connect(self._submit)
        layout.addWidget(self.create_button)
        self.hide()

    def open_panel(self, anchor_widget: QWidget) -> None:
        self._anchor_widget = anchor_widget
        self.show()
        self._install_application_filter()
        QTimer.singleShot(0, self.name_field.setFocus)

    def close_panel(self, *, clear: bool = False) -> None:
        self._remove_application_filter()
        self.set_busy(False)
        if clear:
            self.name_field.clear()
        self.hide()

    def set_busy(self, busy: bool) -> None:
        self.name_field.setReadOnly(busy)
        self.create_button.set_busy(busy)

    def complete_creation(self) -> None:
        self.close_panel(clear=True)

    def _submit(self, name: str | None = None) -> None:
        chat_name = (name if name is not None else self.name_field.text()).strip()
        if not chat_name:
            self.name_field.mark_invalid()
            return
        self.create_requested.emit(chat_name)

    def _install_application_filter(self) -> None:
        application = QApplication.instance()
        if application is None or self._application_filter_installed:
            return
        application.installEventFilter(self)
        self._application_filter_installed = True

    def _remove_application_filter(self) -> None:
        application = QApplication.instance()
        if application is not None and self._application_filter_installed:
            application.removeEventFilter(self)
        self._application_filter_installed = False

    def eventFilter(self, watched, event):
        if self.isVisible() and event.type() == QEvent.Type.MouseButtonPress:
            target = watched if isinstance(watched, QWidget) else None
            if target is None and hasattr(event, "globalPosition"):
                target = QApplication.widgetAt(event.globalPosition().toPoint())

            inside_panel = target is self or (
                target is not None and self.isAncestorOf(target)
            )
            inside_anchor = self._anchor_widget is not None and (
                target is self._anchor_widget
                or (
                    target is not None
                    and self._anchor_widget.isAncestorOf(target)
                )
            )
            if not inside_panel and not inside_anchor:
                self.close_panel()
        return super().eventFilter(watched, event)

    def hideEvent(self, event):
        self._remove_application_filter()
        super().hideEvent(event)
