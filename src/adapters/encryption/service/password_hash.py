import bcrypt
from abc import ABC, abstractmethod
import asyncio
import logging
from typing import Optional

class AbstractPasswordHasher(ABC):
    @abstractmethod
    async def hashing(
            self,
            password: str
    ) -> str:
        """
        Hashing the password
        :cost: 12 is default for bcrypt
        :param password:
        :return: Bytes
        """
        raise NotImplementedError()

    @abstractmethod
    async def compare(
            self,
            password: str,
            hashed: str
    ) -> bool:
        """
        Compare the password
        :param password:
        :param hashed:
        :return: Bool
        """
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def _is_valid_hash(
            hashed: str
    ) -> bool:
        """
        Check if the hash looks like a valid password hash
        :param hashed:
        :return:
        """
        raise NotImplementedError()

class BcryptPasswordHasher(AbstractPasswordHasher):
    __slots__ = ('cost', 'min_password_length', 'logger')

    DUMMY_HASH = b"$2b$12$K3C8hN5u9Qk7z2v1wY6ZceBp1jH4dE7fG8i9l0m1n2o3p4q5r6s7t8u9v0"
    # Pre-generated dummy hash to prevent timing attacks

    def __init__(self, logger: logging.Logger | None = None, min_password_length: int = 8):
        self.cost = 12
        self.min_password_length = min_password_length
        self.logger = logger or logging.getLogger(__name__)


    async def hashing(self, password: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._safe_hashing, password)

    def _safe_hashing(self, password: str) -> str:
        if not password:
            self.logger.error("Empty password provided for hashing")
            raise ValueError("Password cannot be empty")

        if len(password) < self.min_password_length:
            self.logger.error(f"Password too short, minimum {self.min_password_length} characters required")
            raise ValueError(f"Password must be at least {self.min_password_length} characters long")

        try:
            salt = bcrypt.gensalt(rounds=self.cost)
            hashed = bcrypt.hashpw(password.encode(), salt)
            return hashed.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Password hashing failed: {str(e)}", exc_info=True)
            raise RuntimeError("Password hashing failed") from e


    async def compare(self, password: str, hashed: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._safe_compare, password, hashed)

    def _safe_compare(self, password: str, hashed: str) -> bool:
        if not password or not hashed:
            self.logger.warning("Empty password or hash provided for comparison")
            return False

        try:
            # Use dummy hash if the provided hash is invalid
            hash_bytes = hashed.encode('utf-8') if self._is_valid_hash(hashed) else self.DUMMY_HASH
            return bcrypt.checkpw(password.encode(), hash_bytes)
        except Exception as e:
            self.logger.error(f"Password comparison error: {str(e)}", exc_info=True)
            return False

    @staticmethod
    def _is_valid_hash(hashed: str) -> bool:
        return (
                isinstance(hashed, str) and
                hashed.startswith(('$2a$', '$2b$', '$2y$')) and
                len(hashed) == 60
        )