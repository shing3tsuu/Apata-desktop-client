from typing import Any
import base64
import logging

from src.adapters.encryption.dao import Abstract256Cipher, AbstractECDHCipher, AbstractECDSASignature
from src.exceptions import *

class EncryptionService:
    def __init__(
            self,
            aes_cipher: Abstract256Cipher,
            ecdh_cipher: AbstractECDHCipher,
            ecdsa_signer: AbstractECDSASignature,
            logger: logging.Logger
    ):
        self._aes_cipher = aes_cipher
        self._ecdh_cipher = ecdh_cipher
        self._ecdsa_signer = ecdsa_signer
        self._logger = logger

    async def encrypt_message(
            self,
            message: str,
            sender_ecdsa_private_key: str,
            recipient_ecdsa_public_key: str,
            ephemeral_ecdh_private_key: str,
            ephemeral_ecdh_public_key: str,
            recipient_ecdh_public_key: str,
            recipient_ecdh_signature
    ) -> tuple[str, str]:
        """
        Encrypts a message.
        :param message:
            str (plaintext)
        :param sender_ecdsa_private_key:
            our ecdsa private key for signing our ecdh public key
        :param recipient_ecdsa_public_key:
            ecdsa public key of the recipient,
            this is necessary to ensure that his ecdh public key is current and has not been substituted.
        :param ephemeral_ecdh_private_key:
            our ecdh private key for deriving the shared key (ephemeral) is not for every message (not double ratchet),
            name "ephemeral" key here means that it is valid for the current session,
        :param ephemeral_ecdh_public_key:
            our ecdh public key for signing the message,
            attached to messages so that they do not get lost (that's why "ephemeral").
        :param recipient_ecdh_public_key:
            recipient current ECDH public key, which we use to encrypt the message (also check it with ecdsa)
        :param recipient_ecdh_signature:
            needed to check the ECDH key for substitution.
        :return: encrypted message and signature
        """

        self._logger.debug(
            f"Starting encryption message: {message[:50]}",
            extra={
                "recipient_key_present": bool(recipient_ecdh_public_key)
            }
        )

        is_signature_valid = await self._ecdsa_signer.verify_signature(
            public_key_pem=recipient_ecdsa_public_key,
            message=recipient_ecdh_public_key,
            signature=recipient_ecdh_signature
        )

        if not is_signature_valid:
            raise SecurityError(
                "Recipient's ECDH key signature is invalid. "
                "Possible MITM attack or key compromise."
            )

        try:
            ephemeral_signature = await self._ecdsa_signer.sign_string(
                private_key_pem=sender_ecdsa_private_key,
                string=ephemeral_ecdh_public_key
            )

            shared_key = await self._ecdh_cipher.derive_shared_key(
                private_key_pem=ephemeral_ecdh_private_key,
                peer_public_key_pem=recipient_ecdh_public_key
            )

            encrypted_message = await self._aes_cipher.encrypt(
                plaintext=message,
                key=shared_key
            )

            self._logger.info(
                f"Message: ({message[:50]}) encryption successful",
                extra={
                    "message_id": self._generate_message_id(),
                    "encrypted_size": len(encrypted_message)
                }
            )

            return encrypted_message, ephemeral_signature

        except (InvalidKeyError, CryptographyError) as e:
            raise

        except Exception as e:
            self._logger.error(
                "Unexpected error during encryption in service layer",
                extra={
                    "error_type": e.__class__.__name__,
                    "message_preview": message[:50] if message else ""
                },
                exc_info=True
            )

            raise InfrastructureError(
                "Message encryption failed due to technical issue",
                original_error=e
            ) from e

    async def decrypt_message(
            self,
            encrypted_message: str,
            sender_ecdsa_public_key: str,
            recipient_ecdh_private_key: str,
            ephemeral_ecdh_public_key: str,
            ephemeral_signature: str,
    ) -> str:
        """
        Decrypts a message.
        :param encrypted_message:
            base64 encoded ciphertext (encoding in dao layer, not in service layer)
        :param sender_ecdsa_public_key:
            ecdsa public key of the sender, used to verify the signature of the ephemeral ECDH public key
        :param recipient_ecdh_private_key:
            our ecdh private key for deriving the shared key
        :param ephemeral_ecdh_public_key:
            current ecdh public key that was attached to the message
        :param ephemeral_signature:
            his signature for verify
        :return:
        """

        self._logger.debug(
            f"Starting decryption message: {message[:50]}",
            extra={
                "recipient_key_present": bool(recipient_ecdh_public_key)
            }
        )

        is_signature_valid = await self._ecdsa_signer.verify_signature(
            public_key_pem=sender_ecdsa_public_key,
            message=ephemeral_ecdh_public_key,
            signature=ephemeral_signature
        )

        if not is_signature_valid:
            raise SecurityError(
                "Sender's ephemeral key signature is invalid. "
                "Message may be tampered with or from untrusted source."
            )

        try:
            shared_key = await self._ecdh_cipher.derive_shared_key(
                private_key_pem=recipient_ecdh_private_key,
                peer_public_key_pem=ephemeral_ecdh_public_key
            )

            decrypted_message = await self._aes_cipher.decrypt(
                ciphertext=encrypted_message,
                key=shared_key
            )

            self._logger.debug(
                f"Message: ({decrypted_message[:50]}) decryption successful",
                extra={
                    "message_preview": decrypted_message[:50] if decrypted_message else "",
                    "sender_key_fingerprint": self._get_key_fingerprint(sender_ecdsa_public_key)
                }
            )

            return decrypted_message

        except (InvalidCiphertextError, InvalidKeyError) as e:
            raise

        except Exception as e:
            self._logger.error(
                "Unexpected error during decryption in service layer",
                extra={
                    "error_type": e.__class__.__name__,
                    "ephemeral_key_fingerprint": self._get_key_fingerprint(ephemeral_ecdh_public_key)
                },
                exc_info=True
            )

            raise InfrastructureError(
                "Message decryption failed due to technical issue",
                original_error=e,
                context={"operation": "e2ee_decryption"}
            ) from e

    async def generate_key_pairs(self) -> dict[str, Any]:
        """
        Generates new key pairs for ECDH and ECDSA.
        :return: dict { "ecdh_private_key", "ecdh_public_key", "ecdsa_private_key", "ecdsa_public_key" }
        """
        try:
            ecdh_private, ecdh_public = await self._ecdh_cipher.generate_key_pair()
            ecdsa_private, ecdsa_public = await self._ecdsa_signer.generate_key_pair()

            self._logger.info(
                "Generated new key pairs",
                extra={
                    "ecdh_key_fingerprint": self._get_key_fingerprint(ecdh_public),
                    "ecdsa_key_fingerprint": self._get_key_fingerprint(ecdsa_public)
                }
            )

            return {
                "ecdh_private_key": ecdh_private,
                "ecdh_public_key": ecdh_public,
                "ecdsa_private_key": ecdsa_private,
                "ecdsa_public_key": ecdsa_public,
            }

        except KeyGenerationError as e:
            raise
        except Exception as e:
            self._logger.error(
                "Failed to generate key pairs",
                exc_info=True
            )
            raise InfrastructureError(
                "Key generation failed",
                original_error=e
            ) from e

    async def sign_string(self, private_key_pem: str, string: str) -> str:
        """
        Sign a string with ECDSA private key.
        :param private_key_pem: PEM-encoded private key
        :param string: String to sign
        :return: Base64-encoded signature
        """
        try:
            return await self._ecdsa_signer.sign_string(private_key_pem, string)

        except (InvalidKeyError, CryptographyError) as e:
            raise
        except Exception as e:
            self._logger.error(
                "Unexpected error during signing",
                extra={
                    "error_type": e.__class__.__name__,
                    "string_length": len(string)
                },
                exc_info=True
            )
            raise InfrastructureError(
                "Failed to sign string due to technical issue",
                original_error=e
            ) from e

    async def verify_signature(
            self,
            public_key_pem: str,
            string: str,
            signature: str
    ) -> bool:
        """
        Verify ECDSA signature.
        :param public_key_pem: PEM-encoded public key
        :param string: Original string
        :param signature: Base64-encoded signature
        :return: True if signature is valid
        """
        try:
            return await self._ecdsa_signer.verify_signature(
                public_key_pem=public_key_pem,
                message=string,
                signature=signature
            )

        except (InvalidKeyError, InvalidCiphertextError, CryptographyError) as e:
            raise
        except Exception as e:
            self._logger.error(
                "Unexpected error during signature verification",
                extra={
                    "error_type": e.__class__.__name__,
                    "string_length": len(string)
                },
                exc_info=True
            )
            raise InfrastructureError(
                "Failed to verify signature due to technical issue",
                original_error=e
            ) from e