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
        """
        Encrypts the plaintext using symmetric block cipher algorithm
        (Modes: AES-256-GCM, AES-256-GCM-SIV (possible in future), ChaCha20-Poly1305 (possible in future))
        :param plaintext: Text to encrypt
        :param key: 32-byte encryption key
        :return: Base64-encoded encrypted data
        """
        raise NotImplementedError()

    @abstractmethod
    async def decrypt(
            self,
            ciphertext: str,
            key: bytes
    ) -> str:
        """
        Decrypts the plaintext using symmetric block cipher algorithm
        (Modes: AES-256-GCM, AES-256-GCM-SIV (possible in future), ChaCha20-Poly1305 (possible in future))
        :param ciphertext: Base64-encoded encrypted data
        :param key: 32-byte decryption key
        :return: Decrypted text
        """
        raise NotImplementedError()


class AESGCMCipher(AbstractAES256Cipher):
    __slots__ = 'logger'

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger

    async def encrypt(self, plaintext: str, key: bytes) -> bytes:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._safe_encrypt, plaintext, key)

    def _safe_encrypt(self, plaintext: str, key: bytes) -> bytes:
        if len(key) != 32:
            raise ValueError("AES key must be 32 bytes long")

        try:
            nonce = os.urandom(12)
            cipher = Cipher(
                algorithms.AES(key),
                modes.GCM(nonce),
                backend=default_backend()
            )
            encryptor = cipher.encryptor()
            ciphertext = encryptor.update(plaintext.encode()) + encryptor.finalize()
            return nonce + ciphertext + encryptor.tag
        except Exception as e:
            self.logger.error(f"Error encrypting data: {e}")
            raise

    async def decrypt(self, ciphertext: bytes, key: bytes) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._safe_decrypt, ciphertext, key)

    def _safe_decrypt(self, ciphertext: bytes, key: bytes) -> str:
        if len(key) != 32:
            raise ValueError("AES key must be 32 bytes long")

        try:
            if not isinstance(ciphertext, bytes) or len(ciphertext) < 28:
                self.logger.error(f"Invalid ciphertext: type={type(ciphertext)}, length={len(ciphertext) if ciphertext else 0}")
                raise ValueError("Invalid ciphertext")

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
                raise ValueError("Authentication failed")
        except (ValueError, IndexError) as e:
            self.logger.error(f"Invalid ciphertext format: {e}")
            raise
        except Exception as e:
            self.logger.error(f"Decryption failed: {e}")
            raise