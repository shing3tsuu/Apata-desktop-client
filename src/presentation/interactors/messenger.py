from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from dishka import AsyncContainer

from src.adapters.api.dto import ContactPublicDTO
from src.adapters.api.service import ContactHTTPService, MessageHTTPService
from src.adapters.database.dto import (
    AddContactDTO,
    AddMessageTextDTO,
    ContactDTO,
    MessageDTO,
    RequestContactDTO,
)
from src.adapters.database.service import ContactService, MessageService
from src.adapters.database.structures import ContactStatusEnum, MessageContentTypeEnum
from src.providers.cache import ContactCache, MessageCache
from src.providers.state import AppState


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
                ed_public_key=response.ed_public_key,
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
        target.ed_public_key = response.ed_public_key
        target.ecdh_public_key = response.ecdh_public_key

    return saved_contact


async def _find_server_contact(
    contact_http_service: ContactHTTPService,
    server_user_id: UUID,
) -> ContactPublicDTO | None:
    contacts = await contact_http_service.list_all_contacts()
    return next(
        (
            contact
            for contact in contacts
            if contact.user_id == str(server_user_id)
        ),
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
                contact_http_service = await request_container.get(
                    ContactHTTPService
                )
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

                contact_http_service = await request_container.get(
                    ContactHTTPService
                )
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

                contact_http_service = await request_container.get(
                    ContactHTTPService
                )
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

                contact_http_service = await request_container.get(
                    ContactHTTPService
                )
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
                message_http_service = await request_container.get(
                    MessageHTTPService
                )
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

                message_http_service.token = token
                server_message_id = (
                    await message_http_service.send_encrypted_message_text(
                        recipient_id=contact.server_user_id,
                        chat_id=None,
                        message=message_text,
                        recipient_ed_public_key=contact.ed_public_key,
                        sender_ed_private_key=ed_private_key,
                        sender_ecdh_private_key=ecdh_private_key,
                        ephemeral_ecdh_public_key=ecdh_public_key,
                    )
                )
                if server_message_id is None:
                    return False, "FAILED TO SEND MESSAGE", None

                message_service.master_key = master_key
                saved_message = await message_service.add_message_text(
                    AddMessageTextDTO(
                        local_user_id=local_user_id,
                        server_message_id=server_message_id,
                        contact_id=contact.id,
                        chat_id=None,
                        content=message_text,
                        content_type=MessageContentTypeEnum.TEXT,
                        is_outgoing=True,
                        is_delivered=True,
                    )
                )
                self._update_contact_cache(
                    app_state,
                    contact.id,
                    saved_message,
                    message_text,
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
            )
        )
        cached_contact.messages.sort(key=lambda message: message.timestamp)
        del cached_contact.messages[:-10]


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
