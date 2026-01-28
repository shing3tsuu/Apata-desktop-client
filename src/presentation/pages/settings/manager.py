import logging
import asyncio
import base64
from typing import Tuple, Optional, List, Set
from datetime import datetime

from pyexpat.errors import messages
from src.exceptions import *
from dishka import AsyncContainer

from src.providers import AppProvider
from src.presentation.pages import AppState, Contact, Message

from src.adapters.api.service import (
    AuthHTTPService,
    ContactHTTPService,
    MessageHTTPService
)

from src.adapters.database.service import (
    LocalUserService,
    ContactService,
    MessageService
)

from src.adapters.database.dto import (
    LocalUserRequestDTO, LocalUserDTO,
    ContactRequestDTO, ContactDTO,
    MessageRequestDTO, MessageDTO
)

from src.adapters.encryption.dao import (
    Abstract256Cipher,
    AbstractPasswordHasher,
    AbstractECDHCipher
)

from src.adapters.encryption.storage import EncryptedKeyStorage


class SettingsManager:
    def __init__(self, app_state: AppState, container: AsyncContainer):
        self._state = app_state
        self._container = container
        self._logger = logging.getLogger(__name__)

    def get_timezone_options(self) -> dict[int, str]:
        timezones = {}
        for i in range(-12, 13):
            sign = "+" if i >= 0 else ""
            timezones[i] = f"{sign}{i}:00"
        return timezones

    async def get_timezone(self) -> int:
        try:
            async with self._container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                local_user = await local_user_service.get_user_data(
                    LocalUserRequestDTO(username=self._state.username)
                )
                return local_user.timezone
        except Exception as e:
            self._logger.error(f"Error getting timezone: {e}")
            return 0

    async def update_timezone(self, timezone: str) -> tuple[bool, str]:
        try:
            self._logger.info(f"Updating timezone to: {timezone}")
            # timezone: +03:00 -> int: 3
            number = int(timezone.strip().split(':')[0])

            async with self._container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                await local_user_service.update_user_data(
                    LocalUserRequestDTO(
                        username=self._state.username,
                        timezone=number
                    )
                )
            self._logger.info(f"Successfully updated timezone to: {timezone}")
            return True, "Successfully updated timezone"
        except Exception as e:
            self._logger.error(f"Error updating timezone: {e}")
            return False, f"Failed to update timezone: {str(e)}"