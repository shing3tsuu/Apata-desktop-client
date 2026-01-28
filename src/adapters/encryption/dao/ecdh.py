import logging
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import asyncio
from abc import ABC, abstractmethod
from typing import Tuple

from src.exceptions import *

class AbstractECDHCipher(ABC):
    @abstractmethod
    async def generate_key_pair(self) -> tuple[str, str]:
        """
        Generate a key pair (private, public) in PEM format
        :return: tuple of (private_key_pem, public_key_pem)
        """
        raise NotImplementedError()

    @abstractmethod
    async def derive_shared_key(
            self,
            private_key_pem: str,
            peer_public_key_pem: str
    ) -> bytes:
        """
        Derives a shared key using the provided private key and peer's public key
        :param private_key_pem: PEM-encoded private key
        :param peer_public_key_pem: PEM-encoded public key
        :return: derived shared key (32 bytes)
        """
        raise NotImplementedError()


class X25519Cipher(AbstractECDHCipher):
    async def generate_key_pair(self) -> tuple[str, str]:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._generate_key_pair)
        except Exception as e:
            raise KeyGenerationError(
                "Failed to generate X25519 ecdh key pair",
                original_error=e
            ) from e

    def _generate_key_pair(self) -> tuple[str, str]:
        private_key = x25519.X25519PrivateKey.generate()

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

        return private_pem, public_pem

    async def derive_shared_key(
            self,
            private_key_pem: str,
            peer_public_key_pem: str
    ) -> bytes:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None,
                self._derive_shared_key,
                private_key_pem,
                peer_public_key_pem
            )
        except (ValueError, TypeError) as e:
            raise
        except Exception as e:
            raise CryptographyError(
                "Failed to derive shared ke",
                original_error=e
            ) from e

    def _derive_shared_key(
            self,
            private_key_pem: str,
            peer_public_key_pem: str
    ) -> bytes:
        if not private_key_pem or not peer_public_key_pem:
            raise ValueError("Keys cannot be empty")

        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )

        peer_public_key = serialization.load_pem_public_key(
            peer_public_key_pem.encode(),
            backend=default_backend()
        )

        if not isinstance(private_key, x25519.X25519PrivateKey):
            raise TypeError("Invalid private key type, expected X25519")

        if not isinstance(peer_public_key, x25519.X25519PublicKey):
            raise TypeError("Invalid public key type, expected X25519")

        shared_secret = private_key.exchange(peer_public_key)

        derived_key = HKDF(
            algorithm=hashes.SHA512(),
            length=32,
            salt=None,
            info=b'apata_messenger_x25519',
            backend=default_backend()
        ).derive(shared_secret)

        return derived_key