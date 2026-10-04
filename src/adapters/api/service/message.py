import asyncio
import logging
import uuid
from typing import Any
from uuid import UUID

from src.adapters.api.dto import (
    ChatMessageBatchDTO,
    ChatMessageDeliveryDTO,
    ECDHPublicKeyDTO,
    FailedMessageDTO,
    MessageProcessingResultDTO,
    SentChatMessageDeliveryDTO,
)
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

    async def send_encrypted_chat_message_text(
        self,
        chat_id: UUID,
        message: str,
        recipient_ed_public_keys: dict[UUID, str],
        sender_ed_private_key: str,
        sender_ecdh_private_key: str,
        sender_ecdh_public_key: str,
    ) -> list[SentChatMessageDeliveryDTO]:
        if self._current_token is None:
            raise AuthenticationError(
                "Cannot send a chat message without an active session"
            )
        if not recipient_ed_public_keys:
            raise ValueError("A chat message requires at least one recipient")

        token = self._current_token
        try:
            raw_keys = await self._auth_dao.get_ecdh_public_keys_batch(
                list(recipient_ed_public_keys),
                token,
            )
            key_items = [ECDHPublicKeyDTO.from_mapping(raw_key) for raw_key in raw_keys]
            key_user_ids = [key.user_id for key in key_items]
            expected_user_ids = set(recipient_ed_public_keys)
            if (
                len(key_user_ids) != len(set(key_user_ids))
                or set(key_user_ids) != expected_user_ids
            ):
                raise APIError("Bulk ECDH key response does not match chat recipients")

            encrypted_deliveries = (
                await self._encryption_service.encrypt_message_to_chat(
                    message=message,
                    sender_ed_private_key=sender_ed_private_key,
                    recipient_ed_public_keys=recipient_ed_public_keys,
                    ephemeral_ecdh_private_key=sender_ecdh_private_key,
                    ephemeral_ecdh_public_key=sender_ecdh_public_key,
                    recipient_ecdh_public_keys={
                        key.user_id: key.ecdh_public_key for key in key_items
                    },
                    recipient_ecdh_signatures={
                        key.user_id: key.ecdh_signature for key in key_items
                    },
                )
            )
            signatures = {
                delivery.ephemeral_signature for delivery in encrypted_deliveries
            }
            if len(signatures) != 1:
                raise APIError("Chat delivery signatures must be identical")

            logical_message_id = uuid.uuid7()
            batch = ChatMessageBatchDTO(
                logical_message_id=logical_message_id,
                content_type="text",
                ephemeral_public_key=sender_ecdh_public_key,
                ephemeral_signature=next(iter(signatures)),
                deliveries=[
                    ChatMessageDeliveryDTO(
                        recipient_id=delivery.recipient_uuid,
                        message_id=delivery.message_uuid,
                        message=delivery.encrypted_message,
                    )
                    for delivery in encrypted_deliveries
                ],
            )
            raw_response = await self._message_dao.send_chat_message_text(
                chat_id=chat_id,
                batch=batch,
                token=token,
            )
            sent_deliveries = [
                SentChatMessageDeliveryDTO.from_mapping(item) for item in raw_response
            ]
            expected_delivery_ids = {
                delivery.message_uuid for delivery in encrypted_deliveries
            }
            if (
                {delivery.id for delivery in sent_deliveries} != expected_delivery_ids
                or {delivery.recipient_id for delivery in sent_deliveries}
                != expected_user_ids
                or {delivery.logical_message_id for delivery in sent_deliveries}
                != {logical_message_id}
                or len({delivery.timestamp for delivery in sent_deliveries}) != 1
            ):
                raise APIError("Chat message response does not match the sent batch")
            return sent_deliveries

        except AuthenticationError:
            del self.token
            raise
        except (APIError, InfrastructureError):
            self._logger.exception("Failed to send encrypted chat message")
            raise

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
            response = await self._message_dao.get_undelivered_messages(token=token)

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
                message for message, _ in processed_results if message is not None
            ]
            processing_results = [
                result for _, result in processed_results if result is not None
            ]
            if processing_results:
                await self._message_dao.ack_messages(
                    results=processing_results,
                    token=token,
                )
            return decrypted_messages

        except AuthenticationError as e:
            self._logger.warning(
                f"Authentication failed while retrieving messages: {e!s}",
            )
            del self.token
            return []

        except Exception as e:
            self._logger.error(
                f"Error getting undelivered messages: {e!s}",
                exc_info=True,
            )
            return []

    async def _process_undelivered_message(
        self,
        message: dict[str, Any],
        ed_dict: dict[UUID, str],
        recipient_ecdh_private_key: str,
        semaphore: asyncio.Semaphore,
    ) -> tuple[dict[str, Any] | None, MessageProcessingResultDTO | None]:
        async with semaphore:
            try:
                message_id = UUID(str(message["id"]))
            except (KeyError, TypeError, ValueError):
                self._logger.error(
                    "Cannot acknowledge message with an invalid ID: %r",
                    message.get("id"),
                )
                return None, None

            try:
                sender_id = UUID(str(message["sender_id"]))
                sender_ed_public_key = ed_dict.get(sender_id)
                if not sender_ed_public_key:
                    raise DecryptionError(
                        f"Missing ED public key for sender {sender_id}"
                    )

                decrypted_content = await self._encryption_service.decrypt_message(
                    message_uuid=message_id,
                    encrypted_message=message["message"],
                    sender_ed_public_key=sender_ed_public_key,
                    recipient_ecdh_private_key=recipient_ecdh_private_key,
                    ephemeral_ecdh_public_key=message["ephemeral_public_key"],
                    ephemeral_signature=message["ephemeral_signature"],
                )

                return (
                    {
                        **message,
                        "decrypted_content": decrypted_content,
                        "decryption_status": "success",
                    },
                    MessageProcessingResultDTO(
                        message_id=message_id,
                        failed=False,
                    ),
                )

            except DecryptionError as error:
                self._logger.error(
                    f"Decryption failed for message {message.get('id')}, {error}",
                    exc_info=True,
                )
                return None, MessageProcessingResultDTO(
                    message_id=message_id,
                    failed=True,
                )

            except Exception:
                self._logger.error(
                    f"Unexpected error processing message {message.get('id')}",
                    exc_info=True,
                )
                return None, MessageProcessingResultDTO(
                    message_id=message_id,
                    failed=True,
                )

    async def get_failed_messages(self) -> list[FailedMessageDTO]:
        if self._current_token is None:
            self._logger.warning(
                "Cannot retrieve failed messages without an active session"
            )
            return []

        try:
            response = await self._message_dao.get_failed_messages(
                token=self._current_token
            )
            raw_messages = response.get("messages", [])
            if not isinstance(raw_messages, list):
                raise APIError("Failed messages response must contain a list")

            messages: list[FailedMessageDTO] = []
            for raw_message in raw_messages:
                if not isinstance(raw_message, dict):
                    raise APIError("Failed message response item must be an object")
                messages.append(FailedMessageDTO.from_mapping(raw_message))
            return messages
        except AuthenticationError:
            del self.token
            self._logger.warning(
                "Authentication failed while retrieving failed messages"
            )
            return []
        except (APIError, InfrastructureError) as error:
            self._logger.error(
                "Failed to retrieve message failures: %s",
                error,
                exc_info=True,
            )
            return []

    async def health_check(self) -> bool:
        try:
            return await self._message_dao.health_check()
        except Exception as e:
            self._logger.error(
                f"Message service health check failed: {e!s}",
                exc_info=True,
            )
            return False
