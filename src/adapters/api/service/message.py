import asyncio
import logging
from typing import Any
from uuid import UUID

from src.adapters.encryption.service import EncryptionService
from src.exceptions import (
    APIError,
    AuthenticationError,
    DecryptionError,
    InfrastructureError,
)

from ..dao.auth import AuthHTTPDAO
from ..dao.message import MessageHTTPDAO


class MessageHTTPService:
    _MAX_CONCURRENT_DECRYPTIONS = 8

    def __init__(
        self,
        message_dao: MessageHTTPDAO,
        auth_dao: AuthHTTPDAO,
        encryption_service: EncryptionService,
        logger: logging.Logger | None = None,
    ):
        self._message_dao = message_dao
        self._auth_dao = auth_dao
        self._encryption_service = encryption_service
        self._logger = logger or logging.getLogger(__name__)

        self._current_token: str | None = None

    @property
    def token(self) -> str | None:
        return self._current_token

    @token.setter
    def token(self, value: str) -> None:
        if not value:
            raise ValueError("Token cannot be empty")
        self._current_token = value

    @token.deleter
    def token(self):
        self._current_token = None

    async def send_encrypted_message_text(
        self,
        recipient_id: UUID,
        chat_id: UUID | None,
        message: str,
        recipient_ed_public_key: str,
        sender_ed_private_key: str,
        sender_ecdh_private_key: str,
        ephemeral_ecdh_public_key: str,
    ) -> UUID | None:
        if self._current_token is None:
            self._logger.warning("Cannot send message without an active session")
            return None

        token = self._current_token

        try:
            keys = await self._auth_dao.get_public_keys(recipient_id, token)
            recipient_ecdh_public_key = keys.get("ecdh_public_key")
            recipient_ecdh_signature = keys.get("ecdh_signature")
            if not isinstance(recipient_ecdh_public_key, str) or not isinstance(
                recipient_ecdh_signature, str
            ):
                raise APIError("Recipient public keys response is incomplete")

            message_dto = await self._encryption_service.encrypt_message(
                message=message,
                sender_ed_private_key=sender_ed_private_key,
                recipient_ed_public_key=recipient_ed_public_key,
                ephemeral_ecdh_private_key=sender_ecdh_private_key,
                ephemeral_ecdh_public_key=ephemeral_ecdh_public_key,
                recipient_ecdh_public_key=recipient_ecdh_public_key,
                recipient_ecdh_signature=recipient_ecdh_signature,
            )

            await self._message_dao.send_message_text(
                recipient_id=recipient_id,
                chat_id=chat_id,
                message_id=message_dto.message_uuid,
                message=message_dto.encrypted_message,
                content_type="text",
                ephemeral_public_key=ephemeral_ecdh_public_key,
                ephemeral_signature=message_dto.ephemeral_signature,
                token=token,
            )
            return message_dto.message_uuid

        except AuthenticationError:
            del self.token
            self._logger.warning("Authentication failed while sending message")
            return None

        except (APIError, InfrastructureError) as error:
            self._logger.error(
                f"Failed to send encrypted message: {error}", exc_info=True
            )
            return None

    async def get_undelivered_messages(
        self,
        ed_dict: dict[UUID, str],
        recipient_ecdh_private_key: str,
    ) -> list[dict[str, Any]]:

        if self._current_token is None:
            self._logger.warning(
                "Cannot retrieve undelivered messages without an active session",
            )
            return []

        token = self._current_token

        try:
            response = await self._message_dao.get_undelivered_messages(
                token=token
            )

            if not response.get("has_messages") or not response.get("messages"):
                return []

            encrypted_messages = response["messages"]

            semaphore = asyncio.Semaphore(self._MAX_CONCURRENT_DECRYPTIONS)

            processed_results = await asyncio.gather(
                *(
                    self._process_undelivered_message(
                        message=message,
                        ed_dict=ed_dict,
                        recipient_ecdh_private_key=recipient_ecdh_private_key,
                        semaphore=semaphore,
                    )
                    for message in encrypted_messages
                )
            )
            decrypted_messages = [
                message for message in processed_results if message is not None
            ]
            if decrypted_messages:
                await self._message_dao.ack_messages(
                    message_ids=[message["id"] for message in decrypted_messages],
                    token=token,
                )
            return decrypted_messages

        except AuthenticationError as e:
            self._logger.warning(
                f"Authentication failed while retrieving messages: {str(e)}",
            )
            del self.token
            return []

        except Exception as e:
            self._logger.error(
                f"Error getting undelivered messages: {str(e)}",
                exc_info=True,
            )
            return []

    async def _process_undelivered_message(
        self,
        message: dict[str, Any],
        ed_dict: dict[UUID, str],
        recipient_ecdh_private_key: str,
        semaphore: asyncio.Semaphore,
    ) -> dict[str, Any] | None:
        async with semaphore:
            try:
                sender_id = UUID(str(message["sender_id"]))
                sender_ed_public_key = ed_dict.get(sender_id)
                if not sender_ed_public_key:
                    raise DecryptionError(
                        f"Missing ED public key for sender {sender_id}"
                    )

                decrypted_content = await self._encryption_service.decrypt_message(
                    message_uuid=UUID(str(message["id"])),
                    encrypted_message=message["message"],
                    sender_ed_public_key=sender_ed_public_key,
                    recipient_ecdh_private_key=recipient_ecdh_private_key,
                    ephemeral_ecdh_public_key=message["ephemeral_public_key"],
                    ephemeral_signature=message["ephemeral_signature"],
                )

                return {
                    **message,
                    "decrypted_content": decrypted_content,
                    "decryption_status": "success",
                }

            except DecryptionError as error:
                self._logger.error(
                    f"Decryption failed for message {message.get('id')}, {error}",
                    exc_info=True,
                )
                return None

            except Exception:
                self._logger.error(
                    f"Unexpected error processing message {message.get('id')}",
                    exc_info=True,
                )
                return None

    async def health_check(self) -> bool:
        try:
            return await self._message_dao.health_check()
        except Exception as e:
            self._logger.error(
                f"Message service health check failed: {str(e)}",
                exc_info=True,
            )
            return False
