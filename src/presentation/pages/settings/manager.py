import logging

from dishka import AsyncContainer

from src.adapters.api.service import FileStorageState
from src.adapters.database.dto import (
    RequestLocalUserDTO,
)
from src.adapters.database.service import (
    LocalUserService,
)
from src.presentation.pages import AppState


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
                local_user = await local_user_service.get_user_by_username(
                    self._state.require_username
                )
                if local_user is None or local_user.timezone is None:
                    return 0
                return local_user.timezone
        except Exception as e:
            self._logger.error(f"Error getting timezone: {e}")
            return 0

    async def update_timezone(self, timezone: str) -> tuple[bool, str]:
        try:
            self._logger.info(f"Updating timezone to: {timezone}")
            # timezone: +03:00 -> int: 3
            number = int(timezone.strip().split(":")[0])

            async with self._container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                await local_user_service.update_user_data(
                    RequestLocalUserDTO(
                        id=self._state.require_local_user_id,
                        timezone=number,
                    )
                )
            self._logger.info(f"Successfully updated timezone to: {timezone}")
            return True, "Successfully updated timezone"
        except Exception as e:
            self._logger.error(f"Error updating timezone: {e}")
            return False, f"Failed to update timezone: {str(e)}"

    async def update_file_path(self, file_path: str | None) -> tuple[bool, str]:
        """Persist the active user's storage path before updating the DI cache."""
        try:
            async with self._container() as request_container:
                local_user_service = await request_container.get(LocalUserService)
                file_storage_state = await request_container.get(FileStorageState)

                updated_user = await local_user_service.update_user_data(
                    RequestLocalUserDTO(
                        id=self._state.require_local_user_id,
                        file_path=file_path,
                    )
                )
                if updated_user is None:
                    return False, "LOCAL USER NOT FOUND"

                file_storage_state.file_path = updated_user.file_path
                return True, "SUCCESS"
        except Exception as error:
            self._logger.error("Error updating file storage path: %s", error)
            return False, f"FAILED TO UPDATE FILE STORAGE PATH: {error}"
