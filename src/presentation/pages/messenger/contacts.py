from PyQt6.QtCore import QPoint, QRect, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from src.adapters.database.structures import ContactStatusEnum, MessageContentTypeEnum
from src.providers.cache import ChatCache, ContactCache

from .buttons import ContactSectionButton
from .context_menus import ContactContextMenu
from .theme import (
    COLOR_CONTACT_OFFLINE,
    COLOR_CONTACT_ONLINE,
    COLOR_CONVERSATION_CARD_BACKGROUND,
    COLOR_TEXT,
)

Conversation = ContactCache | ChatCache

CONTACT_SECTIONS = (
    ("friends", "F R I E N D S"),
    ("incoming", "I N C O M I N G"),
    ("outgoing", "O U T G O I N G"),
    ("unmapped", "U N M A P P E D"),
    ("blacklist", "B L A C K L I S T"),
)


def conversation_name(conversation: Conversation) -> str:
    if isinstance(conversation, ContactCache):
        return conversation.username
    return conversation.name or f"Chat {str(conversation.server_chat_id)[:8]}"


def conversation_status(conversation: Conversation) -> str:
    if isinstance(conversation, ChatCache):
        return "G R O U P   C H A T"
    if conversation.status == ContactStatusEnum.PENDING_INCOMING:
        return "FRIEND REQUEST"
    if conversation.status == ContactStatusEnum.PENDING_OUTGOING:
        return "REQUEST SENT"
    return ""


def conversation_preview(conversation: Conversation) -> str:
    if not isinstance(conversation, ContactCache) or not conversation.messages:
        return conversation_status(conversation)

    last_message = max(conversation.messages, key=lambda message: message.timestamp)
    if last_message.content_type == MessageContentTypeEnum.TEXT:
        content = " ".join((last_message.content or "").split())
    else:
        content = f"⎙ {last_message.file_name or last_message.content_type.value.upper()}"

    if not content:
        content = "MESSAGE"
    direction = "Y O U" if last_message.is_outgoing else "T O  Y O U"
    return f"{direction}: {content}"


class ContactCard(QWidget):
    selected = pyqtSignal(object)
    action_requested = pyqtSignal(str, object)

    def __init__(
        self,
        contact: Conversation,
        color_primary: str,
        color_inactive: str,
        color_text: str = COLOR_TEXT,
        color_background: str = COLOR_CONVERSATION_CARD_BACKGROUND,
        parent=None,
    ):
        super().__init__(parent)
        self.contact = contact
        self.color_primary = color_primary
        self.color_inactive = color_inactive
        self.color_text = color_text
        self.color_background = color_background

        self.is_selected = False
        self.current_border_color = color_inactive

        self.setFixedHeight(78)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def set_selected(self, selected: bool):
        self.is_selected = selected
        target = self.color_primary if selected else self.color_inactive
        self._animate_to(target)

    def _animate_to(self, target_color: str):
        self._anim_start = QColor(self.current_border_color)
        self._anim_end = QColor(target_color)
        self._anim_step = 0
        self._anim_steps = 20

        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(15)

    def _tick(self):
        if self._anim_step >= self._anim_steps:
            self._timer.stop()
            self.current_border_color = self._anim_end.name()
            self.update()
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

        self.current_border_color = QColor(r, g, b).name()
        self.update()
        self._anim_step += 1

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.selected.emit(self.contact)
        elif event.button() == Qt.MouseButton.RightButton:
            self.selected.emit(self.contact)
        super().mousePressEvent(event)

    def _show_context_menu(self, position: QPoint) -> None:
        if not isinstance(self.contact, ContactCache):
            return
        menu = ContactContextMenu(
            self.contact.status,
            self.color_primary,
            self,
        )
        action = menu.exec_action(self.mapToGlobal(position))
        menu.deleteLater()
        if action is not None:
            self.action_requested.emit(action, self.contact)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        tw = 10
        margin_x = 12
        margin_y = 10
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

        painter.fillPath(path, QColor(self.color_background))
        pen = QPen(QColor(self.current_border_color))
        pen.setWidth(2 if self.is_selected else 1)
        painter.setPen(pen)
        painter.drawPath(path)

        # Имя пользователя — всегда чёрный
        name_font = QFont("Roboto", 11)
        content_left = margin_x + tw + 8
        triangle_width = 19
        triangle_gap = 5
        triangle_color = self.color_text
        if isinstance(self.contact, ContactCache):
            triangle_color = (
                COLOR_CONTACT_ONLINE
                if self.contact.status is ContactStatusEnum.ACCEPTED
                and self.contact.online
                else COLOR_CONTACT_OFFLINE
            )

        painter.setFont(QFont("Segoe UI Symbol", 13))
        painter.setPen(QColor(triangle_color))
        painter.drawText(
            QRect(content_left, margin_y, triangle_width, h // 2 + 4),
            Qt.AlignmentFlag.AlignCenter,
            "⛛",
        )

        painter.setFont(name_font)
        painter.setPen(QColor(self.color_text))
        text_left = content_left + triangle_width + triangle_gap
        text_right = margin_x + w - tw
        maximum_text_width = text_right - text_left
        name_text = f"⌌ {conversation_name(self.contact)} ⌏"
        font_metrics = QFontMetrics(name_font)
        displayed_name = font_metrics.elidedText(
            name_text,
            Qt.TextElideMode.ElideRight,
            maximum_text_width,
        )
        painter.drawText(
            QRect(text_left, margin_y, maximum_text_width, h // 2 + 4),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            displayed_name,
        )

        # Статус — чёрный, чуть прозрачнее
        status_font = QFont("Roboto", 9)
        painter.setFont(status_font)
        status_color = QColor(self.color_text)
        status_color.setAlphaF(0.55)
        painter.setPen(status_color)
        preview_left_offset = 14
        preview_rect = QRect(
            margin_x + tw + preview_left_offset,
            margin_y + h // 2 - 2,
            w - tw * 2 - preview_left_offset,
            h // 2,
        )
        preview_text = QFontMetrics(status_font).elidedText(
            conversation_preview(self.contact),
            Qt.TextElideMode.ElideRight,
            preview_rect.width(),
        )
        painter.drawText(
            preview_rect,
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            preview_text,
        )


class ContactList(QWidget):
    contact_selected = pyqtSignal(object)
    contact_action_requested = pyqtSignal(str, object)

    def __init__(
        self,
        color_primary: str,
        color_inactive: str,
        color_text: str = COLOR_TEXT,
        color_section_background: str = "#161618",
        color_section_text: str = "#FFFFFF",
        color_section_active: str | None = None,
        parent=None,
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_inactive = color_inactive
        self.color_text = color_text
        self.color_section_background = color_section_background
        self.color_section_text = color_section_text
        self.color_section_active = color_section_active or color_primary

        self._cards: list[ContactCard] = []
        self._selected_card: ContactCard | None = None
        self._dynamic_widgets: list[QWidget] = []
        self._section_buttons: dict[str, ContactSectionButton] = {}
        self._section_cards: dict[str, list[ContactCard]] = {}
        self._card_sections: dict[ContactCard, str] = {}
        self._expanded_sections = {key: False for key, _ in CONTACT_SECTIONS}

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(4)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        self._layout = layout
        self.setLayout(layout)

    def set_conversations(
        self,
        contacts: list[ContactCache],
        chats: list[ChatCache],
        *,
        expand_populated_sections: bool = False,
        show_contact_sections: bool | None = None,
    ) -> None:
        for widget in self._dynamic_widgets:
            self._layout.removeWidget(widget)
            widget.deleteLater()
        self._dynamic_widgets.clear()
        self._cards.clear()
        self._section_buttons.clear()
        self._section_cards.clear()
        self._card_sections.clear()
        self._selected_card = None

        if show_contact_sections is None:
            show_contact_sections = bool(contacts)
        if show_contact_sections:
            self._add_contact_sections(contacts, expand_populated_sections)
        for chat in chats:
            self.add_contact(chat)

    def _add_contact_sections(
        self,
        contacts: list[ContactCache],
        expand_populated_sections: bool,
    ) -> None:
        grouped_contacts: dict[str, list[ContactCache]] = {
            key: [] for key, _ in CONTACT_SECTIONS
        }
        for contact in contacts:
            grouped_contacts[self._section_key(contact)].append(contact)

        for section_key, title in CONTACT_SECTIONS:
            if expand_populated_sections:
                self._expanded_sections[section_key] = bool(
                    grouped_contacts[section_key]
                )
            expanded = self._expanded_sections[section_key]
            button = ContactSectionButton(
                title,
                self.color_section_text,
                self.color_section_active,
                self.color_section_background,
                count=len(grouped_contacts[section_key]),
            )
            button.set_expanded(expanded, animated=False)
            button.toggled.connect(
                lambda is_expanded, key=section_key: self._set_section_expanded(
                    key, is_expanded
                )
            )
            self._section_buttons[section_key] = button
            self._section_cards[section_key] = []
            self._dynamic_widgets.append(button)
            self._layout.addWidget(button)

            for contact in grouped_contacts[section_key]:
                self.add_contact(
                    contact,
                    section_key=section_key,
                    visible=expanded,
                )

    @staticmethod
    def _section_key(contact: ContactCache) -> str:
        if contact.status == ContactStatusEnum.ACCEPTED:
            return "friends"
        if contact.status == ContactStatusEnum.PENDING_INCOMING:
            return "incoming"
        if contact.status == ContactStatusEnum.PENDING_OUTGOING:
            return "outgoing"
        if contact.status == ContactStatusEnum.BLACKLIST:
            return "blacklist"
        return "unmapped"

    def _set_section_expanded(self, section_key: str, expanded: bool) -> None:
        self._expanded_sections[section_key] = expanded
        for card in self._section_cards.get(section_key, []):
            card.setVisible(expanded)

    def add_contact(
        self,
        contact: Conversation,
        *,
        section_key: str | None = None,
        visible: bool = True,
    ) -> None:
        card = ContactCard(
            contact,
            self.color_primary,
            self.color_inactive,
            self.color_text,
        )
        card.selected.connect(self._on_card_selected)
        card.action_requested.connect(self.contact_action_requested.emit)
        self._cards.append(card)
        self._dynamic_widgets.append(card)
        self._layout.addWidget(card)
        if section_key is not None:
            self._section_cards[section_key].append(card)
            self._card_sections[card] = section_key
        card.setVisible(visible)

    def select_first(self) -> None:
        if self._cards:
            self.select_conversation(self._cards[0].contact)

    def select_conversation(self, conversation: Conversation) -> None:
        card = next(
            (
                item
                for item in self._cards
                if item.contact is conversation
                or (
                    type(item.contact) is type(conversation)
                    and item.contact.id == conversation.id
                )
            ),
            None,
        )
        if card is None:
            return
        section_key = self._card_sections.get(card)
        if section_key is not None:
            button = self._section_buttons[section_key]
            button.set_expanded(True, animated=False)
            self._set_section_expanded(section_key, True)
        self._on_card_selected(card.contact)

    def refresh_conversation(self, conversation: Conversation) -> None:
        for card in self._cards:
            if card.contact is conversation or (
                type(card.contact) is type(conversation)
                and card.contact.id == conversation.id
            ):
                card.update()
                return

    def _on_card_selected(self, contact: Conversation):
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
