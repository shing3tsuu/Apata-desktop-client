from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea, QSizePolicy
from PyQt6.QtCore import Qt, QRect, QTimer, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QFont, QPainterPath


# Заглушка — потом заменишь на данные из БД
STUB_CONTACTS = [
    {"username": "ghost_user", "status": "O N L I N E"},
    {"username": "xX_n0name_Xx", "status": "O F F L I N E"},
    {"username": "anon_777", "status": "O N L I N E"},
]


class ContactCard(QWidget):
    selected = pyqtSignal(dict)  # отдаёт данные контакта при клике

    def __init__(
        self, contact: dict, color_primary: str, color_inactive: str, parent=None
    ):
        super().__init__(parent)
        self.contact = contact
        self.color_primary = color_primary
        self.color_inactive = color_inactive

        self.is_selected = False
        self.current_color = color_inactive

        self.setFixedHeight(60)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        target = self.color_primary if selected else self.color_inactive
        self._animate_to(target)

    def _animate_to(self, target_color: str):
        self._anim_start = QColor(self.current_color)
        self._anim_end = QColor(target_color)
        self._anim_step = 0
        self._anim_steps = 20

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(15)

    def _tick(self):
        if self._anim_step >= self._anim_steps:
            self._timer.stop()
            return

        ratio = self._anim_step / self._anim_steps
        r = int(
            self._anim_start.red()
            + (self._anim_end.red() - self._anim_start.red()) * ratio
        )
        g = int(
            self._anim_start.green()
            + (self._anim_end.green() - self._anim_start.green()) * ratio
        )
        b = int(
            self._anim_start.blue()
            + (self._anim_end.blue() - self._anim_start.blue()) * ratio
        )

        self.current_color = QColor(r, g, b).name()
        self.update()
        self._anim_step += 1

    def mousePressEvent(self, event):
        self.selected.emit(self.contact)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tw = 10
        margin_x = 12
        margin_y = 8
        w = self.width() - margin_x * 2
        h = self.height() - margin_y * 2

        path = QPainterPath()
        path.moveTo(margin_x + tw, margin_y)
        path.lineTo(margin_x, margin_y + h / 2)
        path.lineTo(margin_x + tw, margin_y + h)
        path.lineTo(margin_x + w - tw, margin_y + h)
        path.lineTo(margin_x + w, margin_y + h / 2)
        path.lineTo(margin_x + w - tw, margin_y)
        path.closeSubpath()

        # Заливка — полностью цветом карточки (серый → зелёный)
        painter.fillPath(path, QColor(self.current_color))
        pen = QPen(QColor(self.current_color))
        pen.setWidth(1)
        painter.setPen(pen)
        painter.drawPath(path)

        # Имя пользователя — всегда чёрный
        name_font = QFont("Roboto", 11)
        painter.setFont(name_font)
        painter.setPen(QColor("#000000"))
        painter.drawText(
            QRect(margin_x + tw + 8, margin_y, w - tw * 2 - 8, h // 2 + 4),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            f"⛛ ⌌ {self.contact.get('username', '???').upper()} ⌏",
        )

        # Статус — чёрный, чуть прозрачнее
        status_font = QFont("Roboto", 8)
        painter.setFont(status_font)
        status_color = QColor("#000000")
        status_color.setAlphaF(0.55)
        painter.setPen(status_color)
        painter.drawText(
            QRect(margin_x + tw + 8, margin_y + h // 2, w - tw * 2 - 8, h // 2),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            self.contact.get("status", ""),
        )


class ContactList(QWidget):
    contact_selected = pyqtSignal(dict)

    def __init__(self, color_primary: str, color_inactive: str, parent=None):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_inactive = color_inactive

        self._cards: list[ContactCard] = []
        self._selected_card: ContactCard | None = None

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._layout = layout
        self.setLayout(layout)

        # Загружаем заглушку
        for contact in STUB_CONTACTS:
            self.add_contact(contact)

    def add_contact(self, contact: dict):
        card = ContactCard(contact, self.color_primary, self.color_inactive)
        card.selected.connect(self._on_card_selected)
        self._cards.append(card)
        self._layout.addWidget(card)

    def _on_card_selected(self, contact: dict):
        # Снимаем выделение с предыдущего
        if self._selected_card:
            self._selected_card.set_selected(False)

        # Находим и выделяем нажатый
        for card in self._cards:
            if card.contact is contact:
                card.set_selected(True)
                self._selected_card = card
                break

        self.contact_selected.emit(contact)
