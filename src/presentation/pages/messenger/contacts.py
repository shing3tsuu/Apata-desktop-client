from PyQt6.QtCore import (
    QEasingCurve,
    QPoint,
    QRect,
    Qt,
    QTimer,
    QVariantAnimation,
    pyqtSignal,
)
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from src.adapters.database.structures import ContactStatusEnum, MessageContentTypeEnum
from src.providers.cache import ChatCache, ContactCache

from .buttons import AddChatParticipantButton, ContactSectionButton
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
        content = (
            f"⎙ {last_message.file_name or last_message.content_type.value.upper()}"
        )

    if not content:
        content = "MESSAGE"
    direction = "Y O U" if last_message.is_outgoing else "T O  Y O U"
    return f"{direction}: {content}"


class ContactCard(QWidget):
    selected = pyqtSignal(object)
    action_requested = pyqtSignal(str, object)
    chat_members_requested = pyqtSignal(object, object)

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
        self._triangle_rotation = 0.0
        self._triangle_animation = QVariantAnimation(self)
        self._triangle_animation.setDuration(180)
        self._triangle_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._triangle_animation.valueChanged.connect(self._set_triangle_rotation)

        self.setFixedHeight(78)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

        self.add_chat_participant_button: AddChatParticipantButton | None = None
        if isinstance(contact, ChatCache):
            self.add_chat_participant_button = AddChatParticipantButton(
                color_active=self.color_primary,
                color_inactive=self.color_inactive,
                parent=self,
            )
            self.add_chat_participant_button.clicked.connect(
                self._request_chat_members
            )
            self.add_chat_participant_button.hide()

    def set_selected(self, selected: bool):
        self.is_selected = selected
        if self.add_chat_participant_button is not None:
            self.add_chat_participant_button.setVisible(selected)
        target = self.color_primary if selected else self.color_inactive
        self._animate_to(target)

    @property
    def triangle_rotation(self) -> float:
        return self._triangle_rotation

    def set_expanded(self, expanded: bool, *, animated: bool = True) -> None:
        target_rotation = 180.0 if expanded else 0.0
        self._triangle_animation.stop()
        if not animated:
            self._triangle_rotation = target_rotation
            self.update()
            return
        self._triangle_animation.setStartValue(self._triangle_rotation)
        self._triangle_animation.setEndValue(target_rotation)
        self._triangle_animation.start()

    def _set_triangle_rotation(self, value: object) -> None:
        if not isinstance(value, (int, float)):
            return
        self._triangle_rotation = float(value)
        self.update()

    def _triangle_color(self) -> str:
        if not isinstance(self.contact, ContactCache):
            return self.color_text
        if self.contact.status is ContactStatusEnum.ACCEPTED and self.contact.online:
            return COLOR_CONTACT_ONLINE
        return COLOR_CONTACT_OFFLINE

    def _draw_triangle(
        self,
        painter: QPainter,
        rectangle: QRect,
        color: str,
    ) -> None:
        painter.save()
        center = rectangle.center()
        painter.translate(center.x(), center.y())
        painter.rotate(self._triangle_rotation)
        painter.translate(-center.x(), -center.y())
        painter.setFont(QFont("Segoe UI Symbol", 13))
        painter.setPen(QColor(color))
        painter.drawText(rectangle, Qt.AlignmentFlag.AlignCenter, "⛛")
        painter.restore()

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

    def _request_chat_members(self) -> None:
        button = self.add_chat_participant_button
        if button is not None and isinstance(self.contact, ChatCache):
            self.chat_members_requested.emit(self.contact, button)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        button = self.add_chat_participant_button
        if button is not None:
            right_edge = self.width() - 22
            button.move(
                right_edge - button.width(),
                (self.height() - button.height()) // 2,
            )

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

        name_font = QFont("Roboto", 11)
        content_left = margin_x + tw + 8
        triangle_width = 19
        triangle_gap = 5
        self._draw_triangle(
            painter,
            QRect(content_left, margin_y, triangle_width, h // 2 + 4),
            self._triangle_color(),
        )

        painter.setFont(name_font)
        painter.setPen(QColor(self.color_text))
        text_left = content_left + triangle_width + triangle_gap
        button_reserve = (
            self.add_chat_participant_button.width() + 8
            if self.add_chat_participant_button is not None
            else 0
        )
        text_right = margin_x + w - tw - button_reserve
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

        status_font = QFont("Roboto", 9)
        painter.setFont(status_font)
        status_color = QColor(self.color_text)
        status_color.setAlphaF(0.55)
        painter.setPen(status_color)
        preview_left_offset = 14
        preview_rect = QRect(
            margin_x + tw + preview_left_offset,
            margin_y + h // 2 - 2,
            w - tw * 2 - preview_left_offset - button_reserve,
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


class ChatParticipantCard(ContactCard):
    def __init__(
        self,
        contact: ContactCache,
        color_primary: str,
        color_inactive: str,
        color_text: str = COLOR_TEXT,
        color_background: str = COLOR_CONVERSATION_CARD_BACKGROUND,
        parent=None,
    ) -> None:
        self.participant = contact
        super().__init__(
            contact,
            color_primary,
            color_inactive,
            color_text,
            color_background,
            parent,
        )
        self.setFixedHeight(54)

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        triangle_edge = 8
        margin_left = 36
        margin_right = 12
        margin_y = 6
        width = self.width() - margin_left - margin_right
        height = self.height() - margin_y * 2

        path = QPainterPath()
        path.moveTo(margin_left + triangle_edge, margin_y)
        path.lineTo(margin_left, margin_y + height / 2)
        path.lineTo(margin_left + triangle_edge, margin_y + height)
        path.lineTo(self.width() - margin_right - triangle_edge, margin_y + height)
        path.lineTo(self.width() - margin_right, margin_y + height / 2)
        path.lineTo(self.width() - margin_right - triangle_edge, margin_y)
        path.closeSubpath()

        painter.fillPath(path, QColor(self.color_background))
        pen = QPen(QColor(self.current_border_color))
        pen.setWidth(2 if self.is_selected else 1)
        painter.setPen(pen)
        painter.drawPath(path)

        content_left = margin_left + triangle_edge + 8
        triangle_width = 19
        triangle_rectangle = QRect(
            content_left,
            margin_y,
            triangle_width,
            height,
        )
        self._draw_triangle(
            painter,
            triangle_rectangle,
            self._triangle_color(),
        )

        name_font = QFont("Roboto", 10)
        painter.setFont(name_font)
        painter.setPen(QColor(self.color_text))
        text_left = content_left + triangle_width + 5
        text_width = max(0, width - triangle_edge * 2 - 32)
        displayed_name = QFontMetrics(name_font).elidedText(
            self.participant.username,
            Qt.TextElideMode.ElideRight,
            text_width,
        )
        painter.drawText(
            QRect(text_left, margin_y, text_width, height),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            displayed_name,
        )


class ContactList(QWidget):
    contact_selected = pyqtSignal(object)
    contact_action_requested = pyqtSignal(str, object)
    chat_members_requested = pyqtSignal(object, object)

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
        self._chat_participant_cards: dict[ContactCard, list[ChatParticipantCard]] = {}
        self._participant_parents: dict[ChatParticipantCard, ContactCard] = {}
        self._expanded_chat_card: ContactCard | None = None
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
        selected_conversation = (
            self._selected_card.contact
            if self._selected_card is not None
            else None
        )
        expanded_server_chat_id = (
            self._expanded_chat_card.contact.server_chat_id
            if self._expanded_chat_card is not None
            and isinstance(self._expanded_chat_card.contact, ChatCache)
            else None
        )
        for widget in self._dynamic_widgets:
            self._layout.removeWidget(widget)
            widget.deleteLater()
        self._dynamic_widgets.clear()
        self._cards.clear()
        self._section_buttons.clear()
        self._section_cards.clear()
        self._card_sections.clear()
        self._chat_participant_cards.clear()
        self._participant_parents.clear()
        self._expanded_chat_card = None
        self._selected_card = None

        if show_contact_sections is None:
            show_contact_sections = bool(contacts)
        if show_contact_sections:
            self._add_contact_sections(contacts, expand_populated_sections)
        for chat in chats:
            self.add_contact(chat)
        if expanded_server_chat_id is not None:
            restored_card = next(
                (
                    card
                    for card in self._cards
                    if isinstance(card.contact, ChatCache)
                    and card.contact.server_chat_id == expanded_server_chat_id
                ),
                None,
            )
            if restored_card is not None:
                self._set_chat_expanded(restored_card, True, animated=False)
        if selected_conversation is not None:
            self._restore_selection(selected_conversation)

    def _restore_selection(self, conversation: Conversation) -> None:
        card = next(
            (
                item
                for item in self._cards
                if type(item.contact) is type(conversation)
                and item.contact.id == conversation.id
            ),
            None,
        )
        if card is not None:
            section_key = self._card_sections.get(card)
            if section_key is not None and self._expanded_sections[section_key]:
                card.setVisible(True)
            self._select_card(card)
            return

        participant_card = next(
            (
                item
                for item in self._participant_parents
                if isinstance(conversation, ContactCache)
                and item.contact.id == conversation.id
            ),
            None,
        )
        if participant_card is None:
            return
        parent = self._participant_parents[participant_card]
        self._set_chat_expanded(parent, True, animated=False)
        self._select_card(participant_card)

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
        card.selected.connect(
            lambda _conversation, item=card: self._on_card_selected(item)
        )
        card.action_requested.connect(self.contact_action_requested.emit)
        card.chat_members_requested.connect(
            lambda _chat, anchor, item=card: self._on_chat_members_requested(
                item,
                anchor,
            )
        )
        self._cards.append(card)
        self._dynamic_widgets.append(card)
        self._layout.addWidget(card)
        if section_key is not None:
            self._section_cards[section_key].append(card)
            self._card_sections[card] = section_key
        card.setVisible(visible)
        if isinstance(contact, ChatCache):
            self._add_chat_participants(card, contact.participants)

    def _add_chat_participants(
        self,
        chat_card: ContactCard,
        participants: list[ContactCache],
    ) -> None:
        participant_cards: list[ChatParticipantCard] = []
        self._chat_participant_cards[chat_card] = participant_cards
        for participant in participants:
            card = ChatParticipantCard(
                participant,
                self.color_primary,
                self.color_inactive,
                self.color_text,
            )
            card.selected.connect(
                lambda _contact, item=card: self._on_participant_selected(item)
            )
            card.action_requested.connect(self.contact_action_requested.emit)
            card.setVisible(False)
            participant_cards.append(card)
            self._participant_parents[card] = chat_card
            self._dynamic_widgets.append(card)
            self._layout.addWidget(card)

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
            participant_cards = list(self._participant_parents)
            if self._expanded_chat_card is not None:
                participant_cards.sort(
                    key=lambda item: (
                        self._participant_parents[item] is not self._expanded_chat_card
                    )
                )
            participant_card = next(
                (
                    item
                    for item in participant_cards
                    if item.contact is conversation
                    or (
                        isinstance(conversation, ContactCache)
                        and item.contact.id == conversation.id
                    )
                ),
                None,
            )
            if participant_card is None:
                return
            parent = self._participant_parents[participant_card]
            self._set_chat_expanded(parent, True, animated=False)
            self._select_card(participant_card)
            self.contact_selected.emit(participant_card.contact)
            return
        section_key = self._card_sections.get(card)
        if section_key is not None:
            button = self._section_buttons[section_key]
            button.set_expanded(True, animated=False)
            self._set_section_expanded(section_key, True)
        self._activate_primary_card(card, toggle_if_repeated=False)

    def refresh_conversation(self, conversation: Conversation) -> None:
        participant_cards = [
            card for cards in self._chat_participant_cards.values() for card in cards
        ]
        for card in [*self._cards, *participant_cards]:
            if card.contact is conversation or (
                type(card.contact) is type(conversation)
                and card.contact.id == conversation.id
            ):
                card.update()

    def _on_card_selected(self, card: ContactCard) -> None:
        self._activate_primary_card(card, toggle_if_repeated=True)

    def _on_chat_members_requested(
        self,
        card: ContactCard,
        anchor: AddChatParticipantButton,
    ) -> None:
        if not isinstance(card.contact, ChatCache):
            return
        if self._selected_card is not card:
            self._activate_primary_card(card, toggle_if_repeated=False)
        self.chat_members_requested.emit(card.contact, anchor)

    def chat_members_button(
        self,
        chat: ChatCache,
    ) -> AddChatParticipantButton | None:
        card = next(
            (
                item
                for item in self._cards
                if isinstance(item.contact, ChatCache)
                and item.contact.server_chat_id == chat.server_chat_id
            ),
            None,
        )
        return card.add_chat_participant_button if card is not None else None

    def _activate_primary_card(
        self,
        card: ContactCard,
        *,
        toggle_if_repeated: bool,
    ) -> None:
        if (
            toggle_if_repeated
            and card is self._selected_card
            and isinstance(card.contact, ChatCache)
        ):
            self._set_chat_expanded(
                card,
                self._expanded_chat_card is not card,
            )
            return

        if (
            isinstance(card.contact, ChatCache)
            and self._expanded_chat_card is not None
            and self._expanded_chat_card is not card
        ):
            self._set_chat_expanded(self._expanded_chat_card, False)

        self._select_card(card)
        self.contact_selected.emit(card.contact)

    def _on_participant_selected(self, card: ChatParticipantCard) -> None:
        self._select_card(card)
        self.contact_selected.emit(card.contact)

    def _select_card(self, card: ContactCard) -> None:
        if self._selected_card is not None and self._selected_card is not card:
            self._selected_card.set_selected(False)
        card.set_selected(True)
        self._selected_card = card

    def _set_chat_expanded(
        self,
        card: ContactCard,
        expanded: bool,
        *,
        animated: bool = True,
    ) -> None:
        if expanded and self._expanded_chat_card is not None:
            previous = self._expanded_chat_card
            if previous is not card:
                self._set_chat_expanded(previous, False, animated=animated)

        for participant_card in self._chat_participant_cards.get(card, []):
            participant_card.setVisible(expanded)
        card.set_expanded(expanded, animated=animated)
        if expanded:
            self._expanded_chat_card = card
        elif self._expanded_chat_card is card:
            self._expanded_chat_card = None
