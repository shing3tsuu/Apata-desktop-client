import asyncio
import logging
import mimetypes
from typing import Any
from uuid import UUID

from src.adapters.api.dto import FileUploadSessionDTO, UndeliveredMessageFileDTO
from src.adapters.encryption.service import EncryptionService
from src.adapters.encryption.service.dto import (
    FileEncryptionContext,
    FileMessageDescriptor,
)
from src.exceptions import (
    APIError,
    AuthenticationError,
    DecryptionError,
    InfrastructureError,
    NetworkError,
)

from ..dao.auth import AuthHTTPDAO
from ..dao.file import FileHTTPDAO


class FileStorageState:
    def __init__(self, file_path: str | None = None):
        self.file_path = file_path

    @property
    def file_path(self) -> str | None:
        return None

    @file_path.setter
    def file_path(self, value: str | None) -> None:
        pass


class FileHTTPService:
    _DEFAULT_PLAINTEXT_CHUNK_SIZE = 4 * 1024 * 1024
    _MAX_CONCURRENT_FILE_DOWNLOADS = 3
    _MAX_CHUNK_RESUME_ATTEMPTS = 3
    _AMBIGUOUS_CHUNK_STATUS_CODES = frozenset({408, 409})

    def __init__(
        self,
        file_dao: FileHTTPDAO,
        auth_dao: AuthHTTPDAO,
        encryption_service: EncryptionService,
        logger: logging.Logger | None = None,
    ):
        self._file_dao = file_dao
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
    def token(self) -> None:
        self._current_token = None

    async def send_encrypted_message_file(
        self,
        *,
        chat_id: UUID | None,
        recipient_id: UUID,
        recipient_ed_public_key: str,
        sender_ed_private_key: str,
        sender_ecdh_private_key: str,
        ephemeral_ecdh_public_key: str,
        file_name: str,
        file_mime_type: str,
        file_content: bytes,
    ) -> UUID | None:
        token = self._require_token()
        if token is None:
            return None

        upload_id: str | None = None
        upload_completed = False

        try:
            file_size = self._prepare_file_content(
                file_name=file_name,
                file_mime_type=file_mime_type,
                file_content=file_content,
            )
            file_encryption_context = self._encryption_service.create_file_encryption()
            requested_chunk_size = (
                self._DEFAULT_PLAINTEXT_CHUNK_SIZE
                + self._encryption_service.file_chunk_encryption_overhead
            )
            encrypted_size = self._encryption_service.get_encrypted_file_size(
                plaintext_size=file_size,
                plaintext_chunk_size=self._DEFAULT_PLAINTEXT_CHUNK_SIZE,
            )

            recipient_keys = await self._auth_dao.get_public_keys(recipient_id, token)
            recipient_ecdh_public_key = recipient_keys.get("ecdh_public_key")
            recipient_ecdh_signature = recipient_keys.get("ecdh_signature")
            if not isinstance(recipient_ecdh_public_key, str) or not isinstance(
                recipient_ecdh_signature,
                str,
            ):
                raise APIError("Recipient public keys response is incomplete")

            metadata_encryption = await self._encryption_service.encrypt_file_metadata(
                context=file_encryption_context,
                file_name=file_name,
                file_mime_type=file_mime_type,
                file_size=file_size,
                plaintext_chunk_size=self._DEFAULT_PLAINTEXT_CHUNK_SIZE,
                sender_ed_private_key=sender_ed_private_key,
                recipient_ed_public_key=recipient_ed_public_key,
                ephemeral_ecdh_private_key=sender_ecdh_private_key,
                ephemeral_ecdh_public_key=ephemeral_ecdh_public_key,
                recipient_ecdh_public_key=recipient_ecdh_public_key,
                recipient_ecdh_signature=recipient_ecdh_signature,
            )

            session = await self._start_upload(
                context=file_encryption_context,
                recipient_id=recipient_id,
                encrypted_size=encrypted_size,
                requested_chunk_size=requested_chunk_size,
                message_id=metadata_encryption.metadata_message_id,
                chat_id=chat_id,
                encrypted_metadata=metadata_encryption.encrypted_metadata,
                ephemeral_public_key=ephemeral_ecdh_public_key,
                ephemeral_signature=metadata_encryption.ephemeral_signature,
                token=token,
            )
            upload_id = session.upload_id

            await self._upload_file_chunks(
                file_content=file_content,
                file_size=file_size,
                session=session,
                context=file_encryption_context,
                token=token,
            )
            await self._complete_upload(
                upload_id=upload_id,
                file_id=file_encryption_context.file_id,
                token=token,
            )
            upload_completed = True
            return metadata_encryption.metadata_message_id

        except AuthenticationError:
            del self.token
            self._logger.warning("Authentication failed while sending file")
            return None
        except (APIError, InfrastructureError, OSError, ValueError) as error:
            self._logger.error("Failed to send file: %s", error, exc_info=True)
            return None
        finally:
            if upload_id is not None and not upload_completed:
                await self._abort_upload(upload_id=upload_id, token=token)

    async def get_undelivered_message_files(
        self,
        *,
        ed_dict: dict[UUID, str],
        recipient_ecdh_private_key: str,
    ) -> list[UndeliveredMessageFileDTO]:
        token = self._require_token()
        if token is None:
            return []

        try:
            response = await self._file_dao.get_undelivered_message_files(token=token)
            raw_files = response.get("files")
            if not response.get("has_files") or not raw_files:
                return []
            if not isinstance(raw_files, list):
                raise APIError("Expected files list from undelivered file API")

            semaphore = asyncio.Semaphore(self._MAX_CONCURRENT_FILE_DOWNLOADS)
            results = await asyncio.gather(
                *(
                    self._process_undelivered_message_file(
                        file_data=file_data,
                        ed_dict=ed_dict,
                        recipient_ecdh_private_key=recipient_ecdh_private_key,
                        token=token,
                        semaphore=semaphore,
                    )
                    for file_data in raw_files
                )
            )
            files = [result for result in results if result is not None]
            if files:
                await self._file_dao.ack_message_files(
                    file_ids=[file.file_id for file in files],
                    token=token,
                )
            return files

        except AuthenticationError:
            del self.token
            self._logger.warning("Authentication failed while retrieving message files")
            return []
        except (APIError, InfrastructureError, ValueError) as error:
            self._logger.error("Failed to retrieve message files: %s", error, exc_info=True)
            return []

    async def _process_undelivered_message_file(
        self,
        *,
        file_data: Any,
        ed_dict: dict[UUID, str],
        recipient_ecdh_private_key: str,
        token: str,
        semaphore: asyncio.Semaphore,
    ) -> UndeliveredMessageFileDTO | None:
        if not isinstance(file_data, dict):
            self._logger.error("Undelivered file item is not an object")
            return None

        file_id = file_data.get("file_id")
        try:
            async with semaphore:
                sender_id = UUID(str(file_data["sender_id"]))
                sender_ed_public_key = ed_dict.get(sender_id)
                if not sender_ed_public_key:
                    raise DecryptionError(
                        f"Missing ED public key for sender {sender_id}"
                    )

                message_id = UUID(str(file_data["message_id"]))
                chat_id = UUID(str(file_data["chat_id"])) if file_data.get("chat_id") else None
                encrypted_metadata = file_data.get("encrypted_metadata")
                ephemeral_public_key = file_data.get("ephemeral_public_key")
                ephemeral_signature = file_data.get("ephemeral_signature")
                if not all(
                    isinstance(value, str)
                    for value in (
                        encrypted_metadata,
                        ephemeral_public_key,
                        ephemeral_signature,
                    )
                ):
                    raise APIError("Undelivered file metadata is incomplete")

                descriptor = await self._encryption_service.decrypt_file_metadata(
                    message_uuid=message_id,
                    encrypted_metadata=encrypted_metadata,
                    sender_ed_public_key=sender_ed_public_key,
                    recipient_ecdh_private_key=recipient_ecdh_private_key,
                    ephemeral_ecdh_public_key=ephemeral_public_key,
                    ephemeral_signature=ephemeral_signature,
                )
                if UUID(str(file_id)) != descriptor.encryption_context.file_id:
                    raise DecryptionError("File metadata does not match the file ID")

                file_content = await self._download_file_content(
                    descriptor=descriptor,
                    token=token,
                )
                return UndeliveredMessageFileDTO(
                    message_id=message_id,
                    sender_id=sender_id,
                    chat_id=chat_id,
                    file_id=descriptor.encryption_context.file_id,
                    file_name=descriptor.file_name,
                    file_mime_type=descriptor.file_mime_type,
                    file_size=descriptor.file_size,
                    file_content=file_content,
                    content_type=self._get_content_type(
                        self._get_media_type(descriptor.file_mime_type)
                    ),
                    timestamp=file_data.get("timestamp")
                )

        except AuthenticationError:
            raise
        except (APIError, InfrastructureError, ValueError) as error:
            self._logger.error(
                "Failed to process undelivered file %s: %s",
                file_id,
                error,
                exc_info=True,
            )
            return None

    @staticmethod
    def _prepare_file_content(
        *,
        file_name: str,
        file_mime_type: str,
        file_content: bytes,
    ) -> int:
        if not isinstance(file_name, str) or not file_name:
            raise ValueError("File name must be a non-empty string")
        if "/" in file_name or "\\" in file_name:
            raise ValueError("File name must not contain a path")
        if file_name in {".", ".."} or "." in file_name:
            raise ValueError("File name must not contain an extension")
        if not isinstance(file_mime_type, str) or not file_mime_type:
            raise ValueError("File MIME type must be a non-empty extension")
        if not file_mime_type.startswith(".") or file_mime_type == ".":
            raise ValueError("File MIME type must start with a dot")
        if "/" in file_mime_type or "\\" in file_mime_type:
            raise ValueError("File MIME type must not contain a path")
        if not isinstance(file_content, bytes):
            raise ValueError("File content must be bytes")
        return len(file_content)

    async def _start_upload(
        self,
        *,
        context: FileEncryptionContext,
        recipient_id: UUID,
        encrypted_size: int,
        requested_chunk_size: int,
        message_id: UUID,
        chat_id: UUID | None,
        encrypted_metadata: str,
        ephemeral_public_key: str,
        ephemeral_signature: str,
        token: str,
    ) -> FileUploadSessionDTO:
        session = await self._file_dao.create_upload(
            file_id=str(context.file_id),
            recipient_id=str(recipient_id),
            message_id=str(message_id),
            chat_id=str(chat_id) if chat_id else None,
            total_size=encrypted_size,
            requested_chunk_size=requested_chunk_size,
            encrypted_metadata=encrypted_metadata,
            ephemeral_public_key=ephemeral_public_key,
            ephemeral_signature=ephemeral_signature,
            token=token,
        )
        self._validate_upload_session(
            session=session,
            context=context,
            requested_chunk_size=requested_chunk_size,
        )
        return session

    async def _upload_file_chunks(
        self,
        *,
        file_content: bytes,
        file_size: int,
        session: FileUploadSessionDTO,
        context: FileEncryptionContext,
        token: str,
    ) -> None:
        plaintext_chunk_size = (
            session.chunk_size - self._encryption_service.file_chunk_encryption_overhead
        )
        if plaintext_chunk_size <= 0:
            raise APIError("File API chunk size is too small for encrypted data")

        chunk_index, plaintext_offset = self._encryption_service.get_file_resume_position(
            plaintext_size=file_size,
            plaintext_chunk_size=plaintext_chunk_size,
            uploaded_ciphertext_size=session.offset,
        )
        offset = session.offset
        remaining = file_size - plaintext_offset
        resume_attempts = 0

        while remaining:
            chunk_size = min(plaintext_chunk_size, remaining)
            plaintext_chunk = file_content[
                plaintext_offset:plaintext_offset + chunk_size
            ]
            if len(plaintext_chunk) != chunk_size:
                raise ValueError("File content changed while it was being uploaded")

            encrypted_chunk = await self._encryption_service.encrypt_file_chunk(
                context=context,
                chunk_index=chunk_index,
                plaintext=plaintext_chunk,
            )
            try:
                next_offset = await self._file_dao.upload_chunk(
                    upload_id=session.upload_id,
                    offset=offset,
                    encrypted_chunk=encrypted_chunk,
                    token=token,
                )
            except (NetworkError, APIError) as error:
                if not self._should_reconcile_upload_after_error(error):
                    raise

                resume_attempts += 1
                if resume_attempts > self._MAX_CHUNK_RESUME_ATTEMPTS:
                    raise

                resumed_session = await self._file_dao.get_upload_session(
                    upload_id=session.upload_id,
                    token=token,
                )
                self._validate_upload_session(
                    session=resumed_session,
                    context=context,
                    requested_chunk_size=session.chunk_size,
                    expected_upload_id=session.upload_id,
                )
                previous_offset = offset
                chunk_index, plaintext_offset = (
                    self._encryption_service.get_file_resume_position(
                        plaintext_size=file_size,
                        plaintext_chunk_size=plaintext_chunk_size,
                        uploaded_ciphertext_size=resumed_session.offset,
                    )
                )
                offset = resumed_session.offset
                remaining = file_size - plaintext_offset
                if offset != previous_offset:
                    resume_attempts = 0
                self._logger.warning(
                    "File chunk result is uncertain; resuming upload %s at offset %s",
                    session.upload_id,
                    offset,
                )
                continue

            expected_offset = offset + len(encrypted_chunk)
            if next_offset != expected_offset:
                raise APIError("File API acknowledged an unexpected upload offset")

            offset = next_offset
            plaintext_offset += len(plaintext_chunk)
            remaining -= len(plaintext_chunk)
            chunk_index += 1
            resume_attempts = 0

        expected_size = self._encryption_service.get_encrypted_file_size(
            plaintext_size=file_size,
            plaintext_chunk_size=plaintext_chunk_size,
        )
        if offset != expected_size:
            raise APIError("Encrypted file upload has an unexpected final size")

    @staticmethod
    def _validate_upload_session(
        *,
        session: FileUploadSessionDTO,
        context: FileEncryptionContext,
        requested_chunk_size: int,
        expected_upload_id: str | None = None,
    ) -> None:
        if expected_upload_id is not None and session.upload_id != expected_upload_id:
            raise APIError("Upload session has an unexpected upload ID")
        if session.file_id != str(context.file_id):
            raise APIError("Upload session belongs to a different file")
        if session.chunk_size != requested_chunk_size:
            raise APIError("File API returned an unexpected encrypted chunk size")

    @classmethod
    def _should_reconcile_upload_after_error(
        cls, error: NetworkError | APIError
    ) -> bool:
        if isinstance(error, NetworkError):
            return True
        if error.status_code in cls._AMBIGUOUS_CHUNK_STATUS_CODES:
            return True
        return error.is_server_error

    async def _download_file_content(
        self,
        *,
        descriptor: FileMessageDescriptor,
        token: str,
    ) -> bytes:
        if descriptor.file_size == 0:
            return b""

        chunks: list[bytes] = []
        remaining = descriptor.file_size
        chunk_index = 0
        while remaining:
            expected_plaintext_size = min(
                descriptor.plaintext_chunk_size,
                remaining,
            )
            encrypted_chunk = await self._file_dao.download_chunk(
                file_id=str(descriptor.encryption_context.file_id),
                chunk_index=chunk_index,
                token=token,
            )
            expected_ciphertext_size = (
                expected_plaintext_size
                + self._encryption_service.file_chunk_encryption_overhead
            )
            if len(encrypted_chunk) != expected_ciphertext_size:
                raise APIError("Downloaded file chunk has an unexpected size")

            plaintext_chunk = await self._encryption_service.decrypt_file_chunk(
                context=descriptor.encryption_context,
                chunk_index=chunk_index,
                ciphertext=encrypted_chunk,
            )
            if len(plaintext_chunk) != expected_plaintext_size:
                raise APIError("Decrypted file chunk has an unexpected size")

            chunks.append(plaintext_chunk)
            remaining -= len(plaintext_chunk)
            chunk_index += 1

        return b"".join(chunks)

    async def _complete_upload(
        self,
        *,
        upload_id: str,
        file_id: UUID,
        token: str,
    ) -> None:
        completed_file_id = UUID(
            await self._file_dao.complete_upload(upload_id=upload_id, token=token)
        )
        if completed_file_id != file_id:
            raise APIError("File API completed a different file")

    async def _abort_upload(self, *, upload_id: str, token: str) -> None:
        try:
            await self._file_dao.abort_upload(upload_id=upload_id, token=token)
        except AuthenticationError:
            del self.token
            self._logger.warning("Authentication failed while aborting file upload")
        except (APIError, InfrastructureError) as error:
            self._logger.warning("Failed to abort file upload %s: %s", upload_id, error)

    @staticmethod
    def _get_media_type(file_mime_type: str) -> str:
        return mimetypes.guess_type(f"file{file_mime_type}")[0] or "application/octet-stream"

    @staticmethod
    def _get_content_type(media_type: str) -> str:
        if media_type.startswith("image/"):
            return "image"
        if media_type.startswith("video/"):
            return "video"
        if media_type.startswith("audio/"):
            return "audio"
        if media_type in {
            "application/zip",
            "application/x-rar-compressed",
            "application/x-tar",
            "application/gzip",
            "application/x-7z-compressed",
        }:
            return "archive"
        return "document"

    def _require_token(self) -> str | None:
        if self._current_token is None:
            self._logger.warning("Cannot use file service without an active session")
        return self._current_token
