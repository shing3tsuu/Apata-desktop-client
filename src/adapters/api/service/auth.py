import asyncio
import base64
import binascii
import inspect
import json
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from src.adapters.api.dto import AuthRegistrationResultDTO, AuthTokenResponseDTO
from src.adapters.encryption.service import EncryptionService
from src.exceptions import (
    APIError,
    AuthenticationError,
    CryptographyError,
    InfrastructureError,
    InvalidKeyError,
    KeyGenerationError,
    UserAlreadyExistsError,
    UserNotRegisteredError,
    NetworkError,
    ValidationError,
)

from ..dao.auth import AuthHTTPDAO
from ..dao.common import CommonHTTPClient

if TYPE_CHECKING:
    from src.providers.state import AppState

SessionExpiredCallback = Callable[[], Awaitable[None] | None]


class AuthHTTPService:
    def __init__(
        self,
        auth_dao: AuthHTTPDAO,
        encryption_service: EncryptionService,
        app_state: "AppState",
        http_client: CommonHTTPClient,
        logger: logging.Logger | None = None,
    ):
        self._auth_dao = auth_dao
        self._encryption_service = encryption_service
        self._app_state = app_state
        self._http_client = http_client
        self._logger = logger or logging.getLogger(__name__)
        self._current_token: str | None = None
        self._current_user: dict[str, Any] | None = None
        self._is_authenticated: bool = False
        self._rotation_lock = asyncio.Lock()
        self._session_expired_callback: SessionExpiredCallback | None = None

    @property
    def token(self):
        if self._current_token:
            return self._current_token
        else:
            raise AuthenticationError("No active session, please login")

    @token.setter
    def token(self, value: str) -> None:
        if not value:
            raise ValidationError("Token cannot be empty")
        self._apply_access_token(value)

    @token.deleter
    def token(self) -> None:
        old_user = self._current_user.get("username") if self._current_user else None
        self._clear_session()
        self._logger.info(f"Session cleared for user: {old_user}")

    def set_session_expired_callback(
        self,
        callback: SessionExpiredCallback,
    ) -> None:
        self._session_expired_callback = callback

    def get_session_status(self) -> dict[str, Any]:
        return {
            "is_authenticated": self._is_authenticated,
            "has_token": self._current_token is not None,
            "current_user": self._current_user.get("username")
            if self._current_user
            else None,
            "user_id": self._current_user.get("id") if self._current_user else None,
        }

    async def register(self, username: str) -> AuthRegistrationResultDTO:
        self._logger.info(f"Starting registration for: {username}")

        try:
            key_pairs = await self._encryption_service.generate_key_pairs()
            ecdh_signature = await self._encryption_service.sign_string(
                private_key_pem=key_pairs.ed_private_key,
                string=key_pairs.ecdh_public_key,
            )

            result = await self._auth_dao.register_user(
                username=username,
                ed_public_key=key_pairs.ed_public_key,
                ecdh_public_key=key_pairs.ecdh_public_key,
                ecdh_signature=ecdh_signature,
            )

            self._logger.info(f"User '{username}' registered successfully")

            return AuthRegistrationResultDTO(
                id=result.id,
                username=result.username,
                ed_private_key=key_pairs.ed_private_key,
                ecdh_private_key=key_pairs.ecdh_private_key,
            )

        except APIError as e:
            if e.status_code == 409:
                raise UserAlreadyExistsError(
                    f"Username '{username}' is already taken",
                    context={"username": username},
                )
            elif e.status_code == 400:
                raise ValidationError(
                    "Invalid registration data", context={"username": username}
                )
            else:
                raise

        except CryptographyError:
            raise KeyGenerationError("Failed to generate cryptographic keys")

        except NetworkError:
            raise InfrastructureError("Check your internet connection")

        except Exception as e:
            self._logger.error(
                f"Unexpected registration error for '{username}': {e}", exc_info=True
            )
            raise InfrastructureError("Registration failed due to technical issue")

    async def login(
        self,
        username: str,
        ed_private_key: str | None = None,
        ecdsa_private_key: str | None = None,
    ) -> AuthTokenResponseDTO:
        self._logger.info(f"Starting login for: {username}")
        private_key = ed_private_key or ecdsa_private_key

        if not username or not private_key:
            raise ValidationError("Username and private key required")

        try:
            challenge_data = await self._auth_dao.get_challenge(username)

            signature = await self._encryption_service.sign_string(
                private_key_pem=private_key,
                string=challenge_data.challenge,
            )

            result = await self._auth_dao.login(username, signature)

            self._apply_access_token(result.access_token)
            self._current_user = self._build_current_user_from_token(
                username=username,
                access_token=result.access_token,
            )

            self._logger.info(f"User '{username}' logged in successfully")
            return result

        except AuthenticationError:
            self._clear_session()
            raise

        except APIError as e:
            if e.status_code == 401:
                raise AuthenticationError("Invalid signature or credentials")
            elif e.status_code == 404:
                raise UserNotRegisteredError(f"User '{username}' not found")
            else:
                raise AuthenticationError(f"Login failed: {e.message}")

        except (InvalidKeyError, CryptographyError):
            raise AuthenticationError("Cryptographic operation failed")

        except Exception as e:
            self._logger.error(
                f"Unexpected login error for '{username}': {e}", exc_info=True
            )
            self._clear_session()
            raise InfrastructureError("Login failed due to technical issue")

    async def rotate_access_token(self, expired_token: str | None = None) -> str:
        async with self._rotation_lock:
            current_token = self._app_state.token or self._current_token
            if (
                expired_token is not None
                and current_token is not None
                and current_token != expired_token
            ):
                return current_token

            username = self._app_state.username
            ed_private_key = self._app_state.ed_private_key
            if username is None or ed_private_key is None:
                await self._invalidate_expired_session()
                raise AuthenticationError(
                    "Access token rotation requires a local ED25519 key"
                )

            try:
                result = await self.login(
                    username=username,
                    ed_private_key=ed_private_key,
                )
            except Exception:
                await self._invalidate_expired_session()
                raise

            self._http_client.replace_expired_auth_token(
                expired_token,
                result.access_token,
            )
            self._logger.info("Access token rotated successfully")
            return result.access_token

    async def logout(self) -> bool:
        token = self._current_token or self._app_state.token
        if token is None:
            self._logger.debug("No active session to logout")
            self._clear_session()
            return True

        username = (
            self._current_user.get("username") if self._current_user else "unknown"
        )
        self._logger.info(f"Logging out user: {username}")

        success = True

        try:
            await self._auth_dao.logout(token)
            self._logger.debug("Remote logout successful")
        except Exception as e:
            self._logger.warning(f"Remote logout failed (proceeding locally): {e}")
            success = False

        self._clear_session()
        return success

    async def get_current_user_info(self) -> dict[str, Any]:
        token = self._validate_session()
        if self._current_user is not None:
            return self._current_user

        try:
            user_info = await self._auth_dao.get_current_user(token)
            self._current_user = user_info
            return user_info

        except AuthenticationError:
            self._clear_session()
            raise

        except APIError as e:
            if e.status_code == 404:
                raise UserNotRegisteredError("User not found on server")
            else:
                raise InfrastructureError("Failed to fetch user info")

    async def get_public_keys(self, user_id: UUID | str) -> dict[str, Any]:
        token = self._validate_session()

        try:
            return await self._auth_dao.get_public_keys(user_id, token)

        except APIError as e:
            if e.status_code == 404:
                raise UserNotRegisteredError(f"User {user_id} not found")
            elif e.status_code == 403:
                raise AuthenticationError("Not authorized to access user keys")
            else:
                raise InfrastructureError("Failed to fetch public keys")

    async def update_ecdh_key(self, sender_ecdsa_private_key: str) -> tuple[str, str]:
        token = self._validate_session()

        self._logger.info("Updating ECDH key pair")

        try:
            key_pairs = await self._encryption_service.generate_key_pairs()
            ecdh_private = key_pairs.ecdh_private_key
            ecdh_public = key_pairs.ecdh_public_key

            signature = await self._encryption_service.sign_string(
                sender_ecdsa_private_key, ecdh_public
            )

            await self._auth_dao.update_ecdh_key(
                ecdh_public_key=ecdh_public,
                signature=signature,
                token=token,
            )

            self._logger.info("ECDH key updated successfully")
            return ecdh_private, ecdh_public

        except APIError as e:
            if e.status_code == 401:
                raise AuthenticationError("Session expired, please login again")
            else:
                raise InfrastructureError("Failed to update key on server")

        except (InvalidKeyError, CryptographyError):
            raise KeyGenerationError("Failed to generate new key pair")

    async def validate_session(self) -> bool:
        if not self._current_token:
            return False

        try:
            await self._auth_dao.get_current_user(self._current_token)
            return True
        except AuthenticationError:
            self._clear_session()
            return False
        except Exception:
            return True

    def _validate_session(self) -> str:
        if not self._is_authenticated or not self._current_token:
            raise AuthenticationError("No active session, please login")
        return self._current_token

    def _build_current_user_from_token(
        self, username: str, access_token: str
    ) -> dict[str, Any]:
        user: dict[str, Any] = {"username": username}
        user_id = self._extract_user_id_from_token(access_token)
        if user_id is not None:
            user["id"] = user_id
        return user

    @staticmethod
    def _extract_user_id_from_token(access_token: str) -> str | None:
        try:
            payload = access_token.split(".")[1]
            padded_payload = payload + "=" * (-len(payload) % 4)
            decoded = json.loads(
                base64.urlsafe_b64decode(padded_payload.encode()).decode()
            )
        except (
            IndexError,
            TypeError,
            ValueError,
            UnicodeDecodeError,
            binascii.Error,
        ):
            return None

        subject = decoded.get("sub")
        return str(subject) if subject is not None else None

    def _clear_session(self) -> None:
        self._current_token = None
        self._current_user = None
        self._is_authenticated = False
        self._http_client.clear_auth_token()
        if self._app_state.token is not None:
            del self._app_state.token

    def _apply_access_token(self, access_token: str) -> None:
        self._current_token = access_token
        self._is_authenticated = True
        self._app_state.token = access_token
        self._http_client.set_auth_token(access_token)
        self._logger.debug("Token set for session")

    async def _invalidate_expired_session(self) -> None:
        self._clear_session()
        self._app_state.clear_state()
        callback = self._session_expired_callback
        if callback is None:
            return
        result = callback()
        if inspect.isawaitable(result):
            await result
