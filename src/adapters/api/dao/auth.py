from typing import Any
import logging
import asyncio

from .common import CommonHTTPClient
from src.exceptions import APIError, NetworkError


class AuthHTTPDAO:
    def __init__(self, http_client: CommonHTTPClient):
        self._http_client = http_client
        self._logger = logging.getLogger(__name__)
        self._current_token: str | None = None

    def set_token(self, token: str):
        """
        Set the current authentication token.
        """
        self._current_token = token
        self._http_client.set_auth_token(token)

    def clear_token(self):
        """
        Clear the current authentication token.
        """
        self._current_token = None
        self._http_client.clear_auth_token()

    def get_current_token(self) -> str:
        """
        Get the current authentication token.
        """
        return self._current_token

    async def register_user(self, username: str, ecdsa_public_key: str, ecdh_public_key: str) -> dict[str, Any]:
        """
        Register a new user.
        :param username:
        :param ecdsa_public_key:
        :param ecdh_public_key:
        :return:
        """
        data = {
            "username": username,
            "ecdsa_public_key": ecdsa_public_key,
            "ecdh_public_key": ecdh_public_key
        }

        self._logger.info(f"Registering new user: {username}")
        try:
            result = await self._http_client.post("/register", data)
            self._logger.info(f"Successfully registered user: {username}")
            return result
        except APIError as e:
            self._logger.error(f"Registration failed for {username}: {e}")
            raise
        except Exception as e:
            self._logger.error(f"Unexpected error during registration: {e}")
            raise

    async def get_challenge(self, username: str) -> dict[str, Any]:
        """
        Receiving a challenge for authentication
        :param username:
        :return:
        """
        self._logger.debug(f"Requesting challenge for user: {username}")
        try:
            result = await self._http_client.get(f"/challenge/{username}")
            return result
        except APIError as e:
            if e.status_code == 404:
                self._logger.warning(f"User not found: {username}")
            raise
        except Exception as e:
            self._logger.error(f"Error getting challenge for {username}: {e}")
            raise

    async def login(self, username: str, signature: str) -> dict[str, Any]:
        """
        Authentication for the user
        :param username:
        :param signature:
        :return:
        """
        data = {
            "username": username,
            "signature": signature
        }

        self._logger.info(f"Attempting login for user: {username}")
        try:
            result = await self._http_client.post("/login", data)

            # Save the token after successful login
            if "access_token" in result:
                self.set_token(result["access_token"])
                self._logger.info(f"Successfully logged in as: {username}")

            return result
        except APIError as e:
            self._logger.error(f"Login failed for {username}: {e}")
            raise
        except Exception as e:
            self._logger.error(f"Unexpected error during login: {e}")
            raise

    async def logout(self) -> dict[str, Any]:
        """
        Logout from the current session
        :return:
        """
        if not self._current_token:
            self._logger.warning("No active session to logout from")
            return {"status": "no active session"}

        try:
            result = await self._http_client.post("/logout", {})
            self.clear_token()
            self._logger.info("Successfully logged out")
            return result
        except APIError as e:
            self._logger.warning(f"Logout API call failed: {e}")
            self.clear_token()
            return {"status": "logged out locally"}
        except Exception as e:
            self._logger.error(f"Error during logout: {e}")
            self.clear_token()
            return {"status": "logged out locally"}

    async def get_current_user(self) -> dict[str, Any]:
        """
        Getting information about the current user
        :return:
        """
        if not self._current_token:
            raise ValueError("No authentication token available")

        self._logger.debug("Getting current user info")
        try:
            return await self._http_client.get("/me")
        except APIError as e:
            if e.status_code == 401:
                self._logger.warning("Token expired or invalid, clearing session")
                self.clear_token()
            raise
        except Exception as e:
            self._logger.error(f"Error getting current user: {e}")
            raise

    async def get_public_keys(self, user_id: int) -> dict[str, Any]:
        """
        Get user public keys
        :param user_id:
        :return:
        """
        if not self._current_token:
            raise ValueError("No authentication token available")

        self._logger.debug(f"Getting public keys for user: {user_id}")
        try:
            return await self._http_client.get(f"/public-keys/{user_id}")
        except APIError as e:
            if e.status_code == 404:
                self._logger.warning(f"Public keys not found for user: {user_id}")
            raise
        except Exception as e:
            self._logger.error(f"Error getting public keys: {e}")
            raise

    async def update_ecdsa_key(self, ecdsa_public_key: str) -> dict[str, Any]:
        """
        Updating the ECDSA public key
        :param ecdsa_public_key:
        :return:
        """
        if not self._current_token:
            raise ValueError("No authentication token available")

        data = {"ecdsa_public_key": ecdsa_public_key}
        self._logger.info("Updating ECDSA public key")

        try:
            result = await self._http_client.put("/ecdsa-update-key", data)
            self._logger.info("Successfully updated ECDSA public key")
            return result
        except Exception as e:
            self._logger.error(f"Error updating ECDSA key: {e}")
            raise

    async def update_ecdh_key(self, ecdh_public_key: str) -> dict[str, Any]:
        """
        Updating the ECDH public key
        :param ecdh_public_key:
        :return:
        """
        if not self._current_token:
            raise ValueError("No authentication token available")

        data = {"ecdh_public_key": ecdh_public_key}
        self._logger.info("Updating ECDH public key")

        try:
            result = await self._http_client.put("/ecdh-update-key", data)
            self._logger.info("Successfully updated ECDH public key")
            return result
        except Exception as e:
            self._logger.error(f"Error updating ECDH key: {e}")
            raise

    async def refresh_token(self) -> dict[str, Any]:
        """
        Refresh token (if API supports)
        :return:
        """
        if not self._current_token:
            raise ValueError("No authentication token available")

        self._logger.debug("Refreshing authentication token")
        try:
            result = await self._http_client.post("/refresh", {})
            if "access_token" in result:
                self.set_token(result["access_token"])
                self._logger.info("Token refreshed successfully")
            return result
        except APIError as e:
            if e.status_code == 401:
                self._logger.warning("Refresh token expired, clearing session")
                self.clear_token()
            raise
        except Exception as e:
            self._logger.error(f"Error refreshing token: {e}")
            raise

    async def validate_session(self) -> bool:
        """
        Checking the validity of the current session
        :return:
        """
        if not self._current_token:
            return False

        try:
            await self.get_current_user()
            return True
        except APIError as e:
            if e.status_code == 401:
                return False
            return True
        except Exception:
            return True

    def get_session_status(self) -> dict[str, Any]:
        """
        Getting the status of the current session
        :return:
        """
        return {
            "has_token": self._current_token is not None,
            "token_length": len(self._current_token) if self._current_token else 0
        }