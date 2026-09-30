from dataclasses import dataclass

from PyQt6.QtCore import QPoint
from PyQt6.QtWidgets import QMenu

from src.adapters.database.structures import ContactStatusEnum

from .theme import (
    COLOR_CONTACT_CONTEXT_MENU_BACKGROUND,
    COLOR_CONTACT_OFFLINE,
    COLOR_PRIMARY,
)


@dataclass(frozen=True, slots=True)
class ContactMenuAction:
    key: str | None
    label: str
    enabled: bool = True


def contact_menu_actions(
    status: ContactStatusEnum | None,
) -> tuple[ContactMenuAction, ...]:
    relationship_actions: tuple[ContactMenuAction, ...]
    if status is ContactStatusEnum.PENDING_INCOMING:
        relationship_actions = (
            ContactMenuAction(
                "accept_request",
                "✓  ACCEPT REQUEST",
            ),
        )
    elif status is None or status is ContactStatusEnum.BLANK:
        relationship_actions = (
            ContactMenuAction(
                "send_request",
                "✉  SEND REQUEST",
            ),
        )
    else:
        relationship_actions = ()

    return relationship_actions + (
        ContactMenuAction("block", "⛒  BLACKLIST"),
    )


class ContactContextMenu(QMenu):
    def __init__(
        self,
        status: ContactStatusEnum | None,
        color_primary: str = COLOR_PRIMARY,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._apply_style(color_primary)
        for action_spec in contact_menu_actions(status):
            action = self.addAction(action_spec.label)
            assert action is not None
            action.setData(action_spec.key)
            action.setEnabled(action_spec.enabled)

    def exec_action(self, global_position: QPoint) -> str | None:
        selected_action = self.exec(global_position)
        if selected_action is None:
            return None
        action_key = selected_action.data()
        return action_key if isinstance(action_key, str) else None

    def _apply_style(self, color_primary: str) -> None:
        self.setStyleSheet(
            f"""
            QMenu {{
                background-color: {COLOR_CONTACT_CONTEXT_MENU_BACKGROUND};
                border: 1px solid {color_primary};
                border-radius: 4px;
                padding: 4px;
            }}
            QMenu::item {{
                color: {color_primary};
                padding: 7px 26px;
                font-family: 'Roboto';
                font-size: 12px;
            }}
            QMenu::item:selected {{
                background-color: {color_primary};
                color: {COLOR_CONTACT_CONTEXT_MENU_BACKGROUND};
            }}
            QMenu::item:disabled {{
                color: {COLOR_CONTACT_OFFLINE};
            }}
            """
        )
