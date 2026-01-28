import logging
from typing import Tuple, Optional
from src.exceptions import *
from dishka import make_async_container, FromDishka, AsyncContainer

from src.providers import AppProvider
from src.presentation.pages import AppState

from src.adapters.api.service import AuthHTTPService

from src.adapters.database.service import LocalUserService
from src.adapters.database.dto import LocalUserRequestDTO, LocalUserDTO

from src.adapters.encryption.storage import EncryptedKeyStorage
from src.adapters.encryption.dao import AbstractPasswordHasher


class AuthManager:
    def __init__(self, app_state: AppState, container: AsyncContainer):
        self._state = app_state
        self._container = container
        self._logger = logging.getLogger(__name__)

    async def authenticate_user(self, username: str, password: str) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                if not username or not password:
                    return False, "Username and password are required"


                # Check if the user exists in the local database
                local_user = await local_user_service.get_user_data(
                    LocalUserRequestDTO(
                        username=username,
                    )
                )

                if local_user is None:
                    self._logger.info(f"No local user found, proceeding with registration: {username}")
                    return await self._register_new_user(username, password)
                else:
                    self._logger.info(f"Local user found, proceeding with login: {username}")
                    return await self._login_existing_user(username, password, local_user)

        except Exception as e:
            error_msg = f"Authentication error: {str(e)}"
            self._logger.error(error_msg)
        return False, error_msg

    async def _register_new_user(self, username: str, password: str) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                auth_http_service = await request_container.get(AuthHTTPService)
                key_storage = await request_container.get(EncryptedKeyStorage)
                password_hasher = await request_container.get(AbstractPasswordHasher)

                self._logger.info(f"Starting registration for user: {username}")

                # 1. Register on the server
                register_data = await auth_http_service.register(username=username)

                # Checking registration data
                if not register_data or register_data["username"] != username:
                    return False, "Registration failed - invalid response from server"

                ecdh_private_key = register_data["ecdh_private_key"]
                ecdsa_private_key = register_data["ecdsa_private_key"]

                if not ecdh_private_key or not ecdsa_private_key:
                    return False, "Registration failed - missing private keys"

                # 2. Saving keys in a secure storage
                if not await key_storage.register_master_key(username=username, password=password):
                    return False, "Failed to register master key"

                if not await key_storage.store_ecdsa_private_key(
                        username=username,
                        private_key_pem=ecdsa_private_key,
                        password=password
                ):
                    return False, "Failed to store ECDSA private key"

                if not await key_storage.store_ecdh_private_key(
                        username=username,
                        ecdh_private_key=ecdh_private_key,
                        password=password
                ):
                    return False, "Failed to store ECDH private key"

                # 3. Login to the server
                login_data = await auth_http_service.login(
                    username=username,
                    ecdsa_private_key=ecdsa_private_key
                )

                if not login_data or not login_data["access_token"]:
                    return False, "Login after registration failed"

                data = await auth_http_service.get_current_user_info()

                # 5. Saving to a local database
                hashed_password = await password_hasher.hashing(password)

                await local_user_service.add_user(
                    LocalUserRequestDTO(
                        server_user_id=data["id"],
                        ecdsa_public_key=data["ecdsa_public_key"],
                        username=username,
                        hashed_password=hashed_password
                    )
                )

                master_key = await key_storage.get_master_key(username=username, password=password)

                local_user = await local_user_service.get_user_data(
                    LocalUserRequestDTO(
                        username=username,
                    )
                )

                # 6. Status Update
                self._state.update_from_login(
                    username=username,
                    local_user_id=local_user.id,
                    server_user_id=data["id"],
                    password=password,
                    master_key=master_key,
                    ecdsa_public_key=data["ecdsa_public_key"],
                    ecdsa_private_key=ecdsa_private_key,
                    ecdh_public_key=None,
                    ecdh_private_key=ecdh_private_key,
                    token=login_data["access_token"],
                )

                self._logger.info(f"Registration successful for user: {username}")
                return True, "Registration successful"

        except UserAlreadyExistsError:
            error_msg = "User already exists on server"
            self._logger.warning(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Registration failed: {str(e)}"
            self._logger.error(error_msg)
            return False, error_msg

    async def _login_existing_user(self, username: str, password: str, local_user) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)
                password_hasher = await request_container.get(AbstractPasswordHasher)
                key_storage = await request_container.get(EncryptedKeyStorage)

                self._logger.info(f"Attempting login for user: {username}")


                # 1. Password verification
                password_valid = await password_hasher.compare(password, local_user.hashed_password)
                if not password_valid:
                    return False, "Invalid password"

                if local_user.username != username:
                    return False, "Username does not match local user"

                # 2. Getting private keys from storage
                ecdsa_private_key = await key_storage.get_ecdsa_private_key(username, password)
                if not ecdsa_private_key:
                    return False, "Failed to retrieve private keys - invalid password or corrupted data"

                # 3. Login to the server
                login_data = await auth_http_service.login(
                    username=username,
                    ecdsa_private_key=ecdsa_private_key
                )

                if not login_data or not login_data["access_token"]:
                    return False, "Server login failed"

                data = await auth_http_service.get_current_user_info()

                # 4. Obtaining an ECDH key for the messenger
                ecdh_private_key = await key_storage.get_ecdh_private_key(username, password)
                if not ecdh_private_key:
                    self._logger.warning("ECDH private key not found, but login successful")

                master_key = await key_storage.get_master_key(username=username, password=password)

                # 5. Status update
                self._state.update_from_login(
                    username=username,
                    local_user_id=local_user.id,
                    server_user_id=data["id"],
                    password=password,
                    master_key=master_key,
                    ecdsa_public_key=data["ecdsa_public_key"],
                    ecdsa_private_key=ecdsa_private_key,
                    ecdh_public_key=None,
                    ecdh_private_key=ecdh_private_key,
                    token=login_data["access_token"],
                )

                self._logger.info(f"Login successful for user: {username}")
                return True, "Login successful"

        except AuthenticationError:
            error_msg = "Authentication failed - invalid credentials"
            self._logger.warning(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Login failed: {str(e)}"
            self._logger.error(error_msg)
            return False, error_msg

    async def logout(self) -> bool:
        try:
            async with self._container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)

                if auth_http_service and self._state.is_authenticated:
                    await auth_http_service.logout()

                self._state.clear()
                self._logger.info("User logged out successfully")
                return True

        except Exception as e:
            self._logger.warning(f"Logout error: {e}")
            self._state.clear()
            return False