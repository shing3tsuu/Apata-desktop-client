import httpx
import asyncio
from typing import Optional, Dict, Any
import logging

from src.exceptions import (
    APIError,
    NetworkError,
    InfrastructureError,
    AuthenticationError,
    RetryableError,
    NonRetryableError
)

class CommonHTTPClient:
    def __init__(
            self,
            base_url: str,
            timeout: float = 60.0,
            max_retries: int = 3,
            retry_delay: float = 1.0,
            verify: bool = False,
            logger: logging.Logger = None
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.verify = verify

        self._client: httpx.AsyncClient | None = None
        self._current_token: str | None = None

        self._logger = logger
        self._request_count = 0
        self._error_count = 0

    async def __aenter__(self):
        await self._initialize_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self._close_client()

    async def _initialize_client(self):
        headers = {"Content-Type": "application/json"}
        if self._current_token:
            headers["Authorization"] = f"Bearer {self._current_token}"

        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            verify=self.verify,
            headers=headers
        )

        self._logger.debug(f"HTTP client initialized for {self.base_url}")

    async def _close_client(self):
        if self._client:
            await self._client.aclose()
            self._client = None
            self._logger.debug("HTTP client closed")

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

    async def get(self, endpoint: str, params: dict | None = None, **kwargs) -> dict[str, Any]:
        return await self._request_with_retry("GET", endpoint, params=params, **kwargs)

    async def post(self, endpoint: str, data: dict[str, Any], **kwargs) -> dict[str, Any]:
        return await self._request_with_retry("POST", endpoint, json=data, **kwargs)

    async def put(self, endpoint: str, data: dict[str, Any], **kwargs) -> dict[str, Any]:
        return await self._request_with_retry("PUT", endpoint, json=data, **kwargs)

    async def delete(self, endpoint: str, **kwargs) -> dict[str, Any]:
        return await self._request_with_retry("DELETE", endpoint, **kwargs)

    async def _request_with_retry(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        last_exception = None
        request_id = f"{method}_{endpoint}_{self._request_count}"

        for attempt in range(self.max_retries):
            try:
                self._request_count += 1
                self._logger.debug(f"Request attempt {attempt + 1}/{self.max_retries} [{request_id}]")

                return await self._request(method, endpoint, **kwargs)

            except (APIError, NetworkError, InfrastructureError) as e:
                last_exception = e
                self._error_count += 1

                if isinstance(e, APIError) and e.is_client_error:
                    self._logger.warning(f"Client error, no retry [{request_id}]: {e}")
                    raise

                if isinstance(e, AuthenticationError):
                    self._logger.warning(f"Authentication error, no retry [{request_id}]: {e}")
                    raise

                if isinstance(e, NonRetryableError):
                    self._logger.warning(f"Non-retryable error [{request_id}]: {e}")
                    raise

                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    self._logger.warning(
                        f"Request failed, retrying in {delay}s [{request_id}]: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    self._logger.error(
                        f"All retry attempts failed [{request_id}]: {e}",
                        exc_info=True
                    )
                    raise

            except Exception as e:
                self._error_count += 1
                self._logger.error(
                    f"Unexpected error in request [{request_id}]: {e}",
                    exc_info=True
                )
                raise InfrastructureError(
                    f"Unexpected error during request: {str(e)}",
                    original_error=e,
                    context={
                        "method": method,
                        "endpoint": endpoint,
                        "request_id": request_id,
                        "attempt": attempt + 1
                    }
                ) from e

        if last_exception:
            raise last_exception

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        if not self._client:
            raise InfrastructureError(
                "HTTP client not initialized. Use async context manager or session() method.",
                context={"method": method, "endpoint": endpoint}
            )

        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        safe_kwargs = self._sanitize_sensitive_data(kwargs)
        self._logger.info(
            f"Making {method} request to {url}",
            extra={"method": method, "url": url, "kwargs": safe_kwargs}
        )

        try:
            response = await self._client.request(method, url, **kwargs)
            response.raise_for_status()

            result = response.json() if response.content else {}

            self._logger.debug(
                f"Request successful: {method} {url} - Status {response.status_code}"
            )

            return result

        except httpx.HTTPStatusError as e:
            await self._handle_http_error(e, method, url)

        except httpx.RequestError as e:
            error_msg = f"Network error for {method} {url}: {str(e)}"
            self._logger.error(error_msg)
            raise NetworkError(
                f"Network request failed: {str(e)}",
                original_error=e,
                context={"method": method, "url": url, "error_type": type(e).__name__}
            ) from e

        except Exception as e:
            error_msg = f"Unexpected error for {method} {url}: {str(e)}"
            self._logger.error(error_msg, exc_info=True)
            raise InfrastructureError(
                f"Unexpected request error: {str(e)}",
                original_error=e,
                context={"method": method, "url": url}
            ) from e

    async def _handle_http_error(self, error: httpx.HTTPStatusError, method: str, url: str):
        status_code = error.response.status_code
        response_text = error.response.text[:1000]

        response_data = None
        if error.response.content:
            try:
                response_data = error.response.json()
            except:
                response_data = {"raw_response": response_text}

        context = {
            "method": method,
            "url": url,
            "status_code": status_code,
            "response_data": response_data,
            "headers": dict(error.response.headers)
        }

        if status_code == 401:
            self._logger.warning(f"Authentication failed for {method} {url}")
            raise AuthenticationError(
                f"Authentication failed: {status_code}",
                context=context
            ) from error

        elif status_code == 403:
            self._logger.warning(f"Access forbidden for {method} {url}")
            raise AuthenticationError(
                f"Access forbidden: {status_code}",
                context=context
            ) from error

        elif 400 <= status_code < 500:
            self._logger.warning(
                f"Client error {status_code} for {method} {url}: {response_text}"
            )
            raise APIError(
                message=f"Client error: {status_code}",
                status_code=status_code,
                response_data=response_data,
                context=context
            ) from error

        else:  # 500+ errors
            self._logger.error(
                f"Server error {status_code} for {method} {url}: {response_text}"
            )
            raise APIError(
                message=f"Server error: {status_code}",
                status_code=status_code,
                response_data=response_data,
                context=context
            ) from error

    def _sanitize_sensitive_data(self, data: Any) -> Any:
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
            'password', 'token', 'secret', 'key', 'signature',
            'auth', 'credential', 'private', 'session'
        }
        key_lower = key.lower()
        return any(pattern in key_lower for pattern in sensitive_patterns)

    async def health_check(self) -> bool:
        try:
            await self.get("/health", timeout=10.0)
            return True
        except (APIError, NetworkError, InfrastructureError) as e:
            self._logger.warning(f"Health check failed: {e}")
            return False

    def get_metrics(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "total_requests": self._request_count,
            "error_requests": self._error_count,
            "success_rate": self._calculate_success_rate(),
            "has_token": self._current_token is not None,
            "client_initialized": self._client is not None
        }

    def _calculate_success_rate(self) -> float:
        if self._request_count == 0:
            return 100.0
        return ((self._request_count - self._error_count) / self._request_count) * 100

    async def execute_with_fallback(self, operation, fallback_value=None, *args, **kwargs):
        try:
            return await operation(*args, **kwargs)
        except (APIError, NetworkError, InfrastructureError) as e:
            self._logger.warning(
                f"Operation failed, using fallback value: {e}",
                exc_info=True
            )
            return fallback_value