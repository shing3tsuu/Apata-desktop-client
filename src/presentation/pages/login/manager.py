import logging
from typing import Tuple, Optional
from src.exceptions import *
from dishka import make_async_container, FromDishka

from src.providers import AppProvider
from src.presentation.pages import AppState, Container

from src.adapters.api.service import AuthHTTPService

from src.adapters.database.service import LocalUserService
from src.adapters.database.dto import LocalUserRequestDTO, LocalUserDTO

from src.adapters.encryption.storage import EncryptedKeyStorage
from src.adapters.encryption.service import AbstractPasswordHasher


class AuthManager(Container):
    async def authenticate_user(
            self,
            username: str,
            password: str,
    ) -> tuple[bool, str]:
        """
        Universal authentication with improved error handling
        - Checks if the user exists in the local database, if not, registers them
        :param username:
        :param password:
        :return:
        """
        if not username or not password:
            return False, "Username and password are required"

        try:
            # Check if the user exists in the local database
            local_user = await self.state.local_user_service.get_user_data(
                LocalUserRequestDTO(
                    username=username,
                )
            )

            if local_user is None:
                self.logger.info(f"No local user found, proceeding with registration: {username}")
                return await self._register_new_user(username, password)
            else:
                self.logger.info(f"Local user found, proceeding with login: {username}")
                return await self._login_existing_user(username, password, local_user)

        except Exception as e:
            error_msg = f"Authentication error: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    async def _register_new_user(self, username: str, password: str) -> Tuple[bool, str]:
        """
        New user registration with checks
        - Checks if the user already exists on the server
        - Registers the user on the server
        - Saves keys securely
        - Logs in the user
        - Saves user data to the local database
        - Updates the application state
        - Returns success or failure
        :param username:
        :param password:
        :return:
        """
        self.logger.info(f"Starting registration for user: {username}")

        try:
            # 1. Register on the server
            register_data = await self.state.auth_http_service.register(username=username)

            # Checking registration data
            if not register_data or register_data["username"] != username:
                return False, "Registration failed - invalid response from server"

            ecdh_private_key = register_data["ecdh_private_key"]
            ecdsa_private_key = register_data["ecdsa_private_key"]

            if not ecdh_private_key or not ecdsa_private_key:
                return False, "Registration failed - missing private keys"

            # 2. Saving keys in a secure storage
            if not await self.state.key_storage.register_master_key(username=username, password=password):
                return False, "Failed to register master key"

            if not await self.state.key_storage.store_ecdsa_private_key(
                    username=username,
                    private_key_pem=ecdsa_private_key,
                    password=password
            ):
                return False, "Failed to store ECDSA private key"

            if not await self.state.key_storage.store_ecdh_private_key(
                    username=username,
                    ecdh_private_key=ecdh_private_key,
                    password=password
            ):
                return False, "Failed to store ECDH private key"

            # 3. Login to the server
            login_data = await self.state.auth_http_service.login(
                username=username,
                ecdsa_private_key=ecdsa_private_key
            )

            if not login_data or not login_data["access_token"]:
                return False, "Login after registration failed"

            data = await self.state.auth_http_service.get_current_user_info()

            # 5. Saving to a local database
            hashed_password = await self.state.password_hasher.hashing(password)

            await self.state.local_user_service.add_user(
                LocalUserRequestDTO(
                    server_user_id=data["id"],
                    username=username,
                    hashed_password=hashed_password
                )
            )

            master_key = await self.state.key_storage.get_master_key(username=username, password=password)

            local_user = await self.state.local_user_service.get_user_data(
                LocalUserRequestDTO(
                    username=username,
                )
            )

            # 6. Status Update
            self.state.update_from_login(
                username=username,
                local_user_id=local_user.id,
                server_user_id=data["id"],
                password=password,
                master_key=master_key,
                ecdsa_private_key=ecdsa_private_key,
                ecdh_private_key=ecdh_private_key,
                token=login_data["access_token"],
            )

            self.logger.info(f"Registration successful for user: {username}")
            return True, "Registration successful"

        except UserAlreadyExistsError:
            error_msg = "User already exists on server"
            self.logger.warning(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Registration failed: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    async def _login_existing_user(self, username: str, password: str, local_user) -> tuple[bool, str]:
        """
        Login of an existing user with checks
        - Checks if the user exists in the local database
        - Logs in the user
        - Updates the application state
        - Returns success or failure
        :param username:
        :param password:
        :param local_user:
        :return:
        """
        self.logger.info(f"Attempting login for user: {username}")

        try:
            # 1. Password verification
            password_valid = await self.state.password_hasher.compare(password, local_user.hashed_password)
            if not password_valid:
                return False, "Invalid password"

            if local_user.username != username:
                return False, "Username does not match local user"

            # 2. Getting private keys from storage
            ecdsa_private_key = await self.state.key_storage.get_ecdsa_private_key(username, password)
            if not ecdsa_private_key:
                return False, "Failed to retrieve private keys - invalid password or corrupted data"

            # 3. Login to the server
            login_data = await self.state.auth_http_service.login(
                username=username,
                ecdsa_private_key=ecdsa_private_key
            )

            if not login_data or not login_data["access_token"]:
                return False, "Server login failed"

            data = await self.state.auth_http_service.get_current_user_info()

            # 4. Obtaining an ECDH key for the messenger
            ecdh_private_key = await self.state.key_storage.get_ecdh_private_key(username, password)
            if not ecdh_private_key:
                self.logger.warning("ECDH private key not found, but login successful")

            master_key = await self.state.key_storage.get_master_key(username=username, password=password)

            # 5. Status update
            self.state.update_from_login(
                username=username,
                local_user_id=local_user.id,
                server_user_id=data["id"],
                password=password,
                master_key=master_key,
                ecdsa_private_key=ecdsa_private_key,
                ecdh_private_key=ecdh_private_key,
                token=login_data["access_token"],
            )

            self.logger.info(f"Login successful for user: {username}")
            return True, "Login successful"

        except AuthenticationError:
            error_msg = "Authentication failed - invalid credentials"
            self.logger.warning(error_msg)
            return False, error_msg
        except Exception as e:
            error_msg = f"Login failed: {str(e)}"
            self.logger.error(error_msg)
            return False, error_msg

    async def logout(self) -> bool:
        """
        Logout with cleaning
        :return:
        """
        try:
            if self.state.auth_http_service and self.state.is_authenticated:
                await self.state.auth_http_service.logout()

            self.state.clear()
            self.logger.info("User logged out successfully")
            return True

        except Exception as e:
            self.logger.warning(f"Logout error: {e}")
            self.state.clear()
            return False