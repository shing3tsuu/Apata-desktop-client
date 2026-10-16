import asyncio
import logging
from datetime import datetime
from uuid import UUID

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QWidget,
)

from src.adapters.api.dto import ContactPublicDTO
from src.adapters.database.dto import ContactDTO
from src.adapters.database.structures import ContactStatusEnum
from src.presentation.interactors.messenger import (
    AcceptContactRequestInteractor,
    AddChatParticipantInteractor,
    BlacklistContactInteractor,
    CreateChatInteractor,
    GetChatReplyTargetsInteractor,
    LoadConversationMessagesInteractor,
    LoadConversationFileMessagesInteractor,
    SaveMessageFileToDiskInteractor,
    SearchContactsGlobalInteractor,
    SearchContactsLocalInteractor,
    SendChatTextMessageInteractor,
    SendContactFileMessageInteractor,
    SendContactRequestInteractor,
    SendContactTextMessageInteractor,
)
from src.providers.cache import ChatCache, ContactCache, MessageCache
from src.providers.state import AppState

from .buttons import LogoutButton
from .demo_data import build_demo_conversations
from .fields import ReplySelection
from .logout import LogoutConfirmationOverlay
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
    logout_requested = pyqtSignal()

    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self._contacts: list[ContactCache] = []
        self._chats: list[ChatCache] = []
        self._current_user_id: UUID | None = None
        self._current_username: str | None = None
        self._search_task: asyncio.Task[None] | None = None
        self._chat_creation_task: asyncio.Task[None] | None = None
        self._conversation_loading_task: asyncio.Task[None] | None = None
        self._file_loading_task: asyncio.Task[None] | None = None
        self._chat_participant_tasks: dict[tuple[UUID, UUID], asyncio.Task[None]] = {}
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
        self.contacts_panel.conversation_selected.connect(self._show_conversation)
        self.contacts_panel.contact_action_requested.connect(
            self._handle_contact_action
        )
        self.contacts_panel.chat_members_requested.connect(
            self.messages_panel.toggle_chat_members_panel
        )
        self.contacts_panel.chat_members_panel_close_requested.connect(
            self.messages_panel.close_chat_members_panel
        )
        self.contacts_panel.search_requested.connect(self._schedule_search)
        self.contacts_panel.search_cleared.connect(self._cancel_search)
        self.contacts_panel.create_chat_requested.connect(self._schedule_chat_creation)
        self.messages_panel.text_message_send_requested.connect(
            self._schedule_text_message
        )
        self.messages_panel.file_message_send_requested.connect(
            self._schedule_file_message
        )
        self.messages_panel.file_save_requested.connect(self._schedule_file_save)
        self.messages_panel.chat_participant_add_requested.connect(
            self._schedule_chat_participant_addition
        )

        self.setLayout(root_layout)

        self.logout_confirmation = LogoutConfirmationOverlay(
            color_primary=COLOR_PRIMARY,
            color_inactive=COLOR_THIRD,
            color_background=COLOR_BACKGROUND,
            color_text=COLOR_THIRD,
            parent=self,
        )
        self.logout_confirmation.setGeometry(self.rect())
        self.logout_confirmation.confirmed.connect(self.logout_requested.emit)

        self.logout_button = LogoutButton(
            color_default=COLOR_THIRD,
            color_hover=COLOR_PRIMARY,
            parent=self,
        )
        self.logout_button.clicked.connect(self.logout_confirmation.open_panel)
        self._position_logout_button()
        self.logout_button.show()
        self.logout_button.raise_()

    def _position_logout_button(self) -> None:
        horizontal_margin = 16
        vertical_margin = 9
        self.logout_button.move(
            self.width() - self.logout_button.width() - horizontal_margin,
            vertical_margin,
        )

    def reset_session(self) -> None:
        tasks = [
            self._search_task,
            self._chat_creation_task,
            self._conversation_loading_task,
            self._file_loading_task,
            *self._chat_participant_tasks.values(),
            *self._message_tasks,
            *self._contact_action_tasks,
        ]
        for task in tasks:
            if task is not None and not task.done():
                task.cancel()

        self._search_task = None
        self._chat_creation_task = None
        self._conversation_loading_task = None
        self._file_loading_task = None
        self._chat_participant_tasks.clear()
        self._message_tasks.clear()
        self._contact_action_tasks.clear()
        self._contacts = []
        self._chats = []
        self._current_user_id = None
        self._current_username = None

        self.logout_confirmation.close_panel()
        self.contacts_panel.reset_session()
        self.messages_panel.set_available_contacts([])
        self.messages_panel.set_current_user(None)
        self._show_conversation(None)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not hasattr(self, "logout_button"):
            return
        self.logout_confirmation.setGeometry(self.rect())
        self._position_logout_button()
        if self.logout_confirmation.isVisible():
            self.logout_confirmation.raise_()
        else:
            self.logout_button.raise_()

    def _handle_contact_action(
        self,
        action: str,
        contact: ContactCache,
    ) -> None:
        if self.main_window is None or self.main_window.container is None:
            logger.warning(
                "Cannot perform contact action without application container"
            )
            return
        if action not in {"send_request", "accept_request", "block"}:
            logger.warning("Unsupported contact action: %s", action)
            return

        task = asyncio.create_task(self._execute_contact_action(action, contact))
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
            cached.server_user_id != contact.server_user_id for cached in self._contacts
        ):
            self._contacts.append(contact)
        self.messages_panel.set_available_contacts(
            self._contacts,
            self._current_user_id,
        )
        self.contacts_panel.set_conversations(self._contacts, self._chats)
        self.contacts_panel.select_conversation(contact)

    async def prepare_screen(self, **kwargs):
        if self.main_window is None or self.main_window.container is None:
            return
        async with self.main_window.container() as request_container:
            app_state = await request_container.get(AppState)
            contacts = app_state.contacts_cache
            chats = app_state.chats_cache
            self._current_user_id = app_state.server_user_id
            self._current_username = app_state.username
        show_demo = not contacts and not chats
        if show_demo:
            contacts, chats = build_demo_conversations()
        self._contacts = contacts
        self._chats = chats
        self.messages_panel.set_available_contacts(
            self._contacts,
            self._current_user_id,
        )
        self.messages_panel.set_current_user(self._current_username)
        self.contacts_panel.set_conversations(self._contacts, self._chats)
        self._show_conversation(None)
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
            self._current_user_id = app_state.server_user_id
            self._current_username = app_state.username

        self.messages_panel.set_available_contacts(
            self._contacts,
            self._current_user_id,
        )
        self.messages_panel.set_current_user(self._current_username)
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
            self._show_conversation(
                replacement,
                preserve_chat_members_panel=True,
            )
            if isinstance(replacement, ChatCache):
                anchor = self.contacts_panel.chat_members_button(replacement)
                if anchor is not None:
                    self.messages_panel.reanchor_chat_members_panel(
                        replacement,
                        anchor,
                    )
        elif selected is not None:
            self._show_conversation(None)

    def _show_conversation(
        self,
        conversation: ContactCache | ChatCache | None,
        *,
        preserve_chat_members_panel: bool = False,
    ) -> None:
        previous = self.messages_panel.selected_conversation
        conversation_changed = self._conversation_key(
            previous
        ) != self._conversation_key(conversation)
        if conversation_changed:
            self._release_loaded_history(previous)
        self.messages_panel.show_conversation(
            conversation,
            preserve_chat_members_panel=preserve_chat_members_panel,
            preserve_scroll_position=not conversation_changed,
        )
        self._schedule_file_loading(conversation)
        self._schedule_conversation_loading(conversation)

    @staticmethod
    def _conversation_key(
        conversation: ContactCache | ChatCache | None,
    ) -> tuple[str, UUID] | None:
        if isinstance(conversation, ContactCache):
            return "contact", conversation.id
        if isinstance(conversation, ChatCache):
            return "chat", conversation.id
        return None

    @staticmethod
    def _release_loaded_history(
        conversation: ContactCache | ChatCache | None,
    ) -> None:
        if conversation is None or not conversation.history_loaded:
            return
        conversation.messages[:] = conversation.messages[-10:]
        conversation.history_loaded = False

    def _schedule_conversation_loading(
        self,
        conversation: ContactCache | ChatCache | None,
    ) -> None:
        if (
            self._conversation_loading_task is not None
            and not self._conversation_loading_task.done()
        ):
            self._conversation_loading_task.cancel()
        self._conversation_loading_task = None

        if conversation is None:
            return
        if self.main_window is None or self.main_window.container is None:
            return

        task = asyncio.create_task(self._load_conversation_messages(conversation))
        self._conversation_loading_task = task
        task.add_done_callback(self._finish_conversation_loading)

    def _finish_conversation_loading(self, task: asyncio.Task[None]) -> None:
        if self._conversation_loading_task is task:
            self._conversation_loading_task = None

    async def _load_conversation_messages(
        self,
        conversation: ContactCache | ChatCache,
    ) -> None:
        try:
            container = self.main_window.container
            (
                success,
                status_message,
                messages,
            ) = await LoadConversationMessagesInteractor()(
                container,
                conversation,
                update_cache=False,
            )
            if not success:
                logger.warning(
                    "Failed to load conversation messages for %s: %s",
                    self._conversation_key(conversation),
                    status_message,
                )
                return
            selected = self.messages_panel.selected_conversation
            if self._conversation_key(selected) != self._conversation_key(conversation):
                return
            if selected is None:
                return
            self._apply_loaded_history(selected, messages)
            self.messages_panel.show_conversation(
                selected,
                preserve_chat_members_panel=True,
                preserve_scroll_position=True,
            )
            self._schedule_file_loading(selected)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Unexpected conversation message loading error for %s",
                self._conversation_key(conversation),
            )

    def _apply_loaded_history(
        self,
        conversation: ContactCache | ChatCache,
        messages: list[MessageCache],
    ) -> None:
        cached_file_contents = {
            message.id: message.file_content
            for message in conversation.messages
            if message.file_content is not None
        }
        for message in messages:
            if message.file_content is None:
                message.file_content = cached_file_contents.get(message.id)

        selected_key = self._conversation_key(conversation)
        matching_cache_found = False
        for cached in [*self._contacts, *self._chats]:
            if self._conversation_key(cached) == selected_key:
                cached.messages[:] = messages
                cached.history_loaded = True
                matching_cache_found = True
            else:
                self._release_loaded_history(cached)

        if not matching_cache_found:
            conversation.messages[:] = messages
            conversation.history_loaded = True

    def _schedule_file_loading(
        self,
        conversation: ContactCache | ChatCache | None,
    ) -> None:
        if self._file_loading_task is not None and not self._file_loading_task.done():
            self._file_loading_task.cancel()
        self._file_loading_task = None

        if not isinstance(conversation, ContactCache):
            return
        if self.main_window is None or self.main_window.container is None:
            return

        message_ids = self.messages_panel.missing_image_message_ids(conversation)
        if not message_ids:
            return

        task = asyncio.create_task(
            self._load_conversation_files(conversation, message_ids)
        )
        self._file_loading_task = task
        task.add_done_callback(self._finish_file_loading)

    def _finish_file_loading(self, task: asyncio.Task[None]) -> None:
        if self._file_loading_task is task:
            self._file_loading_task = None

    async def _load_conversation_files(
        self,
        conversation: ContactCache,
        message_ids: list[UUID],
    ) -> None:
        try:
            (
                success,
                status_message,
                contents,
            ) = await LoadConversationFileMessagesInteractor()(
                self.main_window.container,
                message_ids,
            )
            if not success:
                logger.warning(
                    "Failed to load conversation files for %s: %s",
                    conversation.server_user_id,
                    status_message,
                )
                return
            self.messages_panel.set_loaded_file_contents(conversation, contents)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "Unexpected conversation file loading error for %s",
                conversation.server_user_id,
            )

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
        if self._chat_creation_task is not None and not self._chat_creation_task.done():
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

    def _schedule_chat_participant_addition(
        self,
        chat: ChatCache,
        contact: ContactCache,
    ) -> None:
        key = (chat.server_chat_id, contact.server_user_id)
        existing = self._chat_participant_tasks.get(key)
        if existing is not None and not existing.done():
            return
        if self.main_window is None or self.main_window.container is None:
            self.messages_panel.finish_chat_participant_addition(
                contact,
                False,
                "APPLICATION CONTAINER IS NOT AVAILABLE",
            )
            return

        task = asyncio.create_task(self._add_chat_participant(chat, contact))
        self._chat_participant_tasks[key] = task
        task.add_done_callback(
            lambda completed, task_key=key: self._finish_chat_participant_task(
                task_key,
                completed,
            )
        )

    def _finish_chat_participant_task(
        self,
        key: tuple[UUID, UUID],
        task: asyncio.Task[None],
    ) -> None:
        if self._chat_participant_tasks.get(key) is task:
            self._chat_participant_tasks.pop(key, None)

    async def _add_chat_participant(
        self,
        chat: ChatCache,
        contact: ContactCache,
    ) -> None:
        try:
            success, status_message, _ = await AddChatParticipantInteractor()(
                self.main_window.container,
                chat,
                contact,
            )
            self.messages_panel.finish_chat_participant_addition(
                contact,
                success,
                status_message if not success else None,
            )
            if not success:
                logger.warning(
                    "Failed to add contact %s to chat %s: %s",
                    contact.server_user_id,
                    chat.server_chat_id,
                    status_message,
                )
                return
            await self.refresh_from_state()
        except asyncio.CancelledError:
            self.messages_panel.finish_chat_participant_addition(
                contact,
                False,
                "CHAT PARTICIPANT ADDITION CANCELLED",
            )
            raise
        except Exception as error:
            logger.exception("Unexpected chat participant addition error")
            self.messages_panel.finish_chat_participant_addition(
                contact,
                False,
                str(error).upper(),
            )

    def _schedule_text_message(
        self,
        request_id: UUID,
        conversation: ContactCache | ChatCache,
        text: str,
        reply: ReplySelection | None,
    ) -> None:
        if self.main_window is None or self.main_window.container is None:
            self.messages_panel.finish_text_message(
                request_id,
                False,
                failure_message="APPLICATION CONTAINER IS NOT AVAILABLE",
            )
            return

        task = asyncio.create_task(
            self._send_text_message(request_id, conversation, text, reply)
        )
        self._message_tasks.add(task)
        task.add_done_callback(self._message_tasks.discard)

    async def _send_text_message(
        self,
        request_id: UUID,
        conversation: ContactCache | ChatCache,
        text: str,
        reply: ReplySelection | None,
    ) -> None:
        try:
            reply_to_message = None
            if reply is not None:
                reply_to_message = next(
                    (
                        message
                        for message in conversation.messages
                        if message.id == reply.local_message_id
                        and message.server_message_id == reply.server_message_id
                    ),
                    None,
                )
                if reply_to_message is None:
                    self.messages_panel.finish_text_message(
                        request_id,
                        False,
                        failure_message="REPLY TARGET IS NOT AVAILABLE",
                    )
                    return
            if isinstance(conversation, ContactCache):
                result = await SendContactTextMessageInteractor()(
                    self.main_window.container,
                    conversation,
                    text,
                    reply_to_message,
                )
            else:
                reply_targets: dict[UUID, UUID] | None = None
                if reply_to_message is not None:
                    (
                        targets_success,
                        targets_status,
                        reply_targets,
                    ) = await GetChatReplyTargetsInteractor()(
                        self.main_window.container,
                        conversation,
                        reply_to_message.general_message_uuid,
                    )
                    if not targets_success:
                        self.messages_panel.finish_text_message(
                            request_id,
                            False,
                            failure_message=targets_status,
                        )
                        return
                result = await SendChatTextMessageInteractor()(
                    self.main_window.container,
                    conversation,
                    text,
                    reply_to_message,
                    reply_targets,
                )
            success, status_message, saved_message = result
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
                saved_message.id if success and saved_message is not None else None,
            )
            if success:
                self.contacts_panel.refresh_conversation(conversation)
            else:
                logger.warning(
                    "Failed to send a text message to %s: %s",
                    (
                        conversation.server_user_id
                        if isinstance(conversation, ContactCache)
                        else conversation.server_chat_id
                    ),
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

    def _schedule_file_message(
        self,
        request_id: UUID,
        contact: ContactCache,
        file_path: str,
    ) -> None:
        if self.main_window is None or self.main_window.container is None:
            self.messages_panel.finish_file_message(
                request_id,
                False,
                failure_message="APPLICATION CONTAINER IS NOT AVAILABLE",
            )
            return

        task = asyncio.create_task(
            self._send_file_message(request_id, contact, file_path)
        )
        self._message_tasks.add(task)
        task.add_done_callback(self._message_tasks.discard)

    async def _send_file_message(
        self,
        request_id: UUID,
        contact: ContactCache,
        file_path: str,
    ) -> None:
        try:
            (
                success,
                status_message,
                saved_message,
            ) = await SendContactFileMessageInteractor()(
                self.main_window.container,
                contact,
                file_path,
            )
            server_message_id = (
                saved_message.server_message_id
                if success and saved_message is not None
                else None
            )
            self.messages_panel.finish_file_message(
                request_id,
                success,
                server_message_id,
                status_message if not success else None,
                saved_message.id if success and saved_message is not None else None,
            )
            if success:
                self.contacts_panel.refresh_conversation(contact)
            else:
                logger.warning(
                    "Failed to send a file message to %s: %s",
                    contact.server_user_id,
                    status_message,
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.exception("Unexpected file message sending error")
            self.messages_panel.finish_file_message(
                request_id,
                False,
                failure_message=str(error).upper(),
            )

    def _schedule_file_save(
        self,
        message_id: UUID,
        suggested_name: str,
    ) -> None:
        if self.main_window is None or self.main_window.container is None:
            logger.warning("Cannot save a file without application container")
            return

        destination_path, _ = QFileDialog.getSaveFileName(
            self,
            "SAVE FILE",
            suggested_name,
            "ALL FILES (*)",
        )
        if not destination_path:
            return

        task = asyncio.create_task(
            self._save_message_file(message_id, destination_path)
        )
        self._message_tasks.add(task)
        task.add_done_callback(self._message_tasks.discard)

    async def _save_message_file(
        self,
        message_id: UUID,
        destination_path: str,
    ) -> None:
        try:
            (
                success,
                status_message,
                saved_path,
            ) = await SaveMessageFileToDiskInteractor()(
                self.main_window.container,
                message_id,
                destination_path,
            )
            if success:
                logger.info("File saved to %s", saved_path)
                return
            logger.warning(
                "Failed to save message file %s: %s",
                message_id,
                status_message,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Unexpected message file saving error")

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
