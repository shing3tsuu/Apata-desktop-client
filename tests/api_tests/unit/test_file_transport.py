import asyncio
from math import ceil
from uuid import uuid4

import httpx
import pytest

from src.adapters.api.dao.common import CommonHTTPClient
from src.adapters.api.dto import FileUploadSessionDTO
from src.adapters.api.service.file import FileHTTPService
from src.adapters.encryption.service.dto import FileEncryptionContext
from src.exceptions import APIError, NetworkError
from tests.timing_wrapper import timer


@timer()
def test_patch_chunk_is_not_retried_and_uses_upload_content_type() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise httpx.ConnectError("connection lost", request=request)

    async def scenario() -> None:
        async with CommonHTTPClient(
            base_url="http://testserver",
            max_retries=3,
            retry_delay=0,
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(NetworkError):
                await client.patch_bytes(
                    "/files/uploads/upload-id",
                    b"encrypted chunk",
                    headers={"Upload-Offset": "0"},
                )

    asyncio.run(scenario())

    assert len(requests) == 1
    assert requests[0].headers["Content-Type"] == "application/offset+octet-stream"
    assert requests[0].headers["Accept"] == "application/json"
    assert requests[0].headers["Upload-Offset"] == "0"


@timer()
def test_file_download_requests_binary_content() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, content=b"encrypted file chunk")

    async def scenario() -> bytes:
        async with CommonHTTPClient(
            base_url="http://testserver",
            transport=httpx.MockTransport(handler),
        ) as client:
            return await client.get_bytes("/files/file-id/chunks/0")

    assert asyncio.run(scenario()) == b"encrypted file chunk"
    assert requests[0].headers["Accept"] == "application/octet-stream"


@timer()
def test_json_primitive_response_is_a_contract_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=True)

    async def scenario() -> None:
        async with CommonHTTPClient(
            base_url="http://testserver",
            transport=httpx.MockTransport(handler),
        ) as client:
            with pytest.raises(APIError, match="Expected JSON object or array"):
                await client.get("/health")

    asyncio.run(scenario())


@timer()
def test_retry_after_is_capped_without_jitter() -> None:
    client = CommonHTTPClient(
        base_url="http://testserver",
        max_retry_delay=2,
        retry_jitter=0,
    )
    error = APIError(
        "Too many requests",
        status_code=429,
        context={"response_headers": {"Retry-After": "60"}},
    )

    assert client._retry_delay(error, attempt=1) == 2


class _FakeEncryptionService:
    file_chunk_encryption_overhead = 1

    @staticmethod
    def get_encrypted_file_size(
        *, plaintext_size: int, plaintext_chunk_size: int
    ) -> int:
        if plaintext_size == 0:
            return 0
        return plaintext_size + ceil(plaintext_size / plaintext_chunk_size)

    @staticmethod
    def get_file_resume_position(
        *,
        plaintext_size: int,
        plaintext_chunk_size: int,
        uploaded_ciphertext_size: int,
    ) -> tuple[int, int]:
        encrypted_chunk_size = plaintext_chunk_size + 1
        total_ciphertext_size = _FakeEncryptionService.get_encrypted_file_size(
            plaintext_size=plaintext_size,
            plaintext_chunk_size=plaintext_chunk_size,
        )
        if uploaded_ciphertext_size == total_ciphertext_size:
            return ceil(plaintext_size / plaintext_chunk_size), plaintext_size
        if uploaded_ciphertext_size % encrypted_chunk_size:
            raise ValueError("Offset does not end at an encrypted chunk boundary")
        chunk_index = uploaded_ciphertext_size // encrypted_chunk_size
        return chunk_index, chunk_index * plaintext_chunk_size

    @staticmethod
    async def encrypt_file_chunk(
        *,
        context: FileEncryptionContext,
        chunk_index: int,
        plaintext: bytes,
    ) -> bytes:
        del context, chunk_index
        return b"x" + plaintext


class _ResumingFileDAO:
    def __init__(self, resumed_session: FileUploadSessionDTO, first_error: Exception):
        self.resumed_session = resumed_session
        self.first_error = first_error
        self.uploads: list[tuple[int, bytes]] = []
        self.session_requests = 0

    async def upload_chunk(
        self,
        *,
        upload_id: str,
        offset: int,
        encrypted_chunk: bytes,
        token: str,
    ) -> int:
        del upload_id, token
        self.uploads.append((offset, encrypted_chunk))
        if len(self.uploads) == 1:
            raise self.first_error
        return offset + len(encrypted_chunk)

    async def get_upload_session(
        self, *, upload_id: str, token: str
    ) -> FileUploadSessionDTO:
        del upload_id, token
        self.session_requests += 1
        return self.resumed_session


@pytest.mark.parametrize(
    "first_error",
    [
        NetworkError("Chunk response was lost"),
        APIError("Request timed out", status_code=408),
        APIError("Upload offset conflict", status_code=409),
        APIError("Server error", status_code=500),
    ],
    ids=["network", "408", "409", "5xx"],
)
@timer()
def test_file_upload_reconciles_server_offset_after_ambiguous_error(
    first_error: Exception,
) -> None:
    file_id = uuid4()
    context = FileEncryptionContext(file_id=file_id, key=b"0" * 32)
    session = FileUploadSessionDTO(
        upload_id="upload-id",
        file_id=str(file_id),
        chunk_size=4,
        offset=0,
    )
    resumed_session = FileUploadSessionDTO(
        upload_id="upload-id",
        file_id=str(file_id),
        chunk_size=4,
        offset=4,
    )
    file_dao = _ResumingFileDAO(resumed_session, first_error)
    service = FileHTTPService(
        file_dao=file_dao,
        auth_dao=object(),
        encryption_service=_FakeEncryptionService(),
    )

    asyncio.run(
        service._upload_file_chunks(
            file_content=b"abcdef",
            file_size=6,
            session=session,
            context=context,
            token="token",
        )
    )

    assert file_dao.session_requests == 1
    assert file_dao.uploads == [(0, b"xabc"), (4, b"xdef")]


@timer()
def test_resumed_upload_session_must_keep_its_upload_id() -> None:
    context = FileEncryptionContext(file_id=uuid4(), key=b"0" * 32)
    session = FileUploadSessionDTO(
        upload_id="other-upload-id",
        file_id=str(context.file_id),
        chunk_size=4,
        offset=4,
    )

    with pytest.raises(APIError, match="unexpected upload ID"):
        FileHTTPService._validate_upload_session(
            session=session,
            context=context,
            requested_chunk_size=4,
            expected_upload_id="upload-id",
        )
