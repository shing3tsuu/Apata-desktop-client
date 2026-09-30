"""Temporary messenger data shown only when the conversation cache is empty."""

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from src.adapters.database.structures import ContactStatusEnum, MessageContentTypeEnum
from src.providers.cache import ChatCache, ContactCache, MessageCache


def build_demo_conversations() -> tuple[list[ContactCache], list[ChatCache]]:
    now = datetime.now(timezone.utc)
    first_contact = ContactCache(
        id=uuid4(),
        server_user_id=uuid4(),
        username="ghost_user",
        status=ContactStatusEnum.ACCEPTED,
        last_seen=now - timedelta(minutes=2),
        online=True,
    )
    for minutes_ago, is_outgoing, content in (
        (12, False, "Привет! Это временная тестовая переписка."),
        (10, True, "Отлично, проверяю окно сообщений."),
        (8, False, "Ник теперь виден под заголовком MESSAGES?"),
        (6, True, "Да, и сообщения относятся к выбранному контакту."),
        (4, False, "Попробуй переключиться на другой контакт и обратно."),
        (2, True, "Всё на месте."),
    ):
        first_contact.messages.append(
            MessageCache(
                id=uuid4(),
                server_message_id=uuid4(),
                contact_id=first_contact.id,
                chat_id=None,
                content_type=MessageContentTypeEnum.TEXT,
                content=content,
                file_name=None,
                file_size=None,
                file_mime_type=None,
                timestamp=now - timedelta(minutes=minutes_ago),
                is_outgoing=is_outgoing,
                is_delivered=True,
            )
        )

    contacts = [
        first_contact,
        ContactCache(
            id=uuid4(),
            server_user_id=uuid4(),
            username="xX_n0name_Xx",
            status=ContactStatusEnum.ACCEPTED,
            last_seen=now - timedelta(minutes=40),
            online=False,
        ),
        ContactCache(
            id=uuid4(),
            server_user_id=uuid4(),
            username="anon_777",
            status=ContactStatusEnum.ACCEPTED,
            last_seen=now - timedelta(minutes=7),
            online=True,
        ),
    ]
    chats = [
        ChatCache(
            id=uuid4(),
            server_chat_id=uuid4(),
            server_owner_id=None,
            name="NIGHT SHIFT",
            created_at=now,
        )
    ]
    return contacts, chats
