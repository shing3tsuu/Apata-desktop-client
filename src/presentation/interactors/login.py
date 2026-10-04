import asyncio
import inspect
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from dishka import AsyncContainer

from src.adapters.api.service import (
    AuthHTTPService,
    ChatHTTPService,
    ContactHTTPService,
    FileHTTPService,
    MessageHTTPService,
    WebSocketService,
)
from src.adapters.database.dto import (
    AddChatDTO,
    AddChatEventDTO,
    AddChatParticipantDTO,
    AddContactDTO,
    AddLocalUserDTO,
    AddMessageFileDTO,
    AddMessageTextDTO,
    MessageDTO,
    RequestChatDTO,
    RequestChatParticipantDTO,
    RequestContactDTO,
)
from src.adapters.database.service import (
    ChatService,
    ContactService,
    LocalUserService,
    MessageService,
)
from src.adapters.database.structures import (
    ChatEventTypeEnum,
    ContactStatusEnum,
    MessageContentMimeTypeEnum,
    MessageContentTypeEnum,
)
from src.adapters.encryption.dao import AbstractPasswordHasher
from src.adapters.encryption.storage import EncryptedKeyStorage
from src.exceptions import APIError
from src.providers.cache import ChatCache, ContactCache, MessageCache
from src.providers.state import AppState

from .messenger import (
    ApplyPresenceChangedInteractor,
    SynchronizeRealtimeInteractor,
)


class GetLocalUsernamesInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
    ) -> tuple[bool, list[str]]:
        try:
            async with container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                users = await local_user_service.get_users()

                return True, [user.username for user in users if user.username]

        except Exception:
            return False, []


class CheckLocalUserRegisterInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
        username: str,
        password: str,
    ) -> tuple[bool, str]:
        try:
            async with container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                app_state = await request_container.get(AppState)
                app_state.contacts_cache = []
                app_state.chats_cache = []

                if not username or not password:
                    return False, "USERNAME AND PASSWORD ARE REQUIRED"

                if len(username) < 3:
                    return False, "USERNAME TOO SHORT"

                if len(password) < 8:
                    return False, "PASSWORD MUST BE 8 CHARACTERS LONG"

                local_user = await local_user_service.get_user_by_username(username)

                if local_user:
                    return False, "USER WITH THIS NAME ALREADY EXISTS"
                else:
                    app_state.username = username
                    app_state.password = password
                    return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg


class RegisterUserOnServerInteractor:
    async def __call__(self, container: AsyncContainer) -> tuple[bool, str]:
        try:
            async with container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)
                app_state = await request_container.get(AppState)

                username = app_state.username
                if username is None:
                    return False, "CHECK LOCAL USER OPERATION SKIPPED"

                register_data = await auth_http_service.register(username=username)

                if not register_data or register_data["username"] != username:
                    return False, "REGISTRATION FAILED - INVALID RESPONSE FROM SERVER"
                else:
                    app_state.server_user_id = UUID(str(register_data.id))
                    app_state.ed_private_key = register_data.ed_private_key
                    app_state.ecdh_private_key = register_data.ecdh_private_key
                    return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg


class ContainKeysInteractor:
    async def __call__(self, container: AsyncContainer) -> tuple[bool, str]:
        try:
            async with container() as request_container:
                key_storage = await request_container.get(EncryptedKeyStorage)
                app_state = await request_container.get(AppState)

                ed_private_key = app_state.ed_private_key
                ecdh_private_key = app_state.ecdh_private_key
                username = app_state.username
                password = app_state.password

                if username is None or password is None:
                    return False, "CHECK LOCAL USER OPERATION SKIPPED"

                if not ecdh_private_key or not ed_private_key:
                    return False, "REGISTRATION FAILED - MISSING PRIVATE KEYS"

                if not await key_storage.register_master_key(
                    username=username, password=password
                ):
                    return False, "FAILED TO REGISTER MASTER KEY"

                if not await key_storage.store_ed_private_key(
                    username=username,
                    private_key_pem=ed_private_key,
                    password=password,
                ):
                    return False, "FAILED TO STORE ECDSA PRIVATE KEY"

                if not await key_storage.store_ecdh_private_key(
                    username=username,
                    ecdh_private_key=ecdh_private_key,
                    password=password,
                ):
                    return False, "FAILED TO STORE ECDH PRIVATE KEY"

                master_key = await key_storage.get_master_key(
                    username=username, password=password
                )

                if not master_key:
                    return False, "FAILED TO GET MASTER KEY"

                app_state.master_key = master_key

                return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg


class LoginUserInteractor:
    async def __call__(self, container: AsyncContainer) -> tuple[bool, str]:
        try:
            async with container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)
                app_state = await request_container.get(AppState)

                username = app_state.username
                ed_private_key = app_state.ed_private_key

                if username is None or ed_private_key is None:
                    return False, "CHECK LOCAL USER AND CONTAIN KEYS OPERATIONS SKIPPED"

                login_data = await auth_http_service.login(
                    username=username, ed_private_key=ed_private_key
                )

                if not login_data or not login_data["access_token"]:
                    return False, "LOGIN AFTER REGISTRATION FAILED"
                else:
                    app_state.token = login_data["access_token"]
                    me_data = await auth_http_service.get_current_user_info()
                    keys_data = await auth_http_service.get_public_keys(me_data["id"])

                    if not me_data:
                        return (
                            False,
                            "GET CURRENT USER INFO FAILED - INVALID RESPONSE FROM SERVER",
                        )
                    else:
                        app_state.server_user_id = UUID(str(me_data["id"]))
                        app_state.ed_public_key = keys_data["ed_public_key"]
                        app_state.ecdh_public_key = keys_data["ecdh_public_key"]
                        return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg


class HashingPasswordInteractor:
    async def __call__(self, container: AsyncContainer) -> tuple[bool, str]:
        try:
            async with container() as request_container:
                password_hasher = await request_container.get(AbstractPasswordHasher)
                app_state = await request_container.get(AppState)

                password = app_state.password
                if password is None:
                    return False, "CHECK LOCAL USER OPERATION SKIPPED"

                hashed_password = await password_hasher.hashing(password)

                if not hashed_password:
                    return False, "HASHING PASSWORD FAILED"
                else:
                    app_state.hashed_password = hashed_password
                    return True, "SUCCESS"

        except Exception as e:
            error_msg = f"FAILURE: {(str(e)).upper()}"
            return False, error_msg


class AddUserToDatabaseInteractor:
    async def __call__(self, container: AsyncContainer) -> tuple[bool, str]:
        try:
            async with container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                app_state = await request_container.get(AppState)

                username = app_state.username
                server_user_id = app_state.server_user_id
                ed_public_key = app_state.ed_public_key
                hashed_password = app_state.hashed_password

                if username is None:
                    return False, "CHECK LOCAL USER OPERATION SKIPPED"

                if server_user_id is None or ed_public_key is None:
                    return False, "REGISTER ON SERVER OPERATION SKIPPED"

                if hashed_password is None:
                    return False, "HASHING PASSWORD SKIPPED"

                user = await local_user_service.add_user(
                    AddLocalUserDTO(
                        server_user_id=server_user_id,
                        ed_public_key=ed_public_key,
                        username=username,
                        hashed_password=hashed_password,
                        timezone=None,
                    )
                )

                if not user:
                    return False, "ADD USER TO LOCAL DATABASE FAILED"
                else:
                    app_state.local_user_id = UUID(str(user.id))
                    return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg


class CheckLocalUserLoginInteractor:
    async def __call__(
        self, container: AsyncContainer, username: str, password: str
    ) -> tuple[bool, str]:
        try:
            async with container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                app_state = await request_container.get(AppState)
                app_state.contacts_cache = []
                app_state.chats_cache = []

                if not username or not password:
                    return False, "USERNAME AND PASSWORD ARE REQUIRED"

                local_user = await local_user_service.get_user_by_username(username)

                if not local_user:
                    return False, "USER WITH THIS NAME NOT EXISTS"
                else:
                    hashed_password = local_user.hashed_password
                    if hashed_password is None:
                        return False, "LOCAL USER PASSWORD HASH MISSING"

                    app_state.local_user_id = UUID(str(local_user.id))
                    app_state.username = username
                    app_state.password = password
                    app_state.hashed_password = hashed_password
                    return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg


class ComparePasswordInteractor:
    async def __call__(self, container: AsyncContainer) -> tuple[bool, str]:
        try:
            async with container() as request_container:
                password_hasher = await request_container.get(AbstractPasswordHasher)
                app_state = await request_container.get(AppState)

                username = app_state.username
                password = app_state.password
                hashed_password = app_state.hashed_password

                if username is None or password is None or hashed_password is None:
                    return False, "CHECK LOCAL USER OPERATION SKIPPED"

                password_valid = await password_hasher.compare(
                    password, hashed_password
                )

                if not password_valid:
                    return False, "INVALID PASSWORD"
                else:
                    return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg


class GetPrivateKeysInteractor:
    async def __call__(self, container: AsyncContainer) -> tuple[bool, str]:
        try:
            async with container() as request_container:
                key_storage = await request_container.get(EncryptedKeyStorage)
                app_state = await request_container.get(AppState)

                username = app_state.username
                password = app_state.password

                if username is None or password is None:
                    return False, "CHECK LOCAL USER OPERATION SKIPPED"

                ed_private_key = await key_storage.get_ed_private_key(
                    username, password
                )
                if not ed_private_key:
                    return (
                        False,
                        "FAILED TO RETRIEVE PRIVATE KEYS - INVALID PASSWORD OR CORRUPTED DATA",
                    )

                ecdh_private_key = await key_storage.get_ecdh_private_key(
                    username, password
                )
                if not ecdh_private_key:
                    return (
                        False,
                        "FAILED TO RETRIEVE PRIVATE KEYS - INVALID PASSWORD OR CORRUPTED DATA",
                    )

                master_key = await key_storage.get_master_key(
                    username=username, password=password
                )
                if not master_key:
                    return (
                        False,
                        "FAILED TO RETRIEVE PRIVATE KEYS - INVALID PASSWORD OR CORRUPTED DATA",
                    )

                app_state.ed_private_key = ed_private_key
                app_state.ecdh_private_key = ecdh_private_key
                app_state.master_key = master_key

                return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg


class SynchronizeContactsInteractor:
    async def __call__(
        self, container: AsyncContainer
    ) -> tuple[bool, str, dict[str, int]]:
        add_contact_counts = 0
        edited_contact_counts = 0

        try:
            async with container() as request_container:
                contact_http_service = await request_container.get(ContactHTTPService)
                contact_service = await request_container.get(ContactService)
                app_state = await request_container.get(AppState)

                token = app_state.token
                local_user_id = app_state.local_user_id
                server_user_id = app_state.server_user_id
                if token is None or local_user_id is None or server_user_id is None:
                    return False, "CONTACT SYNCHRONIZATION PREREQUISITES MISSING", {}

                contact_http_service.token = token

                ed_dict = {}

                local_contacts = await contact_service.get_contacts(
                    local_user_id=local_user_id
                )

                for contact in local_contacts:
                    if contact.ed_public_key:
                        ed_dict[contact.server_user_id] = contact.ed_public_key

                server_contacts = await contact_http_service.get_contacts(
                    local_user_id=local_user_id,
                    server_user_id=server_user_id,
                    ed_dict=ed_dict,
                )

                local_contact_map = {
                    contact.server_user_id: contact for contact in local_contacts
                }

                for server_contact in server_contacts:
                    contact_server_user_id = server_contact.server_user_id
                    if contact_server_user_id is None:
                        raise ValueError("Server contact ID is missing")

                    local_contact = local_contact_map.get(contact_server_user_id)
                    if local_contact:
                        await contact_service.update_contact(
                            RequestContactDTO(
                                local_user_id=local_user_id,
                                server_user_id=contact_server_user_id,
                                username=server_contact.username,
                                ecdh_public_key=server_contact.ecdh_public_key,
                                status=server_contact.status,
                                last_seen=server_contact.last_seen,
                                online=server_contact.online,
                            )
                        )
                        edited_contact_counts += 1
                    else:
                        username = server_contact.username
                        ed_public_key = server_contact.ed_public_key
                        ecdh_public_key = server_contact.ecdh_public_key
                        if (
                            username is None
                            or ed_public_key is None
                            or ecdh_public_key is None
                        ):
                            raise ValueError(
                                f"Server contact {contact_server_user_id} is incomplete"
                            )

                        await contact_service.add_contact(
                            AddContactDTO(
                                local_user_id=local_user_id,
                                server_user_id=contact_server_user_id,
                                username=username,
                                ed_public_key=ed_public_key,
                                ecdh_public_key=ecdh_public_key,
                                status=server_contact.status,
                                last_seen=server_contact.last_seen,
                                online=server_contact.online,
                            )
                        )
                        add_contact_counts += 1

                server_contact_ids = {
                    contact.server_user_id for contact in server_contacts
                }
                for local_contact in local_contacts:
                    if (
                        local_contact.server_user_id not in server_contact_ids
                        and local_contact.status != ContactStatusEnum.BLANK
                    ):
                        await contact_service.update_contact(
                            RequestContactDTO(
                                local_user_id=local_user_id,
                                server_user_id=local_contact.server_user_id,
                                status=ContactStatusEnum.BLANK,
                                online=False,
                                last_seen=local_contact.last_seen,
                            )
                        )
                        edited_contact_counts += 1

                return (
                    True,
                    "SUCCESS",
                    {"edited": edited_contact_counts, "added": add_contact_counts},
                )

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg, {}


class SynchronizeChatsInteractor:
    async def __call__(
        self,
        container: AsyncContainer,
    ) -> tuple[bool, str, dict[str, int]]:
        counts = {
            "added": 0,
            "updated": 0,
            "participants_added": 0,
            "participants_left": 0,
            "events_added": 0,
            "unmapped_participants": 0,
        }

        try:
            async with container() as request_container:
                chat_http_service = await request_container.get(ChatHTTPService)
                chat_service = await request_container.get(ChatService)
                contact_service = await request_container.get(ContactService)
                app_state = await request_container.get(AppState)

                if (
                    app_state.token is None
                    or app_state.local_user_id is None
                    or app_state.server_user_id is None
                ):
                    return False, "CHAT SYNCHRONIZATION PREREQUISITES MISSING", {}

                chat_http_service.token = app_state.token
                local_chats = await chat_service.get_chats(app_state.local_user_id)
                local_chats_by_server_id = {
                    chat.server_chat_id: chat for chat in local_chats
                }
                contacts = await contact_service.get_contacts(app_state.local_user_id)
                contacts_by_server_id = {
                    contact.server_user_id: contact for contact in contacts
                }

                server_chats = await chat_http_service.get_chats()
                active_server_chat_ids = {chat.id for chat in server_chats}
                app_state.active_server_chat_ids = active_server_chat_ids
                for server_chat in server_chats:
                    local_chat = local_chats_by_server_id.get(server_chat.id)
                    if local_chat is None:
                        local_chat = await chat_service.add_chat(
                            AddChatDTO(
                                local_user_id=app_state.local_user_id,
                                server_chat_id=server_chat.id,
                                server_owner_id=server_chat.owner_id,
                                name=server_chat.name,
                                created_at=server_chat.created_at,
                            )
                        )
                        local_chats_by_server_id[server_chat.id] = local_chat
                        counts["added"] += 1
                    elif (
                        local_chat.server_owner_id != server_chat.owner_id
                        or local_chat.name != server_chat.name
                        or local_chat.created_at != server_chat.created_at
                    ):
                        updated_chat = await chat_service.update_chat(
                            RequestChatDTO(
                                id=local_chat.id,
                                server_owner_id=server_chat.owner_id,
                                name=server_chat.name,
                                created_at=server_chat.created_at,
                            )
                        )
                        if updated_chat is not None:
                            local_chat = updated_chat
                            counts["updated"] += 1

                    participants = await chat_http_service.get_participants(
                        server_chat.id
                    )
                    for participant in participants:
                        if participant.user_id == app_state.server_user_id:
                            continue

                        contact = contacts_by_server_id.get(participant.user_id)
                        if contact is None:
                            counts["unmapped_participants"] += 1
                            continue

                        existing = await chat_service.get_participant(
                            local_chat.id,
                            contact.id,
                        )
                        if participant.left_at is None:
                            if existing is None or existing.left_at is not None:
                                await chat_service.add_participant(
                                    AddChatParticipantDTO(
                                        chat_id=local_chat.id,
                                        contact_id=contact.id,
                                        joined_at=participant.joined_at,
                                    ),
                                    create_join_event=False,
                                )
                                counts["participants_added"] += 1
                        elif existing is None:
                            await chat_service.add_participant(
                                AddChatParticipantDTO(
                                    chat_id=local_chat.id,
                                    contact_id=contact.id,
                                    joined_at=participant.joined_at,
                                    left_at=participant.left_at,
                                ),
                                create_join_event=False,
                            )
                        elif existing.left_at != participant.left_at:
                            if existing.left_at is None:
                                await chat_service.delete_participant(
                                    local_chat.id,
                                    contact.id,
                                    create_left_event=False,
                                    left_at=participant.left_at,
                                )
                                counts["participants_left"] += 1
                            else:
                                await chat_service.update_participant(
                                    RequestChatParticipantDTO(
                                        chat_id=local_chat.id,
                                        contact_id=contact.id,
                                        left_at=participant.left_at,
                                    )
                                )

                    after = await chat_service.get_latest_server_event_timestamp(
                        local_chat.id
                    )
                    events = await chat_http_service.get_events(
                        server_chat.id,
                        after=after,
                    )
                    for event in sorted(
                        events, key=lambda item: (item.timestamp, item.id)
                    ):
                        if await chat_service.get_chat_event_by_server_event_id(
                            event.id
                        ):
                            continue

                        event_type = ChatEventTypeEnum(event.event_type)
                        actor_contact = contacts_by_server_id.get(event.user_id)
                        await chat_service.add_chat_event(
                            AddChatEventDTO(
                                chat_id=local_chat.id,
                                contact_id=(
                                    actor_contact.id if actor_contact else None
                                ),
                                server_event_id=event.id,
                                actor_server_user_id=event.user_id,
                                target_server_user_id=event.target_user_id,
                                event_type=event_type,
                                timestamp=event.timestamp,
                            )
                        )
                        counts["events_added"] += 1

                        target_user_id = event.target_user_id
                        if event_type == ChatEventTypeEnum.MEMBER_LEFT:
                            target_user_id = event.user_id
                        if (
                            event_type
                            in {
                                ChatEventTypeEnum.MEMBER_LEFT,
                                ChatEventTypeEnum.MEMBER_REMOVED,
                            }
                            and target_user_id is not None
                        ):
                            target_contact = contacts_by_server_id.get(target_user_id)
                            if target_contact is not None:
                                existing = await chat_service.get_participant(
                                    local_chat.id,
                                    target_contact.id,
                                )
                                if existing is not None and existing.left_at is None:
                                    await chat_service.delete_participant(
                                        local_chat.id,
                                        target_contact.id,
                                        create_left_event=False,
                                        left_at=event.timestamp,
                                    )
                                    counts["participants_left"] += 1

                for server_chat_id, local_chat in local_chats_by_server_id.items():
                    if server_chat_id in active_server_chat_ids:
                        continue
                    after = await chat_service.get_latest_server_event_timestamp(
                        local_chat.id
                    )
                    try:
                        events = await chat_http_service.get_events(
                            server_chat_id,
                            after=after,
                        )
                    except APIError as error:
                        if error.status_code == 404:
                            continue
                        raise

                    for event in sorted(
                        events,
                        key=lambda item: (item.timestamp, item.id),
                    ):
                        if await chat_service.get_chat_event_by_server_event_id(
                            event.id
                        ):
                            continue
                        event_type = ChatEventTypeEnum(event.event_type)
                        actor_contact = contacts_by_server_id.get(event.user_id)
                        await chat_service.add_chat_event(
                            AddChatEventDTO(
                                chat_id=local_chat.id,
                                contact_id=(
                                    actor_contact.id if actor_contact else None
                                ),
                                server_event_id=event.id,
                                actor_server_user_id=event.user_id,
                                target_server_user_id=event.target_user_id,
                                event_type=event_type,
                                timestamp=event.timestamp,
                            )
                        )
                        counts["events_added"] += 1

                return True, "SUCCESS", counts

        except Exception as error:
            return False, str(error).upper(), {}


class SyncMessageHistoryInteractor:
    async def __call__(
        self, container: AsyncContainer
    ) -> tuple[bool, str, dict[str, int]]:
        text_count = 0
        file_count = 0

        async with container() as request_container:
            message_http_service = await request_container.get(MessageHTTPService)
            file_http_service = await request_container.get(FileHTTPService)

            contact_service = await request_container.get(ContactService)
            chat_service = await request_container.get(ChatService)
            message_service = await request_container.get(MessageService)

            app_state = await request_container.get(AppState)

            token = app_state.token
            local_user_id = app_state.local_user_id
            master_key = app_state.master_key
            ecdh_private_key = app_state.ecdh_private_key
            if (
                token is None
                or local_user_id is None
                or master_key is None
                or ecdh_private_key is None
            ):
                return False, "MESSAGE SYNCHRONIZATION PREREQUISITES MISSING", {}

            message_http_service.token = token
            file_http_service.token = token
            message_service.master_key = master_key

            contacts = await contact_service.get_contacts(local_user_id)
            chats = await chat_service.get_chats(local_user_id)
            contacts_by_server_id = {
                contact.server_user_id: contact
                for contact in contacts
                if contact.server_user_id is not None
            }
            chats_by_server_id = {
                chat.server_chat_id: chat
                for chat in chats
                if chat.server_chat_id is not None
            }
            ed_dict = {}

            for contact in contacts:
                if contact.ed_public_key:
                    ed_dict[contact.server_user_id] = contact.ed_public_key

            new_messages_text = await message_http_service.get_undelivered_messages(
                ed_dict=ed_dict,
                recipient_ecdh_private_key=ecdh_private_key,
            )

            for new_message_text in new_messages_text:
                sender_server_id = UUID(str(new_message_text["sender_id"]))
                chat_server_id = new_message_text.get("chat_id")
                local_contact = contacts_by_server_id.get(sender_server_id)
                local_chat = (
                    chats_by_server_id.get(UUID(str(chat_server_id)))
                    if chat_server_id is not None
                    else None
                )
                await message_service.add_message_text(
                    AddMessageTextDTO(
                        local_user_id=local_user_id,
                        server_message_id=UUID(str(new_message_text["id"])),
                        logical_message_id=UUID(
                            str(
                                new_message_text.get("logical_message_id")
                                or new_message_text["id"]
                            )
                        ),
                        contact_id=(local_contact.id if local_contact else None),
                        chat_id=(local_chat.id if local_chat else None),
                        content=new_message_text["decrypted_content"],
                        content_type=MessageContentTypeEnum(
                            new_message_text.get("content_type")
                            or MessageContentTypeEnum.TEXT
                        ),
                        timestamp=new_message_text.get(
                            "timestamp",
                            datetime.now(timezone.utc),
                        ),
                        is_outgoing=False,
                        is_delivered=True,
                    )
                )
                text_count += 1

            new_message_files = await file_http_service.get_undelivered_message_files(
                ed_dict=ed_dict,
                recipient_ecdh_private_key=ecdh_private_key,
            )

            for new_message_file in new_message_files:
                local_contact = contacts_by_server_id.get(new_message_file.sender_id)
                local_chat = (
                    chats_by_server_id.get(new_message_file.chat_id)
                    if new_message_file.chat_id is not None
                    else None
                )
                await message_service.add_message_file(
                    AddMessageFileDTO(
                        local_user_id=local_user_id,
                        server_message_id=new_message_file.message_id,
                        contact_id=(local_contact.id if local_contact else None),
                        chat_id=(local_chat.id if local_chat else None),
                        file_name=new_message_file.file_name,
                        file_content=new_message_file.file_content,
                        file_size=new_message_file.file_size,
                        file_mime_type=MessageContentMimeTypeEnum(
                            new_message_file.file_mime_type
                        ),
                        content_type=MessageContentTypeEnum(
                            new_message_file.content_type
                        ),
                        timestamp=new_message_file.timestamp,
                        is_outgoing=False,
                        is_delivered=True,
                    )
                )
                file_count += 1

            failed_messages = await message_http_service.get_failed_messages()
            failed_message_ids = [message.id for message in failed_messages]
            failed_count = await message_service.mark_messages_failed(
                local_user_id,
                failed_message_ids,
            )

            return (
                True,
                "SUCCESS",
                {
                    "text_count": text_count,
                    "file_count": file_count,
                    "failed_count": failed_count,
                },
            )


class RotateKeysInteractor:
    async def __call__(self, container: AsyncContainer) -> tuple[bool, str]:
        try:
            async with container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)
                key_storage = await request_container.get(EncryptedKeyStorage)

                app_state = await request_container.get(AppState)

                token = app_state.token
                ed_private_key = app_state.ed_private_key
                username = app_state.username
                password = app_state.password

                if (
                    token is None
                    or ed_private_key is None
                    or username is None
                    or password is None
                ):
                    return False, "OBTAINING CRYPTOGRAPHIC KEYS OPERATIONS SKIPPED"

                auth_http_service.token = token

                (
                    ecdh_private_key,
                    ecdh_public_key,
                ) = await auth_http_service.update_ecdh_key(ed_private_key)

                if not ecdh_private_key:
                    return False, "FAILED TO ROTATE KEYS"

                key_storage.clear_ecdh_private_key(username)

                success = await key_storage.store_ecdh_private_key(
                    username=username,
                    ecdh_private_key=ecdh_private_key,
                    password=password,
                )

                if not success:
                    return False, "FAILED TO STORE ECDH PRIVATE KEY"

                app_state.ecdh_public_key = ecdh_public_key
                app_state.ecdh_private_key = ecdh_private_key

                return True, "SUCCESS"
        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg


class CacheConversationsInteractor:
    """Build contact and chat previews from the local database."""

    async def __call__(
        self,
        container: AsyncContainer,
    ) -> tuple[bool, str, dict[str, int]]:
        try:
            async with container() as request_container:
                app_state = await request_container.get(AppState)
                local_user_id = app_state.local_user_id
                master_key = app_state.master_key
                app_state.contacts_cache = []
                app_state.chats_cache = []
                if local_user_id is None or master_key is None:
                    return False, "CONVERSATION CACHE PREREQUISITES MISSING", {}

                contact_service = await request_container.get(ContactService)
                chat_service = await request_container.get(ChatService)
                message_service = await request_container.get(MessageService)
                message_service.master_key = master_key

                contacts = await contact_service.get_contacts(local_user_id)
                chats = await chat_service.get_chats(local_user_id)
                if app_state.active_server_chat_ids is not None:
                    chats = [
                        chat
                        for chat in chats
                        if chat.server_chat_id in app_state.active_server_chat_ids
                    ]
                contact_cache: list[ContactCache] = []
                chat_cache: list[ChatCache] = []

                for contact in contacts:
                    messages = await message_service.get_recent_messages(
                        local_user_id,
                        contact_id=contact.id,
                        limit=10,
                    )
                    contact_cache.append(
                        ContactCache(
                            id=contact.id,
                            server_user_id=contact.server_user_id,
                            username=contact.username,
                            status=contact.status,
                            last_seen=contact.last_seen,
                            online=contact.online,
                            ed_public_key=contact.ed_public_key,
                            ecdh_public_key=contact.ecdh_public_key,
                            messages=[
                                self._cache_message(message) for message in messages
                            ],
                        )
                    )

                for chat in chats:
                    messages = await message_service.get_recent_messages(
                        local_user_id,
                        chat_id=chat.id,
                        limit=10,
                    )
                    chat_cache.append(
                        ChatCache(
                            id=chat.id,
                            server_chat_id=chat.server_chat_id,
                            server_owner_id=chat.server_owner_id,
                            name=chat.name,
                            created_at=chat.created_at,
                            messages=[
                                self._cache_message(message) for message in messages
                            ],
                        )
                    )

                app_state.contacts_cache = contact_cache
                app_state.chats_cache = chat_cache
                return (
                    True,
                    "SUCCESS",
                    {
                        "contacts": len(contact_cache),
                        "chats": len(chat_cache),
                        "messages": sum(len(item.messages) for item in contact_cache)
                        + sum(len(item.messages) for item in chat_cache),
                    },
                )
        except Exception as error:
            return False, str(error).upper(), {}

    @staticmethod
    def _cache_message(message: MessageDTO) -> MessageCache:
        return MessageCache(
            id=message.id,
            server_message_id=message.server_message_id,
            logical_message_id=message.logical_message_id,
            contact_id=message.contact_id,
            chat_id=message.chat_id,
            content_type=message.content_type,
            content=message.content,
            file_name=message.file_name,
            file_size=message.file_size,
            file_mime_type=message.file_mime_type,
            timestamp=message.timestamp,
            is_outgoing=message.is_outgoing,
            is_delivered=message.is_delivered,
            failed=message.failed,
        )


RealtimeListener = Callable[[], Awaitable[None] | None]


class RealtimeInteractor:
    _CONTACTS = 1
    _CHATS = 2
    _MESSAGES = 3

    def __init__(
        self,
        container: AsyncContainer,
        logger: logging.Logger | None = None,
    ) -> None:
        self._container = container
        self._logger = logger or logging.getLogger(__name__)
        self._listeners: list[RealtimeListener] = []
        self._websocket_service: WebSocketService | None = None
        self._sync_task: asyncio.Task[None] | None = None
        self._pending_sync_level = 0
        self._apply_presence = ApplyPresenceChangedInteractor()
        self._synchronize = SynchronizeRealtimeInteractor(
            synchronize_contacts=SynchronizeContactsInteractor(),
            synchronize_chats=SynchronizeChatsInteractor(),
            synchronize_messages=SyncMessageHistoryInteractor(),
            cache_conversations=CacheConversationsInteractor(),
        )

    def add_listener(self, listener: RealtimeListener) -> None:
        if listener not in self._listeners:
            self._listeners.append(listener)

    async def __call__(self) -> bool:
        return await self.start()

    async def start(self) -> bool:
        async with self._container() as request_container:
            app_state = await request_container.get(AppState)
            websocket_service = await request_container.get(WebSocketService)
            token = app_state.token

        if token is None:
            return False

        self._websocket_service = websocket_service
        return await websocket_service.start_websocket_listener(
            token=token,
            event_callback=self._handle_event,
            connection_callback=self._handle_connection_state,
        )

    async def stop(self) -> None:
        sync_task = self._sync_task
        self._sync_task = None
        self._pending_sync_level = 0
        if sync_task is not None and not sync_task.done():
            sync_task.cancel()
            try:
                await sync_task
            except asyncio.CancelledError:
                pass

        websocket_service = self._websocket_service
        self._websocket_service = None
        if websocket_service is not None:
            await websocket_service.stop_websocket_listener()

    async def _handle_connection_state(self, connected: bool) -> None:
        async with self._container() as request_container:
            app_state = await request_container.get(AppState)
            app_state.websocket_connected = connected
        if connected:
            self._schedule_sync(self._MESSAGES)

    async def _handle_event(self, event: dict[str, Any]) -> bool:
        event_type = event.get("type")
        payload = event.get("payload")
        if not isinstance(payload, dict):
            return False

        if event_type == "presence_changed":
            success, message = await self._apply_presence(
                self._container,
                payload,
            )
            if not success:
                self._logger.warning("Presence update failed: %s", message)
                return False
            await self._notify_listeners()
            return True
        if event_type == "message_available":
            self._schedule_sync(self._MESSAGES)
        elif event_type == "chat_changed":
            self._schedule_sync(self._CHATS)
        elif event_type == "contact_changed":
            self._schedule_sync(self._CONTACTS)
        return True

    def _schedule_sync(self, level: int) -> None:
        self._pending_sync_level = max(self._pending_sync_level, level)
        if self._sync_task is None or self._sync_task.done():
            self._sync_task = asyncio.create_task(self._run_pending_sync())

    async def _run_pending_sync(self) -> None:
        while self._pending_sync_level:
            level = self._pending_sync_level
            self._pending_sync_level = 0
            try:
                success, message = await self._synchronize(
                    self._container,
                    contacts=True,
                    chats=level >= self._CHATS,
                    messages=level >= self._MESSAGES,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                self._logger.exception("Realtime synchronization crashed")
                continue
            if not success:
                self._logger.warning("Realtime synchronization failed: %s", message)
                continue
            await self._notify_listeners()

    async def _notify_listeners(self) -> None:
        for listener in tuple(self._listeners):
            try:
                result = listener()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                self._logger.exception("Realtime UI listener failed")
