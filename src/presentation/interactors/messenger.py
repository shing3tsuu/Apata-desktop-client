import asyncio
import logging
import os
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any, Protocol
from uuid import UUID

from dishka import AsyncContainer

from src.adapters.api.dto import ContactPublicDTO
from src.adapters.api.service import (
    ChatHTTPService,
    ContactHTTPService,
    FileHTTPService,
    MessageHTTPService,
)
from src.adapters.database.dto import (
    AddChatDTO,
    AddChatEventDTO,
    AddChatParticipantDTO,
    AddContactDTO,
    AddMessageFileDTO,
    AddMessageTextDTO,
    ChatDTO,
    ContactDTO,
    MessageDTO,
    RequestContactDTO,
)
from src.adapters.database.service import ChatService, ContactService, MessageService
from src.adapters.database.structures import (
    ChatEventTypeEnum,
    ContactStatusEnum,
    MessageContentMimeTypeEnum,
    MessageContentTypeEnum,
)
from src.exceptions import APIError
from src.providers.cache import ChatCache, ContactCache, MessageCache
from src.providers.state import AppState

logger = logging.getLogger(__name__)


class RealtimeSynchronizationStep(Protocol):
    async def __call__(
        self,
        container: AsyncContainer,
    ) -> tuple[bool, str, dict[str, int]]: ...


def _parse_last_seen(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


async def _persist_contact_mutation(
    contact_service: ContactService,
    app_state: AppState,
    contact_cache: ContactCache,
    response: ContactPublicDTO,
) -> ContactDTO:
    local_user_id = app_state.local_user_id
    if local_user_id is None:
        raise ValueError("Local user ID is missing")

    server_user_id = UUID(response.user_id)
    if server_user_id != contact_cache.server_user_id:
        raise ValueError("Contact response user does not match selected contact")

    status = ContactStatusEnum(response.status)
    last_seen = _parse_last_seen(response.last_seen)
    existing = await contact_service.get_contact_by_server_user_id(
        local_user_id,
        server_user_id,
    )
    if existing is None:
        saved_contact = await contact_service.add_contact(
            AddContactDTO(
                local_user_id=local_user_id,
                server_user_id=server_user_id,
                status=status,
                username=response.username,
                ed_public_key=response.ed_public_key,
                ecdh_public_key=response.ecdh_public_key,
                last_seen=last_seen,
                online=response.online,
            )
        )
    else:
        updated_contact = await contact_service.update_contact(
            RequestContactDTO(
                local_user_id=local_user_id,
                server_user_id=server_user_id,
                status=status,
                username=response.username,
                ecdh_public_key=response.ecdh_public_key,
                last_seen=last_seen,
                online=response.online,
            )
        )
        if updated_contact is None:
            raise RuntimeError("Failed to update local contact")
        saved_contact = updated_contact

    cached_contact = next(
        (
            cached
            for cached in app_state.contacts_cache
            if cached.server_user_id == server_user_id
        ),
        None,
    )
    targets = [contact_cache]
    if cached_contact is None:
        app_state.contacts_cache.append(contact_cache)
    elif cached_contact is not contact_cache:
        targets.append(cached_contact)

    for target in targets:
        target.id = saved_contact.id
        target.username = response.username
        target.status = status
        target.last_seen = last_seen
        target.online = response.online
        target.ed_public_key = saved_contact.ed_public_key
        target.ecdh_public_key = response.ecdh_public_key

    return saved_contact


async def _find_server_contact(
    contact_http_service: ContactHTTPService,
    server_user_id: UUID,
) -> ContactPublicDTO | None:
    contacts = await contact_http_service.list_all_contacts()
    return next(
        (contact for contact in contacts if contact.user_id == str(server_user_id)),
        None,
    )


class SearchContactsLocalInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        username: str,
    ) -> list[ContactDTO]:
        query = username.strip()
        if not query:
            return []

        try:
            async with container() as request_container:
                contact_service = await request_container.get(ContactService)
                app_state = await request_container.get(AppState)
                local_user_id = app_state.local_user_id
                if local_user_id is None:
                    return []

                return await contact_service.search_contacts_by_username(
                    local_user_id=local_user_id,
                    username=query,
                )

        except Exception:
            return []


class SearchContactsGlobalInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        username: str,
    ) -> list[ContactPublicDTO]:
        query = username.strip()
        if len(query) < 2:
            return []

        try:
            async with container() as request_container:
                contact_http_service = await request_container.get(ContactHTTPService)
                app_state = await request_container.get(AppState)
                token = app_state.token
                if token is None:
                    return []

                contact_http_service.token = token
                contacts = await contact_http_service.search_all_contacts(query)

                current_user_id = app_state.server_user_id
                if current_user_id is None:
                    return contacts

                return [
                    contact
                    for contact in contacts
                    if contact.user_id != str(current_user_id)
                ]

        except Exception:
            return []


class CreateChatInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        name: str,
    ) -> tuple[bool, str, ChatCache | None]:
        chat_name = name.strip()
        if not chat_name:
            return False, "CHAT NAME CANNOT BE EMPTY", None
        if len(chat_name) > 100:
            return False, "CHAT NAME CANNOT EXCEED 100 CHARACTERS", None

        try:
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                token = app_state.token
                local_user_id = app_state.local_user_id
                server_user_id = app_state.server_user_id
                if token is None or local_user_id is None or server_user_id is None:
                    return False, "CHAT CREATION PREREQUISITES MISSING", None

                chat_http_service = await request_container.get(ChatHTTPService)
                chat_service = await request_container.get(ChatService)
                chat_http_service.token = token
                server_chat = await chat_http_service.create_chat(chat_name)
                if server_chat.owner_id != server_user_id:
                    logger.error(
                        "Created chat owner does not match current user: "
                        "server_chat_id=%s owner_id=%s current_user_id=%s",
                        server_chat.id,
                        server_chat.owner_id,
                        server_user_id,
                    )
                    raise ValueError("Created chat owner does not match current user")

                try:
                    local_chat = await chat_service.add_chat(
                        AddChatDTO(
                            local_user_id=local_user_id,
                            server_chat_id=server_chat.id,
                            server_owner_id=server_chat.owner_id,
                            name=server_chat.name,
                            created_at=server_chat.created_at,
                        )
                    )
                except Exception as error:
                    logger.exception(
                        "Chat was created on the server but local persistence "
                        "failed: server_chat_id=%s",
                        server_chat.id,
                    )
                    return (
                        False,
                        f"LOCAL CHAT PERSISTENCE FAILED: {str(error).upper()}",
                        None,
                    )

                cached_chat = ChatCache(
                    id=local_chat.id,
                    server_chat_id=local_chat.server_chat_id,
                    server_owner_id=local_chat.server_owner_id,
                    name=local_chat.name,
                    created_at=local_chat.created_at,
                )
                existing_cache = next(
                    (
                        chat
                        for chat in app_state.chats_cache
                        if chat.server_chat_id == cached_chat.server_chat_id
                    ),
                    None,
                )
                if existing_cache is None:
                    app_state.chats_cache.append(cached_chat)
                else:
                    cached_chat = existing_cache
                return True, "SUCCESS", cached_chat
        except Exception as error:
            return False, str(error).upper(), None


class AddChatParticipantInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        chat_cache: ChatCache,
        contact_cache: ContactCache,
    ) -> tuple[bool, str, ContactCache | None]:
        if contact_cache.status is not ContactStatusEnum.ACCEPTED:
            return False, "ONLY ACCEPTED CONTACTS CAN BE ADDED TO CHATS", None
        if any(
            participant.server_user_id == contact_cache.server_user_id
            for participant in chat_cache.participants
        ):
            return False, "CONTACT IS ALREADY A CHAT PARTICIPANT", None

        try:
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                token = app_state.token
                local_user_id = app_state.local_user_id
                server_user_id = app_state.server_user_id
                if token is None or local_user_id is None or server_user_id is None:
                    return False, "CHAT PARTICIPANT PREREQUISITES MISSING", None
                if contact_cache.server_user_id == server_user_id:
                    return False, "CURRENT USER CANNOT BE ADDED AS A CONTACT", None

                current_chat = next(
                    (
                        chat
                        for chat in app_state.chats_cache
                        if chat.server_chat_id == chat_cache.server_chat_id
                    ),
                    None,
                )
                if current_chat is None or current_chat.id != chat_cache.id:
                    return False, "CHAT CACHE IS NOT CURRENT", None

                current_contact = next(
                    (
                        contact
                        for contact in app_state.contacts_cache
                        if contact.server_user_id == contact_cache.server_user_id
                    ),
                    None,
                )
                if current_contact is None or current_contact.id != contact_cache.id:
                    return False, "CONTACT CACHE IS NOT CURRENT", None
                if current_contact.status is not ContactStatusEnum.ACCEPTED:
                    return False, "ONLY ACCEPTED CONTACTS CAN BE ADDED TO CHATS", None

                chat_http_service = await request_container.get(ChatHTTPService)
                chat_service = await request_container.get(ChatService)
                contact_service = await request_container.get(ContactService)

                local_chat = await chat_service.get_chat_by_id(current_chat.id)
                if (
                    local_chat.local_user_id != local_user_id
                    or local_chat.server_chat_id != current_chat.server_chat_id
                ):
                    return False, "CHAT CACHE DOES NOT MATCH LOCAL CHAT", None

                local_contact = await contact_service.get_contact_by_server_user_id(
                    local_user_id,
                    current_contact.server_user_id,
                )
                if local_contact is None or local_contact.id != current_contact.id:
                    return False, "CONTACT CACHE DOES NOT MATCH LOCAL CONTACT", None
                if local_contact.status is not ContactStatusEnum.ACCEPTED:
                    return False, "ONLY ACCEPTED CONTACTS CAN BE ADDED TO CHATS", None

                existing_participant = await chat_service.get_participant(
                    local_chat.id,
                    local_contact.id,
                )
                if (
                    existing_participant is not None
                    and existing_participant.left_at is None
                ):
                    return False, "CONTACT IS ALREADY A CHAT PARTICIPANT", None

                chat_http_service.token = token
                change = await chat_http_service.add_participant(
                    current_chat.server_chat_id,
                    current_contact.server_user_id,
                )
                participant = change.participant
                event = change.event
                if (
                    participant.chat_id != current_chat.server_chat_id
                    or participant.user_id != current_contact.server_user_id
                    or participant.invited_by_user_id != server_user_id
                    or participant.left_at is not None
                    or event.chat_id != current_chat.server_chat_id
                    or event.user_id != server_user_id
                    or event.target_user_id != current_contact.server_user_id
                ):
                    raise ValueError("Chat participant response does not match request")

                try:
                    event_type = ChatEventTypeEnum(event.event_type)
                except ValueError as error:
                    raise ValueError(
                        "Unsupported chat participant event type"
                    ) from error
                if event_type not in {
                    ChatEventTypeEnum.MEMBER_ADDED,
                    ChatEventTypeEnum.MEMBER_JOINED,
                }:
                    raise ValueError("Unsupported chat participant event type")

                try:
                    await chat_service.add_participant(
                        AddChatParticipantDTO(
                            chat_id=local_chat.id,
                            contact_id=local_contact.id,
                            joined_at=participant.joined_at,
                            left_at=participant.left_at,
                        ),
                        create_join_event=False,
                    )
                    await chat_service.add_chat_event(
                        AddChatEventDTO(
                            chat_id=local_chat.id,
                            server_event_id=event.id,
                            actor_server_user_id=event.user_id,
                            target_server_user_id=event.target_user_id,
                            event_type=event_type,
                            timestamp=event.timestamp,
                        )
                    )
                except Exception as error:
                    logger.exception(
                        "Chat participant was added on the server but local "
                        "persistence failed: chat=%s contact=%s",
                        current_chat.server_chat_id,
                        current_contact.server_user_id,
                    )
                    return (
                        False,
                        "LOCAL CHAT PARTICIPANT PERSISTENCE FAILED: "
                        f"{str(error).upper()}",
                        None,
                    )

                latest_chat = next(
                    (
                        chat
                        for chat in app_state.chats_cache
                        if chat.server_chat_id == current_chat.server_chat_id
                    ),
                    None,
                )
                latest_contact = next(
                    (
                        contact
                        for contact in app_state.contacts_cache
                        if contact.server_user_id == current_contact.server_user_id
                    ),
                    None,
                )
                if latest_chat is not None and latest_contact is not None:
                    if all(
                        cached.server_user_id != latest_contact.server_user_id
                        for cached in latest_chat.participants
                    ):
                        latest_chat.participants.append(latest_contact)
                    current_contact = latest_contact
                return True, "SUCCESS", current_contact
        except Exception as error:
            return False, str(error).upper(), None


class SendContactRequestInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        contact_cache: ContactCache,
    ) -> tuple[bool, str, ContactDTO | None]:
        try:
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                token = app_state.token
                if token is None or app_state.local_user_id is None:
                    return False, "CONTACT ACTION PREREQUISITES MISSING", None

                contact_http_service = await request_container.get(ContactHTTPService)
                contact_service = await request_container.get(ContactService)
                contact_http_service.token = token
                response = await contact_http_service.create_contact_request(
                    str(contact_cache.server_user_id)
                )
                saved_contact = await _persist_contact_mutation(
                    contact_service,
                    app_state,
                    contact_cache,
                    response,
                )
                return True, "SUCCESS", saved_contact
        except Exception as error:
            return False, str(error).upper(), None


class AcceptContactRequestInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        contact_cache: ContactCache,
    ) -> tuple[bool, str, ContactDTO | None]:
        try:
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                token = app_state.token
                if token is None or app_state.local_user_id is None:
                    return False, "CONTACT ACTION PREREQUISITES MISSING", None

                contact_http_service = await request_container.get(ContactHTTPService)
                contact_service = await request_container.get(ContactService)
                contact_http_service.token = token
                server_contact = await _find_server_contact(
                    contact_http_service,
                    contact_cache.server_user_id,
                )
                if server_contact is None or server_contact.contact_id is None:
                    return False, "CONTACT REQUEST NOT FOUND", None

                response = await contact_http_service.accept_contact_request_dto(
                    server_contact.contact_id
                )
                saved_contact = await _persist_contact_mutation(
                    contact_service,
                    app_state,
                    contact_cache,
                    response,
                )
                return True, "SUCCESS", saved_contact
        except Exception as error:
            return False, str(error).upper(), None


class BlacklistContactInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        contact_cache: ContactCache,
    ) -> tuple[bool, str, ContactDTO | None]:
        try:
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                token = app_state.token
                if token is None or app_state.local_user_id is None:
                    return False, "CONTACT ACTION PREREQUISITES MISSING", None

                contact_http_service = await request_container.get(ContactHTTPService)
                contact_service = await request_container.get(ContactService)
                contact_http_service.token = token
                response = await contact_http_service.blacklist_contact(
                    str(contact_cache.server_user_id)
                )
                saved_contact = await _persist_contact_mutation(
                    contact_service,
                    app_state,
                    contact_cache,
                    response,
                )
                return True, "SUCCESS", saved_contact
        except Exception as error:
            return False, str(error).upper(), None


class SendContactTextMessageInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        contact_cache: ContactCache,
        text: str,
        reply_to_message: MessageCache | None = None,
    ) -> tuple[bool, str, MessageDTO | None]:
        message_text = text.strip()
        if not message_text:
            return False, "MESSAGE CANNOT BE EMPTY", None

        try:
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                token = app_state.token
                local_user_id = app_state.local_user_id
                master_key = app_state.master_key
                ed_private_key = app_state.ed_private_key
                ecdh_private_key = app_state.ecdh_private_key
                ecdh_public_key = app_state.ecdh_public_key
                if (
                    token is None
                    or local_user_id is None
                    or master_key is None
                    or ed_private_key is None
                    or ecdh_private_key is None
                    or ecdh_public_key is None
                ):
                    return False, "MESSAGE SENDING PREREQUISITES MISSING", None

                contact_service = await request_container.get(ContactService)
                message_http_service = await request_container.get(MessageHTTPService)
                message_service = await request_container.get(MessageService)
                contact = await contact_service.get_contact_by_server_user_id(
                    local_user_id,
                    contact_cache.server_user_id,
                )
                if contact is None:
                    if (
                        contact_cache.ed_public_key is None
                        or contact_cache.ecdh_public_key is None
                    ):
                        return False, "CONTACT PUBLIC KEYS MISSING", None
                    contact = await contact_service.add_contact(
                        AddContactDTO(
                            local_user_id=local_user_id,
                            server_user_id=contact_cache.server_user_id,
                            status=ContactStatusEnum.BLANK,
                            username=contact_cache.username,
                            ed_public_key=contact_cache.ed_public_key,
                            ecdh_public_key=contact_cache.ecdh_public_key,
                            last_seen=contact_cache.last_seen,
                            online=contact_cache.online,
                        )
                    )
                contact_cache.id = contact.id
                contact_cache.status = contact.status
                contact_cache.ed_public_key = contact.ed_public_key
                contact_cache.ecdh_public_key = contact.ecdh_public_key
                if all(
                    cached.server_user_id != contact_cache.server_user_id
                    for cached in app_state.contacts_cache
                ):
                    app_state.contacts_cache.append(contact_cache)

                message_service.master_key = master_key
                reply_target: MessageDTO | None = None
                if reply_to_message is not None:
                    if (
                        reply_to_message.chat_id is not None
                        or reply_to_message.contact_id != contact.id
                    ):
                        return False, "REPLY TARGET IS OUTSIDE THE CONVERSATION", None
                    reply_target = await message_service.get_message_by_server_id(
                        local_user_id,
                        reply_to_message.server_message_id,
                    )
                    if (
                        reply_target is None
                        or reply_target.id != reply_to_message.id
                        or reply_target.contact_id != contact.id
                        or reply_target.chat_id is not None
                    ):
                        return False, "REPLY TARGET IS NOT AVAILABLE", None

                message_http_service.token = token
                sent_message = (
                    await message_http_service.send_encrypted_message_text(
                        recipient_id=contact.server_user_id,
                        chat_id=None,
                        message=message_text,
                        recipient_ed_public_key=contact.ed_public_key,
                        sender_ed_private_key=ed_private_key,
                        sender_ecdh_private_key=ecdh_private_key,
                        ephemeral_ecdh_public_key=ecdh_public_key,
                        reply_to_id=(
                            reply_target.server_message_id
                            if reply_target is not None
                            else None
                        ),
                    )
                )
                if sent_message is None:
                    return False, "FAILED TO SEND MESSAGE", None

                saved_message = await message_service.add_message_text(
                    AddMessageTextDTO(
                        local_user_id=local_user_id,
                        server_message_id=sent_message.id,
                        contact_id=contact.id,
                        chat_id=None,
                        server_reply_to_id=(
                            reply_target.server_message_id
                            if reply_target is not None
                            else None
                        ),
                        reply_to_id=(
                            reply_target.id if reply_target is not None else None
                        ),
                        content=message_text,
                        content_type=MessageContentTypeEnum.TEXT,
                        timestamp=sent_message.timestamp,
                        is_outgoing=True,
                        is_delivered=True,
                    )
                )
                self._update_contact_cache(
                    app_state,
                    contact.id,
                    saved_message,
                    message_text,
                    reply_to_message,
                )
                return True, "SUCCESS", saved_message

        except Exception as error:
            return False, str(error).upper(), None

    @staticmethod
    def _update_contact_cache(
        app_state: AppState,
        contact_id: UUID,
        saved_message: MessageDTO,
        message_text: str,
        reply_to_message: MessageCache | None,
    ) -> None:
        cached_contact = next(
            (
                contact
                for contact in app_state.contacts_cache
                if contact.id == contact_id
            ),
            None,
        )
        if cached_contact is None:
            return

        cached_contact.messages.append(
            MessageCache(
                id=saved_message.id,
                server_message_id=saved_message.server_message_id,
                general_message_uuid=saved_message.general_message_uuid,
                contact_id=saved_message.contact_id,
                chat_id=None,
                content_type=MessageContentTypeEnum.TEXT,
                content=message_text,
                file_name=None,
                file_size=None,
                file_mime_type=None,
                timestamp=saved_message.timestamp,
                is_outgoing=True,
                is_delivered=saved_message.is_delivered,
                failed=saved_message.failed,
                server_reply_to_id=saved_message.server_reply_to_id,
                reply_to_id=saved_message.reply_to_id,
                reply_author=(
                    app_state.username or "UNKNOWN USER"
                    if reply_to_message is not None and reply_to_message.is_outgoing
                    else cached_contact.username
                    if reply_to_message is not None
                    else None
                ),
                reply_text=(
                    SendContactTextMessageInteractor._reply_preview(reply_to_message)
                    if reply_to_message is not None
                    else None
                ),
            )
        )
        cached_contact.messages.sort(key=lambda message: message.timestamp)
        del cached_contact.messages[:-10]

    @staticmethod
    def _reply_preview(message: MessageCache) -> str:
        if message.content:
            return " ".join(message.content.split())
        if message.content_type is MessageContentTypeEnum.IMAGE:
            return "PHOTO"
        if message.content_type is MessageContentTypeEnum.VIDEO:
            return "VIDEO"
        return message.file_name or message.content_type.value.upper()


class SendContactFileMessageInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        contact_cache: ContactCache,
        file_path: str,
    ) -> tuple[bool, str, MessageDTO | None]:
        source_path = Path(file_path)
        if not source_path.is_file():
            return False, "FILE DOES NOT EXIST", None

        file_size = source_path.stat().st_size
        if file_size > FileHTTPService.MAX_PLAINTEXT_FILE_SIZE:
            return False, "FILE EXCEEDS 100 MIB LIMIT", None

        file_mime_type = self._parse_file_mime_type(source_path)
        if file_mime_type is None:
            return False, "FILE TYPE IS NOT SUPPORTED", None

        file_name = source_path.name[: -len(source_path.suffix)]
        if not file_name:
            return False, "FILE NAME CANNOT BE EMPTY", None

        try:
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                token = app_state.token
                local_user_id = app_state.local_user_id
                master_key = app_state.master_key
                ed_private_key = app_state.ed_private_key
                ecdh_private_key = app_state.ecdh_private_key
                ecdh_public_key = app_state.ecdh_public_key
                if (
                    token is None
                    or local_user_id is None
                    or master_key is None
                    or ed_private_key is None
                    or ecdh_private_key is None
                    or ecdh_public_key is None
                ):
                    return False, "FILE SENDING PREREQUISITES MISSING", None

                contact_service = await request_container.get(ContactService)
                file_http_service = await request_container.get(FileHTTPService)
                message_service = await request_container.get(MessageService)
                contact = await contact_service.get_contact_by_server_user_id(
                    local_user_id,
                    contact_cache.server_user_id,
                )
                recipient_ed_public_key = (
                    contact.ed_public_key
                    if contact is not None
                    else contact_cache.ed_public_key
                )
                if recipient_ed_public_key is None:
                    return False, "CONTACT ED PUBLIC KEY MISSING", None
                if contact is None and contact_cache.ecdh_public_key is None:
                    return False, "CONTACT ECDH PUBLIC KEY MISSING", None

                file_content = await asyncio.to_thread(source_path.read_bytes)
                if len(file_content) > FileHTTPService.MAX_PLAINTEXT_FILE_SIZE:
                    return False, "FILE EXCEEDS 100 MIB LIMIT", None

                file_http_service.token = token
                server_message_id = await file_http_service.send_encrypted_message_file(
                    chat_id=None,
                    recipient_id=contact_cache.server_user_id,
                    recipient_ed_public_key=recipient_ed_public_key,
                    sender_ed_private_key=ed_private_key,
                    sender_ecdh_private_key=ecdh_private_key,
                    ephemeral_ecdh_public_key=ecdh_public_key,
                    file_name=file_name,
                    file_mime_type=file_mime_type.value,
                    file_content=file_content,
                )
                if server_message_id is None:
                    return False, "FAILED TO SEND FILE", None

                if contact is None:
                    contact = await contact_service.add_contact(
                        AddContactDTO(
                            local_user_id=local_user_id,
                            server_user_id=contact_cache.server_user_id,
                            status=ContactStatusEnum.BLANK,
                            username=contact_cache.username,
                            ed_public_key=recipient_ed_public_key,
                            ecdh_public_key=contact_cache.ecdh_public_key,
                            last_seen=contact_cache.last_seen,
                            online=contact_cache.online,
                        )
                    )
                    self._map_contact_cache(app_state, contact_cache, contact)

                content_type = MessageContentTypeEnum(
                    FileHTTPService.get_content_type(file_mime_type.value)
                )
                message_service.master_key = master_key
                saved_message = await message_service.add_message_file(
                    AddMessageFileDTO(
                        local_user_id=local_user_id,
                        server_message_id=server_message_id,
                        contact_id=contact.id,
                        chat_id=None,
                        file_name=file_name,
                        file_content=file_content,
                        file_size=len(file_content),
                        file_mime_type=file_mime_type,
                        content_type=content_type,
                        is_outgoing=True,
                        is_delivered=True,
                    )
                )
                self._update_contact_cache(app_state, contact.id, saved_message)
                return True, "SUCCESS", saved_message
        except Exception as error:
            return False, str(error).upper(), None

    @staticmethod
    def _parse_file_mime_type(
        source_path: Path,
    ) -> MessageContentMimeTypeEnum | None:
        try:
            return MessageContentMimeTypeEnum(source_path.suffix.lower())
        except ValueError:
            return None

    @staticmethod
    def _map_contact_cache(
        app_state: AppState,
        contact_cache: ContactCache,
        contact: ContactDTO,
    ) -> None:
        contact_cache.id = contact.id
        contact_cache.status = contact.status
        contact_cache.ed_public_key = contact.ed_public_key
        contact_cache.ecdh_public_key = contact.ecdh_public_key
        if all(
            cached.server_user_id != contact_cache.server_user_id
            for cached in app_state.contacts_cache
        ):
            app_state.contacts_cache.append(contact_cache)

    @staticmethod
    def _update_contact_cache(
        app_state: AppState,
        contact_id: UUID,
        saved_message: MessageDTO,
    ) -> None:
        cached_contact = next(
            (
                contact
                for contact in app_state.contacts_cache
                if contact.id == contact_id
            ),
            None,
        )
        if cached_contact is None:
            return
        cached_contact.messages.append(
            MessageCache(
                id=saved_message.id,
                server_message_id=saved_message.server_message_id,
                general_message_uuid=saved_message.general_message_uuid,
                contact_id=saved_message.contact_id,
                chat_id=saved_message.chat_id,
                content_type=saved_message.content_type,
                content=None,
                file_name=saved_message.file_name,
                file_size=saved_message.file_size,
                file_mime_type=saved_message.file_mime_type,
                timestamp=saved_message.timestamp,
                is_outgoing=saved_message.is_outgoing,
                is_delivered=saved_message.is_delivered,
                failed=saved_message.failed,
            )
        )
        cached_contact.messages.sort(key=lambda message: message.timestamp)
        del cached_contact.messages[:-10]


class LoadConversationFileMessagesInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        message_ids: Sequence[UUID],
    ) -> tuple[bool, str, dict[UUID, bytes]]:
        unique_message_ids = list(dict.fromkeys(message_ids))
        if not unique_message_ids:
            return True, "SUCCESS", {}

        try:
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                local_user_id = app_state.local_user_id
                master_key = app_state.master_key
                if local_user_id is None or master_key is None:
                    return False, "FILE LOADING PREREQUISITES MISSING", {}

                message_service = await request_container.get(MessageService)
                message_service.master_key = master_key
                messages = await message_service.get_file_messages(
                    local_user_id,
                    unique_message_ids,
                )
                return (
                    True,
                    "SUCCESS",
                    {
                        message.id: message.file_content
                        for message in messages
                        if message.file_content is not None
                    },
                )
        except Exception as error:
            return False, str(error).upper(), {}


class SaveMessageFileToDiskInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        message_id: UUID,
        destination_path: str,
    ) -> tuple[bool, str, Path | None]:
        selected_path = destination_path.strip()
        if not selected_path:
            return False, "DESTINATION PATH IS EMPTY", None

        try:
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                local_user_id = app_state.local_user_id
                master_key = app_state.master_key
                if local_user_id is None or master_key is None:
                    return False, "FILE SAVING PREREQUISITES MISSING", None

                message_service = await request_container.get(MessageService)
                message_service.master_key = master_key
                messages = await message_service.get_file_messages(
                    local_user_id,
                    [message_id],
                )
                message = next(
                    (item for item in messages if item.id == message_id),
                    None,
                )
                if message is None:
                    return False, "FILE MESSAGE NOT FOUND", None
                if (
                    message.file_content is None
                    or message.file_name is None
                    or message.file_size is None
                    or message.file_mime_type is None
                ):
                    return False, "FILE MESSAGE METADATA IS INCOMPLETE", None
                if len(message.file_content) != message.file_size:
                    return (
                        False,
                        "FILE CONTENT SIZE DOES NOT MATCH METADATA",
                        None,
                    )

                destination = await asyncio.to_thread(
                    self._resolve_destination,
                    Path(selected_path).expanduser(),
                    message.file_name,
                    message.file_mime_type.value,
                )
                await asyncio.to_thread(
                    self._write_file_atomically,
                    destination,
                    message.file_content,
                )
                return True, "SUCCESS", destination
        except Exception as error:
            return False, str(error).upper(), None

    @staticmethod
    def _resolve_destination(
        selected_path: Path,
        file_name: str,
        extension: str,
    ) -> Path:
        if selected_path.exists() and selected_path.is_dir():
            destination = selected_path / f"{file_name}{extension}"
        elif selected_path.name.lower().endswith(extension.lower()):
            destination = selected_path
        else:
            destination = Path(f"{selected_path}{extension}")

        if not destination.parent.exists() or not destination.parent.is_dir():
            raise ValueError("Destination directory does not exist")
        return destination

    @staticmethod
    def _write_file_atomically(destination: Path, content: bytes) -> None:
        temporary_path: Path | None = None
        try:
            with NamedTemporaryFile(
                mode="wb",
                dir=destination.parent,
                prefix=f".{destination.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                written = temporary_file.write(content)
                if written != len(content):
                    raise OSError("Failed to write complete file content")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            os.replace(temporary_path, destination)
            temporary_path = None
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)


class GetChatReplyTargetsInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        chat_cache: ChatCache,
        general_message_uuid: UUID | None,
    ) -> tuple[bool, str, dict[UUID, UUID]]:
        if general_message_uuid is None:
            return False, "QUOTED CHAT MESSAGE HAS NO GENERAL MESSAGE UUID", {}

        try:
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                token = app_state.token
                if token is None:
                    return False, "CHAT REPLY TARGET PREREQUISITES MISSING", {}

                current_chat = next(
                    (
                        chat
                        for chat in app_state.chats_cache
                        if chat.server_chat_id == chat_cache.server_chat_id
                    ),
                    None,
                )
                if current_chat is None or current_chat.id != chat_cache.id:
                    return False, "CHAT CACHE IS NOT CURRENT", {}

                chat_http_service = await request_container.get(ChatHTTPService)
                chat_http_service.token = token
                targets = await chat_http_service.get_reply_targets(
                    current_chat.server_chat_id,
                    general_message_uuid,
                )

                user_ids = [target.user_id for target in targets]
                if len(user_ids) != len(set(user_ids)):
                    raise APIError("Chat reply targets contain duplicate users")

                message_ids = [target.message_id for target in targets]
                if len(message_ids) != len(set(message_ids)):
                    raise APIError("Chat reply targets contain duplicate messages")

                return (
                    True,
                    "SUCCESS",
                    {target.user_id: target.message_id for target in targets},
                )
        except Exception as error:
            return False, str(error).upper(), {}


class SendChatTextMessageInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        chat_cache: ChatCache,
        text: str,
        reply_to_message: MessageCache | None = None,
        reply_targets: dict[UUID, UUID] | None = None,
    ) -> tuple[bool, str, MessageDTO | None]:
        message_text = text.strip()
        if not message_text:
            return False, "MESSAGE CANNOT BE EMPTY", None

        try:
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                token = app_state.token
                local_user_id = app_state.local_user_id
                server_user_id = app_state.server_user_id
                master_key = app_state.master_key
                ed_private_key = app_state.ed_private_key
                ecdh_private_key = app_state.ecdh_private_key
                ecdh_public_key = app_state.ecdh_public_key
                if (
                    token is None
                    or local_user_id is None
                    or server_user_id is None
                    or master_key is None
                    or ed_private_key is None
                    or ecdh_private_key is None
                    or ecdh_public_key is None
                ):
                    return False, "MESSAGE SENDING PREREQUISITES MISSING", None

                chat_http_service = await request_container.get(ChatHTTPService)
                contact_http_service = await request_container.get(ContactHTTPService)
                chat_service = await request_container.get(ChatService)
                contact_service = await request_container.get(ContactService)
                message_http_service = await request_container.get(MessageHTTPService)
                message_service = await request_container.get(MessageService)

                local_chat: ChatDTO = await chat_service.get_chat_by_id(chat_cache.id)
                if local_chat.server_chat_id != chat_cache.server_chat_id:
                    return False, "CHAT CACHE DOES NOT MATCH LOCAL CHAT", None

                message_service.master_key = master_key
                reply_target: MessageDTO | None = None
                current_reply_targets = reply_targets
                if reply_to_message is not None:
                    if (
                        reply_to_message.chat_id != local_chat.id
                        or reply_to_message.general_message_uuid is None
                    ):
                        return False, "REPLY TARGET IS OUTSIDE THE CHAT", None
                    if current_reply_targets is None:
                        return False, "CHAT REPLY TARGETS ARE MISSING", None
                    reply_target = await message_service.get_message_by_server_id(
                        local_user_id,
                        reply_to_message.server_message_id,
                    )
                    if (
                        reply_target is None
                        or reply_target.id != reply_to_message.id
                        or reply_target.chat_id != local_chat.id
                        or reply_target.general_message_uuid
                        != reply_to_message.general_message_uuid
                    ):
                        return False, "REPLY TARGET IS NOT AVAILABLE", None
                elif current_reply_targets is not None:
                    return False, "CHAT REPLY MESSAGE IS MISSING", None

                chat_http_service.token = token
                contact_http_service.token = token
                message_http_service.token = token

                sent_deliveries = None
                for attempt in range(2):
                    if attempt and reply_target is not None:
                        refreshed_targets = await chat_http_service.get_reply_targets(
                            chat_cache.server_chat_id,
                            reply_target.general_message_uuid,
                        )
                        refreshed_user_ids = [
                            target.user_id for target in refreshed_targets
                        ]
                        if len(refreshed_user_ids) != len(set(refreshed_user_ids)):
                            return False, "CHAT REPLY TARGET USERS MUST BE UNIQUE", None
                        current_reply_targets = {
                            target.user_id: target.message_id
                            for target in refreshed_targets
                        }
                    participants = await chat_http_service.get_participants(
                        chat_cache.server_chat_id
                    )
                    participant_ids = [
                        participant.user_id for participant in participants
                    ]
                    if len(participant_ids) != len(set(participant_ids)):
                        return False, "CHAT PARTICIPANTS MUST BE UNIQUE", None
                    if server_user_id not in participant_ids:
                        return False, "USER IS NOT AN ACTIVE CHAT PARTICIPANT", None

                    recipient_ids = set(participant_ids) - {server_user_id}
                    if not recipient_ids:
                        return False, "CHAT HAS NO MESSAGE RECIPIENTS", None

                    local_contacts = await contact_service.get_contacts(local_user_id)
                    contacts_by_server_id = {
                        contact.server_user_id: contact for contact in local_contacts
                    }
                    missing_contact_ids = recipient_ids - set(contacts_by_server_id)
                    if missing_contact_ids:
                        server_contacts = await contact_http_service.list_all_contacts()
                        server_contacts_by_id = {
                            UUID(contact.user_id): contact
                            for contact in server_contacts
                            if UUID(contact.user_id) in missing_contact_ids
                        }
                        for missing_contact_id in sorted(
                            missing_contact_ids,
                            key=str,
                        ):
                            server_contact = server_contacts_by_id.get(
                                missing_contact_id
                            )
                            if server_contact is None:
                                continue
                            saved_contact = await contact_service.add_contact(
                                AddContactDTO(
                                    local_user_id=local_user_id,
                                    server_user_id=missing_contact_id,
                                    status=ContactStatusEnum(server_contact.status),
                                    username=server_contact.username,
                                    ed_public_key=server_contact.ed_public_key,
                                    ecdh_public_key=server_contact.ecdh_public_key,
                                    last_seen=_parse_last_seen(
                                        server_contact.last_seen
                                    ),
                                    online=server_contact.online,
                                )
                            )
                            cached_contact = next(
                                (
                                    contact
                                    for contact in app_state.contacts_cache
                                    if contact.server_user_id == missing_contact_id
                                ),
                                None,
                            )
                            if cached_contact is None:
                                app_state.contacts_cache.append(
                                    ContactCache(
                                        id=saved_contact.id,
                                        server_user_id=saved_contact.server_user_id,
                                        username=saved_contact.username,
                                        status=saved_contact.status,
                                        last_seen=saved_contact.last_seen,
                                        online=saved_contact.online,
                                        ed_public_key=saved_contact.ed_public_key,
                                        ecdh_public_key=saved_contact.ecdh_public_key,
                                    )
                                )
                            else:
                                cached_contact.id = saved_contact.id
                                cached_contact.username = saved_contact.username
                                cached_contact.status = saved_contact.status
                                cached_contact.last_seen = saved_contact.last_seen
                                cached_contact.online = saved_contact.online
                                cached_contact.ed_public_key = (
                                    saved_contact.ed_public_key
                                )
                                cached_contact.ecdh_public_key = (
                                    saved_contact.ecdh_public_key
                                )

                        local_contacts = await contact_service.get_contacts(
                            local_user_id
                        )
                        contacts_by_server_id = {
                            contact.server_user_id: contact
                            for contact in local_contacts
                        }

                    if any(
                        recipient_id not in contacts_by_server_id
                        or not contacts_by_server_id[recipient_id].ed_public_key
                        for recipient_id in recipient_ids
                    ):
                        return False, "PINNED ED PUBLIC KEY IS MISSING", None

                    recipient_ed_public_keys: dict[UUID, str] = {}
                    for recipient_id in recipient_ids:
                        ed_public_key = contacts_by_server_id[
                            recipient_id
                        ].ed_public_key
                        assert ed_public_key is not None
                        recipient_ed_public_keys[recipient_id] = ed_public_key
                    try:
                        sent_deliveries = (
                            await message_http_service.send_encrypted_chat_message_text(
                                chat_id=chat_cache.server_chat_id,
                                message=message_text,
                                recipient_ed_public_keys=recipient_ed_public_keys,
                                sender_ed_private_key=ed_private_key,
                                sender_ecdh_private_key=ecdh_private_key,
                                sender_ecdh_public_key=ecdh_public_key,
                                reply_to_general_message_uuid=(
                                    reply_target.general_message_uuid
                                    if reply_target is not None
                                    else None
                                ),
                                reply_targets=current_reply_targets,
                            )
                        )
                        break
                    except APIError as error:
                        if error.status_code != 409 or attempt == 1:
                            raise

                if not sent_deliveries:
                    return False, "FAILED TO SEND CHAT MESSAGE", None

                representative = min(
                    sent_deliveries,
                    key=lambda delivery: str(delivery.id),
                )
                saved_message = await message_service.add_message_text(
                    AddMessageTextDTO(
                        local_user_id=local_user_id,
                        server_message_id=representative.id,
                        general_message_uuid=representative.general_message_uuid,
                        server_reply_to_id=(
                            reply_target.server_message_id
                            if reply_target is not None
                            else None
                        ),
                        reply_to_general_message_uuid=(
                            reply_target.general_message_uuid
                            if reply_target is not None
                            else None
                        ),
                        reply_to_id=(
                            reply_target.id if reply_target is not None else None
                        ),
                        chat_id=local_chat.id,
                        content=message_text,
                        content_type=MessageContentTypeEnum.TEXT,
                        timestamp=representative.timestamp,
                        is_outgoing=True,
                        is_delivered=True,
                    )
                )
                cached_message = MessageCache(
                    id=saved_message.id,
                    server_message_id=saved_message.server_message_id,
                    general_message_uuid=saved_message.general_message_uuid,
                    server_reply_to_id=saved_message.server_reply_to_id,
                    reply_to_general_message_uuid=(
                        saved_message.reply_to_general_message_uuid
                    ),
                    reply_to_id=saved_message.reply_to_id,
                    contact_id=None,
                    chat_id=saved_message.chat_id,
                    content_type=MessageContentTypeEnum.TEXT,
                    content=message_text,
                    file_name=None,
                    file_size=None,
                    file_mime_type=None,
                    timestamp=saved_message.timestamp,
                    is_outgoing=True,
                    is_delivered=saved_message.is_delivered,
                    failed=None,
                    reply_author=(
                        app_state.username or "UNKNOWN USER"
                        if reply_to_message is not None
                        and reply_to_message.is_outgoing
                        else next(
                            (
                                contact.username
                                for contact in app_state.contacts_cache
                                if reply_to_message is not None
                                and contact.id == reply_to_message.contact_id
                            ),
                            "UNKNOWN USER",
                        )
                        if reply_to_message is not None
                        else None
                    ),
                    reply_text=(
                        SendContactTextMessageInteractor._reply_preview(
                            reply_to_message
                        )
                        if reply_to_message is not None
                        else None
                    ),
                )
                cache_targets = [chat_cache]
                state_chat = next(
                    (
                        cached_chat
                        for cached_chat in app_state.chats_cache
                        if cached_chat.id == local_chat.id
                    ),
                    None,
                )
                if state_chat is not None and state_chat is not chat_cache:
                    cache_targets.append(state_chat)
                for target in cache_targets:
                    target.messages.append(cached_message)
                    target.messages.sort(key=lambda message: message.timestamp)
                    del target.messages[:-10]
                return True, "SUCCESS", saved_message

        except Exception as error:
            return False, str(error).upper(), None


class ApplyPresenceChangedInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        payload: dict[str, Any],
    ) -> tuple[bool, str]:
        try:
            server_user_id = UUID(str(payload["user_id"]))
            online = payload["online"]
            if not isinstance(online, bool):
                return False, "INVALID PRESENCE STATUS"

            last_seen_value = payload.get("last_seen")
            last_seen = (
                datetime.fromisoformat(str(last_seen_value))
                if last_seen_value is not None
                else None
            )

            async with container() as request_container:
                app_state = await request_container.get(AppState)
                local_user_id = app_state.local_user_id
                if local_user_id is None:
                    return False, "LOCAL USER IS NOT AVAILABLE"

                contact_service = await request_container.get(ContactService)
                contact = await contact_service.get_contact_by_server_user_id(
                    local_user_id,
                    server_user_id,
                )
                if contact is None:
                    return True, "CONTACT IS NOT CACHED"

                await contact_service.update_contact(
                    RequestContactDTO(
                        local_user_id=local_user_id,
                        server_user_id=server_user_id,
                        online=online,
                        last_seen=last_seen,
                    )
                )
                for cached_contact in app_state.contacts_cache:
                    if cached_contact.server_user_id == server_user_id:
                        cached_contact.online = online
                        cached_contact.last_seen = last_seen
                        break
            return True, "SUCCESS"
        except (KeyError, TypeError, ValueError) as error:
            return False, str(error).upper()


class SynchronizeRealtimeInteractor:
    def __init__(
        self,
        synchronize_contacts: RealtimeSynchronizationStep,
        synchronize_chats: RealtimeSynchronizationStep,
        synchronize_messages: RealtimeSynchronizationStep,
        cache_conversations: RealtimeSynchronizationStep,
    ) -> None:
        self._synchronize_contacts = synchronize_contacts
        self._synchronize_chats = synchronize_chats
        self._synchronize_messages = synchronize_messages
        self._cache_conversations = cache_conversations

    async def __call__(
        self,
        container: AsyncContainer,
        *,
        contacts: bool = True,
        chats: bool = True,
        messages: bool = True,
    ) -> tuple[bool, str]:
        if contacts:
            success, message, _ = await self._synchronize_contacts(container)
            if not success:
                return False, message

        if chats:
            success, message, _ = await self._synchronize_chats(container)
            if not success:
                return False, message

        if messages:
            success, message, _ = await self._synchronize_messages(container)
            if not success:
                return False, message

        success, message, _ = await self._cache_conversations(container)
        return success, message
