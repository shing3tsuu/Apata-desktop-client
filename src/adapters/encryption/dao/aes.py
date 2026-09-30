import asyncio
import base64
import os
from abc import ABC, abstractmethod
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from cryptography.hazmat.primitives.ciphers.aead import AESGCMSIV

from src.exceptions import (
    DecryptionError,
    EncryptionError,
    InvalidCiphertextError,
    InvalidKeyError,
)


class Abstract256Cipher(ABC):
    @abstractmethod
    async def encrypt(self, plaintext: str, key: bytes) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def decrypt(self, ciphertext: str, key: bytes) -> str:
        raise NotImplementedError()

class AbstractCipherWithMessageUUID(Abstract256Cipher):
    @abstractmethod
    async def encrypt_with_message_uuid(self, plaintext: str, key: bytes, message_id: UUID) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def decrypt_with_message_uuid(self, ciphertext: str, key: bytes, message_id: UUID) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def encrypt_bytes_with_message_uuid(self, plaintext: bytes, key: bytes, message_id: UUID) -> bytes:
        raise NotImplementedError()

    @abstractmethod
    async def decrypt_bytes_with_message_uuid(self, ciphertext: bytes, key: bytes, message_id: UUID) -> bytes:
        raise NotImplementedError()


class AES256GCMCipher(Abstract256Cipher):
    async def encrypt(self, plaintext: str, key: bytes) -> str:
        try:
            loop = asyncio.get_running_loop()
            ciphertext = await loop.run_in_executor(
                None, self._safe_encrypt, plaintext, key
            )
            return ciphertext
        except (InvalidKeyError, ValueError):
            raise
        except Exception as e:
            context = {"plaintext": plaintext[:100], "key_length": len(key)}
            raise EncryptionError(
                "AES encryption failed, unexpected error",
                original_error=e,
                context=context,
            ) from e

    def _safe_encrypt(self, plaintext: str, key: bytes) -> str:
        if not plaintext:
            raise ValueError("Data must not be zero length")
        if len(key) != 32:
            raise InvalidKeyError(
                "AES key must be 32 bytes long", context={"key_length": len(key)}
            )

        nonce = os.urandom(12)
        cipher = Cipher(
            algorithms.AES(key), modes.GCM(nonce), backend=default_backend()
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()

        combined = nonce + ciphertext + encryptor.tag
        return base64.b64encode(combined).decode()

    async def decrypt(self, b64_ciphertext: str, key: bytes) -> str:
        try:
            loop = asyncio.get_running_loop()
            plaintext = await loop.run_in_executor(
                None, self._safe_decrypt, b64_ciphertext, key
            )
            return plaintext
        except (InvalidKeyError, InvalidCiphertextError, ValueError, DecryptionError):
            raise
        except Exception as e:
            context = {
                "ciphertext_preview": b64_ciphertext[:100],
                "ciphertext_length": len(b64_ciphertext),
                "key_length": len(key),
            }
            raise DecryptionError(
                "AES decryption failed, unexpected error",
                original_error=e,
                context=context,
            ) from e

    def _safe_decrypt(self, b64_ciphertext: str, key: bytes) -> str:
        if not b64_ciphertext or not isinstance(b64_ciphertext, str):
            raise InvalidCiphertextError(
                "Invalid ciphertext: empty or wrong type",
                context={"ciphertext_type": type(b64_ciphertext).__name__},
            )

        try:
            ciphertext = base64.b64decode(b64_ciphertext, validate=True)
        except Exception as e:
            raise InvalidCiphertextError(
                "Invalid base64 encoding",
                original_error=e,
                context={"ciphertext_length": len(b64_ciphertext)},
            ) from e

        if len(ciphertext) < 28:  # 12(nonce) + 16(tag)
            raise InvalidCiphertextError(
                f"Invalid ciphertext length: {len(ciphertext)} bytes. "
                f"Minimum required: 28 bytes",
                context={"ciphertext_length": len(ciphertext)},
            )

        if len(key) != 32:
            raise InvalidKeyError(
                "AES key must be 32 bytes long", context={"key_length": len(key)}
            )

        nonce = ciphertext[:12]
        ciphertext_data = ciphertext[12:-16]
        tag = ciphertext[-16:]

        cipher = Cipher(
            algorithms.AES(key), modes.GCM(nonce, tag), backend=default_backend()
        )
        decryptor = cipher.decryptor()

        try:
            decrypted = decryptor.update(ciphertext_data) + decryptor.finalize()
            return decrypted.decode()
        except InvalidTag as e:
            raise DecryptionError(
                "Authentication failed: invalid tag",
                original_error=e,
                context={
                    "ciphertext_length": len(b64_ciphertext),
                    "decoded_length": len(ciphertext),
                },
            ) from e

class AES256GCMSIVCipher(AbstractCipherWithMessageUUID):
    def __init__(self):
        self._nonce_length = 12

    async def encrypt(self, plaintext: str, key: bytes) -> str:
        try:
            loop = asyncio.get_running_loop()
            ciphertext = await loop.run_in_executor(
                None, self._safe_encrypt, plaintext, key
            )
            return ciphertext
        except (InvalidKeyError, ValueError):
            raise
        except Exception as e:
            context = {"plaintext": plaintext[:100], "key_length": len(key)}
            raise EncryptionError(
                "AES encryption failed",
                original_error=e,
                context=context,
            ) from e

    def _safe_encrypt(self, plaintext: str, key: bytes) -> str:
        if not plaintext:
            raise ValueError("Data must not be zero length")
        if len(key) != 32:
            raise InvalidKeyError(
                "AES key must be 32 bytes long",
                context={"key_length": len(key)},
            )

        nonce = os.urandom(self._nonce_length)
        cipher = AESGCMSIV(key)

        encrypted = cipher.encrypt(nonce, plaintext.encode("utf-8"), None)
        combined = nonce + encrypted
        return base64.b64encode(combined).decode("utf-8")

    async def decrypt(self, ciphertext: str, key: bytes) -> str:
        try:
            loop = asyncio.get_running_loop()
            plaintext = await loop.run_in_executor(
                None, self._safe_decrypt, ciphertext, key
            )
            return plaintext
        except (InvalidKeyError, InvalidCiphertextError, ValueError, DecryptionError):
            raise
        except Exception as e:
            context = {
                "ciphertext_preview": ciphertext[:100],
                "ciphertext_length": len(ciphertext),
                "key_length": len(key),
            }
            raise DecryptionError(
                "AES decryption failed",
                original_error=e,
                context=context,
            ) from e

    def _safe_decrypt(self, b64_ciphertext: str, key: bytes) -> str:
        if not b64_ciphertext or not isinstance(b64_ciphertext, str):
            raise InvalidCiphertextError(
                "Invalid ciphertext: empty or wrong type",
                context={"ciphertext_type": type(b64_ciphertext).__name__},
            )

        try:
            combined = base64.b64decode(b64_ciphertext, validate=True)
        except Exception as e:
            raise InvalidCiphertextError(
                "Invalid base64 encoding",
                original_error=e,
                context={"ciphertext_length": len(b64_ciphertext)},
            ) from e

        if len(combined) < 28:
            raise InvalidCiphertextError(
                f"Invalid ciphertext length: {len(combined)} bytes. "
                f"Minimum required: 28 bytes",
                context={"ciphertext_length": len(combined)},
            )

        if len(key) != 32:
            raise InvalidKeyError(
                "AES key must be 32 bytes long",
                context={"key_length": len(key)},
            )

        nonce = combined[:self._nonce_length]
        encrypted = combined[self._nonce_length:]

        cipher = AESGCMSIV(key)
        try:
            decrypted = cipher.decrypt(nonce, encrypted, None)
            return decrypted.decode("utf-8")
        except InvalidTag as e:
            raise DecryptionError(
                "Authentication failed: invalid tag",
                original_error=e,
                context={
                    "ciphertext_length": len(b64_ciphertext),
                    "decoded_length": len(combined),
                },
            ) from e

    async def encrypt_with_message_uuid(self, plaintext: str, key: bytes, message_uuid: UUID) -> str:
        try:
            loop = asyncio.get_running_loop()
            ciphertext = await loop.run_in_executor(
                None, self._safe_encrypt_with_aad, plaintext, key, message_uuid
            )
            return ciphertext
        except (InvalidKeyError, ValueError):
            raise
        except Exception as e:
            context = {
                "plaintext": plaintext[:100],
                "key_length": len(key),
                "message_id": str(message_uuid),
            }
            raise EncryptionError(
                "AES encryption with UUID failed",
                original_error=e,
                context=context,
            ) from e

    def _safe_encrypt_with_aad(self, plaintext: str, key: bytes, message_uuid: UUID) -> str:
        if not plaintext:
            raise ValueError("Data must not be zero length")
        if len(key) != 32:
            raise InvalidKeyError(
                "AES key must be 32 bytes long",
                context={"key_length": len(key)},
            )
        if message_uuid.version != 7:
            raise ValueError("Only UUID version 7 is supported")

        nonce = os.urandom(self._nonce_length)
        aad = message_uuid.bytes
        cipher = AESGCMSIV(key)

        encrypted = cipher.encrypt(nonce, plaintext.encode("utf-8"), aad)
        combined = nonce + encrypted
        return base64.b64encode(combined).decode("utf-8")

    async def decrypt_with_message_uuid(self, ciphertext: str, key: bytes, message_uuid: UUID) -> str:
        try:
            loop = asyncio.get_running_loop()
            plaintext = await loop.run_in_executor(
                None, self._safe_decrypt_with_aad, ciphertext, key, message_uuid
            )
            return plaintext
        except (InvalidKeyError, InvalidCiphertextError, ValueError, DecryptionError):
            raise
        except Exception as e:
            context = {
                "ciphertext_preview": ciphertext[:100],
                "ciphertext_length": len(ciphertext),
                "key_length": len(key),
                "message_id": str(message_uuid),
            }
            raise DecryptionError(
                "AES decryption with UUID failed",
                original_error=e,
                context=context,
            ) from e

    def _safe_decrypt_with_aad(self, b64_ciphertext: str, key: bytes, message_uuid: UUID) -> str:
        if not b64_ciphertext or not isinstance(b64_ciphertext, str):
            raise InvalidCiphertextError(
                "Invalid ciphertext: empty or wrong type",
                context={"ciphertext_type": type(b64_ciphertext).__name__},
            )
        if message_uuid.version != 7:
            raise ValueError("Only UUID version 7 is supported")

        try:
            combined = base64.b64decode(b64_ciphertext, validate=True)
        except Exception as e:
            raise InvalidCiphertextError(
                "Invalid base64 encoding",
                original_error=e,
                context={"ciphertext_length": len(b64_ciphertext)},
            ) from e

        if len(combined) < 28:
            raise InvalidCiphertextError(
                f"Invalid ciphertext length: {len(combined)} bytes. "
                f"Minimum required: 28 bytes",
                context={"ciphertext_length": len(combined)},
            )

        if len(key) != 32:
            raise InvalidKeyError(
                "AES key must be 32 bytes long",
                context={"key_length": len(key)},
            )

        nonce = combined[:self._nonce_length]
        encrypted = combined[self._nonce_length:]
        aad = message_uuid.bytes

        cipher = AESGCMSIV(key)
        try:
            decrypted = cipher.decrypt(nonce, encrypted, aad)
            return decrypted.decode("utf-8")
        except InvalidTag as e:
            raise DecryptionError(
                "Authentication failed: invalid tag",
                original_error=e,
                context={
                    "ciphertext_length": len(b64_ciphertext),
                    "decoded_length": len(combined),
                    "message_id": str(message_uuid),
                },
            ) from e

    async def encrypt_bytes_with_message_uuid(self, plaintext: bytes, key: bytes, message_uuid: UUID) -> bytes:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self._safe_encrypt_bytes_with_aad, plaintext, key, message_uuid
            )
        except (InvalidKeyError, ValueError):
            raise
        except Exception as e:
            context = {
                "plaintext_size": len(plaintext),
                "key_length": len(key),
                "message_id": str(message_uuid),
            }
            raise EncryptionError(
                "AES encryption (bytes) with UUID failed",
                original_error=e,
                context=context,
            ) from e

    def _safe_encrypt_bytes_with_aad(self, plaintext: bytes, key: bytes, message_uuid: UUID) -> bytes:
        if not plaintext:
            raise ValueError("Data must not be zero length")
        if len(key) != 32:
            raise InvalidKeyError(
                "AES key must be 32 bytes long",
                context={"key_length": len(key)},
            )
        if message_uuid.version != 7:
            raise ValueError("Only UUID version 7 is supported")

        nonce = os.urandom(self._nonce_length)
        aad = message_uuid.bytes
        cipher = AESGCMSIV(key)

        encrypted = cipher.encrypt(nonce, plaintext, aad)
        return nonce + encrypted

    async def decrypt_bytes_with_message_uuid(self, ciphertext: bytes, key: bytes, message_uuid: UUID) -> bytes:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self._safe_decrypt_bytes_with_aad, ciphertext, key, message_uuid
            )
        except (InvalidKeyError, InvalidCiphertextError, ValueError, DecryptionError):
            raise
        except Exception as e:
            context = {
                "ciphertext_size": len(ciphertext),
                "key_length": len(key),
                "message_id": str(message_uuid),
            }
            raise DecryptionError(
                "AES decryption (bytes) with UUID failed",
                original_error=e,
                context=context,
            ) from e

    def _safe_decrypt_bytes_with_aad(self, ciphertext: bytes, key: bytes, message_uuid: UUID) -> bytes:
        if not ciphertext:
            raise InvalidCiphertextError(
                "Invalid ciphertext: empty",
                context={"ciphertext_size": 0},
            )
        if message_uuid.version != 7:
            raise ValueError("Only UUID version 7 is supported")

        if len(ciphertext) < 28:
            raise InvalidCiphertextError(
                f"Invalid ciphertext length: {len(ciphertext)} bytes. "
                f"Minimum required: 28 bytes",
                context={"ciphertext_length": len(ciphertext)},
            )

        if len(key) != 32:
            raise InvalidKeyError(
                "AES key must be 32 bytes long",
                context={"key_length": len(key)},
            )

        nonce = ciphertext[:self._nonce_length]
        encrypted = ciphertext[self._nonce_length:]
        aad = message_uuid.bytes

        cipher = AESGCMSIV(key)
        try:
            return cipher.decrypt(nonce, encrypted, aad)
        except InvalidTag as e:
            raise DecryptionError(
                "Authentication failed: invalid tag",
                original_error=e,
                context={
                    "ciphertext_size": len(ciphertext),
                    "message_id": str(message_uuid),
                },
            ) from e