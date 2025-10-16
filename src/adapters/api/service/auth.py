from typing import Dict, Any
import logging
import asyncio
from datetime import datetime

from ..dao.auth import AuthHTTPDAO
from src.adapters.encryption.service import AbstractECDSASignature, AbstractECDHCipher
from src.exceptions import *


class AuthHTTPService:
    def __init__(
            self,
            auth_dao: AuthHTTPDAO,
            ecdsa_signer: AbstractECDSASignature,
            ecdh_cipher: AbstractECDHCipher,
            logger: logging.Logger = None
    ):
        self._auth_dao = auth_dao
        self._ecdsa_signer = ecdsa_signer
        self._ecdh_cipher = ecdh_cipher
        self._logger = logger or logging.getLogger(__name__)

        self._current_token: str | None = None
        self._current_user: dict[str, Any] | None = None
        self._is_authenticated: bool = False

    async def register(self, username: str) -> dict[str, Any]:
        """
        User registration
        :param username:
        :return:
        """
        self._logger.info(f"Starting registration for user: {username}")

        try:
            # Generating new keys
            ecdsa_private, ecdsa_public = await self._ecdsa_signer.generate_key_pair()
            ecdh_private, ecdh_public = await self._ecdh_cipher.generate_key_pair()

            # Registering user on server
            result = await self._auth_dao.register_user(username, ecdsa_public, ecdh_public)

            self._logger.info(f"Successfully registered user: {username} with ID: {result['id']}")

            return {
                **result,
                "ecdsa_private_key": ecdsa_private,
                "ecdh_private_key": ecdh_private
            }
        except KeyGenerationError as e:
            self._logger.error(f"Key generation failed: {e}")
            raise
        except APIError as e:
            if e.status_code == 400 and "already exists" in str(e.response_data):
                raise UserAlreadyExistsError(f"User {username} already exists") from e
            raise
        except Exception as e:
            self._logger.error(f"Registration failed: {e}")
            raise InfrastructureError("Registration failed", original_error=e) from e

    async def login(self, username: str, ecdsa_private_key: str) -> dict[str, Any]:
        """
        User authentication
        :param username:
        :param ecdsa_private_key:
        :return:
        """
        self._logger.info(f"Attempting login for user: {username}")

        try:
            # Get challenge from server
            challenge_data = await self._auth_dao.get_challenge(username)
            challenge = challenge_data["challenge"]

            # Sign challenge with user's private key
            signature = await self._ecdsa_signer.sign_message(ecdsa_private_key, challenge)

            # Authenticate
            result = await self._auth_dao.login(username, signature)

            # Save the token after successful login
            self._current_token = result["access_token"]
            self._is_authenticated = True

            # Get user info
            self._current_user = await self._auth_dao.get_current_user()

            self._logger.info(f"Successfully logged in as: {username}")
            return result

        except APIError as e:
            self._logger.error(f"Login failed for {username}: {e}")
            self._clear_session()
            raise AuthenticationError(f"Login failed: {e}")
        except Exception as e:
            self._logger.error(f"Unexpected error during login: {e}")
            self._clear_session()
            raise

    async def logout(self) -> dict[str, Any]:
        """
        Logout from the session
        :return:
        """
        if not self._is_authenticated:
            self._logger.warning("Attempted logout without active session")
            return {"status": "no active session"}

        try:
            result = await self._auth_dao.logout()
            self._logger.info("Successfully logged out")
            return result
        except Exception as e:
            self._logger.warning(f"Logout API call failed: {e}")
            return {"status": "logged out locally"}
        finally:
            self._clear_session()

    async def get_current_user_info(self) -> dict[str, Any]:
        """
        Get information about the user
        :return:
        """
        if not self._is_authenticated:
            raise AuthenticationError("Not authenticated")

        try:
            self._current_user = await self._auth_dao.get_current_user()
            return self._current_user
        except APIError as e:
            if e.status_code == 401:
                self._logger.warning("Token expired during user info request")
                self._clear_session()
                raise AuthenticationError("Session expired")
            raise
        except Exception as e:
            self._logger.error(f"Error getting user info: {e}")
            raise

    async def get_public_keys(self, user_id: int) -> dict[str, Any]:
        """
        Getting public keys for a user
        :param user_id:
        :return:
        """
        if not self._is_authenticated:
            raise AuthenticationError("Not authenticated")

        self._logger.debug(f"Requesting public keys for user: {user_id}")

        try:
            return await self._auth_dao.get_public_keys(user_id)
        except APIError as e:
            if e.status_code == 401:
                self._logger.warning("Token expired during public keys request")
                self._clear_session()
                raise AuthenticationError("Session expired")
            raise
        except Exception as e:
            self._logger.error(f"Error getting public keys: {e}")
            raise

    async def update_keys(self) -> dict[str, Any]:
        """
        Update user's keys
        :return:
        """
        if not self._is_authenticated:
            raise AuthenticationError("Not authenticated")

        self._logger.info("Starting key rotation")

        try:
            # Generating new keys
            ecdsa_private, ecdsa_public = await self._ecdsa_signer.generate_key_pair()
            ecdh_private, ecdh_public = await self._ecdh_cipher.generate_key_pair()

            # Update keys on server
            await self._auth_dao.update_ecdsa_key(ecdsa_public)
            await self._auth_dao.update_ecdh_key(ecdh_public)

            self._logger.info("Successfully updated user keys")

            return {
                "ecdsa_private_key": ecdsa_private,
                "ecdh_private_key": ecdh_private
            }

        except APIError as e:
            if e.status_code == 401:
                self._logger.warning("Token expired during key update")
                self._clear_session()
                raise AuthenticationError("Session expired")
            self._logger.error(f"Key update failed: {e}")
            raise
        except Exception as e:
            self._logger.error(f"Unexpected error during key update: {e}")
            raise

    async def validate_session(self) -> bool:
        """
        Session validation
        :return:
        """
        if not self._is_authenticated or not self._current_token:
            return False

        try:
            await self._auth_dao.get_current_user()
            return True
        except APIError as e:
            if e.status_code == 401:
                self._logger.warning("Session validation failed: token expired")
                self._clear_session()
                return False
            return True
        except Exception:
            return True

    def get_session_status(self) -> dict[str, Any]:
        """
        Getting current session status
        :return:
        """
        return {
            "is_authenticated": self._is_authenticated,
            "has_token": self._current_token is not None,
            "current_user": self._current_user.get("username") if self._current_user else None,
            "user_id": self._current_user.get("id") if self._current_user else None
        }

    def set_token(self, token: str):
        """
        Manual token installation (for session recovery cases)
        :param token:
        :return:
        """
        self._current_token = token
        self._auth_dao.set_token(token)
        self._is_authenticated = True
        self._logger.info("Token set manually")

    def get_current_token(self) -> str:
        """
        Getting the current token
        :return:
        """
        return self._current_token

    def _clear_session(self):
        """
        Clearing session data
        :return:
        """
        self._current_token = None
        self._current_user = None
        self._is_authenticated = False
        self._auth_dao.clear_token()
        self._logger.debug("Session cleared")

    async def health_check(self) -> bool:
        """
        Checking the availability of the authentication service
        :return:
        """
        try:
            return await self._auth_dao.health_check()
        except Exception as e:
            self._logger.error(f"Health check failed: {e}")
            return False