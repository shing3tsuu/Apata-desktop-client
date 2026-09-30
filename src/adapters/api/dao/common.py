import asyncio
import logging
import random
from collections.abc import Mapping
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, NoReturn

import httpx

from src.exceptions import (
    APIError,
    AuthenticationError,
    InfrastructureError,
    NetworkError,
)

JSONResponse = dict[str, Any] | list[Any]
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class CommonHTTPClient:
    def __init__(
        self,
        base_url: str,
        timeout: float = 60.0,
        max_retries: int = 2,
        retry_delay: float = 1.0,
        verify: bool = False,
        logger: logging.Logger | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        trust_env: bool = False,
        connect_timeout: float = 10.0,
        read_timeout: float | None = None,
        write_timeout: float | None = None,
        pool_timeout: float = 10.0,
        file_read_timeout: float | None = None,
        file_write_timeout: float | None = None,
        max_retry_delay: float = 30.0,
        retry_jitter: float = 0.25,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.verify = verify
        self.transport = transport
        self.trust_env = trust_env
        self.connect_timeout = connect_timeout
        self.read_timeout = read_timeout if read_timeout is not None else timeout
        self.write_timeout = write_timeout if write_timeout is not None else timeout
        self.pool_timeout = pool_timeout
        self.file_read_timeout = (
            file_read_timeout
            if file_read_timeout is not None
            else max(self.read_timeout, 120.0)
        )
        self.file_write_timeout = (
            file_write_timeout
            if file_write_timeout is not None
            else max(self.write_timeout, 120.0)
        )
        self.max_retry_delay = max_retry_delay
        self.retry_jitter = retry_jitter
        self._default_timeout = self._build_timeout(
            connect=self.connect_timeout,
            read=self.read_timeout,
            write=self.write_timeout,
            pool=self.pool_timeout,
        )
        self._file_transfer_timeout = self._build_timeout(
            connect=self.connect_timeout,
            read=self.file_read_timeout,
            write=self.file_write_timeout,
            pool=self.pool_timeout,
        )

        self._client: httpx.AsyncClient | None = None
        self._current_token: str | None = None

        self._logger = logger or logging.getLogger(__name__)
        self._request_count = 0
        self._attempt_count = 0
        self._error_count = 0

    async def __aenter__(self):
        await self._initialize_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_client()

    async def _initialize_client(self) -> None:
        if self._client and not self._client.is_closed:
            return

        headers = {"Accept": "application/json"}
        if self._current_token:
            headers["Authorization"] = f"Bearer {self._current_token}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self._default_timeout,
            verify=self.verify,
            headers=headers,
            transport=self.transport,
            trust_env=self.trust_env,
        )

        self._logger.debug(f"HTTP client initialized for {self.base_url}")

    async def _close_client(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._logger.debug("HTTP client closed")
        self._client = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            await self._initialize_client()

        if self._client is None:
            raise InfrastructureError("HTTP client is not available")

        return self._client

    def set_auth_token(self, token: str):
        self._current_token = token
        if self._client:
            self._client.headers["Authorization"] = f"Bearer {token}"

        self._logger.debug("Authentication token updated")

    def clear_auth_token(self):
        self._current_token = None
        if self._client and "Authorization" in self._client.headers:
            del self._client.headers["Authorization"]

        self._logger.debug("Authentication token cleared")

    def get_current_token(self) -> str | None:
        return self._current_token

    async def get(
        self, endpoint: str, params: dict | None = None, **kwargs
    ) -> JSONResponse:
        return await self._request_with_retry("GET", endpoint, params=params, **kwargs)

    async def get_bytes(
        self, endpoint: str, params: dict | None = None, **kwargs
    ) -> bytes:
        kwargs["headers"] = self._merge_headers(
            defaults={"Accept": "application/octet-stream"},
            headers=kwargs.pop("headers", None),
        )
        kwargs.setdefault("timeout", self._file_transfer_timeout)
        response = await self._request_with_retry(
            "GET",
            endpoint,
            params=params,
            raw_response=True,
            **kwargs,
        )
        if isinstance(response, bytes):
            return response
        raise InfrastructureError("Expected binary response from HTTP request")

    async def post(self, endpoint: str, data: dict[str, Any], **kwargs) -> JSONResponse:
        return await self._request_with_retry("POST", endpoint, json=data, **kwargs)

    async def put(self, endpoint: str, data: dict[str, Any], **kwargs) -> JSONResponse:
        return await self._request_with_retry("PUT", endpoint, json=data, **kwargs)

    async def patch(
        self, endpoint: str, data: dict[str, Any], **kwargs
    ) -> JSONResponse:
        return await self._request_with_retry("PATCH", endpoint, json=data, **kwargs)

    async def patch_bytes(
        self,
        endpoint: str,
        content: bytes,
        *,
        headers: Mapping[str, str] | None = None,
        **kwargs,
    ) -> dict[str, Any] | list[Any] | bytes:
        kwargs.setdefault("timeout", self._file_transfer_timeout)
        return await self._request_with_retry(
            "PATCH",
            endpoint,
            content=content,
            headers=self._merge_headers(
                defaults={
                    "Accept": "application/json",
                    "Content-Type": "application/offset+octet-stream",
                },
                headers=headers,
            ),
            max_attempts=1,
            **kwargs,
        )

    async def delete(self, endpoint: str, **kwargs) -> JSONResponse:
        return await self._request_with_retry("DELETE", endpoint, **kwargs)

    async def _request_with_retry(
        self,
        method: str,
        endpoint: str,
        *,
        raw_response: bool = False,
        max_attempts: int | None = None,
        **kwargs,
    ) -> JSONResponse | bytes:
        attempts = max(1, max_attempts if max_attempts is not None else self.max_retries)
        self._request_count += 1
        request_id = f"{method}:{endpoint}:{self._request_count}"
        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                self._attempt_count += 1
                self._logger.debug(
                    f"HTTP request attempt {attempt}/{attempts} [{request_id}]"
                )

                return await self._request(
                    method,
                    endpoint,
                    raw_response=raw_response,
                    **kwargs,
                )

            except AuthenticationError:
                self._error_count += 1
                raise

            except APIError as error:
                last_error = error
                if self._should_retry_api_error(error, attempt, attempts):
                    delay = self._retry_delay(error, attempt)
                    self._logger.debug(
                        f"Retryable API error, retrying in {delay}s "
                        f"[{request_id}]: {error.message}"
                    )
                    await asyncio.sleep(delay)
                    continue

                self._error_count += 1
                raise

            except NetworkError as error:
                last_error = error
                if attempt < attempts:
                    delay = self._retry_delay(error, attempt)
                    self._logger.debug(
                        f"Network error, retrying in {delay}s "
                        f"[{request_id}]: {error.message}"
                    )
                    await asyncio.sleep(delay)
                    continue

                self._error_count += 1
                raise

            except InfrastructureError:
                self._error_count += 1
                raise

            except Exception as error:
                self._error_count += 1
                raise InfrastructureError(
                    "Unexpected error during HTTP request",
                    original_error=error,
                    context={
                        "method": method,
                        "endpoint": endpoint,
                        "request_id": request_id,
                        "attempt": attempt,
                    },
                ) from error

        if last_error:
            raise last_error

        raise InfrastructureError(
            f"Request failed without a response [{request_id}]",
            context={"method": method, "endpoint": endpoint},
        )

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        raw_response: bool = False,
        **kwargs,
    ) -> JSONResponse | bytes:
        client = await self._get_client()
        request_url = self._normalize_endpoint(endpoint)
        display_url = self._display_url(endpoint)

        safe_kwargs = self._sanitize_sensitive_data(kwargs)
        self._logger.debug(
            f"HTTP request started: {method} {display_url}",
            extra={"method": method, "url": display_url, "kwargs": safe_kwargs},
        )

        try:
            response = await client.request(method, request_url, **kwargs)
            response.raise_for_status()
            result = response.content if raw_response else self._decode_response(response)

            self._logger.debug(
                f"HTTP request successful: {method} {response.request.url} "
                f"- Status {response.status_code}"
            )

            return result

        except httpx.HTTPStatusError as error:
            self._raise_for_status_error(error, method, str(error.request.url))

        except httpx.InvalidURL as error:
            raise InfrastructureError(
                "Invalid HTTP request URL",
                original_error=error,
                context={"method": method, "url": display_url},
            ) from error

        except httpx.RequestError as error:
            message = (
                "HTTP request timed out"
                if isinstance(error, httpx.TimeoutException)
                else "HTTP network request failed"
            )
            raise NetworkError(
                message,
                original_error=error,
                context={
                    "method": method,
                    "url": display_url,
                    "error_type": type(error).__name__,
                },
            ) from error

    def _raise_for_status_error(
        self, error: httpx.HTTPStatusError, method: str, url: str
    ) -> NoReturn:
        status_code = error.response.status_code
        response_data = self._decode_error_response(error.response)
        response_headers = dict(error.response.headers)

        context = {
            "method": method,
            "url": url,
            "status_code": status_code,
            "response_data": response_data,
            "response_headers": response_headers,
        }

        server_message = self._extract_error_message(response_data)

        if status_code == 401:
            raise AuthenticationError(
                server_message or "Authentication failed",
                original_error=error,
                context=context,
            ) from error

        if status_code == 403:
            raise AuthenticationError(
                server_message or "Access forbidden",
                original_error=error,
                context=context,
            ) from error

        if 300 <= status_code < 400:
            message = server_message or f"Unexpected redirect: {status_code}"
            raise APIError(
                message=message,
                status_code=status_code,
                response_data=response_data,
                context=context,
            ) from error

        if 400 <= status_code < 500:
            message = server_message or f"Client error: {status_code}"
            raise APIError(
                message=message,
                status_code=status_code,
                response_data=response_data,
                context=context,
            ) from error

        message = server_message or f"Server error: {status_code}"
        raise APIError(
            message=message,
            status_code=status_code,
            response_data=response_data,
            context=context,
        ) from error

    def _decode_response(self, response: httpx.Response) -> JSONResponse:
        if not response.content:
            return {}

        try:
            data = response.json()
        except ValueError as error:
            response_data = {"raw_response": self._response_preview(response)}
            raise APIError(
                message="Invalid JSON response from API",
                status_code=response.status_code,
                response_data=response_data,
                context={
                    "method": response.request.method,
                    "url": str(response.request.url),
                    "status_code": response.status_code,
                },
            ) from error

        if isinstance(data, (dict, list)):
            return data

        raise APIError(
            message="Expected JSON object or array response from API",
            status_code=response.status_code,
            response_data={"response_type": type(data).__name__},
            context={
                "method": response.request.method,
                "url": str(response.request.url),
                "status_code": response.status_code,
            },
        )

    def _decode_error_response(self, response: httpx.Response) -> dict[str, Any] | None:
        if not response.content:
            return None

        try:
            data = response.json()
        except ValueError:
            return {"raw_response": self._response_preview(response)}

        if isinstance(data, dict):
            return data

        return {"detail": data}

    def _response_preview(self, response: httpx.Response) -> str:
        try:
            return response.text[:1000]
        except UnicodeDecodeError:
            return response.content[:1000].decode("utf-8", errors="replace")

    def _extract_error_message(
        self, response_data: dict[str, Any] | None
    ) -> str | None:
        if not response_data:
            return None

        for key in ("message", "detail", "error", "error_description"):
            value = response_data.get(key)
            if isinstance(value, str) and value:
                return value
            if isinstance(value, list) and value:
                return str(value[0])

        return None

    def _should_retry_api_error(
        self, error: APIError, attempt: int, attempts: int
    ) -> bool:
        return (
            attempt < attempts
            and error.status_code is not None
            and error.status_code in RETRYABLE_STATUS_CODES
        )

    def _retry_delay(self, error: APIError | NetworkError, attempt: int) -> float:
        delay: float
        if isinstance(error, APIError):
            retry_after = self._retry_after_seconds(error)
            if retry_after is not None:
                delay = retry_after
            else:
                delay = self.retry_delay * (2 ** (attempt - 1))
        else:
            delay = self.retry_delay * (2 ** (attempt - 1))

        delay = min(max(0.0, delay), self.max_retry_delay)
        max_jitter = min(self.retry_jitter, self.max_retry_delay - delay)
        return delay + random.uniform(0.0, max(0.0, max_jitter))

    def _retry_after_seconds(self, error: APIError) -> float | None:
        headers = error.context.get("response_headers")
        if not isinstance(headers, dict):
            return None

        retry_after = None
        for key, value in headers.items():
            if key.lower() == "retry-after":
                retry_after = value
                break

        if retry_after is None:
            return None

        try:
            return max(0.0, float(retry_after))
        except (TypeError, ValueError):
            pass

        try:
            retry_at = parsedate_to_datetime(str(retry_after))
        except (TypeError, ValueError):
            return None

        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)

        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())

    @staticmethod
    def _merge_headers(
        *,
        defaults: Mapping[str, str],
        headers: Mapping[str, str] | None,
    ) -> dict[str, str]:
        result = dict(defaults)
        if headers is not None:
            result.update(headers)
        return result

    @staticmethod
    def _build_timeout(
        *,
        connect: float,
        read: float,
        write: float,
        pool: float,
    ) -> httpx.Timeout:
        if any(value <= 0 for value in (connect, read, write, pool)):
            raise ValueError("HTTP timeouts must be positive")
        return httpx.Timeout(connect=connect, read=read, write=write, pool=pool)

    def _normalize_endpoint(self, endpoint: str) -> str:
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return f"/{endpoint.lstrip('/')}"

    def _display_url(self, endpoint: str) -> str:
        if endpoint.startswith(("http://", "https://")):
            return endpoint
        return f"{self.base_url}/{endpoint.lstrip('/')}"

    def _sanitize_sensitive_data(self, data: Any) -> Any:
        if isinstance(data, (bytes, bytearray, memoryview)):
            return {"binary_data_length": len(data)}
        if isinstance(data, dict):
            sanitized = {}
            for key, value in data.items():
                if self._is_sensitive_key(key):
                    sanitized[key] = "***HIDDEN***"
                elif isinstance(value, (dict, list)):
                    sanitized[key] = self._sanitize_sensitive_data(value)
                else:
                    sanitized[key] = value
            return sanitized
        elif isinstance(data, list):
            return [self._sanitize_sensitive_data(item) for item in data]
        else:
            return data

    def _is_sensitive_key(self, key: str) -> bool:
        sensitive_patterns = {
            "password",
            "token",
            "secret",
            "key",
            "signature",
            "auth",
            "credential",
            "private",
            "session",
        }
        key_lower = key.lower()
        return any(pattern in key_lower for pattern in sensitive_patterns)

    async def health_check(self) -> bool:
        try:
            await self.get("/health", timeout=10.0)
            return True
        except (APIError, AuthenticationError, NetworkError, InfrastructureError) as e:
            self._logger.warning(f"Health check failed: {e}")
            return False

    def get_metrics(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "total_requests": self._request_count,
            "total_attempts": self._attempt_count,
            "error_requests": self._error_count,
            "success_rate": self._calculate_success_rate(),
            "has_token": self._current_token is not None,
            "client_initialized": self._client is not None,
        }

    def _calculate_success_rate(self) -> float:
        if self._request_count == 0:
            return 100.0
        return ((self._request_count - self._error_count) / self._request_count) * 100

    async def execute_with_fallback(
        self, operation, fallback_value=None, *args, **kwargs
    ):
        try:
            return await operation(*args, **kwargs)
        except (APIError, AuthenticationError, NetworkError, InfrastructureError) as e:
            self._logger.warning(
                f"Operation failed, using fallback value: {e}", exc_info=True
            )
            return fallback_value
