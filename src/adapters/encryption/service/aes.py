import os
import base64
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidTag
from abc import ABC, abstractmethod
import asyncio
import logging


class AbstractAES256Cipher(ABC):
    @abstractmethod
    async def encrypt(
            self,
            plaintext: str,
            key: bytes
    ) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def decrypt(
            self,
            ciphertext: str,
            key: bytes
    ) -> str:
        raise NotImplementedError()


class AESGCMCipher(AbstractAES256Cipher):
    __slots__ = 'logger'

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger

    async def encrypt(self, plaintext: str, key: bytes) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._safe_encrypt, plaintext, key)

    def _safe_encrypt(self, plaintext: str, key: bytes) -> str:
        if len(key) != 32:
            raise ValueError("AES key must be 32 bytes long")

        nonce = os.urandom(12)
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()
        return base64.b64encode(nonce + ciphertext + encryptor.tag).decode()

    async def decrypt(self, b64_ciphertext: str, key: bytes) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._safe_decrypt, b64_ciphertext, key)

    def _safe_decrypt(self, b64_ciphertext: str, key: bytes) -> str:
        if not b64_ciphertext or not isinstance(b64_ciphertext, str):
            self.logger.error("Empty or invalid ciphertext format")
            raise ValueError("Invalid ciphertext: empty or wrong type")

        try:
            ciphertext = base64.b64decode(b64_ciphertext, validate=True)
        except Exception as e:
            self.logger.error(f"Base64 decoding failed: {str(e)}")
            raise ValueError("Invalid base64 encoding")

        if len(ciphertext) < 28:  # 12(nonce) + 16(tag) + 0(data)
            self.logger.error(
                f"Invalid ciphertext length: {len(ciphertext)} bytes. "
                f"Minimum required: 28 bytes"
            )
            raise ValueError("Invalid ciphertext: too short")

        if len(key) != 32:
            raise ValueError(f"Key must be 32 bytes, got {len(key)}")

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
        except InvalidTag:
            self.logger.error("Authentication failed: invalid tag")
            raise ValueError("Authentication failed")
        except Exception as e:
            self.logger.error(f"Decryption failed: {str(e)}")
            raise ValueError("Decryption failed")