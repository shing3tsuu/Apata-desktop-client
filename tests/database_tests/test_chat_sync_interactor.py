from dataclasses import replace
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from src.adapters.api.dto import (
    ChatDTO as ServerChatDTO,
    ChatEventDTO as ServerChatEventDTO,
    ChatParticipantDTO as ServerChatParticipantDTO,
)
from src.adapters.api.service import ChatHTTPService
from src.adapters.database.dto import (
    AddChatDTO,
    AddChatEventDTO,
    AddChatParticipantDTO,
    ChatDTO as LocalChatDTO,
    ChatEventDTO as LocalChatEventDTO,
    ChatParticipantDTO as LocalChatParticipantDTO,
    RequestChatParticipantDTO,
)
from src.adapters.database.service import ChatService, ContactService
from src.adapters.database.structures import ChatEventTypeEnum
from src.presentation.interactors.login import SynchronizeChatsInteractor
from src.providers.state import AppState


class FakeRequestContainer:
    def __init__(self, services: dict[type, object]):
        self._services = services

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback):
        return False

    async def get(self, dependency_type: type):
        return self._services[dependency_type]


class FakeContainer:
    def __init__(self, services: dict[type, object]):
        self._request_container = FakeRequestContainer(services)

    def __call__(self):
        return self._request_container


class FakeChatHTTPService:
    def __init__(
        self,
        chat: ServerChatDTO,
        participant: ServerChatParticipantDTO,
        event: ServerChatEventDTO,
    ):
        self.token: str | None = None
        self._chat = chat
        self._participant = participant
        self._event = event
        self.after_values: list[datetime | None] = []

    async def get_chats(self) -> list[ServerChatDTO]:
        return [self._chat]

    async def get_participants(
        self,
        chat_id: UUID,
    ) -> list[ServerChatParticipantDTO]:
        assert chat_id == self._chat.id
        return [self._participant]

    async def get_events(
        self,
        chat_id: UUID,
        after: datetime | None = None,
    ) -> list[ServerChatEventDTO]:
        assert chat_id == self._chat.id
        self.after_values.append(after)
        if after is not None:
            return []

        self._participant = replace(self._participant, left_at=self._event.timestamp)
        return [self._event]


class FakeFormerParticipantChatHTTPService:
    def __init__(self, event: ServerChatEventDTO):
        self.token: str | None = None
        self._event = event
        self.after_values: list[datetime | None] = []

    async def get_chats(self) -> list[ServerChatDTO]:
        return []

    async def get_events(
        self,
        chat_id: UUID,
        after: datetime | None = None,
    ) -> list[ServerChatEventDTO]:
        assert chat_id == self._event.chat_id
        self.after_values.append(after)
        return [self._event] if after is None else []


class FakeContactService:
    def __init__(self, contacts: list[object]):
        self._contacts = contacts

    async def get_contacts(self, local_user_id: UUID) -> list[object]:
        return self._contacts


class FakeChatService:
    def __init__(self):
        self.chats: list[LocalChatDTO] = []
        self.participants: dict[tuple[UUID, UUID], LocalChatParticipantDTO] = {}
        self.events: list[LocalChatEventDTO] = []

    async def get_chats(self, local_user_id: UUID) -> list[LocalChatDTO]:
        return self.chats

    async def add_chat(self, chat: AddChatDTO) -> LocalChatDTO:
        created = LocalChatDTO(id=uuid4(), **chat.model_dump())
        self.chats.append(created)
        return created

    async def update_chat(self, chat):
        for index, existing in enumerate(self.chats):
            if existing.id == chat.id:
                updated = existing.model_copy(
                    update=chat.model_dump(exclude_unset=True, exclude={"id"})
                )
                self.chats[index] = updated
                return updated
        return None

    async def get_participant(
        self,
        chat_id: UUID,
        contact_id: UUID,
    ) -> LocalChatParticipantDTO | None:
        return self.participants.get((chat_id, contact_id))

    async def add_participant(
        self,
        participant: AddChatParticipantDTO,
        create_join_event: bool,
    ) -> LocalChatParticipantDTO:
        key = (participant.chat_id, participant.contact_id)
        created = LocalChatParticipantDTO(**participant.model_dump())
        self.participants[key] = created
        return created

    async def update_participant(
        self,
        participant: RequestChatParticipantDTO,
    ) -> LocalChatParticipantDTO | None:
        key = (participant.chat_id, participant.contact_id)
        existing = self.participants.get(key)
        if existing is None:
            return None
        updated = existing.model_copy(
            update=participant.model_dump(
                exclude_unset=True,
                exclude={"chat_id", "contact_id"},
            )
        )
        self.participants[key] = updated
        return updated

    async def delete_participant(
        self,
        chat_id: UUID,
        contact_id: UUID,
        create_left_event: bool,
        left_at: datetime,
    ) -> bool:
        key = (chat_id, contact_id)
        existing = self.participants.get(key)
        if existing is None or existing.left_at is not None:
            return False
        self.participants[key] = existing.model_copy(update={"left_at": left_at})
        return True

    async def get_latest_server_event_timestamp(
        self,
        chat_id: UUID,
    ) -> datetime | None:
        timestamps = [
            event.timestamp
            for event in self.events
            if event.chat_id == chat_id and event.server_event_id is not None
        ]
        return max(timestamps) if timestamps else None

    async def get_chat_event_by_server_event_id(
        self,
        server_event_id: UUID,
    ) -> LocalChatEventDTO | None:
        return next(
            (
                event
                for event in self.events
                if event.server_event_id == server_event_id
            ),
            None,
        )

    async def add_chat_event(self, event: AddChatEventDTO) -> LocalChatEventDTO:
        created = LocalChatEventDTO(id=uuid4(), **event.model_dump())
        self.events.append(created)
        return created


@pytest.mark.asyncio
async def test_chat_synchronization_persists_server_state_and_uses_cursor():
    local_user_id = uuid4()
    local_server_user_id = uuid4()
    remote_contact_server_id = uuid4()
    local_contact_id = uuid4()
    server_chat_id = uuid4()
    server_event_id = uuid4()
    timestamp = datetime.now(timezone.utc)

    server_chat = ServerChatDTO(
        id=server_chat_id,
        owner_id=local_server_user_id,
        name="project",
        created_at=timestamp,
    )
    server_participant = ServerChatParticipantDTO(
        chat_id=server_chat_id,
        user_id=remote_contact_server_id,
        invited_by_user_id=local_server_user_id,
        joined_at=timestamp,
        left_at=None,
    )
    server_event = ServerChatEventDTO(
        id=server_event_id,
        chat_id=server_chat_id,
        user_id=local_server_user_id,
        target_user_id=remote_contact_server_id,
        event_type=ChatEventTypeEnum.MEMBER_REMOVED.value,
        timestamp=timestamp,
    )
    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id
    app_state.server_user_id = local_server_user_id

    chat_http_service = FakeChatHTTPService(
        server_chat,
        server_participant,
        server_event,
    )
    chat_service = FakeChatService()
    contact_service = FakeContactService(
        [
            type(
                "Contact",
                (),
                {
                    "id": local_contact_id,
                    "server_user_id": remote_contact_server_id,
                },
            )()
        ]
    )
    container = FakeContainer(
        {
            ChatHTTPService: chat_http_service,
            ChatService: chat_service,
            ContactService: contact_service,
            AppState: app_state,
        }
    )

    first_success, _, first_counts = await SynchronizeChatsInteractor()(container)
    second_success, _, second_counts = await SynchronizeChatsInteractor()(container)

    local_chat = chat_service.chats[0]
    participant = chat_service.participants[(local_chat.id, local_contact_id)]
    event = chat_service.events[0]
    assert first_success is True
    assert first_counts == {
        "added": 1,
        "updated": 0,
        "participants_added": 1,
        "participants_left": 1,
        "events_added": 1,
        "unmapped_participants": 0,
    }
    assert local_chat.server_owner_id == local_server_user_id
    assert local_chat.created_at == timestamp
    assert participant.left_at == timestamp
    assert event.server_event_id == server_event_id
    assert event.actor_server_user_id == local_server_user_id
    assert event.target_server_user_id == remote_contact_server_id
    assert event.contact_id is None
    assert second_success is True
    assert second_counts["events_added"] == 0
    assert len(chat_service.events) == 1
    assert chat_http_service.after_values == [None, timestamp]


@pytest.mark.asyncio
async def test_chat_synchronization_reads_final_event_after_user_was_removed():
    local_user_id = uuid4()
    local_server_user_id = uuid4()
    owner_id = uuid4()
    server_chat_id = uuid4()
    timestamp = datetime.now(timezone.utc)
    event = ServerChatEventDTO(
        id=uuid4(),
        chat_id=server_chat_id,
        user_id=owner_id,
        target_user_id=local_server_user_id,
        event_type=ChatEventTypeEnum.MEMBER_REMOVED.value,
        timestamp=timestamp,
    )
    app_state = AppState()
    app_state.token = "access-token"
    app_state.local_user_id = local_user_id
    app_state.server_user_id = local_server_user_id
    chat_service = FakeChatService()
    chat_service.chats.append(
        LocalChatDTO(
            id=uuid4(),
            local_user_id=local_user_id,
            server_chat_id=server_chat_id,
            server_owner_id=owner_id,
            name="project",
            created_at=timestamp,
        )
    )
    chat_http_service = FakeFormerParticipantChatHTTPService(event)
    container = FakeContainer(
        {
            ChatHTTPService: chat_http_service,
            ChatService: chat_service,
            ContactService: FakeContactService([]),
            AppState: app_state,
        }
    )

    success, _, counts = await SynchronizeChatsInteractor()(container)

    assert success is True
    assert counts["events_added"] == 1
    assert chat_service.events[0].server_event_id == event.id
    assert chat_http_service.after_values == [None]
