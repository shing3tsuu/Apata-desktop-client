from typing import Dict, Any
import logging
from datetime import datetime

from ..dao.auth import AuthHTTPDAO
from src.adapters.encryption.service import AbstractECDSASignature, AbstractECDHCipher
from src.exceptions import *


class AuthHTTPService:
    __slots__ = (
        "_auth_dao",
        "_ecdsa_signer",
        "_ecdh_cipher",
        "_logger",
        "_current_token",
        "_current_user",
        "_is_authenticated",
        "__weakref__"
    )
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

    def set_token(self, token: str):
        """Set authentication token"""
        self._current_token = token
        self._is_authenticated = True

    def clear_token(self):
        """Clear authentication token"""
        self._current_token = None
        self._is_authenticated = False

    async def register(self, username: str) -> dict[str, Any]:
        context = {
            "username": username,
            "operation": "user_registration"
        }

        self._logger.info(
            "Starting user registration",
            extra={"context": context}
        )

        try:
            # Generate cryptographic keys
            ecdsa_private, ecdsa_public = await self._ecdsa_signer.generate_key_pair()
            ecdh_private, ecdh_public = await self._ecdh_cipher.generate_key_pair()

            # Register user on server
            result = await self._auth_dao.register_user(username, ecdsa_public, ecdh_public)

            self._logger.info(
                "User registration completed successfully",
                extra={"context": {**context, "status": "success"}}
            )

            return {
                **result,
                "ecdsa_private_key": ecdsa_private,
                "ecdh_private_key": ecdh_private
            }

        except UserAlreadyExistsError as e:
            self._logger.warning(
                f"Registration failed - user already exists: {str(e)}",
                extra={"context": context}
            )
            raise

        except ValidationError as e:
            self._logger.error(
                "Registration validation failed",
                extra={"context": {**context, "validation_error": str(e)}}
            )
            raise

        except CryptographyError as e:
            self._logger.error(
                "Cryptography error during key generation",
                extra={"context": context},
                exc_info=True
            )
            raise InfrastructureError(
                "Key generation failed during registration",
                original_error=e,
                context=context
            ) from e

        except Exception as e:
            self._logger.error(
                "Unexpected error during registration",
                extra={"context": context},
                exc_info=True
            )
            raise InfrastructureError(
                f"Registration process failed: {str(e)}",
                original_error=e,
                context=context
            ) from e

    async def login(self, username: str, ecdsa_private_key: str) -> dict[str, Any]:
        context = {
            "username": username,
            "operation": "user_login"
        }

        self._logger.info(
            "Starting login process",
            extra={"context": context}
        )

        try:
            # Get challenge from server
            challenge_data = await self._auth_dao.get_challenge(username)
            challenge = challenge_data["challenge"]

            # Sign challenge with user's private key
            signature = await self._ecdsa_signer.sign_message(ecdsa_private_key, challenge)

            # Authenticate with signature
            result = await self._auth_dao.login(username, signature)

            # Save session state
            self._current_token = result["access_token"]
            self._is_authenticated = True

            # Get user info to complete login
            self._current_user = await self._auth_dao.get_current_user(token=self._current_token)

            self._logger.info(
                "Login completed successfully",
                extra={"context": {**context, "status": "success", "user_id": self._current_user.get("id")}}
            )

            return result

        except UserNotRegisteredError as e:
            self._logger.warning(
                f"Login failed - user not registered: {str(e)}",
                extra={"context": context}
            )
            self._clear_session()
            raise

        except AuthenticationError as e:
            self._logger.warning(
                f"Login failed - authentication failed: {str(e)}",
                extra={"context": context}
            )
            self._clear_session()
            raise

        except ValueError and AttributeError as e:
            self._logger.error(
                "Cryptography error during login signature",
                extra={"context": context},
                exc_info=True
            )
            self._clear_session()
            raise CryptographyError(
                f"Cryptography error during login signature: {str(e)}",
                original_error=e,
                context=context
            ) from e

        except APIError as e:
            self._logger.error(
                f"Login API error: {e.message}",
                extra={"context": {**context, "status_code": e.status_code}}
            )
            self._clear_session()
            raise AuthenticationError(
                f"Login failed: {e.message}",
                original_error=e,
                context=context
            ) from e

        except Exception as e:
            self._logger.error(
                "Unexpected error during login",
                extra={"context": context},
                exc_info=True
            )
            self._clear_session()
            raise InfrastructureError(
                f"Login process failed: {str(e)}",
                original_error=e,
                context=context
            ) from e

    async def logout(self) -> dict[str, Any]:
        context = {"operation": "user_logout"}

        if not self._is_authenticated:
            self._logger.debug(
                "Logout called without active session",
                extra={"context": context}
            )
            return {"status": "no_active_session"}

        context.update({
            "username": self._current_user.get("username") if self._current_user else None,
            "user_id": self._current_user.get("id") if self._current_user else None
        })

        self._logger.info(
            "Starting logout process",
            extra={"context": context}
        )

        try:
            result = await self._auth_dao.logout(token=self._current_token)

            self._logger.info(
                "Logout completed successfully",
                extra={"context": {**context, "status": "success"}}
            )
            return result

        except APIError as e:
            self._logger.warning(
                "Logout API call failed, but session will be cleared locally",
                extra={"context": {**context, "error": str(e)}}
            )
            return {"status": "logged_out_locally"}

        except Exception as e:
            self._logger.error(
                f"Unexpected error during logout: {str(e)}",
                extra={"context": context},
                exc_info=True
            )
            return {"status": "logged_out_locally"}
        finally:
            self._clear_session()

    async def get_current_user_info(self) -> dict[str, Any]:
        context = {"operation": "get_current_user_info"}

        if not self._is_authenticated:
            raise AuthenticationError(
                "No active session",
                context=context
            )

        self._logger.debug(
            "Fetching current user info",
            extra={"context": context}
        )

        try:
            self._current_user = await self._auth_dao.get_current_user(token=self._current_token)

            self._logger.debug(
                "Current user info retrieved successfully",
                extra={"context": {**context, "status": "success"}}
            )
            return self._current_user

        except AuthenticationError as e:
            self._logger.warning(
                f"Session expired while fetching user info: {str(e)}",
                extra={"context": context}
            )
            self._clear_session()
            raise

        except APIError as e:
            self._logger.error(
                f"Get user info API error: {e.message}",
                extra={"context": {**context, "status_code": e.status_code}}
            )
            raise InfrastructureError(
                f"Failed to get user info: {e.message}",
                original_error=e,
                context=context
            ) from e

        except Exception as e:
            self._logger.error(
                "Unexpected error fetching current user info",
                extra={"context": context},
                exc_info=True
            )
            raise InfrastructureError(
                f"Failed to get user info: {str(e)}",
                original_error=e,
                context=context
            ) from e

    async def get_public_keys(self, user_id: int) -> dict[str, Any]:
        context = {
            "operation": "get_public_keys",
            "target_user_id": user_id
        }

        if not self._is_authenticated:
            raise AuthenticationError(
                "Authentication required",
                context=context
            )

        self._logger.debug(
            f"Fetching public keys for user {user_id}",
            extra={"context": context}
        )

        try:
            result = await self._auth_dao.get_public_keys(user_id, token=self._current_token)

            self._logger.debug(
                "Public keys retrieved successfully",
                extra={"context": {**context, "status": "success"}}
            )
            return result

        except UserNotRegisteredError as e:
            self._logger.warning(
                f"Public keys not found for user {user_id}: {str(e)}",
                extra={"context": context}
            )
            raise

        except AuthenticationError as e:
            self._logger.warning(
                f"Authentication failed while fetching public keys: {str(e)}",
                extra={"context": context}
            )
            self._clear_session()
            raise

        except APIError as e:
            self._logger.error(
                f"Get public keys API error: {e.message}",
                extra={"context": {**context, "status_code": e.status_code}}
            )
            raise InfrastructureError(
                f"Failed to get public keys: {e.message}",
                original_error=e,
                context=context
            ) from e

        except Exception as e:
            self._logger.error(
                "Unexpected error fetching public keys",
                extra={"context": context},
                exc_info=True
            )
            raise InfrastructureError(
                f"Failed to get public keys: {str(e)}",
                original_error=e,
                context=context
            ) from e

    async def update_ecdh_key(self) -> tuple[str, str]:
        context = {"operation": "update_ecdh_key"}

        if not self._is_authenticated:
            raise AuthenticationError(
                "Authentication required for key update",
                context=context
            )

        self._logger.info(
            "Starting ECDH key update",
            extra={"context": context}
        )

        try:
            # Generate new key pair
            ecdh_private, ecdh_public = await self._ecdh_cipher.generate_key_pair()

            # Update key on server
            await self._auth_dao.update_ecdh_key(ecdh_public, token=self._current_token)

            self._logger.info(
                "ECDH key updated successfully",
                extra={"context": {**context, "status": "success"}}
            )

            return ecdh_private, ecdh_public

        except AuthenticationError as e:
            self._logger.warning(
                f"Authentication failed during key update: {str(e)}",
                extra={"context": context}
            )
            self._clear_session()
            raise

        except CryptographyError as e:
            self._logger.error(
                "Cryptography error during key generation",
                extra={"context": context},
                exc_info=True
            )
            raise InfrastructureError(
                "Key generation failed",
                original_error=e,
                context=context
            ) from e

        except APIError as e:
            self._logger.error(
                f"Key update API error: {e.message}",
                extra={"context": {**context, "status_code": e.status_code}}
            )
            raise InfrastructureError(
                f"Key update failed: {e.message}",
                original_error=e,
                context=context
            ) from e

        except Exception as e:
            self._logger.error(
                "Unexpected error during key update",
                extra={"context": context},
                exc_info=True
            )
            raise InfrastructureError(
                f"Key update failed: {str(e)}",
                original_error=e,
                context=context
            ) from e

    async def validate_session(self) -> bool:
        context = {"operation": "validate_session"}

        if not self._current_token:
            self._logger.warning(
                "Session validation failed - no token",
                extra={"context": context}
            )
            return False

        try:
            await self._auth_dao.get_current_user(token=self._current_token)

            self._logger.debug(
                "Session validation successful",
                extra={"context": context}
            )
            return True

        except AuthenticationError:
            self._logger.warning(
                "Session validation failed - token expired",
                extra={"context": context}
            )
            self._clear_session()
            return False

        except Exception as e:
            self._logger.warning(
                "Session validation failed with unexpected error",
                extra={"context": {**context, "error": str(e)}}
            )
            # Don't clear session on unexpected errors - might be temporary
            return True

    def get_session_status(self) -> dict[str, Any]:
        status = {
            "is_authenticated": self._is_authenticated,
            "has_token": self._current_token is not None,
            "current_user": self._current_user.get("username") if self._current_user else None,
            "user_id": self._current_user.get("id") if self._current_user else None,
            "timestamp": datetime.utcnow().isoformat()
        }

        self._logger.debug(
            "Session status retrieved",
            extra={"context": {"operation": "get_session_status", "status": status}}
        )

        return status

    def _clear_session(self):
        """Clear current session"""
        old_user = self._current_user.get("username") if self._current_user else None

        self._current_token = None
        self._current_user = None
        self._is_authenticated = False

        self._logger.info(
            "Session cleared",
            extra={"context": {
                "operation": "clear_session",
                "previous_user": old_user
            }}
        )

    async def health_check(self) -> bool:
        context = {"operation": "health_check"}

        try:
            result = await self._auth_dao.health_check()

            self._logger.debug(
                f"Health check completed: {result}",
                extra={"context": context}
            )
            return result

        except Exception as e:
            self._logger.error(
                f"Health check failed: {str(e)}",
                extra={"context": context},
                exc_info=True
            )
            return False