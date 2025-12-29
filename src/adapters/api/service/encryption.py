from typing import Any
import base64
import logging

from src.adapters.encryption.service import AbstractAES256Cipher, AbstractECDHCipher, AbstractECDSASignature
from src.exceptions import (
    CryptographyError,
    EncryptionError,
    DecryptionError,
    InvalidKeyError,
    KeyGenerationError,
    InfrastructureError
)


class EncryptionService:
    __slots__ = (
        "_aes_cipher",
        "_ecdh_cipher",
        "_ecdsa_signer",
        "_logger",
        "__weakref__"
    )
    def __init__(
            self,
            aes_cipher: AbstractAES256Cipher,
            ecdh_cipher: AbstractECDHCipher,
            ecdsa_signer: AbstractECDSASignature,
            logger: logging.Logger = None
    ):
        self._aes_cipher = aes_cipher
        self._ecdh_cipher = ecdh_cipher
        self._ecdsa_signer = ecdsa_signer
        self._logger = logger or logging.getLogger(__name__)

    async def encrypt_message(
            self,
            message: str,
            sender_ecdsa_private_key: str,
            recipient_ecdsa_public_key: str,
            ephemeral_ecdh_private_key: str,
            ephemeral_ecdh_public_key: str,
            recipient_ecdh_public_key: str,
            recipient_ecdh_signature
    ) -> tuple[str, str, str]:
        context = {
            "operation": "encrypt_message",
            "message_length": len(message),
            "has_ephemeral_key": bool(ephemeral_ecdh_public_key),
            "has_recipient_key": bool(recipient_ecdh_public_key)
        }

        self._logger.info(
            "Starting message encryption",
            extra={"context": context}
        )

        try:
            verify = await self._ecdsa_signer.verify_signature(
                public_key_pem=recipient_ecdsa_public_key,
                message=recipient_ecdh_public_key,
                signature=recipient_ecdh_signature
            )

            if not verify:
                raise CryptographyError("Invalid ECDH signature, high probability of MITM attack.")

            signature = await self._ecdsa_signer.sign_message(
                private_key_pem=sender_ecdsa_private_key,
                message=ephemeral_ecdh_public_key
            )

            shared_key = await self._ecdh_cipher.derive_shared_key(
                ephemeral_ecdh_private_key,
                recipient_ecdh_public_key
            )

            context["shared_key_derived"] = True
            context["shared_key_length"] = len(shared_key) if shared_key else 0

            encrypted_message = await self._aes_cipher.encrypt(message, shared_key)

            self._logger.info(
                "Message encrypted successfully",
                extra={"context": {**context, "status": "success",
                                   "encrypted_length": len(encrypted_message)}}
            )

            return encrypted_message, signature

        except InvalidKeyError as e:
            self._logger.error(
                "Encryption failed - invalid key provided",
                extra={"context": {**context, "error_type": "InvalidKeyError", "error_message": str(e)}}
            )
            raise

        except CryptographyError as e:
            self._logger.error(
                "Cryptography error during encryption",
                extra={"context": context},
                exc_info=True
            )
            raise EncryptionError(
                f"Encryption failed: {str(e)}",
                original_error=e,
                operation="message_encryption",
                algorithm="AES-256-GCM",
                context=context
            ) from e

        except Exception as e:
            self._logger.error(
                "Unexpected error during message encryption",
                extra={"context": context},
                exc_info=True
            )
            raise InfrastructureError(
                f"Message encryption failed: {str(e)}",
                original_error=e,
                context=context
            ) from e

    async def decrypt_message(
            self,
            encrypted_message: str,
            sender_ecdsa_public_key: str,
            recipient_ecdh_private_key: str,
            ephemeral_ecdh_public_key: str,
            ephemeral_signature: str,
    ) -> str:
        context = {
            "operation": "decrypt_message",
            "encrypted_message_length": len(encrypted_message) if encrypted_message else 0,
            "has_recipient_private_key": bool(recipient_ecdh_private_key),
            "has_ephemeral_public_key": bool(ephemeral_ecdh_public_key)
        }

        self._logger.info(
            "Starting message decryption",
            extra={"context": context}
        )

        try:
            verify = await self._ecdsa_signer.verify_signature(
                public_key_pem=sender_ecdsa_public_key,
                message=ephemeral_ecdh_public_key,
                signature=ephemeral_signature
            )
            if not verify:
                raise CryptographyError("Invalid ECDH signature, high probability of MITM attack.")

            shared_key = await self._ecdh_cipher.derive_shared_key(
                recipient_ecdh_private_key,
                ephemeral_ecdh_public_key
            )

            context["shared_key_derived"] = True
            context["shared_key_length"] = len(shared_key) if shared_key else 0

            # Decrypt message with AES
            decrypted_message = await self._aes_cipher.decrypt(encrypted_message, shared_key)

            self._logger.info(
                "Message decrypted successfully",
                extra={"context": {**context, "status": "success", "decrypted_length": len(decrypted_message)}}
            )

            return decrypted_message

        except InvalidKeyError as e:
            self._logger.error(
                "Decryption failed - invalid key provided",
                extra={"context": {**context, "error_type": "InvalidKeyError", "error_message": str(e)}}
            )
            raise

        except CryptographyError as e:
            self._logger.error(
                "Cryptography error during decryption",
                extra={"context": context},
                exc_info=True
            )
            raise DecryptionError(
                f"Decryption failed: {str(e)}",
                original_error=e,
                operation="message_decryption",
                algorithm="AES-256-GCM",
                context=context
            ) from e

        except Exception as e:
            self._logger.error(
                "Unexpected error during message decryption",
                extra={"context": context},
                exc_info=True
            )
            raise InfrastructureError(
                f"Message decryption failed: {str(e)}",
                original_error=e,
                context=context
            ) from e

    async def generate_key_pairs(self) -> dict[str, Any]:
        """Generate both ECDSA and ECDH key pairs for a new user"""
        context = {"operation": "generate_key_pairs"}

        self._logger.info(
            "Generating cryptographic key pairs",
            extra={"context": context}
        )

        try:
            # Generate ECDH key pair for encryption
            ecdh_private, ecdh_public = await self._ecdh_cipher.generate_key_pair()

            context["ecdh_keys_generated"] = True

            self._logger.info(
                "Key pairs generated successfully",
                extra={"context": {**context, "status": "success"}}
            )

            return {
                "ecdh_private_key": ecdh_private,
                "ecdh_public_key": ecdh_public
            }

        except KeyGenerationError as e:
            self._logger.error(
                "Key generation failed",
                extra={"context": context},
                exc_info=True
            )
            raise

        except Exception as e:
            self._logger.error(
                "Unexpected error during key generation",
                extra={"context": context},
                exc_info=True
            )
            raise InfrastructureError(
                f"Key generation failed: {str(e)}",
                original_error=e,
                context=context
            ) from e