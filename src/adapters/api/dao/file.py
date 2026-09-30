from collections.abc import Sequence
from typing import Any
from uuid import UUID

from src.adapters.api.dto import FileUploadSessionDTO
from src.exceptions import APIError

from .common import CommonHTTPClient


class FileHTTPDAO:
    def __init__(self, http_client: CommonHTTPClient):
        self._http_client = http_client

    @staticmethod
    def _expect_object(response: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if isinstance(response, dict):
            return response

        raise APIError(
            "Expected JSON object response from file API",
            response_data={"response_type": type(response).__name__},
        )

    @staticmethod
    def _required_file_id(data: dict[str, Any]) -> str:
        file_id = data.get("file_id")
        if isinstance(file_id, str) and file_id:
            return file_id

        raise APIError("Expected non-empty string field 'file_id' in upload response")

    @staticmethod
    def _required_offset(data: dict[str, Any]) -> int:
        offset = data.get("offset")
        if isinstance(offset, int) and offset >= 0:
            return offset

        raise APIError("Expected non-negative integer field 'offset' in upload response")

    async def create_upload(
        self,
        *,
        file_id: str,
        recipient_id: str,
        message_id: str,
        chat_id: str | None,
        total_size: int,
        requested_chunk_size: int,
        encrypted_metadata: str,
        ephemeral_public_key: str,
        ephemeral_signature: str,
        token: str,
    ) -> FileUploadSessionDTO:
        self._http_client.set_auth_token(token)
        response = self._expect_object(
            await self._http_client.post(
                "/files/uploads",
                {
                    "file_id": file_id,
                    "recipient_id": recipient_id,
                    "message_id": message_id,
                    "chat_id": chat_id,
                    "total_size": total_size,
                    "chunk_size": requested_chunk_size,
                    "encrypted_metadata": encrypted_metadata,
                    "ephemeral_public_key": ephemeral_public_key,
                    "ephemeral_signature": ephemeral_signature,
                },
            )
        )
        return FileUploadSessionDTO.from_mapping(response)

    async def get_upload_session(
        self, *, upload_id: str, token: str
    ) -> FileUploadSessionDTO:
        self._http_client.set_auth_token(token)
        response = self._expect_object(
            await self._http_client.get(f"/files/uploads/{upload_id}")
        )
        return FileUploadSessionDTO.from_mapping(response)

    async def upload_chunk(
        self,
        *,
        upload_id: str,
        offset: int,
        encrypted_chunk: bytes,
        token: str,
    ) -> int:
        self._http_client.set_auth_token(token)
        response = self._expect_object(
            await self._http_client.patch_bytes(
                f"/files/uploads/{upload_id}",
                encrypted_chunk,
                headers={
                    "Upload-Offset": str(offset),
                },
            )
        )
        return self._required_offset(response)

    async def download_chunk(
        self,
        *,
        file_id: str,
        chunk_index: int,
        token: str,
    ) -> bytes:
        self._http_client.set_auth_token(token)
        return await self._http_client.get_bytes(
            f"/files/{file_id}/chunks/{chunk_index}"
        )

    async def get_undelivered_message_files(self, *, token: str) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return self._expect_object(await self._http_client.get("/files/undelivered"))

    async def ack_message_files(
        self,
        *,
        file_ids: Sequence[UUID | str],
        token: str,
    ) -> dict[str, Any]:
        self._http_client.set_auth_token(token)
        return self._expect_object(
            await self._http_client.post(
                "/files/ack",
                {"file_ids": [str(file_id) for file_id in file_ids]},
            )
        )

    async def complete_upload(self, *, upload_id: str, token: str) -> str:
        self._http_client.set_auth_token(token)
        response = self._expect_object(
            await self._http_client.post(
                f"/files/uploads/{upload_id}/complete", {}
            )
        )
        return self._required_file_id(response)

    async def abort_upload(self, *, upload_id: str, token: str) -> None:
        self._http_client.set_auth_token(token)
        await self._http_client.delete(f"/files/uploads/{upload_id}")
