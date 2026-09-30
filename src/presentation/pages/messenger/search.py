"""Conversation search controls and UI-only extension points."""

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtWidgets import QSizePolicy, QVBoxLayout, QWidget

from .buttons import CreateChatButton, GlobalSearchToggleButton
from .fields import ConversationSearchField


class ConversationSearchPanel(QWidget):
    search_requested = pyqtSignal(str, bool)
    search_cleared = pyqtSignal()
    create_chat_requested = pyqtSignal()

    def __init__(
        self,
        color_primary: str,
        color_inactive: str,
        parent=None,
    ):
        super().__init__(parent)
        self.color_primary = color_primary
        self.color_inactive = color_inactive
        self._mode = "contacts"
        self._queries = {"contacts": "", "chats": ""}
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self._setup_ui()
        self.set_mode("contacts")

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 4)
        layout.setSpacing(2)

        self.search_field = ConversationSearchField()
        self.create_chat_button = CreateChatButton(self.color_primary)
        self.search_field.set_trailing_widget(self.create_chat_button)
        self.search_field.text_changed.connect(self._on_text_changed)
        self.search_field.search_submitted.connect(self._submit_search)
        self.create_chat_button.clicked.connect(self.create_chat_requested.emit)
        layout.addWidget(self.search_field)

        self.global_search_toggle = GlobalSearchToggleButton(
            self.color_primary,
            self.color_inactive,
        )
        layout.addWidget(self.global_search_toggle)

    @property
    def mode(self) -> str:
        return self._mode

    def set_mode(self, mode: str) -> None:
        if mode not in {"contacts", "chats"}:
            raise ValueError(f"Unsupported search mode: {mode}")

        self._queries[self._mode] = self.search_field.text()
        self._mode = mode
        blocker = QSignalBlocker(self.search_field)
        self.search_field.set_text(self._queries[mode])
        del blocker

        self.search_field.set_placeholder_text(
            "SEARCH CONTACTS" if mode == "contacts" else "SEARCH CHATS"
        )
        self.create_chat_button.setVisible(mode == "chats")
        self._update_global_search_visibility()

    def _on_text_changed(self, text: str) -> None:
        self._queries[self._mode] = text
        self._update_global_search_visibility()
        if not text.strip():
            self.search_cleared.emit()

    def _submit_search(self, text: str) -> None:
        query = text.strip()
        if not query:
            self.search_cleared.emit()
            return

        self.search_requested.emit(
            query,
            self.global_search_toggle.checked if self._mode == "contacts" else False,
        )

    def _update_global_search_visibility(self) -> None:
        show_global = self._mode == "contacts" and bool(
            self.search_field.text().strip()
        )
        self.global_search_toggle.setVisible(show_global)
        self.updateGeometry()
