import logging
import asyncio
import base64
from typing import Tuple, Optional, List, Set
from datetime import datetime

from pyexpat.errors import messages
from src.exceptions import *
from dishka import AsyncContainer

from src.providers import AppProvider
from src.presentation.pages import AppState, Contact, Message

from src.adapters.api.service import (
    AuthHTTPService,
    ContactHTTPService,
    MessageHTTPService
)

from src.adapters.database.service import (
    LocalUserService,
    ContactService,
    MessageService
)

from src.adapters.database.dto import (
    LocalUserRequestDTO, LocalUserDTO,
    ContactRequestDTO, ContactDTO,
    MessageRequestDTO, MessageDTO
)

from src.adapters.encryption.dao import (
    Abstract256Cipher,
    AbstractPasswordHasher,
    AbstractECDHCipher
)

from src.adapters.encryption.storage import EncryptedKeyStorage


class MessengerManager:
    def __init__(self, app_state: AppState, container: AsyncContainer):
        self._state = app_state
        self._container = container
        self._logger = logging.getLogger(__name__)

        self._message_callback = None
        self._ws_started = False

    def set_message_callback(self, callback):
        self._message_callback = callback

    async def get_timezone(self) -> int:
        try:
            async with self._container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                local_user = await local_user_service.get_user_data(LocalUserRequestDTO(username=self._state.username))
                return local_user.timezone
        except Exception as e:
            self._logger.error(f"Error getting timezone: {e}")
            return 0

    async def get_contacts(self) -> list[Contact]:
        try:
            async with self._container() as request_container:
                contact_service = await request_container.get(ContactService)
                db_contacts = await contact_service.get_contacts(self._state.local_user_id)
                return [
                    Contact(
                        server_user_id=contact.server_user_id,
                        username=contact.username,
                        ecdsa_public_key=contact.ecdsa_public_key,
                        ecdh_public_key=contact.ecdh_public_key,
                        last_seen=contact.last_seen,
                        online=contact.online,
                        status=contact.status
                    ) for contact in db_contacts
                ]
        except Exception as e:
            self._logger.error(f"Error fetching contacts: {e}", exc_info=True)
            return []

    async def get_messages(self, contact_id: int) -> list[dict]:
        try:
            async with self._container() as request_container:
                message_service = await request_container.get(MessageService)
                aes_cipher = await request_container.get(AbstractAES256Cipher)
                # Get messages from the database
                self._logger.info(f"Getting messages for contact {contact_id}")
                db_messages = await message_service.get_messages(
                    local_user_id=self._state.local_user_id,
                    contact_id=contact_id,
                    limit=50
                )

                if not db_messages:
                    self._logger.info("No messages found for contact")
                    return [{
                        "id": 0,
                        "content": "Напишите свое первое сообщение!",
                        "content_type": "text",
                        "is_outgoing": False,
                        "timestamp": ""
                    }]

                # Decrypt and convert to the required format
                messages = []
                self._logger.info(f"Start decrypting {len(db_messages)} messages content")
                for message in db_messages:
                    try:
                        decrypted_content = await aes_cipher.decrypt(
                            b64_ciphertext=message.content,
                            key=self._state.master_key
                        )

                        messages.append({
                            "id": message.server_message_id,
                            "content": decrypted_content,
                            "content_type": message.content_type,
                            "is_outgoing": message.is_outgoing,
                            "timestamp": self._format_timestamp(message.timestamp)
                        })

                    except Exception as e:
                        self._logger.error(f"Error decrypting message: {e}", exc_info=True,)
                        continue

                return messages
        except Exception as e:
            self._logger.error(f"Error fetching messages: {e}", exc_info=True)
            return []

    @staticmethod
    def _format_timestamp(timestamp):
        if not timestamp:
            return ""

        if isinstance(timestamp, str):
            return timestamp

        # Format datetime in a readable format
        now = datetime.utcnow()
        if isinstance(timestamp, datetime):
            diff = now - timestamp
            if diff.total_seconds() < 60:
                return "just now"
            elif diff.total_seconds() < 3600:
                minutes = int(diff.total_seconds() / 60)
                return f"{minutes} min ago"
            else:
                return timestamp.strftime("%H:%M")

        return str(timestamp)

    async def _handle_incoming_message(self, message_data: dict):
        try:
            message_type = message_data.get("type")

            context = {
                "message_id": message_data.get("id"),
                "sender_id": message_data.get("sender_id"),
                "decryption_status": message_data.get("decryption_status")
            }

            self._logger.info(f"Processing WebSocket message: {context}")
            self._logger.debug(f"Full message data: {message_data}")

            if message_type == "message":
                await self._handle_websocket_message(message_data)
            elif message_type == "user_status":
                await self._handle_user_status(message_data)
            elif message_type == "error":
                await self._handle_error_message(message_data)
            else:
                self._logger.warning(f"Unknown WebSocket message type: {message_type}")

        except Exception as e:
            self._logger.error(f"Error handling WebSocket message: {e}", exc_info=True)

    async def _handle_websocket_message(self, message_data: dict):
        context = {
            "message_id": message_data.get("id"),
            "sender_id": message_data.get("sender_id"),
            "decryption_status": message_data.get("decryption_status")
        }

        self._logger.info(f"Processing WebSocket message: {context}")

        if message_data.get("decryption_status") != "success":
            self._logger.error(f"Message decryption failed: {message_data.get('decryption_error')}")
            return

        try:
            async with self._container() as request_container:
                contact_service = await request_container.get(ContactService)
                message_service = await request_container.get(MessageService)
                aes_cipher = await request_container.get(AbstractAES256Cipher)

                sender_id = message_data.get("sender_id")
                decrypted_content = message_data["decrypted_content"]

                ciphertext = await aes_cipher.encrypt(
                    plaintext=decrypted_content,
                    key=self._state.master_key
                )

                await message_service.add_message(
                    MessageRequestDTO(
                        local_user_id=self._state.local_user_id,
                        server_message_id=message_data["id"],
                        contact_id=sender_id,
                        content=ciphertext,
                        content_type=message_data.get("content_type", "text"),
                        timestamp=datetime.utcnow(),
                        is_outgoing=False,
                        is_delivered=True
                    )
                )

                ephemeral_public_key = message_data.get("ephemeral_public_key")
                await contact_service.update_contact(
                    contact=ContactRequestDTO(
                        local_user_id=self._state.local_user_id,
                        server_user_id=sender_id,
                        ecdh_public_key=ephemeral_public_key
                    )
                )

                if self._message_callback:
                    await self._message_callback({
                        "type": "new_message",
                        "contact_id": sender_id,
                        "message": decrypted_content,
                        "timestamp": datetime.utcnow().isoformat(),
                        "server_message_id": message_data["id"]
                    })

                self._logger.info(f"Successfully processed incoming message from {sender_id}")

        except Exception as e:
            self._logger.error(f"Error processing WebSocket message: {e}", exc_info=True)

    async def _handle_user_status(self, status_data: dict):
        try:
            user_id = status_data.get("user_id")
            online = status_data.get("online")
            timestamp = status_data.get("timestamp")

            self._logger.info(f"User status update: user_{user_id} -> {'online' if online else 'offline'}")

            async with self._container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)
                auth_http_service.set_token(self._state.token)
                contact_service = await request_container.get(ContactService)

                keys = await auth_http_service.get_public_keys(user_id=user_id)

                await contact_service.update_contact(
                    contact=ContactRequestDTO(
                        local_user_id=self._state.local_user_id,
                        server_user_id=user_id,
                        ecdh_public_key=keys.get("ecdh_public_key"),
                        online=online,
                        last_seen=datetime.utcnow()
                    )
                )

            if self._message_callback:
                await self._message_callback({
                    "type": "user_status",
                    "user_id": user_id,
                    "online": online,
                    "timestamp": timestamp
                })

        except Exception as e:
            self._logger.error(f"Error handling user status: {e}")

    async def _handle_error_message(self, error_data: dict):
        error_type = error_data.get("error_type")
        error_message = error_data.get("message")

        self._logger.error(f"WebSocket error: {error_type} - {error_message}")

        if self._message_callback:
            await self._message_callback({
                "type": "error",
                "error_type": error_type,
                "message": error_message
            })

    async def start_ws(self) -> bool:
        try:
            async with self._container() as request_container:
                message_http_service = await request_container.get(MessageHTTPService)
                message_http_service.set_token(self._state.token)

                await message_http_service.start_websocket_listener(
                    token=self._state.token,
                    user_private_key=self._state.ecdh_private_key,
                    message_callback=self._handle_incoming_message
                )
                self._ws_started = True
                self._state.update_ws_status(True)
                return True

        except Exception as e:
            self.logger.error(f"Failed to start message ws: {e}")
            return False

    async def stop_ws(self):
        self._logger.info("Trying stop WebSocket connection")
        try:
            async with self._container() as request_container:
                message_http_service = await request_container.get(MessageHTTPService)
                message_http_service.set_token(self._state.token)

                await message_http_service.stop_websocket_listener()

                self._ws_started = False
                self._state.update_ws_status(False)

        except Exception as e:
            self._logger.error(f"Failed to stop message ws: {e}")
            raise

    async def send_message(self, contact_id: int, text: str, content_type: str | None = None) -> bool:
        content_type = content_type or "text"
        try:
            async with self._container() as request_container:
                message_http_service = await request_container.get(MessageHTTPService)
                message_http_service.set_token(self._state.token)
                contact_service = await request_container.get(ContactService)
                message_service = await request_container.get(MessageService)
                aes_cipher = await request_container.get(AbstractAES256Cipher)

                self._logger.info(f"Start sending message to {contact_id}: {text}")
                # Find contact data
                contact = await contact_service.get_contact(
                    local_user_id=self._state.local_user_id,
                    contact_id=contact_id
                )
                # Send encrypted message
                message = await message_http_service.send_encrypted_message(
                    recipient_id=contact_id,
                    message=text,
                    content_type=content_type,
                    recipient_ecdsa_public_key=contact.ecdsa_public_key,
                    sender_ecdsa_private_key=self._state.ecdsa_private_key,
                    sender_ecdh_private_key=self._state.ecdh_private_key,
                    ephemeral_ecdh_public_key=self._state.ecdh_public_key,
                )

                if not message:
                    self._logger.error("Failed to send message, no response from server")
                    return False
                # Encrypt the message content with the master key
                ciphertext = await aes_cipher.encrypt(
                    plaintext=text,
                    key=self._state.master_key
                )
                # Save the message to the local database
                await message_service.add_message(
                    MessageRequestDTO(
                        local_user_id=self._state.local_user_id,
                        server_message_id=message.get("id"),
                        contact_id=contact_id,
                        content=ciphertext,
                        content_type=content_type,
                        timestamp=datetime.utcnow(),
                        type=content_type,
                        is_outgoing=True,
                        is_delivered=True
                    )
                )
                # Make sure polling is running
                if not self._ws_started:
                    await self.start_ws()

                return True

        except Exception as e:
            self._logger.error(f"Error sending message: {e}", exc_info=True)
            return False

    def get_connection_status(self) -> dict:
        return {
            "websocket_started": self._ws_started,
            "has_token": self._state.token,
            "is_authenticated": self._state.is_authenticated
        }

    async def logout(self):
        try:
            async with self._container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)
                auth_http_service.set_token(self._state.token)
                await auth_http_service.logout()
                self._state.clear()
                self._logger.info("Successfully logged out")
                return True
        except Exception as e:
            self._logger.error(f"Error logging out: {e}")
            return False