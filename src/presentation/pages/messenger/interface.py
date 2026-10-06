import asyncio
import logging
from datetime import datetime
from uuid import UUID

from PyQt6.QtWidgets import (
    QHBoxLayout,
    QWidget,
)

from src.adapters.api.dto import ContactPublicDTO
from src.adapters.database.dto import ContactDTO
from src.adapters.database.structures import ContactStatusEnum
from src.presentation.interactors.messenger import (
    AcceptContactRequestInteractor,
    BlacklistContactInteractor,
    CreateChatInteractor,
    SearchContactsGlobalInteractor,
    SearchContactsLocalInteractor,
    SendContactRequestInteractor,
    SendContactTextMessageInteractor,
)
from src.providers.cache import ChatCache, ContactCache
from src.providers.state import AppState

from .demo_data import build_demo_conversations
from .panels import ContactsPanel, MessagesPanel, PanelDivider
from .theme import (
    COLOR_BACKGROUND,
    COLOR_CONTACT_BORDER,
    COLOR_DIVIDER,
    COLOR_ERROR,
    COLOR_MESSAGE_INCOMING,
    COLOR_MESSAGE_OUTGOING,
    COLOR_MESSAGE_PENDING,
    COLOR_PRIMARY,
    COLOR_THIRD,
)

logger = logging.getLogger(__name__)


class MessengerInterface(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self._contacts: list[ContactCache] = []
        self._chats: list[ChatCache] = []
        self._search_task: asyncio.Task[None] | None = None
        self._chat_creation_task: asyncio.Task[None] | None = None
        self._message_tasks: set[asyncio.Task[None]] = set()
        self._contact_action_tasks: set[asyncio.Task[None]] = set()
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet(f"background-color: {COLOR_BACKGROUND};")

        root_layout = QHBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self.contacts_panel = ContactsPanel(
            contacts_title="▙▜ C O N T Ʌ C T S",
            chats_title="▙▚▚▜ C H Ʌ T S",
            color_primary=COLOR_PRIMARY,
            color_third=COLOR_THIRD,
            color_divider=COLOR_DIVIDER,
        )
        root_layout.addWidget(self.contacts_panel, stretch=3)

        divider = PanelDivider(COLOR_DIVIDER)
        root_layout.addWidget(divider)

        self.messages_panel = MessagesPanel(
            "▌▌▌ M Ξ S S Ʌ G Ξ S",
            COLOR_PRIMARY,
            COLOR_MESSAGE_OUTGOING,
            COLOR_MESSAGE_INCOMING,
            COLOR_ERROR,
            COLOR_MESSAGE_PENDING,
            COLOR_PRIMARY,
            COLOR_CONTACT_BORDER,
            COLOR_DIVIDER,
        )
        root_layout.addWidget(self.messages_panel, stretch=7)
        self.contacts_panel.conversation_selected.connect(
            self.messages_panel.show_conversation
        )
        self.contacts_panel.contact_action_requested.connect(
            self._handle_contact_action
        )
        self.contacts_panel.search_requested.connect(self._schedule_search)
        self.contacts_panel.search_cleared.connect(self._cancel_search)
        self.contacts_panel.create_chat_requested.connect(
            self._schedule_chat_creation
        )
        self.messages_panel.text_message_send_requested.connect(
            self._schedule_text_message
        )

        self.setLayout(root_layout)

    def _handle_contact_action(
        self,
        action: str,
        contact: ContactCache,
    ) -> None:
        if self.main_window is None or self.main_window.container is None:
            logger.warning("Cannot perform contact action without application container")
            return
        if action not in {"send_request", "accept_request", "block"}:
            logger.warning("Unsupported contact action: %s", action)
            return

        task = asyncio.create_task(
            self._execute_contact_action(action, contact)
        )
        self._contact_action_tasks.add(task)
        task.add_done_callback(self._contact_action_tasks.discard)

    async def _execute_contact_action(
        self,
        action: str,
        contact: ContactCache,
    ) -> None:
        if self.main_window is None or self.main_window.container is None:
            return
        try:
            if action == "send_request":
                result = await SendContactRequestInteractor()(
                    self.main_window.container,
                    contact,
                )
            elif action == "accept_request":
                result = await AcceptContactRequestInteractor()(
                    self.main_window.container,
                    contact,
                )
            else:
                result = await BlacklistContactInteractor()(
                    self.main_window.container,
                    contact,
                )
            success, status_message, _ = result
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Unexpected contact action error: action=%s contact=%s",
                action,
                contact.server_user_id,
            )
            return

        if not success:
            logger.warning(
                "Contact action failed: action=%s contact=%s reason=%s",
                action,
                contact.server_user_id,
                status_message,
            )
            return

        if all(
            cached.server_user_id != contact.server_user_id
            for cached in self._contacts
        ):
            self._contacts.append(contact)
        self.contacts_panel.set_conversations(self._contacts, self._chats)
        self.contacts_panel.select_conversation(contact)

    async def prepare_screen(self, **kwargs):
        if self.main_window is None or self.main_window.container is None:
            return
        async with self.main_window.container() as request_container:
            app_state = await request_container.get(AppState)
            contacts = app_state.contacts_cache
            chats = app_state.chats_cache
        show_demo = not contacts and not chats
        if show_demo:
            contacts, chats = build_demo_conversations()
        self._contacts = contacts
        self._chats = chats
        self.contacts_panel.set_conversations(self._contacts, self._chats)
        self.messages_panel.show_conversation(None)
        if show_demo:
            self.contacts_panel.select_first_conversation()

    async def refresh_from_state(self) -> None:
        if self.main_window is None or self.main_window.container is None:
            return

        selected = self.messages_panel.selected_conversation
        selected_contact_id = (
            selected.server_user_id if isinstance(selected, ContactCache) else None
        )
        selected_chat_id = (
            selected.server_chat_id if isinstance(selected, ChatCache) else None
        )
        async with self.main_window.container() as request_container:
            app_state = await request_container.get(AppState)
            self._contacts = app_state.contacts_cache
            self._chats = app_state.chats_cache

        self.contacts_panel.set_conversations(self._contacts, self._chats)
        replacement: ContactCache | ChatCache | None = next(
            (
                contact
                for contact in self._contacts
                if contact.server_user_id == selected_contact_id
            ),
            None,
        )
        if replacement is None:
            replacement = next(
                (
                    chat
                    for chat in self._chats
                    if chat.server_chat_id == selected_chat_id
                ),
                None,
            )
        if replacement is not None:
            self.contacts_panel.select_conversation(replacement)
        elif selected is not None:
            self.messages_panel.show_conversation(None)

    def _schedule_search(
        self,
        section: str,
        query: str,
        global_search: bool,
    ) -> None:
        if section != "contacts" or not query.strip():
            return
        if self.main_window is None or self.main_window.container is None:
            return

        self._cancel_search()
        self._search_task = asyncio.create_task(
            self._search_contacts(query, global_search)
        )

    def _cancel_search(self) -> None:
        if self._search_task is not None and not self._search_task.done():
            self._search_task.cancel()
        self._search_task = None

    def _schedule_chat_creation(self, name: str) -> None:
        if (
            self._chat_creation_task is not None
            and not self._chat_creation_task.done()
        ):
            return
        if self.main_window is None or self.main_window.container is None:
            logger.warning("Cannot create a chat without application container")
            self.contacts_panel.finish_chat_creation(False)
            return

        self.contacts_panel.set_chat_creation_busy(True)
        self._chat_creation_task = asyncio.create_task(self._create_chat(name))

    async def _create_chat(self, name: str) -> None:
        current_task = asyncio.current_task()
        try:
            success, status_message, chat = await CreateChatInteractor()(
                self.main_window.container,
                name,
            )
            if not success or chat is None:
                logger.warning("Failed to create chat: %s", status_message)
                self.contacts_panel.finish_chat_creation(False)
                return

            self.contacts_panel.finish_chat_creation(True)
            await self.refresh_from_state()
            self.contacts_panel.select_conversation(chat)
        except asyncio.CancelledError:
            self.contacts_panel.finish_chat_creation(False)
            raise
        except Exception:
            logger.exception("Unexpected chat creation error")
            self.contacts_panel.finish_chat_creation(False)
        finally:
            if self._chat_creation_task is current_task:
                self._chat_creation_task = None

    def _schedule_text_message(
        self,
        request_id: UUID,
        contact: ContactCache,
        text: str,
    ) -> None:
        if self.main_window is None or self.main_window.container is None:
            self.messages_panel.finish_text_message(
                request_id,
                False,
                failure_message="APPLICATION CONTAINER IS NOT AVAILABLE",
            )
            return

        task = asyncio.create_task(
            self._send_text_message(request_id, contact, text)
        )
        self._message_tasks.add(task)
        task.add_done_callback(self._message_tasks.discard)

    async def _send_text_message(
        self,
        request_id: UUID,
        contact: ContactCache,
        text: str,
    ) -> None:
        try:
            success, status_message, saved_message = (
                await SendContactTextMessageInteractor()(
                    self.main_window.container,
                    contact,
                    text,
                )
            )
            server_message_id = (
                saved_message.server_message_id
                if success and saved_message is not None
                else None
            )
            self.messages_panel.finish_text_message(
                request_id,
                success,
                server_message_id,
                status_message if not success else None,
            )
            if success:
                self.contacts_panel.refresh_conversation(contact)
            else:
                logger.warning(
                    "Failed to send a text message to %s: %s",
                    contact.server_user_id,
                    status_message,
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("Unexpected text message sending error")
            self.messages_panel.finish_text_message(
                request_id,
                False,
                failure_message=str(error).upper(),
            )

    async def _search_contacts(self, query: str, global_search: bool) -> None:
        current_task = asyncio.current_task()
        try:
            container = self.main_window.container
            if global_search:
                results = await SearchContactsGlobalInteractor()(container, query)
                contacts = self._map_global_results(results)
            else:
                local_results = await SearchContactsLocalInteractor()(container, query)
                contacts = self._map_local_results(local_results)

            if self._search_task is current_task:
                self.contacts_panel.show_contact_search_results(contacts)
        except asyncio.CancelledError:
            raise
        finally:
            if self._search_task is current_task:
                self._search_task = None

    def _map_local_results(self, results: list[ContactDTO]) -> list[ContactCache]:
        cached_by_id = {contact.id: contact for contact in self._contacts}
        contacts: list[ContactCache] = []
        for result in results:
            cached = cached_by_id.get(result.id)
            if cached is not None:
                contacts.append(cached)
                continue

            contacts.append(
                ContactCache(
                    id=result.id,
                    server_user_id=result.server_user_id,
                    username=result.username,
                    status=result.status,
                    last_seen=result.last_seen,
                    online=result.online,
                    ed_public_key=result.ed_public_key,
                    ecdh_public_key=result.ecdh_public_key,
                )
            )
        return contacts

    def _map_global_results(
        self,
        results: list[ContactPublicDTO],
    ) -> list[ContactCache]:
        cached_by_server_id = {
            contact.server_user_id: contact for contact in self._contacts
        }
        contacts: list[ContactCache] = []
        for result in results:
            try:
                server_user_id = UUID(result.user_id)
            except ValueError:
                continue

            cached = cached_by_server_id.get(server_user_id)
            if cached is not None:
                contacts.append(cached)
                continue

            try:
                status = ContactStatusEnum(result.status)
            except ValueError:
                status = None

            contacts.append(
                ContactCache(
                    id=server_user_id,
                    server_user_id=server_user_id,
                    username=result.username,
                    status=status,
                    last_seen=self._parse_last_seen(result.last_seen),
                    online=result.online,
                    ed_public_key=result.ed_public_key,
                    ecdh_public_key=result.ecdh_public_key,
                )
            )
        return contacts

    @staticmethod
    def _parse_last_seen(value: str | None) -> datetime | None:
        if value is None:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
