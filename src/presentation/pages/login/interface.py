import asyncio

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qasync import asyncSlot

from src.presentation.interactors.login import (
    AddUserToDatabaseInteractor,
    CacheConversationsInteractor,
    CheckLocalUserLoginInteractor,
    CheckLocalUserRegisterInteractor,
    ComparePasswordInteractor,
    ContainKeysInteractor,
    GetLocalUsernamesInteractor,
    GetPrivateKeysInteractor,
    HashingPasswordInteractor,
    LoginUserInteractor,
    RegisterUserOnServerInteractor,
    RotateKeysInteractor,
    SynchronizeChatsInteractor,
    SynchronizeContactsInteractor,
    SyncMessageHistoryInteractor,
)

from .accounts import LocalAccountsPanel
from .backgrounds import (
    BackgroundTriangle,
    BottomLeftCorner,
    BottomRightCorner,
    HeaderLabel,
    TopLeftCorner,
    TopRightCorner,
    UpperArtifacts,
)
from .buttons import AccessButton, AccountToggleButton, ChooseButton
from .fields import LoginField
from .logs import LoginLogs
from .theme import (
    COLOR_ACCESS_BACKGROUND,
    COLOR_ACCESS_INACTIVE,
    COLOR_ACCESS_TEXT,
    COLOR_ACCOUNT_PANEL_BACKGROUND,
    COLOR_ACCOUNT_PANEL_TEXT,
    COLOR_ACCOUNT_TOGGLE_ACTIVE,
    COLOR_ACCOUNT_TOGGLE_DEFAULT,
    COLOR_ARTIFACT_INACTIVE,
    COLOR_ARTIFACT_PRIMARY,
    COLOR_ARTIFACT_SECONDARY,
    COLOR_BACKGROUND,
    COLOR_CHOOSE_ACTIVE,
    COLOR_CHOOSE_INACTIVE,
    COLOR_CHOOSE_TEXT,
    COLOR_CORNER,
    COLOR_FIELD_BACKGROUND,
    COLOR_FIELD_BORDER_IDLE,
    COLOR_FIELD_TEXT,
    COLOR_HEADER_PRIMARY,
    COLOR_HEADER_TEXT,
    COLOR_LOG_BACKGROUND,
    COLOR_LOG_ERROR,
    COLOR_LOG_PRIMARY,
    COLOR_LOG_SECONDARY,
    COLOR_LOG_SUCCESS,
    COLOR_TRIANGLE_BACKGROUND,
)


class LoginInterface(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window

        self.mode: str = "register"
        self.username: str = ""
        self.password: str = ""
        self.local_usernames: list[str] = []
        self.local_usernames_ready = False
        self._local_usernames_task = None

        self.setup_ui()
        self._connect_signals()

        self.get_local_usernames_interactor = GetLocalUsernamesInteractor()
        self.check_local_user_register_interactor = CheckLocalUserRegisterInteractor()
        self.register_user_on_server_interactor = RegisterUserOnServerInteractor()
        self.contains_keys_interactor = ContainKeysInteractor()
        self.login_user_interactor = LoginUserInteractor()
        self.hashing_password_interactor = HashingPasswordInteractor()
        self.add_user_to_database_interactor = AddUserToDatabaseInteractor()
        self.check_local_user_login_interactor = CheckLocalUserLoginInteractor()
        self.compare_password_interactor = ComparePasswordInteractor()
        self.get_private_keys_interactor = GetPrivateKeysInteractor()
        self.synchronize_contacts_interactor = SynchronizeContactsInteractor()
        self.synchronize_chats_interactor = SynchronizeChatsInteractor()
        self.sync_message_history_interactor = SyncMessageHistoryInteractor()
        self.rotate_keys_interactor = RotateKeysInteractor()
        self.cache_conversations_interactor = CacheConversationsInteractor()

    def setup_ui(self):
        self.setStyleSheet(f"background-color: {COLOR_BACKGROUND};")

        self.background_triangle = BackgroundTriangle(
            color=COLOR_TRIANGLE_BACKGROUND,
            parent=self,
        )
        self.background_triangle.setGeometry(self.rect())
        self.background_triangle.lower()

        self.header_label = HeaderLabel(
            text="Ʌ P Ʌ T Ʌ -  暗 号 化 対 策  |  𝙴 𝙽 𝙲 𝚁 𝚈 𝙿 𝚃 𝙸 𝙾 𝙽   𝙼 𝙴 𝙰 𝚂 𝚄 𝚁 𝙴 𝚂",
            color_primary=COLOR_HEADER_PRIMARY,
            color_text=COLOR_HEADER_TEXT,
            parent=self,
        )

        self.corner_tl = TopLeftCorner(color=COLOR_CORNER, parent=self)
        self.corner_tr = TopRightCorner(color=COLOR_CORNER, parent=self)
        self.corner_bl = BottomLeftCorner(color=COLOR_CORNER, parent=self)
        self.corner_br = BottomRightCorner(color=COLOR_CORNER, parent=self)

        self.upper_artifacts = UpperArtifacts(
            color_primary=COLOR_ARTIFACT_PRIMARY,
            color_secondary=COLOR_ARTIFACT_SECONDARY,
            color_inactive=COLOR_ARTIFACT_INACTIVE,
            parent=self,
        )

        self.choose_button = ChooseButton(
            first_text="R Ξ G I S T R Ʌ T I O N",
            second_text="L O G I N",
            color_primary=COLOR_CHOOSE_ACTIVE,
            color_secondary=COLOR_CHOOSE_TEXT,
            color_inactive=COLOR_CHOOSE_INACTIVE,
        )

        self.username_field = LoginField(
            placeholder="U S Ξ R N Ʌ M Ξ",
            color_primary=COLOR_CHOOSE_ACTIVE,
            color_secondary=COLOR_FIELD_BORDER_IDLE,
            color_background=COLOR_FIELD_BACKGROUND,
            color_text=COLOR_FIELD_TEXT,
        )

        self.account_toggle_button = AccountToggleButton(
            color_default=COLOR_ACCOUNT_TOGGLE_DEFAULT,
            color_active=COLOR_ACCOUNT_TOGGLE_ACTIVE,
        )
        self.account_toggle_button.hide()

        self.account_toggle_placeholder = QWidget()
        self.account_toggle_placeholder.setFixedSize(
            self.account_toggle_button.width(),
            self.account_toggle_button.height(),
        )
        self.account_toggle_placeholder.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )
        self.account_toggle_placeholder.setStyleSheet("background: transparent;")
        self.account_toggle_placeholder.hide()

        self.accounts_panel = LocalAccountsPanel(
            color_primary=COLOR_ACCOUNT_TOGGLE_ACTIVE,
            color_background=COLOR_ACCOUNT_PANEL_BACKGROUND,
            color_text=COLOR_ACCOUNT_PANEL_TEXT,
            parent=self,
        )
        self.accounts_panel.hide()

        self.password_field = LoginField(
            placeholder="P Ʌ S S W O R D",
            color_primary=COLOR_CHOOSE_ACTIVE,
            color_secondary=COLOR_FIELD_BORDER_IDLE,
            color_background=COLOR_FIELD_BACKGROUND,
            color_text=COLOR_FIELD_TEXT,
            is_password=True,
        )

        self.button = AccessButton(
            text="Ʌ C C Ξ S S",
            color_primary=COLOR_ACCESS_BACKGROUND,
            color_secondary=COLOR_ACCESS_TEXT,
            color_error=COLOR_LOG_ERROR,
            color_inactive=COLOR_ACCESS_INACTIVE,
        )

        self.logs_container = LoginLogs(
            color_primary=COLOR_LOG_PRIMARY,
            color_secondary=COLOR_LOG_SECONDARY,
            color_success=COLOR_LOG_SUCCESS,
            color_error=COLOR_LOG_ERROR,
            color_background=COLOR_LOG_BACKGROUND,
            parent=self,
        )

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(0, 0, 0, 20)
        root_layout.setSpacing(0)

        center_layout = QVBoxLayout()
        center_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center_layout.setSpacing(20)

        center_layout.addWidget(
            self.upper_artifacts, alignment=Qt.AlignmentFlag.AlignCenter
        )
        center_layout.addSpacing(30)
        center_layout.addWidget(
            self.choose_button, alignment=Qt.AlignmentFlag.AlignCenter
        )
        username_layout = QHBoxLayout()
        username_layout.setContentsMargins(0, 0, 0, 0)
        username_layout.setSpacing(8)
        username_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        username_layout.addWidget(self.account_toggle_placeholder)
        username_layout.addWidget(self.username_field)
        username_layout.addWidget(self.account_toggle_button)
        center_layout.addLayout(username_layout)
        center_layout.addWidget(
            self.password_field, alignment=Qt.AlignmentFlag.AlignCenter
        )
        center_layout.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignCenter)

        center_widget = QWidget()
        center_widget.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        center_widget.setStyleSheet("background: transparent;")
        center_widget.setLayout(center_layout)

        root_layout.addStretch(5)
        root_layout.addWidget(center_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        root_layout.addStretch(1)
        root_layout.addWidget(
            self.logs_container, alignment=Qt.AlignmentFlag.AlignCenter
        )

    def _connect_signals(self):
        self.choose_button.registration_clicked.connect(self._on_register_selected)
        self.choose_button.login_clicked.connect(self._on_login_selected)

        self.account_toggle_button.toggled.connect(self._on_accounts_toggled)
        self.accounts_panel.account_selected.connect(self._on_account_selected)

        self.username_field.textChanged.connect(self._on_username_changed)
        self.password_field.textChanged.connect(self._on_password_changed)

        self.button.clicked.connect(self._on_access_clicked)

    def _on_accounts_toggled(self, expanded: bool):
        if not expanded:
            self.accounts_panel.hide()
            return

        if self.local_usernames_ready:
            self.accounts_panel.set_accounts(self.local_usernames)
        else:
            self.accounts_panel.set_loading()

        self._position_accounts_panel()
        self.accounts_panel.show()
        self.accounts_panel.raise_()

    def _start_local_usernames_loading(self):
        if self._local_usernames_task is None:
            self._local_usernames_task = asyncio.create_task(
                self._load_local_usernames()
            )

    async def _load_local_usernames(self):
        success, usernames = await self.get_local_usernames_interactor(
            container=self.main_window.container
        )
        self.local_usernames = usernames if success else []
        self.local_usernames_ready = True

        if self.account_toggle_button.expanded:
            self.accounts_panel.set_accounts(self.local_usernames)

    def _on_account_selected(self, username: str):
        self.username_field.setText(username)
        self.username_field.setFocus()
        self.account_toggle_button.set_expanded(False)
        self.accounts_panel.hide()

    def _position_accounts_panel(self):
        field_position = self.username_field.mapTo(
            self,
            QPoint(0, self.username_field.height() + 8),
        )
        panel_x = (
            field_position.x()
            + (self.username_field.width() - self.accounts_panel.width()) // 2
        )
        self.accounts_panel.move(panel_x, field_position.y())

    @asyncSlot()
    async def _on_access_clicked(self, checked: bool = False):
        self.logs_container.clear()

        if self.mode == "register":
            self.logs_container.add_log("CHECK REGISTRATION POSSIBILITY")
            success, message = await self.check_local_user_register_interactor(
                container=self.main_window.container,
                username=self.username,
                password=self.password,
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("REGISTER USER ON SERVER")
            success, message = await self.register_user_on_server_interactor(
                container=self.main_window.container
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("STORAGE CRYPTOGRAPHY KEYS")
            success, message = await self.contains_keys_interactor(
                container=self.main_window.container
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("LOGIN AS NEW USER")
            success, message = await self.login_user_interactor(
                container=self.main_window.container
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("HASHING PASSWORD WITH SALT")
            success, message = await self.hashing_password_interactor(
                container=self.main_window.container
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("ADDING USER TO LOCAL DATABASE")
            success, message = await self.add_user_to_database_interactor(
                container=self.main_window.container
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

        elif self.mode == "login":
            self.logs_container.add_log("USER EXISTENCE CHECK")
            success, message = await self.check_local_user_login_interactor(
                container=self.main_window.container,
                username=self.username,
                password=self.password,
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("COMPARE PASSWORD")
            success, message = await self.compare_password_interactor(
                container=self.main_window.container
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("OBTAINING CRYPTOGRAPHIC KEYS")
            success, message = await self.get_private_keys_interactor(
                container=self.main_window.container
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("LOGIN USER ON SERVER")
            success, message = await self.login_user_interactor(
                container=self.main_window.container
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log(text="SYNCHRONIZATION CONTACTS", is_dict=True)
            (
                success,
                message,
                contact_count_dict,
            ) = await self.synchronize_contacts_interactor(
                container=self.main_window.container
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            added = contact_count_dict.get("added", 0)
            edited = contact_count_dict.get("edited", 0)
            self.logs_container.add_info(f"› ADDED CONTACTS: {added}", indent=4)
            self.logs_container.add_info(f"› EDITED CONTACTS: {edited}", indent=4)

            self.logs_container.add_log(text="SYNCHRONIZATION CHATS", is_dict=True)
            success, message, chat_count_dict = await self.synchronize_chats_interactor(
                container=self.main_window.container
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            added = chat_count_dict.get("added", 0)
            updated = chat_count_dict.get("updated", 0)
            participants_added = chat_count_dict.get("participants_added", 0)
            participants_left = chat_count_dict.get("participants_left", 0)
            events_added = chat_count_dict.get("events_added", 0)
            unmapped_participants = chat_count_dict.get("unmapped_participants", 0)
            self.logs_container.add_info(f"› ADDED CHATS: {added}", indent=4)
            self.logs_container.add_info(f"› UPDATED CHATS: {updated}", indent=4)
            self.logs_container.add_info(
                f"› ADDED PARTICIPANTS: {participants_added}",
                indent=4,
            )
            self.logs_container.add_info(
                f"› LEFT PARTICIPANTS: {participants_left}",
                indent=4,
            )
            self.logs_container.add_info(
                f"› ADDED CHAT EVENTS: {events_added}", indent=4
            )
            self.logs_container.add_info(
                f"› UNMAPPED PARTICIPANTS: {unmapped_participants}",
                indent=4,
            )

            self.logs_container.add_log("SYNCHRONIZATION MESSAGES", is_dict=True)
            (
                success,
                message,
                message_count_dict,
            ) = await self.sync_message_history_interactor(
                container=self.main_window.container
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            added = message_count_dict.get("text_count", 0)
            edited = message_count_dict.get("file_count", 0)
            failed = message_count_dict.get("failed_count", 0)
            self.logs_container.add_info(f"› TEXT MESSAGE CATCH: {added}", indent=4)
            self.logs_container.add_info(f"› FILE MESSAGE CATCH: {edited}", indent=4)
            self.logs_container.add_info(
                f"› FAILED MESSAGES: {failed}",
                indent=4,
            )

            self.logs_container.add_log("ROTATING CRYPTOGRAPHY KEYS")
            success, message = await self.rotate_keys_interactor(
                container=self.main_window.container
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

        self.logs_container.add_log("CACHING CONVERSATIONS", is_dict=True)
        success, message, cache_counts = await self.cache_conversations_interactor(
            container=self.main_window.container
        )
        self.logs_container.finish_log(success, message)
        if not success:
            return
        self.logs_container.add_info(
            f"› CONTACTS: {cache_counts['contacts']}", indent=4
        )
        self.logs_container.add_info(f"› CHATS: {cache_counts['chats']}", indent=4)
        self.logs_container.add_info(
            f"› RECENT MESSAGES: {cache_counts['messages']}", indent=4
        )

        self.logs_container.add_log("CONNECTING REALTIME")
        realtime_started = await self.main_window.realtime_interactor.start()
        self.logs_container.finish_log(
            realtime_started,
            "SUCCESS" if realtime_started else "FAILED",
        )

        if (
            hasattr(self.main_window, "screens")
            and "messenger" in self.main_window.screens
        ):
            self.logs_container.add_log(text="DEPLOYING IN")
            await asyncio.sleep(1)
            self.logs_container.finish_log(True, "1")
            self.logs_container.add_log(text="DEPLOYING IN")
            await asyncio.sleep(1)
            self.logs_container.finish_log(True, "2")
            self.logs_container.add_log(text="DEPLOYING IN")
            await asyncio.sleep(1)
            self.logs_container.finish_log(True, "3")
            await asyncio.sleep(0.75)

            await self.main_window.show_screen("messenger")

    def _on_username_changed(self, text: str):
        self.username = text.strip()

    def _on_password_changed(self, text: str):
        self.password = text

    def _on_register_selected(self):
        self.mode = "register"
        self.account_toggle_button.set_expanded(False)
        self.account_toggle_button.hide()
        self.account_toggle_placeholder.hide()
        self.accounts_panel.hide()

    def _on_login_selected(self):
        self.mode = "login"
        self.account_toggle_placeholder.show()
        self.account_toggle_button.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if hasattr(self, "background_triangle"):
            self.background_triangle.setGeometry(self.rect())
            self.background_triangle.lower()

        if hasattr(self, "header_label"):
            self.header_label.move((self.width() - self.header_label.width()) // 2, 50)
            self.header_label.raise_()

        if hasattr(self, "accounts_panel") and self.accounts_panel.isVisible():
            self._position_accounts_panel()
            self.accounts_panel.raise_()

        horizontal_margin = 300
        vertical_margin = 275

        self.corner_tl.move(horizontal_margin, vertical_margin)
        self.corner_tr.move(self.width() - 90 - horizontal_margin, vertical_margin)
        self.corner_bl.move(
            horizontal_margin, self.height() - self.corner_bl.height() - vertical_margin
        )
        self.corner_br.move(
            self.width() - 90 - horizontal_margin,
            self.height() - self.corner_br.height() - vertical_margin,
        )

    async def prepare_screen(self, **kwargs):
        self.mode = "register"
        self.account_toggle_button.set_expanded(False, animated=False)
        self.account_toggle_button.hide()
        self.account_toggle_placeholder.hide()
        self.accounts_panel.hide()
        self._start_local_usernames_loading()
