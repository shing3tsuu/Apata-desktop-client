import asyncio
import logging
from collections.abc import Sequence
from uuid import UUID

from src.adapters.database.dto import (
    AddMessageFileDTO,
    AddMessageTextDTO,
    MessageDTO,
)
from src.adapters.encryption.dao import Abstract256Cipher

from ..dao.common import AbstractCommonDAO, error_handler
from ..dao.message import AbstractMessageDAO


class MessageService:
    def __init__(
        self,
        message_dao: AbstractMessageDAO,
        common_dao: AbstractCommonDAO,
        aes_cipher: Abstract256Cipher,
        logger: logging.Logger,
    ):
        self._message_dao = message_dao
        self._common_dao = common_dao
        self._aes_cipher = aes_cipher
        self._logger = logger

        self._master_key: bytes | None = None

    @property
    def master_key(self) -> bytes | None:
        return self._master_key

    @master_key.setter
    def master_key(self, value: bytes):
        self._master_key = value

    @master_key.deleter
    def master_key(self):
        if self._master_key is not None:
            self._master_key = None

    @error_handler
    async def add_message_text(self, message: AddMessageTextDTO) -> MessageDTO:
        if self._master_key is None:
            raise ValueError("Master key is not set")

        encrypted = await self._aes_cipher.encrypt_with_message_uuid(
            plaintext=message.content,
            key=self._master_key,
            message_uuid=message.server_message_id,
        )
        prepared = message.model_copy(update={"content": encrypted})
        return await self._message_dao.add_message_text(prepared)

    @error_handler
    async def add_message_file(self, message: AddMessageFileDTO) -> MessageDTO:
        if self._master_key is None:
            raise ValueError("Master key is not set")

        encrypted = await self._aes_cipher.encrypt_bytes_with_message_uuid(
            plaintext=message.file_content,
            key=self._master_key,
            message_uuid=message.server_message_id,
        )
        prepared = message.model_copy(update={"file_content": encrypted})
        return await self._message_dao.add_message_file(prepared)

    @error_handler
    async def add_messages(
        self,
        texts: list[AddMessageTextDTO] | None = None,
        files: list[AddMessageFileDTO] | None = None,
    ) -> tuple[list[MessageDTO], list[MessageDTO]]:
        if self._master_key is None:
            raise ValueError("Master key is not set")

        texts = texts or []
        files = files or []

        if not texts and not files:
            raise ValueError("No texts and no files")

        tasks = []
        tasks.extend([self.add_message_text(msg) for msg in texts])
        tasks.extend([self.add_message_file(msg) for msg in files])

        results = await asyncio.gather(*tasks)

        text_results = results[: len(texts)]
        file_results = results[len(texts) :]
        return text_results, file_results

    async def _decrypt_one(self, msg: MessageDTO) -> MessageDTO | None:
        try:
            if msg.file_content is not None:
                decrypted_bytes = (
                    await self._aes_cipher.decrypt_bytes_with_message_uuid(
                        ciphertext=msg.file_content,
                        key=self._master_key,
                        message_uuid=msg.server_message_id,
                    )
                )
                return msg.model_copy(update={"file_content": decrypted_bytes})
            else:
                decrypted_str = await self._aes_cipher.decrypt_with_message_uuid(
                    ciphertext=msg.content,
                    key=self._master_key,
                    message_uuid=msg.server_message_id,
                )
                return msg.model_copy(update={"content": decrypted_str})
        except Exception as e:
            self._logger.error(f"Failed to decrypt message {msg.id}: {e}")
            return None

    async def _decrypt_preview(self, msg: MessageDTO) -> MessageDTO | None:
        if msg.content is not None:
            return await self._decrypt_one(msg)
        return msg

    @error_handler
    async def get_messages(
        self,
        local_user_id: UUID,
        contact_id: UUID,
        limit: int | None = None,
    ) -> list[MessageDTO]:
        if self._master_key is None:
            raise ValueError("Master key is not set")

        messages = await self._message_dao.get_messages(
            local_user_id, contact_id, limit
        )

        if not messages:
            return []

        decrypted_results = await asyncio.gather(
            *[self._decrypt_one(msg) for msg in messages]
        )
        decrypted = [msg for msg in decrypted_results if msg is not None]
        return decrypted

    @error_handler
    async def get_recent_messages(
        self,
        local_user_id: UUID,
        *,
        contact_id: UUID | None = None,
        chat_id: UUID | None = None,
        limit: int = 10,
    ) -> list[MessageDTO]:
        if self._master_key is None:
            raise ValueError("Master key is not set")

        messages = await self._message_dao.get_recent_messages(
            local_user_id,
            contact_id=contact_id,
            chat_id=chat_id,
            limit=limit,
        )
        decrypted = await asyncio.gather(
            *(self._decrypt_preview(message) for message in messages)
        )
        return [message for message in decrypted if message is not None]

    @error_handler
    async def delete_message(self, message_id: UUID) -> bool:
        return await self._message_dao.delete_message(message_id)

    @error_handler
    async def mark_messages_failed(
        self,
        local_user_id: UUID,
        server_message_ids: Sequence[UUID],
    ) -> int:
        return await self._message_dao.mark_messages_failed(
            local_user_id,
            server_message_ids,
        )
