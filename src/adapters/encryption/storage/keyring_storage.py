import base64
import logging
import keyring
from keyring.errors import KeyringError
from cryptography.exceptions import InvalidTag
from typing import Optional, Tuple

from src.adapters.encryption.service import KeyManager


class EncryptedKeyStorage:
    def __init__(
            self,
            key_manager: KeyManager,
            logger: logging.Logger | None = None
    ):
        self.key_manager = key_manager
        self.logger = logger or logging.getLogger(__name__)

        # Constants for naming keys in keyring
        self.MASTER_KEY_SERVICE = "apata_messenger_master_key"
        self.ECDH_KEY_SERVICE = "apata_messenger_ecdh_key"
        self.ECDSA_KEY_SERVICE = "apata_messenger_ecdsa_key"

    def is_master_key_registered(self, username: str) -> bool:
        """Checks if the master key is registered for the user."""
        try:
            encrypted_data = keyring.get_password(self.MASTER_KEY_SERVICE, username)
            return encrypted_data is not None and len(encrypted_data) > 0
        except KeyringError as e:
            self.logger.error(f"Keyring error: {e}")
            return False

    async def register_master_key(self, username: str, password: str) -> bool:
        """Registers a new master key and stores it encrypted"""
        if not username or not password:
            self.logger.error("Username or password is empty")
            return False

        if self.is_master_key_registered(username):
            self.logger.warning("Master key already registered")
            return False

        try:
            # Generate a new master key
            master_key = await self.key_manager.generate_master_key()
            if not master_key:
                self.logger.error("Failed to generate master key")
                return False

            # Encrypt the master key with a password
            result = await self.key_manager.encrypt_master_key(master_key, password)
            if not result or result[0] is None or result[1] is None:
                self.logger.error("Failed to encrypt master key")
                return False

            encrypted_master_key, salt = result

            # Save in keyring (combine salt + encrypted_master_key in one line)
            combined_data = base64.b64encode(salt + encrypted_master_key).decode('utf-8')
            keyring.set_password(self.MASTER_KEY_SERVICE, username, combined_data)

            self.logger.info(f"Master key registered for user: {username}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to register master key: {e}")
            return False

    async def get_master_key(self, username: str, password: str) -> bytes | None:
        """Retrieves and decrypts the master key"""
        if not username or not password:
            self.logger.error("Username or password is empty")
            return None

        try:
            # Get encrypted data from keyring
            combined_data = keyring.get_password(self.MASTER_KEY_SERVICE, username)
            if not combined_data:
                self.logger.error("No master key found in keyring")
                return None

            # Decode and separate the salt and encrypted master key
            decoded_data = base64.b64decode(combined_data)
            if len(decoded_data) < 16:
                self.logger.error("Invalid combined data length")
                return None

            salt = decoded_data[:16]
            encrypted_master_key = decoded_data[16:]

            # Decrypting the master key
            master_key = await self.key_manager.decrypt_master_key(
                encrypted_master_key, password, salt
            )

            if not master_key:
                self.logger.error("Failed to decrypt master key")

            return master_key
        except (InvalidTag, ValueError) as e:
            self.logger.error(f"Invalid password or corrupted data: {e}")
            return None
        except KeyringError as e:
            self.logger.error(f"Keyring error: {e}")
            return None
        except Exception as e:
            self.logger.error(f"Unexpected error getting master key: {e}")
            return None

    async def store_ecdh_private_key(self, username: str, ecdh_private_key: str, password: str) -> bool:
        """Stores the ECDH private key in encrypted form"""
        if not username or not ecdh_private_key or not password:
            self.logger.error("Missing required parameters for storing ECDH key")
            return False

        try:
            # Get the master key
            master_key = await self.get_master_key(username, password)
            if not master_key:
                self.logger.error("Failed to get master key for ECDH storage")
                return False

            # Encrypt and save the private key
            encrypted_ecdh = await self.key_manager.encrypt_with_master_key(
                ecdh_private_key.encode('utf-8'), master_key
            )

            if not encrypted_ecdh:
                self.logger.error("Failed to encrypt ECDH private key")
                return False

            # Save in keyring
            keyring.set_password(
                self.ECDH_KEY_SERVICE,
                username,
                base64.b64encode(encrypted_ecdh).decode('utf-8')
            )

            self.logger.info(f"ECDH private key stored for user: {username}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store ECDH private key: {e}")
            return False

    async def store_ecdsa_private_key(self, username: str, password: str, private_key_pem: str) -> bool:
        """Stores the ECDSA private key in encrypted form"""
        if not username or not private_key_pem or not password:
            self.logger.error("Missing required parameters for storing ECDSA key")
            return False

        try:
            # Get the master key
            master_key = await self.get_master_key(username, password)
            if not master_key:
                self.logger.error("Failed to get master key for ECDSA storage")
                return False

            # Encrypt and save the private key
            encrypted_ecdsa = await self.key_manager.encrypt_with_master_key(
                private_key_pem.encode('utf-8'), master_key
            )

            if not encrypted_ecdsa:
                self.logger.error("Failed to encrypt ECDSA private key")
                return False

            # Save in keyring
            keyring.set_password(
                self.ECDSA_KEY_SERVICE,
                username,
                base64.b64encode(encrypted_ecdsa).decode('utf-8')
            )

            self.logger.info(f"ECDSA private key stored for user: {username}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store ECDSA private key: {e}")
            return False

    async def get_ecdh_private_key(self, username: str, password: str) -> Optional[str]:
        """Retrieves and decrypts the ECDH private key"""
        if not username or not password:
            self.logger.error("Username or password is empty")
            return None

        try:
            master_key = await self.get_master_key(username, password)
            if not master_key:
                self.logger.error("Failed to get master key for ECDH retrieval")
                return None

            # Get encrypted private key
            encrypted_ecdh = keyring.get_password(self.ECDH_KEY_SERVICE, username)
            if not encrypted_ecdh:
                self.logger.error("No ECDH key found in keyring")
                return None

            # Decrypt the key
            decrypted_ecdh = await self.key_manager.decrypt_with_master_key(
                base64.b64decode(encrypted_ecdh), master_key
            )

            if not decrypted_ecdh:
                self.logger.error("Failed to decrypt ECDH private key")
                return None

            return decrypted_ecdh.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Failed to get ECDH private key: {e}")
            return None

    async def get_ecdsa_private_key(self, username: str, password: str) -> Optional[str]:
        """Retrieves and decrypts the ECDSA private key"""
        if not username or not password:
            self.logger.error("Username or password is empty")
            return None

        try:
            master_key = await self.get_master_key(username, password)
            if not master_key:
                self.logger.error("Failed to get master key for ECDSA retrieval")
                return None

            # Get encrypted private key
            encrypted_ecdsa = keyring.get_password(self.ECDSA_KEY_SERVICE, username)
            if not encrypted_ecdsa:
                self.logger.error("No ECDSA key found in keyring")
                return None

            # Decrypt the key
            decrypted_ecdsa = await self.key_manager.decrypt_with_master_key(
                base64.b64decode(encrypted_ecdsa), master_key
            )

            if not decrypted_ecdsa:
                self.logger.error("Failed to decrypt ECDSA private key")
                return None

            return decrypted_ecdsa.decode('utf-8')
        except Exception as e:
            self.logger.error(f"Failed to get ECDSA private key: {e}")
            return None

    def clear_ecdh_key(self, username: str) -> bool:
        """Clears the ECDH key from storage."""
        if not username:
            self.logger.error("Username is empty")
            return False

        try:
            keyring.delete_password(self.ECDH_KEY_SERVICE, username)
            return True
        except Exception as e:
            self.logger.error(f"Failed to clear ECDH key: {e}")
            return False

    def clear_storage(self, username: str) -> bool:
        """Clears all user keys from storage."""
        if not username:
            self.logger.error("Username is empty")
            return False

        try:
            success = True
            for service in [self.MASTER_KEY_SERVICE, self.ECDH_KEY_SERVICE, self.ECDSA_KEY_SERVICE]:
                try:
                    keyring.delete_password(service, username)
                except KeyringError:
                    success = False
                    self.logger.warning(f"Failed to delete password for service: {service}")
            return success
        except Exception as e:
            self.logger.error(f"Failed to clear storage: {e}")
            return False