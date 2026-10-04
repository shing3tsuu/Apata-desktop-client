import asyncio
import base64
import binascii
import hashlib
import json
import logging
import secrets
import uuid
from pathlib import Path
from typing import Any
from uuid import UUID

from src.adapters.encryption.dao import (
    Abstract256Cipher,
    AbstractECDHCipher,
    AbstractEDSignature,
)
from src.adapters.encryption.service.dto import (
    EncryptMessageResult,
    EncryptMessageToChatResult,
    FileEncryptionContext,
    FileMessageDescriptor,
    FileMetadataEncryptionResult,
    GenerateKeyPairResult,
)
from src.exceptions import SecurityError


class EncryptionService:
    _FILE_CHUNK_INDEX_SIZE = 8
    _FILE_AEAD_OVERHEAD = 28
    _MAX_CONCURRENT_CHAT_ENCRYPTIONS = 4

    @staticmethod
    def _validate_file_name(value: Any) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("File name must be a non-empty string")
        if "/" in value or "\\" in value:
            raise ValueError("File name must not contain a path")
        if value in {".", ".."} or "." in value:
            raise ValueError("File name must not contain an extension")
        return value

    @staticmethod
    def _validate_file_mime_type(value: Any) -> str:
        if not isinstance(value, str) or not value:
            raise ValueError("File MIME type must be a non-empty extension")
        if not value.startswith(".") or value == ".":
            raise ValueError("File MIME type must start with a dot")
        if "/" in value or "\\" in value:
            raise ValueError("File MIME type must not contain a path")
        return value

    def __init__(
        self,
        aes_cipher: Abstract256Cipher,
        ecdh_cipher: AbstractECDHCipher,
        ed_signer: AbstractEDSignature,
        logger: logging.Logger,
    ):
        self._aes_cipher = aes_cipher
        self._ecdh_cipher = ecdh_cipher
        self._ed_signer = ed_signer
        self._logger = logger

    @staticmethod
    def _get_key_fingerprint(public_key_pem: str) -> str:
        return hashlib.sha256(public_key_pem.encode("utf-8")).hexdigest()[:16]

    async def encrypt_message(
        self,
        message: str,
        sender_ed_private_key: str,
        recipient_ed_public_key: str,
        ephemeral_ecdh_private_key: str,
        ephemeral_ecdh_public_key: str,
        recipient_ecdh_public_key: str,
        recipient_ecdh_signature: str,
    ) -> EncryptMessageResult:
        """
        Encrypts a message.
        :param message:
            str (plaintext)
        :param sender_ed_private_key:
            our ed private key for signing our ecdh public key
        :param recipient_ed_public_key:
            ed public key of the recipient,
            this is necessary to ensure that his ecdh public key is current and has not been substituted.
        :param ephemeral_ecdh_private_key:
            our ecdh private key for deriving the shared key (ephemeral) is not for every message (not double ratchet),
            name "ephemeral" key here means that it is valid for the current session,
        :param ephemeral_ecdh_public_key:
            our ecdh public key for signing the message,
            attached to messages so that they do not get lost (that's why "ephemeral").
        :param recipient_ecdh_public_key:
            recipient current ECDH public key, which we use to encrypt the message (also check it with ecdsa)
        :param recipient_ecdh_signature:
            needed to check the ECDH key for substitution.
        :return: encrypted message, signature and UUID
        """
        self._logger.info(
            f"Starting encryption message: {message[:50]}",
            extra={"recipient_key_present": bool(recipient_ecdh_public_key)},
        )

        try:
            is_signature_valid, ephemeral_signature, shared_key = await asyncio.gather(
                self._ed_signer.verify_signature(
                    public_key_pem=recipient_ed_public_key,
                    string=recipient_ecdh_public_key,
                    signature=recipient_ecdh_signature,
                ),
                self._ed_signer.sign_string(
                    private_key_pem=sender_ed_private_key,
                    string=ephemeral_ecdh_public_key,
                ),
                self._ecdh_cipher.derive_shared_key(
                    private_key_pem=ephemeral_ecdh_private_key,
                    peer_public_key_pem=recipient_ecdh_public_key,
                ),
            )

            if not is_signature_valid:
                raise SecurityError(
                    "Recipient's ECDH key signature is invalid. "
                    "Possible MITM attack or key compromise."
                )

            message_uuid = uuid.uuid7()

            encrypted_message = await self._aes_cipher.encrypt_with_message_uuid(
                plaintext=message, key=shared_key, message_uuid=message_uuid
            )

            self._logger.info(
                f"Message: ({message[:50]}) encryption successful",
                extra={
                    "message_id": message_uuid,
                    "encrypted_size": len(encrypted_message),
                },
            )

            return EncryptMessageResult(
                encrypted_message=encrypted_message,
                ephemeral_signature=ephemeral_signature,
                message_uuid=message_uuid,
            )

        except Exception as e:
            self._logger.error(
                "Unexpected error during encryption in service layer",
                extra={
                    "error_type": e.__class__.__name__,
                    "message_preview": message[:50] if message else "",
                },
                exc_info=True,
            )
            raise

    async def encrypt_message_to_chat(
        self,
        message: str,
        sender_ed_private_key: str,
        recipient_ed_public_keys: dict[UUID, str],
        ephemeral_ecdh_private_key: str,
        ephemeral_ecdh_public_key: str,
        recipient_ecdh_public_keys: dict[UUID, str],
        recipient_ecdh_signatures: dict[UUID, str],
    ) -> list[EncryptMessageToChatResult]:
        """
        Encrypts a message for multiple recipients (chat).

        :param message: plaintext message
        :param sender_ed_private_key: sender's ED private key (for signing ephemeral key)
        :param recipient_ed_public_keys: dict {recipient_uuid: ED public key}
        :param ephemeral_ecdh_private_key: ephemeral ECDH private key (same for all recipients)
        :param ephemeral_ecdh_public_key: ephemeral ECDH public key (same for all recipients)
        :param recipient_ecdh_public_keys: dict {recipient_uuid: ECDH public key}
        :param recipient_ecdh_signatures: dict {recipient_uuid: signature of ECDH key}
        :return: one encrypted delivery result per recipient
        """
        recipient_set = set(recipient_ed_public_keys.keys())
        if recipient_set != set(
            recipient_ecdh_public_keys.keys()
        ) or recipient_set != set(recipient_ecdh_signatures.keys()):
            raise ValueError("Mismatched recipient UUID sets in provided dictionaries")

        self._logger.info(
            f"Starting encryption for {len(recipient_set)} recipients",
            extra={"recipient_count": len(recipient_set)},
        )

        try:
            ephemeral_signature = await self._ed_signer.sign_string(
                private_key_pem=sender_ed_private_key,
                string=ephemeral_ecdh_public_key,
            )
            semaphore = asyncio.Semaphore(self._MAX_CONCURRENT_CHAT_ENCRYPTIONS)

            async def encrypt_for_recipient(
                recipient_uuid: UUID,
            ) -> EncryptMessageToChatResult:
                async with semaphore:
                    is_signature_valid, shared_key = await asyncio.gather(
                        self._ed_signer.verify_signature(
                            public_key_pem=recipient_ed_public_keys[recipient_uuid],
                            string=recipient_ecdh_public_keys[recipient_uuid],
                            signature=recipient_ecdh_signatures[recipient_uuid],
                        ),
                        self._ecdh_cipher.derive_shared_key(
                            private_key_pem=ephemeral_ecdh_private_key,
                            peer_public_key_pem=recipient_ecdh_public_keys[
                                recipient_uuid
                            ],
                        ),
                    )
                    if not is_signature_valid:
                        raise SecurityError(
                            "Recipient's ECDH key signature is invalid. "
                            "Possible MITM attack or key compromise."
                        )

                    message_uuid = uuid.uuid7()
                    encrypted_message = (
                        await self._aes_cipher.encrypt_with_message_uuid(
                            plaintext=message,
                            key=shared_key,
                            message_uuid=message_uuid,
                        )
                    )
                    return EncryptMessageToChatResult(
                        recipient_uuid=recipient_uuid,
                        encrypted_message=encrypted_message,
                        ephemeral_signature=ephemeral_signature,
                        message_uuid=message_uuid,
                    )

            output = await asyncio.gather(
                *(
                    encrypt_for_recipient(recipient_uuid)
                    for recipient_uuid in sorted(recipient_set, key=str)
                )
            )

            self._logger.info(
                f"Successfully encrypted message for {len(output)} recipients",
                extra={"recipient_count": len(output)},
            )
            return output

        except Exception as e:
            self._logger.error(
                "Unexpected error during encryption in service layer",
                extra={
                    "error_type": e.__class__.__name__,
                    "message_preview": message[:50] if message else "",
                },
                exc_info=True,
            )
            raise

    async def decrypt_message(
        self,
        message_uuid: UUID,
        encrypted_message: str,
        sender_ed_public_key: str,
        recipient_ecdh_private_key: str,
        ephemeral_ecdh_public_key: str,
        ephemeral_signature: str,
    ) -> str:
        """
        Decrypts a message.
        :param message_uuid:
            uuid7 of message on server UUID
        :param encrypted_message:
            base64 encoded ciphertext (encoding in dao layer, not in service layer)
        :param sender_ed_public_key:
            ed public key of the sender, used to verify the signature of the ephemeral ECDH public key
        :param recipient_ecdh_private_key:
            our ecdh private key for deriving the shared key
        :param ephemeral_ecdh_public_key:
            current ecdh public key that was attached to the message
        :param ephemeral_signature:
            his signature for verify
        :return:
        """
        self._logger.debug(
            f"Starting decryption message: {encrypted_message[:50]}",
            extra={"recipient_key_present": bool(recipient_ecdh_private_key)},
        )

        try:
            is_signature_valid, shared_key = await asyncio.gather(
                self._ed_signer.verify_signature(
                    public_key_pem=sender_ed_public_key,
                    string=ephemeral_ecdh_public_key,
                    signature=ephemeral_signature,
                ),
                self._ecdh_cipher.derive_shared_key(
                    private_key_pem=recipient_ecdh_private_key,
                    peer_public_key_pem=ephemeral_ecdh_public_key,
                ),
            )

            if not is_signature_valid:
                raise SecurityError(
                    "Sender's ephemeral key signature is invalid. "
                    "Message may be tampered with or from untrusted source."
                )

            decrypted_message = await self._aes_cipher.decrypt_with_message_uuid(
                ciphertext=encrypted_message, key=shared_key, message_uuid=message_uuid
            )

            self._logger.debug(
                f"Message: ({decrypted_message[:50]}) decryption successful",
                extra={
                    "message_preview": decrypted_message[:50]
                    if decrypted_message
                    else "",
                    "sender_key_fingerprint": self._get_key_fingerprint(
                        sender_ed_public_key
                    ),
                },
            )

            return decrypted_message

        except Exception as e:
            self._logger.error(
                "Unexpected error during decryption in service layer",
                extra={
                    "error_type": e.__class__.__name__,
                    "ephemeral_key_fingerprint": self._get_key_fingerprint(
                        ephemeral_ecdh_public_key
                    ),
                },
                exc_info=True,
            )
            raise

    @property
    def file_chunk_encryption_overhead(self) -> int:
        return self._FILE_CHUNK_INDEX_SIZE + self._FILE_AEAD_OVERHEAD

    def create_file_encryption(self) -> FileEncryptionContext:
        return FileEncryptionContext(file_id=uuid.uuid7(), key=secrets.token_bytes(32))

    def get_encrypted_file_size(
        self,
        *,
        plaintext_size: int,
        plaintext_chunk_size: int,
    ) -> int:
        if plaintext_size < 0:
            raise ValueError("Plaintext file size cannot be negative")
        if plaintext_chunk_size <= 0:
            raise ValueError("Plaintext chunk size must be positive")
        if plaintext_size == 0:
            return 0

        chunk_count = (
            plaintext_size + plaintext_chunk_size - 1
        ) // plaintext_chunk_size
        return plaintext_size + chunk_count * self.file_chunk_encryption_overhead

    def get_file_resume_position(
        self,
        *,
        plaintext_size: int,
        plaintext_chunk_size: int,
        uploaded_ciphertext_size: int,
    ) -> tuple[int, int]:
        total_ciphertext_size = self.get_encrypted_file_size(
            plaintext_size=plaintext_size,
            plaintext_chunk_size=plaintext_chunk_size,
        )
        if not 0 <= uploaded_ciphertext_size <= total_ciphertext_size:
            raise ValueError("Upload offset is outside encrypted file bounds")
        if uploaded_ciphertext_size == total_ciphertext_size:
            chunk_count = (
                plaintext_size + plaintext_chunk_size - 1
            ) // plaintext_chunk_size
            return chunk_count, plaintext_size

        encrypted_chunk_size = (
            plaintext_chunk_size + self.file_chunk_encryption_overhead
        )
        if uploaded_ciphertext_size % encrypted_chunk_size:
            raise ValueError("Upload offset does not point to a chunk boundary")

        chunk_index = uploaded_ciphertext_size // encrypted_chunk_size
        plaintext_offset = chunk_index * plaintext_chunk_size
        if plaintext_offset > plaintext_size:
            raise ValueError("Upload offset exceeds plaintext file size")
        return chunk_index, plaintext_offset

    async def encrypt_file_chunk(
        self,
        *,
        context: FileEncryptionContext,
        chunk_index: int,
        plaintext: bytes,
    ) -> bytes:
        if chunk_index < 0:
            raise ValueError("File chunk index cannot be negative")
        if not plaintext:
            raise ValueError("File chunk cannot be empty")

        indexed_plaintext = (
            chunk_index.to_bytes(
                self._FILE_CHUNK_INDEX_SIZE,
                byteorder="big",
            )
            + plaintext
        )
        return await self._aes_cipher.encrypt_bytes_with_message_uuid(
            plaintext=indexed_plaintext,
            key=context.key,
            message_uuid=context.file_id,
        )

    async def decrypt_file_chunk(
        self,
        *,
        context: FileEncryptionContext,
        chunk_index: int,
        ciphertext: bytes,
    ) -> bytes:
        if chunk_index < 0:
            raise ValueError("File chunk index cannot be negative")

        indexed_plaintext = await self._aes_cipher.decrypt_bytes_with_message_uuid(
            ciphertext=ciphertext,
            key=context.key,
            message_uuid=context.file_id,
        )
        if len(indexed_plaintext) <= self._FILE_CHUNK_INDEX_SIZE:
            raise SecurityError("Decrypted file chunk has no content")
        stored_index = int.from_bytes(
            indexed_plaintext[: self._FILE_CHUNK_INDEX_SIZE],
            byteorder="big",
        )
        if stored_index != chunk_index:
            raise SecurityError("File chunk index integrity check failed")
        return indexed_plaintext[self._FILE_CHUNK_INDEX_SIZE :]

    def _create_file_metadata_payload(
        self,
        *,
        context: FileEncryptionContext,
        file_name: str,
        file_mime_type: str,
        file_size: int,
        plaintext_chunk_size: int,
    ) -> str:
        file_name = self._validate_file_name(file_name)
        file_mime_type = self._validate_file_mime_type(file_mime_type)
        if file_size < 0:
            raise ValueError("File size cannot be negative")

        return json.dumps(
            {
                "type": "file",
                "version": 2,
                "file_id": str(context.file_id),
                "file_name": file_name,
                "file_mime_type": file_mime_type,
                "file_size": file_size,
                "chunk_size": plaintext_chunk_size,
                "file_key": base64.b64encode(context.key).decode("ascii"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _parse_file_message_parts(data: dict[str, Any]) -> tuple[str, str]:
        version = data.get("version")
        if version == 2:
            file_name = data.get("file_name")
            file_mime_type = data.get("file_mime_type")
        elif version == 1:
            legacy_file_name = data.get("file_name")
            legacy_mime_type = data.get("mime_type")
            if not isinstance(legacy_file_name, str) or not legacy_file_name:
                raise ValueError("File message contains an invalid legacy file name")
            if not isinstance(legacy_mime_type, str) or not legacy_mime_type:
                raise ValueError("File message contains an invalid legacy MIME type")

            legacy_path = Path(legacy_file_name)
            if "/" in legacy_file_name or "\\" in legacy_file_name:
                raise ValueError("File message contains an invalid legacy file name")
            file_name = legacy_path.stem
            file_mime_type = legacy_path.suffix
        else:
            raise ValueError("Unsupported file message payload version")

        try:
            return (
                EncryptionService._validate_file_name(file_name),
                EncryptionService._validate_file_mime_type(file_mime_type),
            )
        except ValueError as error:
            raise ValueError(
                "File message contains invalid file name or MIME type"
            ) from error

    def _parse_file_metadata_payload(self, payload: str) -> FileMessageDescriptor:
        try:
            data = json.loads(payload)
        except (TypeError, ValueError) as error:
            raise ValueError("File message payload is not valid JSON") from error

        if not isinstance(data, dict):
            raise ValueError("File message payload must be a JSON object")
        if data.get("type") != "file":
            raise ValueError("Unsupported file message payload")

        file_id_raw = data.get("file_id")
        file_key_raw = data.get("file_key")
        file_size = data.get("file_size")
        chunk_size = data.get("chunk_size")

        if not isinstance(file_id_raw, str):
            raise ValueError("File message has no file ID")
        try:
            file_id = UUID(file_id_raw)
        except ValueError as error:
            raise ValueError("File message contains an invalid file ID") from error
        if file_id.version != 7:
            raise ValueError("File message must use a UUIDv7 file ID")

        if not isinstance(file_key_raw, str):
            raise ValueError("File message has no file key")
        try:
            file_key = base64.b64decode(file_key_raw, validate=True)
        except (ValueError, binascii.Error) as error:
            raise ValueError("File message contains an invalid file key") from error
        if len(file_key) != 32:
            raise ValueError("File message contains an invalid file key length")

        file_name, file_mime_type = self._parse_file_message_parts(data)
        if type(file_size) is not int or file_size < 0:
            raise ValueError("File message contains an invalid file size")
        if type(chunk_size) is not int or chunk_size <= 0:
            raise ValueError("File message contains an invalid chunk size")

        return FileMessageDescriptor(
            encryption_context=FileEncryptionContext(file_id=file_id, key=file_key),
            file_name=file_name,
            file_mime_type=file_mime_type,
            file_size=file_size,
            plaintext_chunk_size=chunk_size,
        )

    async def encrypt_file_metadata(
        self,
        *,
        context: FileEncryptionContext,
        file_name: str,
        file_mime_type: str,
        file_size: int,
        plaintext_chunk_size: int,
        sender_ed_private_key: str,
        recipient_ed_public_key: str,
        ephemeral_ecdh_private_key: str,
        ephemeral_ecdh_public_key: str,
        recipient_ecdh_public_key: str,
        recipient_ecdh_signature: str,
    ) -> FileMetadataEncryptionResult:
        metadata_payload = self._create_file_metadata_payload(
            context=context,
            file_name=file_name,
            file_mime_type=file_mime_type,
            file_size=file_size,
            plaintext_chunk_size=plaintext_chunk_size,
        )
        message_encryption = await self.encrypt_message(
            message=metadata_payload,
            sender_ed_private_key=sender_ed_private_key,
            recipient_ed_public_key=recipient_ed_public_key,
            ephemeral_ecdh_private_key=ephemeral_ecdh_private_key,
            ephemeral_ecdh_public_key=ephemeral_ecdh_public_key,
            recipient_ecdh_public_key=recipient_ecdh_public_key,
            recipient_ecdh_signature=recipient_ecdh_signature,
        )
        return FileMetadataEncryptionResult(
            encrypted_metadata=message_encryption.encrypted_message,
            ephemeral_signature=message_encryption.ephemeral_signature,
            metadata_message_id=message_encryption.message_uuid,
        )

    async def decrypt_file_metadata(
        self,
        *,
        message_uuid: UUID,
        encrypted_metadata: str,
        sender_ed_public_key: str,
        recipient_ecdh_private_key: str,
        ephemeral_ecdh_public_key: str,
        ephemeral_signature: str,
    ) -> FileMessageDescriptor:
        metadata_payload = await self.decrypt_message(
            message_uuid=message_uuid,
            encrypted_message=encrypted_metadata,
            sender_ed_public_key=sender_ed_public_key,
            recipient_ecdh_private_key=recipient_ecdh_private_key,
            ephemeral_ecdh_public_key=ephemeral_ecdh_public_key,
            ephemeral_signature=ephemeral_signature,
        )
        return self._parse_file_metadata_payload(metadata_payload)

    async def generate_key_pairs(self) -> GenerateKeyPairResult:
        """
        Generates new key pairs for ECDH and ED.
        :return: GenerateKeyPairResult
        """
        try:
            ecdh_private, ecdh_public = await self._ecdh_cipher.generate_key_pair()
            ed_private, ed_public = await self._ed_signer.generate_key_pair()

            self._logger.info("Generated new key pairs")

            return GenerateKeyPairResult(
                ecdh_private_key=ecdh_private,
                ecdh_public_key=ecdh_public,
                ed_private_key=ed_private,
                ed_public_key=ed_public,
            )

        except Exception:
            self._logger.error("Failed to generate key pairs", exc_info=True)
            raise

    async def sign_string(self, private_key_pem: str, string: str) -> str:
        """
        Sign a string with ED private key.
        :param private_key_pem: PEM-encoded private key
        :param string: String to sign
        :return: Base64-encoded signature
        """
        try:
            return await self._ed_signer.sign_string(private_key_pem, string)
        except Exception as e:
            self._logger.error(
                "Unexpected error during signing",
                extra={
                    "error_type": e.__class__.__name__,
                    "string_length": len(string),
                },
                exc_info=True,
            )
            raise

    async def verify_signature(
        self, public_key_pem: str, string: str, signature: str
    ) -> bool:
        """
        Verify a signature using ED public key.
        :param public_key_pem: PEM-encoded public key
        :param string: Original string that was signed
        :param signature: Base64-encoded signature
        :return: True if signature is valid, False otherwise
        """
        try:
            return await self._ed_signer.verify_signature(
                public_key_pem=public_key_pem, string=string, signature=signature
            )
        except Exception as e:
            self._logger.error(
                "Unexpected error during signature verification",
                extra={
                    "error_type": e.__class__.__name__,
                    "string_length": len(string),
                },
                exc_info=True,
            )
            raise
