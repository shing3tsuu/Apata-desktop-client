import asyncio
import os
from datetime import UTC, datetime
from uuid import uuid4

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QMainWindow

from src.adapters.database.structures import MessageContentTypeEnum
from src.presentation.pages.tray.controller import TrayController
from src.presentation.pages.tray.notifications import MessageNotificationTracker
from src.providers.cache import ChatCache, ContactCache, MessageCache
from src.providers.state import AppState


def _message(*, outgoing: bool, content: str = "Hello") -> MessageCache:
    return MessageCache(
        id=uuid4(),
        server_message_id=uuid4(),
        contact_id=None,
        chat_id=None,
        content_type=MessageContentTypeEnum.TEXT,
        content=content,
        file_name=None,
        file_size=None,
        file_mime_type=None,
        timestamp=datetime.now(UTC),
        is_outgoing=outgoing,
        is_delivered=True,
    )


def _contact(username: str) -> ContactCache:
    return ContactCache(
        id=uuid4(),
        server_user_id=uuid4(),
        username=username,
        status=None,
        last_seen=None,
        online=None,
    )


def test_notification_tracker_uses_existing_cache_as_baseline() -> None:
    app_state = AppState()
    contact = _contact("ghost")
    contact.messages.append(_message(outgoing=False))
    app_state.contacts_cache = [contact]
    tracker = MessageNotificationTracker(app_state)

    tracker.arm_from_state()

    assert tracker.collect_new() == []


def test_notification_tracker_finds_new_incoming_direct_message_once() -> None:
    app_state = AppState()
    contact = _contact("ghost")
    app_state.contacts_cache = [contact]
    tracker = MessageNotificationTracker(app_state)
    tracker.arm_from_state()
    contact.messages.extend(
        [
            _message(outgoing=True, content="My message"),
            _message(outgoing=False, content="  New   incoming message  "),
        ]
    )

    notifications = tracker.collect_new()

    assert len(notifications) == 1
    assert notifications[0].title == "ghost"
    assert notifications[0].body == "New incoming message"
    assert tracker.collect_new() == []


def test_notification_tracker_builds_chat_sender_title_and_file_preview() -> None:
    app_state = AppState()
    sender = _contact("alice")
    app_state.contacts_cache = [sender]
    chat = ChatCache(
        id=uuid4(),
        server_chat_id=uuid4(),
        server_owner_id=None,
        name="NIGHT SHIFT",
        created_at=None,
    )
    app_state.chats_cache = [chat]
    tracker = MessageNotificationTracker(app_state)
    tracker.arm_from_state()
    image = _message(outgoing=False)
    image.contact_id = sender.id
    image.chat_id = chat.id
    image.content_type = MessageContentTypeEnum.IMAGE
    image.content = None
    image.file_name = "photo.png"
    chat.messages.append(image)

    notifications = tracker.collect_new()

    assert len(notifications) == 1
    assert notifications[0].title == "alice · NIGHT SHIFT"
    assert notifications[0].body == "PHOTO"


def test_notification_tracker_truncates_long_text_preview() -> None:
    app_state = AppState()
    contact = _contact("ghost")
    app_state.contacts_cache = [contact]
    tracker = MessageNotificationTracker(app_state)
    tracker.arm_from_state()
    contact.messages.append(_message(outgoing=False, content="x" * 200))

    notification = tracker.collect_new()[0]

    assert len(notification.body) == 120
    assert notification.body.endswith("...")


class _RealtimeStub:
    def __init__(self) -> None:
        self.presence_updates: list[bool] = []

    async def set_presence(self, online: bool) -> bool:
        self.presence_updates.append(online)
        return True


@pytest.mark.asyncio
async def test_tray_hide_and_restore_update_presence() -> None:
    application = QApplication.instance() or QApplication([])
    app_state = AppState()
    app_state.token = "token"
    window = QMainWindow()
    window.show()
    realtime = _RealtimeStub()
    controller = TrayController(  # type: ignore[arg-type]
        window=window,
        app_state=app_state,
        realtime_interactor=realtime,
    )
    controller._available = True

    assert controller.hide_window() is True
    await asyncio.sleep(0)
    assert window.isHidden()
    assert realtime.presence_updates == [False]

    controller.restore_window()
    await asyncio.sleep(0)
    assert window.isVisible()
    assert realtime.presence_updates == [False, True]

    controller._tray_icon.hide()
    window.close()
    application.processEvents()
