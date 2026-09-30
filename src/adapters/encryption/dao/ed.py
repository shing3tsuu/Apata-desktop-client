import asyncio
import base64
import logging
from abc import ABC, abstractmethod

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519

from src.exceptions import CryptographyError, InvalidCiphertextError, SignatureError


class AbstractEDSignature(ABC):
    @abstractmethod
    async def generate_key_pair(self) -> tuple[str, str]:
        raise NotImplementedError()

    @abstractmethod
    async def sign_string(self, private_key_pem: str, string: str) -> str:
        raise NotImplementedError()

    @abstractmethod
    async def verify_signature(
        self, public_key_pem: str, string: str, signature: str
    ) -> bool:
        raise NotImplementedError()


class SECP256R1Signature(AbstractEDSignature):
    def __init__(self, logger: logging.Logger | None = None):
        self._curve = ec.SECP256R1()
        self.logger = logger or logging.getLogger(__name__)

    async def generate_key_pair(self) -> tuple[str, str]:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._generate_key_pair)
        except Exception as e:
            raise CryptographyError(
                "Failed to generate signature keys", original_error=e
            ) from e

    def _generate_key_pair(self) -> tuple[str, str]:
        private_key = ec.generate_private_key(self._curve, default_backend())

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        return private_pem, public_pem

    async def sign_string(self, private_key_pem: str, string: str) -> str:
        try:
            loop = asyncio.get_running_loop()
            signature = await loop.run_in_executor(
                None, self._sign_string, private_key_pem, string
            )
            return signature
        except (ValueError, TypeError):
            raise
        except Exception as e:
            raise CryptographyError(
                "Failed to create signature", original_error=e
            ) from e

    def _sign_string(self, private_key_pem: str, string: str) -> str:
        if not private_key_pem:
            raise ValueError("Private key cannot be empty")
        if not isinstance(string, str):
            raise TypeError("Message must be a string")
        if not string:
            raise ValueError("Message cannot be empty")

        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None, backend=default_backend()
        )

        if not isinstance(private_key, ec.EllipticCurvePrivateKey):
            raise TypeError("Invalid private key type")

        signature = private_key.sign(string.encode("utf-8"), ec.ECDSA(hashes.SHA256()))

        return base64.b64encode(signature).decode("utf-8")

    async def verify_signature(
        self, public_key_pem: str, string: str, signature: str
    ) -> bool:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self._verify_signature, public_key_pem, string, signature
            )
        except (ValueError, TypeError, InvalidCiphertextError):
            raise
        except SignatureError:
            return False
        except Exception as e:
            raise CryptographyError(
                "Failed to verify signature", original_error=e
            ) from e

    def _verify_signature(
        self, public_key_pem: str, string: str, signature: str
    ) -> bool:
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
                "Invalid base64 signature", original_error=e
            ) from e

        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode())
        except ValueError as e:
            raise SignatureError("Invalid public key format", original_error=e)

        if not isinstance(public_key, ec.EllipticCurvePublicKey):
            raise TypeError("Invalid public key type")

        try:
            public_key.verify(
                signature_bytes, string.encode("utf-8"), ec.ECDSA(hashes.SHA256())
            )
            return True
        except Exception as e:
            raise SignatureError(
                "Signature verification failed", original_error=e
            ) from e


class Ed25519Signature(AbstractEDSignature):
    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    async def generate_key_pair(self) -> tuple[str, str]:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._generate_key_pair)
        except Exception as e:
            raise CryptographyError(
                "Failed to generate signature keys", original_error=e
            ) from e

    def _generate_key_pair(self) -> tuple[str, str]:
        private_key = ed25519.Ed25519PrivateKey.generate()

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode("utf-8")

        public_key = private_key.public_key()
        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

        return private_pem, public_pem

    async def sign_string(self, private_key_pem: str, string: str) -> str:
        try:
            loop = asyncio.get_running_loop()
            signature = await loop.run_in_executor(
                None, self._sign_string, private_key_pem, string
            )
            return signature
        except (ValueError, TypeError):
            raise
        except Exception as e:
            raise CryptographyError(
                "Failed to create signature", original_error=e
            ) from e

    def _sign_string(self, private_key_pem: str, string: str) -> str:
        if not private_key_pem:
            raise ValueError("Private key cannot be empty")
        if not isinstance(string, str):
            raise TypeError("Message must be a string")
        if not string:
            raise ValueError("Message cannot be empty")

        private_key = serialization.load_pem_private_key(
            private_key_pem.encode(), password=None
        )

        if not isinstance(private_key, ed25519.Ed25519PrivateKey):
            raise TypeError("Invalid private key type")

        signature = private_key.sign(string.encode("utf-8"))
        return base64.b64encode(signature).decode("utf-8")

    async def verify_signature(
        self, public_key_pem: str, string: str, signature: str
    ) -> bool:
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                None, self._verify_signature, public_key_pem, string, signature
            )
        except (ValueError, TypeError, InvalidCiphertextError):
            raise
        except SignatureError:
            return False
        except Exception as e:
            raise CryptographyError(
                "Failed to verify signature", original_error=e
            ) from e

    def _verify_signature(
        self, public_key_pem: str, string: str, signature: str
    ) -> bool:
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
                "Invalid base64 signature", original_error=e
            ) from e

        try:
            public_key = serialization.load_pem_public_key(public_key_pem.encode())
        except ValueError as e:
            raise SignatureError("Invalid public key format", original_error=e)

        if not isinstance(public_key, ed25519.Ed25519PublicKey):
            raise TypeError("Invalid public key type")

        try:
            public_key.verify(signature_bytes, string.encode("utf-8"))
            return True
        except Exception as e:
            raise SignatureError(
                "Signature verification failed", original_error=e
            ) from e
