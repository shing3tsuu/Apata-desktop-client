import os
import asyncio
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from cryptography.exceptions import InvalidTag
import logging
from typing import Tuple, Optional
import secrets


class KeyManager:
    def __init__(self, iterations: int, logger: logging.Logger | None = None):
        self.iterations = iterations
        self.logger = logger or logging.getLogger(__name__)

    def derive_key_from_password(self, password: str, salt: bytes | None = None, iterations: int | None = None) -> bytes:
        """Generate a key from a password and salt"""
        if not password:
            raise ValueError("Password cannot be empty")

        if not salt:
            salt = os.urandom(16)

        if iterations is None:
            iterations = self.iterations

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA512(),
            length=32,
            salt=salt,
            iterations=iterations,
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))

    async def generate_master_key(self) -> bytes:
        """Generate a random 256-bit master key"""
        return secrets.token_bytes(32)

    async def encrypt_with_master_key(self, data: bytes, master_key: bytes) -> Optional[bytes]:
        """Encrypt data using AES-GCM with master key"""
        if not data or not master_key:
            self.logger.error("Cannot encrypt: data or master key is empty")
            return None

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._encrypt_with_master_key, data, master_key)
        except Exception as e:
            self.logger.error("Failed to encrypt data: %s", str(e), exc_info=True)
            return None

    def _encrypt_with_master_key(self, data: bytes, master_key: bytes) -> bytes:
        if len(master_key) != 32:
            raise ValueError("Master key must be 32 bytes")

        nonce = os.urandom(12)
        cipher = Cipher(
            algorithms.AES(master_key),
            modes.GCM(nonce),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(data) + encryptor.finalize()
        return nonce + encryptor.tag + ciphertext

    async def decrypt_with_master_key(self, encrypted_data: bytes, master_key: bytes) -> Optional[bytes]:
        """Decrypt data using AES-GCM with master key"""
        if not encrypted_data or not master_key:
            self.logger.error("Cannot decrypt: encrypted data or master key is empty")
            return None

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._decrypt_with_master_key, encrypted_data, master_key)
        except (InvalidTag, ValueError) as e:
            self.logger.error("Failed to decrypt data: %s", str(e), exc_info=True)
            return None

    def _decrypt_with_master_key(self, encrypted_data: bytes, master_key: bytes) -> bytes:
        if len(encrypted_data) < 28:  # 12 (nonce) + 16 (tag)
            raise ValueError("Invalid encrypted data")

        nonce = encrypted_data[:12]
        tag = encrypted_data[12:28]
        ciphertext = encrypted_data[28:]

        cipher = Cipher(
            algorithms.AES(master_key),
            modes.GCM(nonce, tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()
        return decryptor.update(ciphertext) + decryptor.finalize()

    async def encrypt_master_key(self, master_key: bytes, password: str) -> tuple[bytes | None, bytes | None]:
        """Encrypt master key with password-derived key"""
        if not master_key or not password:
            self.logger.error("Cannot encrypt master key: master key or password is empty")
            return None, None

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._encrypt_master_key, master_key, password)
        except Exception as e:
            self.logger.error("Failed to encrypt master key: %s", str(e), exc_info=True)
            return None, None

    def _encrypt_master_key(self, master_key: bytes, password: str) -> tuple[bytes, bytes]:
        salt = os.urandom(16)
        key = self.derive_key_from_password(password, salt)

        nonce = os.urandom(12)
        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce),
            backend=default_backend()
        )
        encryptor = cipher.encryptor()
        ciphertext = encryptor.update(master_key) + encryptor.finalize()

        encrypted_data = nonce + encryptor.tag + ciphertext
        return encrypted_data, salt

    async def decrypt_master_key(self, encrypted_master_key: bytes, password: str, salt: bytes) -> bytes | None:
        """Decrypt master key with password"""
        if not encrypted_master_key or not password or not salt:
            self.logger.error("Cannot decrypt master key: missing required parameters")
            return None

        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._decrypt_master_key, encrypted_master_key, password, salt)
        except Exception as e:
            self.logger.error("Failed to decrypt master key: %s", str(e), exc_info=True)
            return None

    def _decrypt_master_key(self, encrypted_master_key: bytes, password: str, salt: bytes) -> bytes:
        if len(encrypted_master_key) < 28:  # 12 (nonce) + 16 (tag)
            raise ValueError("Invalid encrypted master key")

        nonce = encrypted_master_key[:12]
        tag = encrypted_master_key[12:28]
        ciphertext = encrypted_master_key[28:]

        key = self.derive_key_from_password(password, salt)

        cipher = Cipher(
            algorithms.AES(key),
            modes.GCM(nonce, tag),
            backend=default_backend()
        )
        decryptor = cipher.decryptor()

        try:
            return decryptor.update(ciphertext) + decryptor.finalize()
        except InvalidTag:
            raise ValueError("Invalid password or corrupted data")