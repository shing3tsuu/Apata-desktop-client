from uuid import UUID

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (
    QApplication,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from src.adapters.database.structures import ContactStatusEnum
from src.providers.cache import ChatCache, ContactCache


class ChatMemberCandidateRow(QWidget):
    clicked = pyqtSignal(object)

    def __init__(
        self,
        contact: ContactCache,
        color_primary: str,
        color_border: str,
        color_background: str,
        color_text: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.contact = contact
        self.color_primary = color_primary
        self.color_border = color_border
        self.color_background = color_background
        self.color_text = color_text
        self._busy = False
        self.setFixedHeight(44)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("background: transparent;")

    def set_busy(self, busy: bool) -> None:
        self._busy = busy
        self.setCursor(
            Qt.CursorShape.BusyCursor
            if busy
            else Qt.CursorShape.PointingHandCursor
        )
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if (
            not self._busy
            and event.button() == Qt.MouseButton.LeftButton
            and self.rect().contains(event.position().toPoint())
        ):
            self.clicked.emit(self.contact)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        margin = 2
        triangle_width = 7
        path = QPainterPath()
        path.moveTo(margin + triangle_width, margin)
        path.lineTo(margin, self.height() / 2)
        path.lineTo(margin + triangle_width, self.height() - margin)
        path.lineTo(self.width() - margin - triangle_width, self.height() - margin)
        path.lineTo(self.width() - margin, self.height() / 2)
        path.lineTo(self.width() - margin - triangle_width, margin)
        path.closeSubpath()

        painter.fillPath(path, QColor(self.color_background))
        border_color = self.color_primary if self._busy else self.color_border
        painter.setPen(QPen(QColor(border_color), 1))
        painter.drawPath(path)

        painter.setPen(QColor(self.color_text))
        painter.setFont(QFont("Roboto", 10))
        painter.drawText(
            self.rect().adjusted(16, 0, -12, 0),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.contact.username,
        )


class ChatMembersPanel(QWidget):
    add_requested = pyqtSignal(object, object)
    closed = pyqtSignal()

    def __init__(
        self,
        color_primary: str,
        color_border: str,
        color_background: str,
        color_text: str,
        color_scrollbar: str,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_border = color_border
        self.color_background = color_background
        self.color_text = color_text
        self.color_scrollbar = color_scrollbar
        self._chat: ChatCache | None = None
        self._contacts: list[ContactCache] = []
        self._current_user_id: UUID | None = None
        self._anchor_widget: QWidget | None = None
        self._application_filter_installed = False
        self._busy_user_ids: set[UUID] = set()
        self._rows: dict[UUID, ChatMemberCandidateRow] = {}
        self.setMinimumSize(220, 180)
        self.setStyleSheet("background: transparent;")
        self._setup_ui()
        self.hide()

    @property
    def candidate_contacts(self) -> list[ContactCache]:
        return [row.contact for row in self._rows.values()]

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        title = QLabel("A D D   T O   C H A T", self)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setFixedHeight(28)
        title.setStyleSheet(
            f"color: {self.color_primary}; background: transparent; "
            "font-family: 'Roboto Condensed'; font-size: 10px;"
        )
        layout.addWidget(title)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll.setStyleSheet(
            f"""
            QScrollArea {{ border: none; background: {self.color_background}; }}
            QScrollBar:vertical {{
                background: {self.color_background};
                width: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: {self.color_scrollbar};
                border-radius: 2px;
            }}
            QScrollBar::add-line:vertical,
            QScrollBar::sub-line:vertical {{ height: 0px; }}
            """
        )
        self.content = QWidget(self.scroll)
        self.content.setStyleSheet(f"background: {self.color_background};")
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(4)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, stretch=1)

    def toggle(
        self,
        chat: ChatCache,
        contacts: list[ContactCache],
        current_user_id: UUID | None,
        anchor_widget: QWidget,
    ) -> None:
        if (
            self.isVisible()
            and self._chat is not None
            and self._chat.server_chat_id == chat.server_chat_id
        ):
            self.close_panel()
            return
        self.open_for(chat, contacts, current_user_id, anchor_widget)

    def open_for(
        self,
        chat: ChatCache,
        contacts: list[ContactCache],
        current_user_id: UUID | None,
        anchor_widget: QWidget,
    ) -> None:
        self._chat = chat
        self._contacts = contacts
        self._current_user_id = current_user_id
        self._anchor_widget = anchor_widget
        self._rebuild_rows()
        self.show()
        self.raise_()
        self._install_application_filter()

    def update_context(
        self,
        chat: ChatCache,
        contacts: list[ContactCache],
        current_user_id: UUID | None,
    ) -> None:
        self._chat = chat
        self._contacts = contacts
        self._current_user_id = current_user_id
        if self.isVisible():
            self._rebuild_rows()

    def set_anchor_widget(self, anchor_widget: QWidget) -> None:
        self._anchor_widget = anchor_widget

    def close_panel(self) -> None:
        if self.isVisible():
            self.hide()

    def finish_add(
        self,
        contact: ContactCache,
        success: bool,
        failure_message: str | None = None,
    ) -> None:
        self._busy_user_ids.discard(contact.server_user_id)
        if success:
            self._rebuild_rows()
            return
        row = self._rows.get(contact.server_user_id)
        if row is not None:
            row.set_busy(False)
            if failure_message:
                row.setToolTip(failure_message)

    def _candidate_contacts(self) -> list[ContactCache]:
        if self._chat is None:
            return []
        participant_ids = {
            participant.server_user_id for participant in self._chat.participants
        }
        return sorted(
            (
                contact
                for contact in self._contacts
                if contact.status is ContactStatusEnum.ACCEPTED
                and contact.server_user_id != self._current_user_id
                and contact.server_user_id not in participant_ids
            ),
            key=lambda contact: contact.username.casefold(),
        )

    def _rebuild_rows(self) -> None:
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._rows.clear()

        candidates = self._candidate_contacts()
        if not candidates:
            placeholder = QLabel("N O   C O N T A C T S", self.content)
            placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
            placeholder.setStyleSheet(
                f"color: {self.color_border}; background: transparent; "
                "font-family: 'Roboto Condensed'; font-size: 9px;"
            )
            placeholder.setFixedHeight(44)
            self.content_layout.addWidget(placeholder)
            return

        for contact in candidates:
            row = ChatMemberCandidateRow(
                contact=contact,
                color_primary=self.color_primary,
                color_border=self.color_border,
                color_background=self.color_background,
                color_text=self.color_text,
                parent=self.content,
            )
            row.set_busy(contact.server_user_id in self._busy_user_ids)
            row.clicked.connect(self._request_add)
            self._rows[contact.server_user_id] = row
            self.content_layout.addWidget(row)

    def _request_add(self, contact: ContactCache) -> None:
        chat = self._chat
        if chat is None or contact.server_user_id in self._busy_user_ids:
            return
        self._busy_user_ids.add(contact.server_user_id)
        row = self._rows.get(contact.server_user_id)
        if row is not None:
            row.set_busy(True)
        self.add_requested.emit(chat, contact)

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
            global_position = (
                event.globalPosition().toPoint()
                if hasattr(event, "globalPosition")
                else None
            )
            inside_panel = (
                global_position is not None
                and self.rect().contains(self.mapFromGlobal(global_position))
            ) or target is self or (
                target is not None and self.isAncestorOf(target)
            )
            anchor = self._anchor_widget
            inside_anchor = anchor is not None and (
                (
                    global_position is not None
                    and anchor.rect().contains(anchor.mapFromGlobal(global_position))
                )
                or target is anchor
                or (target is not None and anchor.isAncestorOf(target))
            )
            if not inside_panel and not inside_anchor:
                self.close_panel()
        return super().eventFilter(watched, event)

    def hideEvent(self, event) -> None:
        self._remove_application_filter()
        self.closed.emit()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(self.color_background))
        painter.setPen(QPen(QColor(self.color_primary), 1))
        painter.drawRect(self.rect().adjusted(0, 0, -1, -1))
