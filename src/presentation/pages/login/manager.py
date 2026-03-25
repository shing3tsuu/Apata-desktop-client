import logging
from typing import Tuple, Optional
from dataclasses import dataclass

from dishka import make_async_container, FromDishka, AsyncContainer

from src.providers import AppProvider
from src.presentation.pages import AppState

from src.adapters.api.service import (
    AuthHTTPService,
    ContactHTTPService,
    MessageHTTPService,
)
from src.adapters.database.service import (
    LocalUserService,
    ContactService,
    MessageService,
)
from src.adapters.database.dto import (
    LocalUserRequestDTO,
    LocalUserDTO,
    UpdateLocalUserRequestDTO,
    ContactRequestDTO,
    ContactDTO,
    AddContactRequestDTO,
    MessageRequestDTO,
    MessageDTO,
)

from src.adapters.encryption.storage import EncryptedKeyStorage
from src.adapters.encryption.dao import AbstractPasswordHasher, Abstract256Cipher

from src.exceptions import *


class RegisterManager:
    def __init__(self, app_state: AppState, container: AsyncContainer):
        self._state = app_state
        self._container = container

        self.__register_data = None
        self.__login_data = None
        self.__current_data = None

        self.__ecdsa_private_key = None
        self.__ecdh_private_key = None

        self.__hashed_password = None

    async def check_local_user(self, username: str, password: str) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                if not username or not password:
                    return False, "USERNAME AND PASSWORD ARE REQUIRED"

                local_user = await local_user_service.get_user_data(
                    LocalUserRequestDTO(
                        username=username,
                    )
                )

                if local_user:
                    return False, "USER WITH THIS NAME ALREADY EXISTS"
                else:
                    return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    async def register_user_on_server(
        self, username: str, password: str
    ) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)

                register_data = await auth_http_service.register(username=username)

                if not register_data or register_data["username"] != username:
                    return False, "REGISTRATION FAILED - INVALID RESPONSE FROM SERVER"
                else:
                    self.__register_data = register_data
                    return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    async def contain_keys(self, username: str, password: str) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                key_storage = await request_container.get(EncryptedKeyStorage)

                ecdsa_private_key = self.__register_data["ecdsa_private_key"]
                ecdh_private_key = self.__register_data["ecdh_private_key"]

                if not ecdh_private_key or not ecdsa_private_key:
                    return False, "REGISTRATION FAILED - MISSING PRIVATE KEYS"

                self.__ecdsa_private_key = ecdsa_private_key
                self.__ecdh_private_key = ecdh_private_key

                if not await key_storage.register_master_key(
                    username=username, password=password
                ):
                    return False, "FAILED TO REGISTER MASTER KEY"

                if not await key_storage.store_ecdsa_private_key(
                    username=username,
                    private_key_pem=ecdsa_private_key,
                    password=password,
                ):
                    return False, "FAILED TO STORE ECDSA PRIVATE KEY"

                if not await key_storage.store_ecdh_private_key(
                    username=username,
                    ecdh_private_key=ecdh_private_key,
                    password=password,
                ):
                    return False, "FAILED TO STORE ECDH PRIVATE KEY"

                return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    async def login_new_user(self, username: str, password: str) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)

                login_data = await auth_http_service.login(
                    username=username, ecdsa_private_key=self.__ecdsa_private_key
                )

                if not login_data or not login_data["access_token"]:
                    return False, "LOGIN AFTER REGISTRATION FAILED"
                else:
                    self.__login_data = login_data
                    data = await auth_http_service.get_current_user_info()

                    if not data:
                        return (
                            False,
                            "GET CURRENT USER INFO FAILED - INVALID RESPONSE FROM SERVER",
                        )
                    else:
                        self.__current_data = data
                        return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    async def hashing_password(self, username: str, password: str) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                password_hasher = await request_container.get(AbstractPasswordHasher)

                hashed_password = await password_hasher.hashing(password)

                if not hashed_password:
                    return False, "HASHING PASSWORD FAILED"
                else:
                    self.__hashed_password = hashed_password
                    return True, "SUCCESS"

        except Exception as e:
            error_msg = f"FAILURE: {(str(e)).upper()}"
            return False, error_msg

    async def add_user_to_database(
        self, username: str, password: str
    ) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                local_user_service = await request_container.get(LocalUserService)

                user = await local_user_service.add_user(
                    LocalUserRequestDTO(
                        server_user_id=self.__current_data["id"],
                        ecdsa_public_key=self.__current_data["ecdsa_public_key"],
                        username=username,
                        hashed_password=self.__hashed_password,
                        timezone=None,
                    )
                )

                if not user:
                    return False, "ADD USER TO LOCAL DATABASE FAILED"
                else:
                    return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    async def update_state(self, username: str, password: str) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                key_storage = await request_container.get(EncryptedKeyStorage)

                master_key = await key_storage.get_master_key(
                    username=username, password=password
                )

                local_user = await local_user_service.get_user_data(
                    LocalUserRequestDTO(
                        username=username,
                    )
                )

                self._state.update_from_login(
                    username=username,
                    local_user_id=local_user.id,
                    server_user_id=self.__current_data["id"],
                    password=password,
                    master_key=master_key,
                    ecdsa_public_key=self.__current_data["ecdsa_public_key"],
                    ecdsa_private_key=self.__ecdsa_private_key,
                    ecdh_public_key=None,
                    ecdh_private_key=self.__ecdh_private_key,
                    token=self.__login_data["access_token"],
                )

                return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    """
    async def _register_new_user(self, username: str, password: str) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                auth_http_service = await request_container.get(AuthHTTPService)
                key_storage = await request_container.get(EncryptedKeyStorage)
                password_hasher = await request_container.get(AbstractPasswordHasher)
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
    """


class LoginManager:
    def __init__(self, app_state: AppState, container: AsyncContainer):
        self._state = app_state
        self._container = container

        self.__local_user = None
        self.__register_data = None
        self.__login_data = None
        self.__current_data = None

        self.__ecdsa_private_key = None
        self.__ecdh_private_key = None
        self.__master_key = None

        self.__hashed_password = None

    async def check_local_user(self, username: str, password: str) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                if not username or not password:
                    return False, "USERNAME AND PASSWORD ARE REQUIRED"

                local_user = await local_user_service.get_user_data(
                    LocalUserRequestDTO(
                        username=username,
                    )
                )

                if not local_user:
                    return False, "USER WITH THIS NAME NOT EXISTS"
                else:
                    self.__local_user = local_user
                    return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    async def compare_password(self, username: str, password: str) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                password_hasher = await request_container.get(AbstractPasswordHasher)

                password_valid = await password_hasher.compare(
                    password, self.__local_user.hashed_password
                )

                if not password_valid:
                    return False, "INVALID PASSWORD"
                else:
                    return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    async def get_ecdsa_private_key(
        self, username: str, password: str
    ) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                key_storage = await request_container.get(EncryptedKeyStorage)

                ecdsa_private_key = await key_storage.get_ecdsa_private_key(
                    username, password
                )
                if not ecdsa_private_key:
                    return (
                        False,
                        "FAILED TO RETRIEVE PRIVATE KEYS - INVALID PASSWORD OR CORRUPTED DATA",
                    )

                ecdh_private_key = await key_storage.get_ecdh_private_key(
                    username, password
                )
                if not ecdh_private_key:
                    return (
                        False,
                        "FAILED TO RETRIEVE PRIVATE KEYS - INVALID PASSWORD OR CORRUPTED DATA",
                    )

                master_key = await key_storage.get_master_key(
                    username=username, password=password
                )
                if not master_key:
                    return (
                        False,
                        "FAILED TO RETRIEVE PRIVATE KEYS - INVALID PASSWORD OR CORRUPTED DATA",
                    )

                self.__ecdsa_private_key = ecdsa_private_key
                self.__ecdh_private_key = ecdh_private_key
                self.__master_key = master_key

                return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    async def login_user(self, username: str, password: str) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)

                login_data = await auth_http_service.login(
                    username=username, ecdsa_private_key=self.__ecdsa_private_key
                )

                if not login_data or not login_data["access_token"]:
                    return False, "LOGIN FAILED - INVALID OR CORRUPTED DATA"
                else:
                    self.__login_data = login_data
                    data = await auth_http_service.get_current_user_info()

                    if not data:
                        return (
                            False,
                            "GET CURRENT USER INFO FAILED - INVALID RESPONSE FROM SERVER",
                        )
                    else:
                        self.__current_data = data
                        return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    async def update_state(self, username: str, password: str) -> tuple[bool, str]:
        try:
            self._state.update_from_login(
                username=username,
                local_user_id=self.__local_user.id,
                server_user_id=self.__current_data["id"],
                password=password,
                master_key=self.__master_key,
                ecdsa_public_key=self.__current_data["ecdsa_public_key"],
                ecdsa_private_key=self.__ecdsa_private_key,
                ecdh_public_key=None,
                ecdh_private_key=self.__ecdh_private_key,
                token=self.__login_data["access_token"],
            )

            return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    """
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
    """


class LoadingManager:
    def __init__(self, app_state: AppState, container: AsyncContainer):
        self._state = app_state
        self._container = container

    async def synchronize_contacts(self) -> bool:
        try:
            async with self._container() as request_container:
                contact_http_service = await request_container.get(ContactHTTPService)
                contact_http_service.set_token(self._state.token)
                local_user_service = await request_container.get(LocalUserService)
                contact_service = await request_container.get(ContactService)

                ecdsa_dict = {}

                local_contacts = await contact_service.get_contacts(
                    local_user_id=self._state.local_user_id
                )

                for contact in local_contacts:
                    if contact.ecdsa_public_key:
                        ecdsa_dict[contact.server_user_id] = contact.ecdsa_public_key

                # Get all contacts from server with complete information
                server_contacts = await contact_http_service.get_contacts(
                    local_user_id=self._state.local_user_id,
                    server_user_id=self._state.server_user_id,
                    ecdsa_dict=ecdsa_dict,
                )

                local_contact_map = {
                    contact.server_user_id: contact for contact in local_contacts
                }
                # Process each server contact
                for server_contact in server_contacts:
                    self._state.update_contacts(
                        Contact(
                            server_user_id=server_contact.server_user_id,
                            username=server_contact.username,
                            ecdh_public_key=server_contact.ecdh_public_key,
                            last_seen=server_contact.last_seen,
                            online=server_contact.online,
                            status=server_contact.status,
                        )
                    )
                    local_contact = local_contact_map.get(server_contact.server_user_id)
                    if local_contact:
                        # Update existing contact
                        await contact_service.update_contact(
                            ContactRequestDTO(
                                local_user_id=self._state.local_user_id,
                                server_user_id=server_contact.server_user_id,
                                username=server_contact.username,
                                ecdh_public_key=server_contact.ecdh_public_key,
                                status=server_contact.status,
                                last_seen=server_contact.last_seen,
                                online=server_contact.online,
                            )
                        )
                    else:
                        # Add new contact
                        await contact_service.add_contact(
                            AddContactRequestDTO(
                                local_user_id=self._state.local_user_id,
                                server_user_id=server_contact.server_user_id,
                                username=server_contact.username,
                                ecdsa_public_key=server_contact.ecdsa_public_key,
                                ecdh_public_key=server_contact.ecdh_public_key,
                                status=server_contact.status,
                                last_seen=server_contact.last_seen,
                                online=server_contact.online,
                            )
                        )

                # Remove local contacts that no longer exist on server (need to test)
                # server_contact_ids = {contact.server_user_id for contact in server_contacts}
                # for local_contact in local_contacts:
                #    if local_contact.server_user_id not in server_contact_ids:
                #        await contact_service.delete_contact(local_contact.id)
                #        self._logger.info(f"Removed local contact: {local_contact.username}")

                return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    async def sync_message_history(self) -> tuple[bool, str]:
        try:
            async with self._container() as request_container:
                message_http_service = await request_container.get(MessageHTTPService)
                message_http_service.set_token(self._state.token)
                contact_service = await request_container.get(ContactService)
                message_service = await request_container.get(MessageService)
                aes_cipher = await request_container.get(Abstract256Cipher)

                contacts = await contact_service.get_contacts(self._state.local_user_id)
                ecdsa_dict = {}

                for contact in contacts:
                    if contact.ecdsa_public_key:
                        ecdsa_dict[contact.server_user_id] = contact.ecdsa_public_key

                new_messages = await message_http_service.get_undelivered_messages(
                    ecdsa_dict=ecdsa_dict,
                    recipient_ecdh_private_key=self._state.ecdh_private_key,
                )

                if new_messages is [] or None:
                    return True, "No new messages to synchronize"

                for new_message in new_messages:
                    encrypted_message = await aes_cipher.encrypt(
                        new_message["decrypted_content"], self._state.master_key
                    )

                    await message_service.add_message(
                        MessageRequestDTO(
                            local_user_id=self._state.local_user_id,
                            server_message_id=new_message["id"],
                            contact_id=new_message["sender_id"],
                            content=encrypted_message,
                            content_type=new_message.get("content_type"),
                            timestamp=new_message.get("timestamp", datetime.utcnow()),
                            is_outgoing=False,
                            is_delivered=True,
                        )
                    )

                return True, "SUCCESS"

        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg

    async def rotate_keys(self) -> bool:
        try:
            async with self._container() as request_container:
                auth_http_service = await request_container.get(AuthHTTPService)
                auth_http_service.set_token(self._state.token)
                key_storage = await request_container.get(EncryptedKeyStorage)

                (
                    ecdh_private_key,
                    ecdh_public_key,
                ) = await auth_http_service.update_ecdh_key(
                    self._state.ecdsa_private_key
                )

                if not ecdh_private_key:
                    return False, "FAILED TO ROTATE KEYS"

                key_storage.clear_ecdh_private_key(self._state.username)

                success = await key_storage.store_ecdh_private_key(
                    username=self._state.username,
                    ecdh_private_key=ecdh_private_key,
                    password=self._state.password,
                )

                if not success:
                    return False, "FAILED TO STORE ECDH PRIVATE KEY"

                self._state.update_ecdh_keys(
                    ecdh_public_key=ecdh_public_key,
                    ecdh_private_key=ecdh_private_key,
                )

                return True, "SUCCESS"
        except Exception as e:
            error_msg = f"{(str(e)).upper()}"
            return False, error_msg
