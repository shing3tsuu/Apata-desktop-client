from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from abc import ABC, abstractmethod
import logging
import asyncio
from typing import Optional, Tuple
import base64


class AbstractECDSASignature(ABC):
    @abstractmethod
    async def generate_key_pair(self) -> tuple[str, str]:
        """
        Generate a key pair (private, public) in PEM format
        :return:
        """
        raise NotImplementedError()

    @abstractmethod
    async def sign_message(self, private_key_pem: str, message: str) -> str:
        """
        Message signing private key
        :param private_key_pem:
        :param message:
        :return:
        """
        raise NotImplementedError()

    @abstractmethod
    async def verify_signature(self, public_key_pem: str, message: str, signature: str) -> bool:
        """
        Verify signature
        :param public_key_pem:
        :param message:
        :param signature:
        :return:
        """
        raise NotImplementedError()

class SECP384R1Signature(AbstractECDSASignature):
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.curve = ec.SECP384R1()

    async def generate_key_pair(self) -> tuple[str, str]:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._generate_key_pair)
        except Exception as e:
            self.logger.error("Error generating key pair: %s", str(e))
            raise

    def _generate_key_pair(self) -> Tuple[str, str]:
        private_key = ec.generate_private_key(self.curve, default_backend())

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

    async def sign_message(self, private_key_pem: str, message: str) -> str:
        try:
            loop = asyncio.get_running_loop()
            signature = await loop.run_in_executor(
                None, self._sign_message, private_key_pem, message
            )
            return base64.b64encode(signature).decode('utf-8')
        except Exception as e:
            self.logger.error("Error signing message: %s", str(e))
            raise

    def _sign_message(self, private_key_pem: str, message: str) -> bytes:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )

        signature = private_key.sign(
            message.encode(),
            ec.ECDSA(hashes.SHA384())
        )

        return signature

    async def verify_signature(self, public_key_pem: str, message: str, signature: str) -> bool:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self._verify_signature, public_key_pem, message, signature
            )
        except Exception as e:
            self.logger.warning("Signature verification failed: %s", str(e))
            return False

    def _verify_signature(self, public_key_pem: str, message: str, signature: str) -> bool:
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode(),
            backend=default_backend()
        )

        signature_bytes = base64.b64decode(signature)

        public_key.verify(
            signature_bytes,
            message.encode(),
            ec.ECDSA(hashes.SHA384())
        )

        return True