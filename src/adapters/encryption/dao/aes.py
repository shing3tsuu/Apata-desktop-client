import os
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidTag
from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Any

from src.exceptions import *

class Abstract256Cipher(ABC):
    """in future maybe we add aes-gcm-siv and chacha20-poly1305 ciphers (for android/ios)"""

    @abstractmethod
    async def encrypt(
            self,
            plaintext: str,
            key: bytes
    ) -> str:
        """
        Encrypts the plaintext using 256-bit cipher with the given key.
        :param plaintext:
        :param key: 256-bit key
        :return: base64 encoded (important!) ciphertext (no need to encode for API (json) on service level)
        """
        raise NotImplementedError()

    @abstractmethod
    async def decrypt(
            self,
            ciphertext: str,
            key: bytes
    ) -> str:
        """
        Decrypts the ciphertext using 256-bit cipher with the given key.
        :param ciphertext: base64 encoded (important!) ciphertext
        :param key: 256-bit key
        :return: plaintext
        """
        raise NotImplementedError()


class AES256GCMCipher(Abstract256Cipher):
    async def encrypt(self, plaintext: str, key: bytes) -> str:
        try:
            loop = asyncio.get_running_loop()
            ciphertext = await loop.run_in_executor(
                None, self._safe_encrypt, plaintext, key
            )
            return ciphertext
        except (InvalidKeyError, ValueError) as e:
            raise
        except Exception as e:
            context = {"plaintext": plaintext[:100], "key_length": len(key)}
            raise EncryptionError(
                "AES encryption failed, unexpected error",
                original_error=e,
                context=context
            ) from e

    def _safe_encrypt(self, plaintext: str, key: bytes) -> str:
        if len(key) != 32:
            raise InvalidKeyError(
                f"AES key must be 32 bytes long",
                context={"key_length": len(key)}
            )

        nonce = os.urandom(12)
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce),
            backend=default_backend()
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
        except (InvalidKeyError, InvalidCiphertextError, ValueError) as e:
            raise
        except Exception as e:
            context = {
                "ciphertext_preview": b64_ciphertext[:100],
                "ciphertext_length": len(b64_ciphertext),
                "key_length": len(key)
            }
            raise DecryptionError(
                "AES decryption failed, unexpected error",
                original_error=e,
                context=context
            ) from e

    def _safe_decrypt(self, b64_ciphertext: str, key: bytes) -> str:
        if not b64_ciphertext or not isinstance(b64_ciphertext, str):
            raise InvalidCiphertextError(
                "Invalid ciphertext: empty or wrong type",
                context={"ciphertext_type": type(b64_ciphertext).__name__}
            )

        try:
            ciphertext = base64.b64decode(b64_ciphertext, validate=True)
        except Exception as e:
            raise InvalidCiphertextError(
                "Invalid base64 encoding",
                original_error=e,
                context={"ciphertext_length": len(b64_ciphertext)}
            ) from e

        if len(ciphertext) < 28:  # 12(nonce) + 16(tag)
            raise InvalidCiphertextError(
                f"Invalid ciphertext length: {len(ciphertext)} bytes. "
                f"Minimum required: 28 bytes",
                context={"ciphertext_length": len(ciphertext)}
            )

        if len(key) != 32:
            raise InvalidKeyError(
                f"AES key must be 32 bytes long",
                context={"key_length": len(key)}
            )

        nonce = ciphertext[:12]
        ciphertext_data = ciphertext[12:-16]
        tag = ciphertext[-16:]

        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce, tag),
            backend=default_backend()
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
                    "decoded_length": len(ciphertext)
                }
            ) from e