import asyncio
from abc import ABC, abstractmethod

import bcrypt
from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, InvalidHash


class AbstractPasswordHasher(ABC):
    @abstractmethod
    async def hashing(self, password: str) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def compare(self, password: str, hashed: str) -> bool:
        raise NotImplementedError()

    @staticmethod
    @abstractmethod
    def _is_valid_hash(hashed: str) -> bool:
        raise NotImplementedError()


class BcryptPasswordHasher(AbstractPasswordHasher):
    DUMMY_HASH = b"$2b$4$K3C8hN5u9Qk7z2v1wY6ZceBp1jH4dE7fG8i9l0m1n2o3p4q5r6s7t8u9v0"

    def __init__(self, min_password_length: int = 8):
        self.cost = 4
        self.min_password_length = min_password_length

    async def hashing(self, password: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._safe_hashing, password)

    def _safe_hashing(self, password: str) -> str:
        try:
            if not password:
                raise ValueError("Password cannot be empty")

            if len(password) < self.min_password_length:
                raise ValueError(
                    f"Password must be at least {self.min_password_length} characters long"
                )

            salt = bcrypt.gensalt(rounds=self.cost)
            hashed = bcrypt.hashpw(password.encode(), salt)
            return hashed.decode("utf-8")
        except Exception as e:
            raise e

    async def compare(self, password: str, hashed: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._safe_compare, password, hashed)

    def _safe_compare(self, password: str, hashed: str) -> bool:
        try:
            if not password or not hashed:
                return False

            hash_bytes = (
                hashed.encode("utf-8")
                if self._is_valid_hash(hashed)
                else self.DUMMY_HASH
            )
            return bcrypt.checkpw(password.encode(), hash_bytes)
        except Exception:
            return False

    @staticmethod
    def _is_valid_hash(hashed: str) -> bool:
        return (
            isinstance(hashed, str)
            and hashed.startswith(("$2a$", "$2b$", "$2y$"))
            and len(hashed) == 60
        )

class Argon2PasswordHasher(AbstractPasswordHasher):
    DUMMY_HASH = None

    def __init__(
        self,
        min_password_length: int = 8,
        time_cost: int = 3,
        memory_cost: int = 65536,
        parallelism: int = 4,
        hash_len: int = 16,
        salt_len: int = 16,
    ):
        self.min_password_length = min_password_length
        self._ph = PasswordHasher(
            time_cost=time_cost,
            memory_cost=memory_cost,
            parallelism=parallelism,
            hash_len=hash_len,
            salt_len=salt_len,
        )
        if Argon2PasswordHasher.DUMMY_HASH is None:
            Argon2PasswordHasher.DUMMY_HASH = self._ph.hash("__dummy__")

    async def hashing(self, password: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._safe_hashing, password)

    def _safe_hashing(self, password: str) -> str:
        if not password:
            raise ValueError("Password cannot be empty")

        if len(password) < self.min_password_length:
            raise ValueError(
                f"Password must be at least {self.min_password_length} characters long"
            )

        return self._ph.hash(password)

    async def compare(self, password: str, hashed: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._safe_compare, password, hashed)

    def _safe_compare(self, password: str, hashed: str) -> bool:
        if not password or not hashed:
            return False

        hash_to_check = hashed if self._is_valid_hash(hashed) else self.DUMMY_HASH

        try:
            self._ph.verify(hash_to_check, password)
            return True
        except VerificationError:
            return False

    @staticmethod
    def _is_valid_hash(hashed: str) -> bool:
        return (
            isinstance(hashed, str)
            and hashed.startswith("$argon2id$")
            and len(hashed) >= 60
        )

    def check_needs_rehash(self, hashed: str) -> bool:
        if not self._is_valid_hash(hashed):
            return True
        return self._ph.check_needs_rehash(hashed)