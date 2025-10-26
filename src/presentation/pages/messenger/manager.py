import logging
import asyncio
from typing import Tuple, Optional, List, Set
from datetime import datetime

from pyexpat.errors import messages
from src.exceptions import *
from dishka import AsyncContainer

from src.providers import AppProvider
from src.presentation.pages import AppState, Contact, Message, Container

from src.adapters.api.dao import (
    ContactHTTPDAO,
    MessageHTTPDAO
)

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

from src.adapters.encryption.service import (
    AbstractAES256Cipher,
    AbstractPasswordHasher,
    AbstractECDHCipher
)

from src.adapters.encryption.storage import EncryptedKeyStorage

class MessengerManager(Container):
    def __init__(self, app_state: AppState, container: AsyncContainer):
        super().__init__(app_state, container)
        self._message_callbacks: Set[Callable[[dict], Any]] = set()
        self._polling_started = False
        self._polling_task:asyncio.Task | None = None

    async def get_contacts(self) -> list[Contact]:
        """
        Returns a list of actual contacts from the cache
        :return:
        """
        return self.state.contacts_cache

    async def get_messages(self, contact_id: int) -> list[dict]:
        """
        Get messages for a specific contact from the database (decrypted)
        :param contact_id:
        :return:
        """
        try:
            # Get messages from the database
            self.logger.info(f"Getting messages for contact {contact_id}")
            db_messages = await self.state.message_service.get_messages(
                local_user_id=self.state.local_user_id,
                contact_id=contact_id,
                limit=50
            )

            # If there are no messages, return a welcome message
            if not db_messages:
                self.logger.info("No messages found for contact")
                return [{
                    "id": 0,
                    "text": "Напишите свое первое сообщение!",
                    "is_outgoing": False,
                    "timestamp": ""
                }]

            # Decrypt and convert to the required format
            messages = []
            self.logger.info(f"Start decrypting {len(db_messages)} messages content")
            for message in db_messages:
                try:
                    decrypted_content = await self.state.aes_cipher.decrypt(
                        ciphertext=message.content,
                        key=self.state.master_key
                    )

                    messages.append({
                        "id": message.server_message_id,
                        "text": decrypted_content,
                        "is_outgoing": message.is_outgoing,
                        "timestamp": self._format_timestamp(message.timestamp)
                    })

                except Exception as e:
                    self.logger.error(f"Error decrypting message: {e}", exc_info=True,)
                    continue

            return messages
        except Exception as e:
            self.logger.error(f"Error fetching messages: {e}", exc_info=True)
            return []

    @staticmethod
    def _format_timestamp(timestamp):
        """
        Formats a timestamp for the UI
        :param timestamp:
        :return:
        """
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

    def add_message_callback(self, callback):
        """
        Add a callback function to be called when a new message arrives
        :param callback:
        :return:
        """
        self._message_callbacks.add(callback)
        self.logger.info(f"Added message callback, total: {len(self._message_callbacks)}")

    def remove_message_callback(self, callback):
        """
        Remove a callback function
        :param callback:
        :return:
        """
        self._message_callbacks.discard(callback)

    async def _handle_incoming_message(self, message_data: dict):
        """
        Handle incoming message from polling
        :param message_data:
        :return:
        """
        try:
            self.logger.info(f"Handling incoming message: {message_data}")

            # Save the message to the local database
            if message_data.get("decryption_status") == "success":
                contact_id = message_data.get("sender_id")
                ciphertext = await self.state.aes_cipher.encrypt(
                    plaintext=message_data["decrypted_content"],
                    key=self.state.master_key
                )

                await self.state.message_service.add_message(
                    MessageRequestDTO(
                        local_user_id=self.state.local_user.id,
                        server_message_id=message_data["id"],
                        contact_id=contact_id,
                        content=ciphertext,
                        timestamp=datetime.utcnow(),
                        type="text",
                        is_outgoing=False,
                        is_delivered=True
                    )
                )
                # Forced update of contact data due to a potential new session and a new key on the other side
                response = await self.state.auth_http_service.get_public_keys(contact_id)
                await self.state.contact_service.update_contact(
                    ContactRequestDTO(
                        local_user_id=self.state.local_user.id,
                        server_user_id=contact_id,
                        ecdh_public_key=response["ecdh_public_key"]
                    )
                )

                # Call all registered callbacks
                for callback in self._message_callbacks:
                    try:
                        if asyncio.iscoroutinefunction(callback):
                            await callback(message_data)
                        else:
                            callback(message_data)
                    except Exception as e:
                        self.logger.error(f"Error in message callback: {e}")

        except Exception as e:
            self.logger.error(f"Error handling incoming message: {e}")

    async def start_polling(self):
        """
        Start message polling
        :return:
        """
        if self._polling_started:
            self.logger.warning("Message polling already started")
            return

        try:
            # Create a callback function for MessageHTTPService
            async def polling_callback(message_data):
                await self._handle_incoming_message(message_data)

            # Start polling
            await self.state.message_http_service.start_message_polling(
                token=self.state.token,
                user_private_key=self.state.ecdh_private_key,
                message_callback=polling_callback
            )

            self._polling_started = True

            self.logger.info("Message polling started successfully")

        except Exception as e:
            self._polling_started = False
            self.logger.error(f"Failed to start message polling: {e}")
            raise

    async def stop_polling(self):
        """
        Stop message polling
        :return:
        """
        if not self._polling_started:
            return

        try:
            await self.state.message_http_service.stop_message_polling()
            self._polling_started = False
            self.logger.info("Message polling stopped")
        except Exception as e:
            self.logger.error(f"Error stopping message polling: {e}")

    async def send_message(self, contact_id: int, text: str) -> bool:
        try:
            self.logger.info(f"Start sending message to {contact_id}: {text}")
            # Find contact data
            contact = await self.state.contact_service.get_contact(
                local_user_id=self.state.local_user_id,
                contact_id=contact_id
            )
            # Send encrypted message
            message = await self.state.message_http_service.send_encrypted_message(
                recipient_id=contact_id,
                message=text,
                sender_private_key=self.state.ecdh_private_key,
                sender_public_key=self.state.ecdh_public_key,
                recipient_public_key=contact.ecdh_public_key,
            )

            if not message:
                self.logger.error("Failed to send message, no response from server")
                return False
            # Encrypt the message content with the master key
            ciphertext = await self.state.aes_cipher.encrypt(
                plaintext=text,
                key=self.state.master_key
            )
            # Save the message to the local database
            await self.state.message_service.add_message(
                MessageRequestDTO(
                    local_user_id=self.state.local_user_id,
                    server_message_id=message.get("id"),
                    contact_id=contact_id,
                    content=ciphertext,
                    timestamp=datetime.utcnow(),
                    type="text",
                    is_outgoing=True,
                    is_delivered=True
                )
            )
            # Make sure polling is running
            if not self._polling_started:
                await self.start_polling()

            return True

        except Exception as e:
            self.logger.error(f"Error sending message: {e}", exc_info=True)
            return False

    async def logout(self):
        try:
            self.state.clear()
            self.logger.info("Successfully logged out")
            return True
        except Exception as e:
            self.logger.error(f"Error logging out: {e}")
            return False