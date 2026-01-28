from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.backends import default_backend
from abc import ABC, abstractmethod
import logging
import asyncio
from typing import Tuple
import base64

from src.exceptions import CryptographyError, SignatureError, InvalidCiphertextError


class AbstractECDSASignature(ABC):
    @abstractmethod
    async def generate_key_pair(self) -> tuple[str, str]:
        """
        Generate a key pair (private, public) in PEM format
        :return: tuple of (private_key_pem, public_key_pem)
        """
        raise NotImplementedError()

    @abstractmethod
    async def sign_string(self, private_key_pem: str, string: str) -> str:
        """
        String signing private key
        :param private_key_pem:
        :param string:
        :return: base64 encoded signature
        """
        raise NotImplementedError()

    @abstractmethod
    async def verify_signature(self, public_key_pem: str, string: str, signature: str) -> bool:
        """
        Verify signature
        :param public_key_pem:
        :param string:
        :param signature: base64 encoded signature
        :return: True if signature is valid
        """
        raise NotImplementedError()


class SECP256R1Signature(AbstractECDSASignature):
    def __init__(self):
        self._curve = ec.SECP256R1()

    async def generate_key_pair(self) -> tuple[str, str]:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._generate_key_pair)
        except Exception as e:
            if self.logger:
                self.logger.error("Failed to generate SECP256R1 key pair: %s", str(e), exc_info=True)
            raise CryptographyError(
                "Failed to generate signature keys",
                original_error=e
            ) from e

    def _generate_key_pair(self) -> tuple[str, str]:
        private_key = ec.generate_private_key(self._curve, default_backend())

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

    async def sign_string(self, private_key_pem: str, string: str) -> str:
        try:
            loop = asyncio.get_running_loop()
            signature = await loop.run_in_executor(
                None, self._sign_string, private_key_pem, string
            )
            return signature
        except (ValueError, TypeError) as e:
            raise
        except Exception as e:
            raise CryptographyError(
                "Failed to create signature",
                original_error=e
            ) from e

    def _sign_string(self, private_key_pem: str, string: str) -> str:
        if not private_key_pem:
            raise ValueError("Private key cannot be empty")
        if not isinstance(string, str):
            raise TypeError("Message must be a string")
        if not string:
            raise ValueError("Message cannot be empty")

        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )

        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise TypeError("Invalid private key type")

        signature = private_key.sign(
            string.encode('utf-8'),
            ec.ECDSA(hashes.SHA256())
        )

        return base64.b64encode(signature).decode('utf-8')

    async def verify_signature(self, public_key_pem: str, message: str, signature: str) -> bool:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self._verify_signature, public_key_pem, message, signature
            )
        except (ValueError, TypeError, InvalidCiphertextError) as e:
            raise
        except SignatureError:
            return False
        except Exception as e:
            raise CryptographyError(
                "Failed to verify signature",
                original_error=e
            ) from e

    def _verify_signature(self, public_key_pem: str, string: str, signature: str) -> bool:
        if not public_key_pem:
            raise ValueError("Public key cannot be empty")
        if not isinstance(string, str):
            raise TypeError("String must be a str")
        if not string:
            raise ValueError("String cannot be empty")
        if not signature:
            raise ValueError("Signature cannot be empty")

        try:
            signature_bytes = base64.b64decode(signature)
        except Exception as e:
            raise InvalidCiphertextError(
                "Invalid base64 signature",
                original_error=e
            ) from e

        public_key = serialization.load_pem_public_key(
            public_key_pem.encode(),
            backend=default_backend()
        )

        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise TypeError("Invalid public key type")

        try:
            public_key.verify(
                signature_bytes,
                string.encode('utf-8'),
                ec.ECDSA(hashes.SHA256())
            )
            return True
        except Exception as e:
            raise SignatureError(
                "Signature verification failed",
                original_error=e
            ) from e

""" 
This bullshit is not needed yet and generally needs to be rewritten

class SECP521R1Signature(AbstractECDSASignature):
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)
        self.curve = ec.SECP521R1()

    async def generate_key_pair(self) -> tuple[str, str]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._generate_key_pair)

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
        loop = asyncio.get_running_loop()
        signature = await loop.run_in_executor(
            None, self._sign_message, private_key_pem, message
        )
        return base64.b64encode(signature).decode('utf-8')

    def _sign_message(self, private_key_pem: str, message: str) -> bytes:
        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(),
            password=None,
            backend=default_backend()
        )

        signature = private_key.sign(
            message.encode(),
            ec.ECDSA(hashes.SHA512())
        )

        return signature

    async def verify_signature(self, public_key_pem: str, message: str, signature: str) -> bool:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._verify_signature, public_key_pem, message, signature
        )

    def _verify_signature(self, public_key_pem: str, message: str, signature: str) -> bool:
        public_key = serialization.load_pem_public_key(
            public_key_pem.encode(),
            backend=default_backend()
        )

        signature_bytes = base64.b64decode(signature)

        try:
            public_key.verify(
                signature_bytes,
                message.encode(),
                ec.ECDSA(hashes.SHA512())
            )
            return True
        except Exception:
            return False
"""