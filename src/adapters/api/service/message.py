from typing import List, Dict, Any, Optional
import base64
import asyncio
from datetime import datetime
import logging

from ..dao.message import MessageHTTPDAO
from ..dao.auth import AuthHTTPDAO
from .encryption import EncryptionService
from src.exceptions import MessageDeliveryError, EncryptionError

class MessageHTTPService:
    def __init__(
            self,
            message_dao: MessageHTTPDAO,
            auth_dao: AuthHTTPDAO,
            encryption_service: EncryptionService,
            logger: logging.Logger = None
    ):
        self._message_dao = message_dao
        self._auth_dao = auth_dao
        self._encryption_service = encryption_service
        self._logger = logger or logging.getLogger(__name__)

        # State for managing long polling
        self._is_polling = False
        self._current_token: str | None = None
        self._polling_task: asyncio.Task | None = None

    async def send_encrypted_message(
            self,
            recipient_id: int,
            message: str,
            sender_private_key: str,
            sender_public_key: str,
            recipient_public_key: str
    ) -> dict[str, Any]:
        """
        Sending an encrypted message
        :param recipient_id: Recipient ID
        :param message: Message text
        :param sender_private_key: Sender's private key
        :param sender_public_key: Sender's public key
        :param recipient_public_key: Recipient's public key
        :return: Sending result
        """
        try:
            # Encrypt the message
            encrypted_message = await self._encryption_service.encrypt_message(
                message=message,
                sender_private_key=sender_private_key,
                recipient_public_key=recipient_public_key
            )

            # Send the encrypted message
            result = await self._message_dao.send_message(
                recipient_id=recipient_id,
                message=encrypted_message,
                ephemeral_public_key=sender_public_key
            )

            self._logger.info(f"Encrypted message sent to {recipient_id}")
            return result

        except Exception as e:
            self._logger.error(f"Failed to send encrypted message: {e}")
            raise MessageDeliveryError(f"Message delivery failed: {e}")

    async def get_undelivered_messages(
            self,
            user_private_key: str,
    ) -> list[dict[str, Any]]:
        """
        Fetch undelivered messages
        :param user_private_key:
        :return:
        """
        # Fetch undelivered messages
        response = await self._message_dao.get_undelivered_messages()

        if response.get("has_messages") and response.get("messages"):
            encrypted_messages = response["messages"]
            message_ids = []

            for message in encrypted_messages:
                try:
                    # Decrypt the message
                    decrypted_content = await self._encryption_service.decrypt_message(
                        encrypted_message=message["message"],
                        recipient_private_key=user_private_key,
                        sender_public_key=message["ephemeral_public_key"]
                    )

                    # Collecting the result
                    decrypted_message = {
                        **message,
                        "decrypted_content": decrypted_content,
                        "decryption_status": "success"
                    }

                    message_ids.append(message["id"])
                    await message_callback(decrypted_message)

                except Exception as e:
                    self._logger.error(f"Failed to process message {message.get('id')}: {e}")
                    # Send an error message to the callback
                    error_message = {
                        **message,
                        "decrypted_content": None,
                        "decryption_status": "failed",
                        "decryption_error": str(e)
                    }
                    message_ids.append(message["id"])
                    await message_callback(error_message)

            # Confirm all processed messages
            if message_ids:
                await self._message_dao.ack_messages(message_ids)


    async def start_message_polling(
            self,
            token: str,
            user_private_key: str,
            message_callback: callable
    ):
        """
        Start message polling
        :param token:
        :param user_private_key:
        :param message_callback:
        :return:
        """
        if self._is_polling:
            self._logger.warning("Polling is already running")
            return

        self._is_polling = True
        self._current_token = token

        self._polling_task = asyncio.create_task(
            self._polling_loop(user_private_key, message_callback)
        )

    async def _polling_loop(self, user_private_key, message_callback):
        """
        Long polling loop
        :param user_private_key:
        :param sender_public_keys:
        :param message_callback:
        :return:
        """
        # TODO: Add a forced update of public ecdh keys, since the response will come from the user with a new session
        while self._is_polling:
            try:
                response = await self._message_dao.poll_messages(timeout=30)

                if response.get("has_messages") and response.get("messages"):
                    encrypted_messages = response["messages"]
                    message_ids = []

                    for message in encrypted_messages:
                        try:
                            # Decrypt the message
                            decrypted_content = await self._encryption_service.decrypt_message(
                                encrypted_message=message["message"],
                                recipient_private_key=user_private_key,
                                sender_public_key=message["ephemeral_public_key"]
                            )

                            # Collecting the result
                            decrypted_message = {
                                **message,
                                "decrypted_content": decrypted_content,
                                "decryption_status": "success"
                            }

                            message_ids.append(message["id"])
                            await message_callback(decrypted_message)

                        except Exception as e:
                            self._logger.error(f"Failed to process message {message.get('id')}: {e}")
                            # Send an error message to the callback
                            error_message = {
                                **message,
                                "decrypted_content": None,
                                "decryption_status": "failed",
                                "decryption_error": str(e)
                            }
                            message_ids.append(message["id"])
                            await message_callback(error_message)

                    # Confirm all processed messages
                    if message_ids:
                        await self._message_dao.ack_messages(message_ids)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self._logger.error(f"Polling error: {e}")
                await asyncio.sleep(1)

    async def stop_message_polling(self):
        """
        Stop message polling
        :return:
        """
        if not self._is_polling:
            return

        self._is_polling = False

        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass

        self._logger.info("Message polling stopped")

    def get_polling_status(self) -> dict[str, Any]:
        """
        Get polling status
        :return: Polling status
        """
        return {
            "is_polling": self._is_polling,
            "task_running": self._polling_task is not None and not self._polling_task.done()
        }