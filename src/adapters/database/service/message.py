import logging

from ..dao.message import AbstractMessageDAO
from ..dao.common import AbstractCommonDAO
from src.adapters.database.dto import MessageDTO, MessageRequestDTO

class MessageService:
    __slots__ = (
        "_message_dao",
        "_common_dao",
        "_logger",
        "__weakref__"
    )
    def __init__(self, message_dao: AbstractMessageDAO, common_dao: AbstractCommonDAO, logger: logging.Logger):
        self._message_dao = message_dao
        self._common_dao = common_dao
        self._logger = logger

    async def add_message(self, message: MessageRequestDTO) -> MessageDTO:
        try:
            result = await self._message_dao.add_message(message)
            await self._common_dao.commit()
            return result
        except Exception as e:
            self._logger.error(f"Error adding message: {e}")
            await self._common_dao.rollback()
            raise

    async def get_messages(self, local_user_id: int, contact_id: int, limit: int | None = None) -> list[MessageDTO]:
        try:
            return await self._message_dao.get_messages(
                local_user_id=local_user_id,
                contact_id=contact_id,
                limit=limit
            )
        except Exception as e:
            self._logger.error(f"Error fetching messages: {e}")
            return []

    async def delete_message(self, message_id: int) -> bool:
        try:
            result = await self._message_dao.delete_message(message_id)
            await self._common_dao.commit()
            return result
        except Exception as e:
            self._logger.error(f"Error deleting message: {e}")
            await self._common_dao.rollback()
            return False