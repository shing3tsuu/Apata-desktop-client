import base64
import logging

import keyring
from cryptography.exceptions import InvalidTag
from keyring.errors import KeyringError

from src.adapters.encryption.service import KeyManager


class EncryptedKeyStorage:
    def __init__(self, key_manager: KeyManager, logger: logging.Logger | None = None):
        self.key_manager = key_manager
        self.logger = logger or logging.getLogger(__name__)

        # Constants for naming keys in keyring
        self.MASTER_KEY_SERVICE = "apata_messenger_master_key"
        self.ECDH_KEY_SERVICE = "apata_messenger_ecdh_key"
        self.ED_KEY_SERVICE = "apata_messenger_ed_key"

    def is_master_key_registered(self, username: str) -> bool:
        try:
            encrypted_data = keyring.get_password(self.MASTER_KEY_SERVICE, username)
            return encrypted_data is not None and len(encrypted_data) > 0
        except KeyringError as e:
            self.logger.error(f"Keyring error: {e}")
            return False

    async def register_master_key(self, username: str, password: str) -> bool:
        if not username or not password:
            self.logger.error("Username or password is empty")
            return False

        if self.is_master_key_registered(username):
            self.logger.warning("Master key already registered")
            return False

        try:
            master_key = await self.key_manager.generate_master_key()
            if not master_key:
                self.logger.error("Failed to generate master key")
                return False

            result = await self.key_manager.encrypt_master_key(master_key, password)
            if not result:
                self.logger.error("Failed to encrypt master key")
                return False

            encrypted_master_key, salt = result
            if encrypted_master_key is None or salt is None:
                self.logger.error("Failed to encrypt master key")
                return False

            combined_data = base64.b64encode(salt + encrypted_master_key).decode(
                "utf-8"
            )
            keyring.set_password(self.MASTER_KEY_SERVICE, username, combined_data)

            self.logger.info(f"Master key registered for user: {username}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to register master key: {e}")
            return False

    async def get_master_key(self, username: str, password: str) -> bytes | None:
        if not username or not password:
            self.logger.error("Username or password is empty")
            return None

        try:
            combined_data = keyring.get_password(self.MASTER_KEY_SERVICE, username)
            if not combined_data:
                self.logger.error("No master key found in keyring")
                return None

            decoded_data = base64.b64decode(combined_data)
            if len(decoded_data) < 16:
                self.logger.error("Invalid combined data length")
                return None

            salt = decoded_data[:16]
            encrypted_master_key = decoded_data[16:]

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

    async def store_ecdh_private_key(
        self, username: str, ecdh_private_key: str, password: str
    ) -> bool:
        if not username or not ecdh_private_key or not password:
            self.logger.error("Missing required parameters for storing ECDH key")
            return False

        try:
            master_key = await self.get_master_key(username, password)
            if not master_key:
                self.logger.error("Failed to get master key for ECDH storage")
                return False

            encrypted_ecdh = await self.key_manager.encrypt_with_master_key(
                ecdh_private_key.encode("utf-8"), master_key
            )

            if not encrypted_ecdh:
                self.logger.error("Failed to encrypt ECDH private key")
                return False

            keyring.set_password(
                self.ECDH_KEY_SERVICE,
                username,
                base64.b64encode(encrypted_ecdh).decode("utf-8"),
            )

            self.logger.info(f"ECDH private key stored for user: {username}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store ECDH private key: {e}")
            return False

    async def store_ed_private_key(
        self, username: str, password: str, private_key_pem: str
    ) -> bool:
        if not username or not private_key_pem or not password:
            self.logger.error("Missing required parameters for storing ED key")
            return False

        try:
            master_key = await self.get_master_key(username, password)
            if not master_key:
                self.logger.error("Failed to get master key for ED storage")
                return False

            encrypted_ed = await self.key_manager.encrypt_with_master_key(
                private_key_pem.encode("utf-8"), master_key
            )

            if not encrypted_ed:
                self.logger.error("Failed to encrypt ED private key")
                return False

            keyring.set_password(
                self.ED_KEY_SERVICE,
                username,
                base64.b64encode(encrypted_ed).decode("utf-8"),
            )

            self.logger.info(f"ED private key stored for user: {username}")
            return True
        except Exception as e:
            self.logger.error(f"Failed to store ED private key: {e}")
            return False

    async def get_ecdh_private_key(self, username: str, password: str) -> str | None:
        if not username or not password:
            self.logger.error("Username or password is empty")
            return None

        try:
            master_key = await self.get_master_key(username, password)
            if not master_key:
                self.logger.error("Failed to get master key for ECDH retrieval")
                return None

            encrypted_ecdh = keyring.get_password(self.ECDH_KEY_SERVICE, username)
            if not encrypted_ecdh:
                self.logger.error("No ECDH key found in keyring")
                return None

            decrypted_ecdh = await self.key_manager.decrypt_with_master_key(
                base64.b64decode(encrypted_ecdh), master_key
            )

            if not decrypted_ecdh:
                self.logger.error("Failed to decrypt ECDH private key")
                return None

            return decrypted_ecdh.decode("utf-8")
        except Exception as e:
            self.logger.error(f"Failed to get ECDH private key: {e}")
            return None

    async def get_ed_private_key(self, username: str, password: str) -> str | None:
        if not username or not password:
            self.logger.error("Username or password is empty")
            return None

        try:
            master_key = await self.get_master_key(username, password)
            if not master_key:
                self.logger.error("Failed to get master key for ED retrieval")
                return None

            encrypted_ed = keyring.get_password(self.ED_KEY_SERVICE, username)
            if not encrypted_ed:
                self.logger.error("No ED key found in keyring")
                return None

            decrypted_ecdsa = await self.key_manager.decrypt_with_master_key(
                base64.b64decode(encrypted_ed), master_key
            )

            if not decrypted_ecdsa:
                self.logger.error("Failed to decrypt ED private key")
                return None

            return decrypted_ecdsa.decode("utf-8")
        except Exception as e:
            self.logger.error(f"Failed to get ED private key: {e}")
            return None

    def clear_ecdh_private_key(self, username: str) -> bool:
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
        if not username:
            self.logger.error("Username is empty")
            return False

        try:
            success = True
            for service in [
                self.MASTER_KEY_SERVICE,
                self.ECDH_KEY_SERVICE,
                self.ED_KEY_SERVICE,
            ]:
                try:
                    keyring.delete_password(service, username)
                except KeyringError:
                    success = False
                    self.logger.warning(
                        f"Failed to delete password for service: {service}"
                    )
            return success
        except Exception as e:
            self.logger.error(f"Failed to clear storage: {e}")
            return False
