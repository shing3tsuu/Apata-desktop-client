import logging

from ..dao.message import AbstractMessageDAO
from ..dao.common import AbstractCommonDAO, error_handler
from src.adapters.database.dto import MessageDTO, MessageRequestDTO

class MessageService:
    def __init__(self, message_dao: AbstractMessageDAO, common_dao: AbstractCommonDAO, logger: logging.Logger):
        self._message_dao = message_dao
        self._common_dao = common_dao
        self._logger = logger

    @error_handler
    async def add_message(self, message: MessageRequestDTO) -> MessageDTO:
            result = await self._message_dao.add_message(message)
            return result

    @error_handler
    async def get_messages(self, local_user_id: int, contact_id: int, limit: int | None = None) -> list[MessageDTO]:
        return await self._message_dao.get_messages(
            local_user_id=local_user_id,
            contact_id=contact_id,
            limit=limit
        )

    @error_handler
    async def delete_message(self, message_id: int) -> bool:
        result = await self._message_dao.delete_message(message_id)
        return result