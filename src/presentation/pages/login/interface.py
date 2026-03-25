from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import Qt
import qasync
import asyncio

from src.presentation.pages import AppState
from .backgrounds import (
    UpperArtifacts,
    TopLeftCorner,
    TopRightCorner,
    BottomLeftCorner,
    BottomRightCorner,
)
from .buttons import AccessButton, ChooseButton
from .fields import LoginField
from .logs import LoginLogs

from .manager import RegisterManager, LoginManager, LoadingManager

COLOR_PRIMARY = "#b3ff15"
COLOR_SECONDARY = "#000000"
COLOR_ERROR = "#ff153e"


class LoginInterface(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window

        self.mode: str = "register"
        self.username: str = ""
        self.password: str = ""

        self.setup_ui()
        self._connect_signals()

        self.register_manager = RegisterManager(
            self.main_window.app_state, self.main_window.container
        )

        self.login_manager = LoginManager(
            self.main_window.app_state, self.main_window.container
        )

        self.loading_manager = LoadingManager(
            self.main_window.app_state, self.main_window.container
        )

    def setup_ui(self):
        self.setStyleSheet("background-color: #000000;")

        self.corner_tl = TopLeftCorner(color=COLOR_PRIMARY, parent=self)
        self.corner_tr = TopRightCorner(color=COLOR_PRIMARY, parent=self)
        self.corner_bl = BottomLeftCorner(color=COLOR_PRIMARY, parent=self)
        self.corner_br = BottomRightCorner(color=COLOR_PRIMARY, parent=self)

        self.upper_artifacts = UpperArtifacts(
            color_primary=COLOR_PRIMARY, color_secondary=COLOR_SECONDARY, parent=self
        )

        self.choose_button = ChooseButton(
            first_text="R Ξ G I S T R Ʌ T I O N",
            second_text="L O G I N",
            color_primary=COLOR_PRIMARY,
            color_secondary=COLOR_SECONDARY,
            color_inactive="#373737",
        )

        self.username_field = LoginField(
            placeholder="U S Ξ R N Ʌ M Ξ",
            color_primary=COLOR_PRIMARY,
            color_secondary=COLOR_SECONDARY,
        )

        self.password_field = LoginField(
            placeholder="P Ʌ S S W O R D",
            color_primary=COLOR_PRIMARY,
            color_secondary=COLOR_SECONDARY,
            is_password=True,
        )

        self.button = AccessButton(
            text="Ʌ C C Ξ S S",
            color_primary=COLOR_PRIMARY,
            color_secondary=COLOR_SECONDARY,
            color_error=COLOR_ERROR,
        )

        self.logs_container = LoginLogs(
            color_primary=COLOR_PRIMARY,
            color_secondary=COLOR_SECONDARY,
            color_error=COLOR_ERROR,
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
        center_layout.addWidget(
            self.username_field, alignment=Qt.AlignmentFlag.AlignCenter
        )
        center_layout.addWidget(
            self.password_field, alignment=Qt.AlignmentFlag.AlignCenter
        )
        center_layout.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignCenter)

        center_widget = QWidget()
        center_widget.setLayout(center_layout)

        root_layout.addStretch(5)
        root_layout.addWidget(center_widget, alignment=Qt.AlignmentFlag.AlignCenter)
        root_layout.addStretch(1)
        root_layout.addWidget(
            self.logs_container, alignment=Qt.AlignmentFlag.AlignCenter
        )

        self.setLayout(center_layout)

    def _connect_signals(self):
        self.choose_button.registration_clicked.connect(self._on_register_selected)
        self.choose_button.login_clicked.connect(self._on_login_selected)

        self.username_field.textChanged.connect(self._on_username_changed)
        self.password_field.textChanged.connect(self._on_password_changed)

        self.button.clicked.connect(qasync.asyncSlot()(self._on_access_clicked))

    async def _on_access_clicked(self, checked: bool = False):
        self.logs_container.clear()

        if self.mode == "register":
            self.logs_container.add_log("CHECK REGISTRATION POSSIBILITY")
            success, message = await self.register_manager.check_local_user(
                self.username, self.password
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("REGISTER USER ON SERVER")
            success, message = await self.register_manager.register_user_on_server(
                self.username, self.password
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("STORAGE CRYPTOGRAPHY KEYS")
            success, message = await self.register_manager.contain_keys(
                self.username, self.password
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("LOGIN AS NEW USER")
            success, message = await self.register_manager.login_new_user(
                self.username, self.password
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("HASHING PASSWORD WITH SALT")
            success, message = await self.register_manager.hashing_password(
                self.username, self.password
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("ADDING USER TO LOCAL DATABASE")
            success, message = await self.register_manager.add_user_to_database(
                self.username, self.password
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("CACHING OF USED VARIABLES")
            success, message = await self.register_manager.update_state(
                self.username, self.password
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

        elif self.mode == "login":
            self.logs_container.add_log("USER EXISTENCE CHECK")
            success, message = await self.login_manager.check_local_user(
                self.username, self.password
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("COMPARE PASSWORD")
            success, message = await self.login_manager.compare_password(
                self.username, self.password
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("OBTAINING CRYPTOGRAPHIC KEYS")
            success, message = await self.login_manager.get_ecdsa_private_key(
                self.username, self.password
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("LOGIN USER ON SERVER")
            success, message = await self.login_manager.login_user(
                self.username, self.password
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

            self.logs_container.add_log("CACHING OF USED VARIABLES")
            success, message = await self.login_manager.update_state(
                self.username, self.password
            )
            self.logs_container.finish_log(success, message)

            if not success:
                return

        self.logs_container.add_log("SYNCHRONIZATION CONTACTS")
        success, message = await self.loading_manager.synchronize_contacts()
        self.logs_container.finish_log(success, message)

        if not success:
            return

        self.logs_container.add_log("SYNCHRONIZATION MESSAGES")
        success, message = await self.loading_manager.sync_message_history()
        self.logs_container.finish_log(success, message)

        if not success:
            return

        self.logs_container.add_log("ROTATING CRYPTOGRAPHY KEYS")
        success, message = await self.loading_manager.rotate_keys()
        self.logs_container.finish_log(success, message)

        if not success:
            return

        if (
            hasattr(self.main_window, "screens")
            and "messenger" in self.main_window.screens
        ):
            await self.main_window.show_screen("messenger")

    def _on_username_changed(self, text: str):
        self.username = text.strip()

    def _on_password_changed(self, text: str):
        self.password = text

    def _on_register_selected(self):
        self.mode = "register"

    def _on_login_selected(self):
        self.mode = "login"

    def resizeEvent(self, event):
        super().resizeEvent(event)
        margin = 300

        self.corner_tl.move(margin, margin)
        self.corner_tr.move(self.width() - 90 - margin, margin)
        self.corner_bl.move(margin, self.height() - 120 - margin)
        self.corner_br.move(self.width() - 90 - margin, self.height() - 120 - margin)

    async def prepare_screen(self, **kwargs):
        self.mode = "register"
