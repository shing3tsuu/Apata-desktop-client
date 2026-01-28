from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt

from src.presentation.pages import AppState
from .backgrounds import UpperArtifacts
from .buttons import AccessButton, ChooseButton
from .fields import LoginField

COLOR_PRIMARY = "#b3ff15"
COLOR_SECONDARY = "#000000"
COLOR_ERROR = "#ff2400"

class LoginInterface(QWidget):
    def __init__(self, main_window=None):
        super().__init__()
        self.main_window = main_window
        self.setup_ui()

    def setup_ui(self):
        self.setStyleSheet("background-color: black;")

        layout = QVBoxLayout()
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setContentsMargins(0, 0, 0, 300)  # left, top, right, bottom
        layout.setSpacing(30)  # отступы между виджетами

        self.upper_artifacts = UpperArtifacts(
            color_primary=COLOR_PRIMARY,
            color_secondary=COLOR_SECONDARY,
            parent=self
        )

        self.choose_button = ChooseButton(
            first_text="R Ξ G I S T R Ʌ T I O N",
            second_text="L O G I N",
            color_primary=COLOR_PRIMARY,
            color_secondary=COLOR_SECONDARY,
            color_inactive="#373737"
        )

        #self.choose_button.registration_clicked.connect(self.on_registration_mode)
        #self.choose_button.login_clicked.connect(self.on_login_mode)

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

        layout.addWidget(self.upper_artifacts, alignment=Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignCenter)
        layout.addSpacing(100)
        layout.addWidget(self.choose_button, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.username_field, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.password_field, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.button, alignment=Qt.AlignmentFlag.AlignCenter)

        self.setLayout(layout)

    async def prepare_screen(self, **kwargs):
        pass