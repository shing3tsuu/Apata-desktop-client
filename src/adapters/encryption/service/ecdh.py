import logging
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import serialization
import base64
import asyncio
from abc import ABC, abstractmethod

class AbstractECDHCipher(ABC):
    @abstractmethod
    async def generate_key_pair(self) -> tuple[str, str]:
        """
        Generate a key pair (private, public) in PEM format
        :return:
        """
        raise NotImplementedError()

    @abstractmethod
    async def derive_shared_key(self, private_key_pem: str, peer_public_key_pem: str) -> bytes:
        """
        Derives a shared key using the provided private key and peer's public key
        :param private_key_pem: PEM-encoded private key
        :param peer_public_key_pem: PEM-encoded public key
        :return:
        """
        raise NotImplementedError()

class X25519Cipher(AbstractECDHCipher):
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    async def generate_key_pair(self) -> tuple[str, str]:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._generate_key_pair)
        except Exception as e:
            self.logger.error("Error generating key pair: %s", str(e))
            raise

    def _generate_key_pair(self) -> tuple[str, str]:
        # Generate private key using X25519
        private_key = x25519.X25519PrivateKey.generate()

        # Serialize private key to PEM format
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption()
        ).decode('utf-8')

        # Get public key and serialize to PEM format
        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')

        return private_pem, public_pem

    async def derive_shared_key(self, private_key_pem: str, peer_public_key_pem: str) -> bytes:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self._derive_shared_key, private_key_pem, peer_public_key_pem
            )
        except Exception as e:
            self.logger.error("Error deriving shared key: %s", str(e))
            raise

    def _derive_shared_key(self, private_key_pem: str, peer_public_key_pem: str) -> bytes:
        # Load private key
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )

        # Load peer public key
        peer_public_key = serialization.load_pem_public_key(
            peer_public_key_pem.encode(),
            backend=default_backend()
        )

        # Perform key exchange (X25519 uses different method)
        shared_secret = private_key.exchange(peer_public_key)

        # Derive key using HKDF
        derived_key = HKDF(
            algorithm=hashes.SHA512(),
            length=32,
            salt=None,
            info=b'apata_messenger_x25519',
            backend=default_backend()
        ).derive(shared_secret)

        return derived_key