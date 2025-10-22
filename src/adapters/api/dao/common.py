import httpx
import asyncio
import time
from typing import Optional, Dict, Any
import logging
from datetime import datetime

from src.exceptions import APIError, NetworkError, InfrastructureError


class CommonHTTPClient:
    """
    Base class for HTTP requests, using httpx async client
    """
    def __init__(
            self,
            base_url: str,
            timeout: float = 60.0,
            max_retries: int = 3,
            retry_delay: float = 1.0,
            logger: logging.Logger | None = None
    ):
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._client: httpx.AsyncClient | None = None

        self._current_token: str | None = None

        self._logger = logger or logging.getLogger(__name__)

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=self.timeout,
            headers={"Content-Type": "application/json"}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
            self._client = None

    def set_auth_token(self, token: str):
        """
        Setting an authentication token for all subsequent requests
        """
        self._current_token = token
        if self._client:
            self._client.headers["Authorization"] = f"Bearer {token}"

    def clear_auth_token(self):
        """
        Clearing the authentication token
        """
        self._current_token = None
        if self._client and "Authorization" in self._client.headers:
            del self._client.headers["Authorization"]

    def get_current_token(self) -> str | None:
        """
        Getting the currently installed token
        """
        return self._current_token

    async def get(self, endpoint: str, params: dict | None = None) -> dict[str, Any]:
        return await self._request_with_retry("GET", endpoint, params=params)

    async def post(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request_with_retry("POST", endpoint, json=data)

    async def put(self, endpoint: str, data: dict[str, Any]) -> dict[str, Any]:
        return await self._request_with_retry("PUT", endpoint, json=data)

    async def delete(self, endpoint: str) -> dict[str, Any]:
        return await self._request_with_retry("DELETE", endpoint)

    async def _request_with_retry(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        last_exception = None

        for attempt in range(self.max_retries):
            try:
                return await self._request(method, endpoint, **kwargs)

            except APIError as e:
                if e.is_client_error:
                    raise
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    self._logger.warning(f"Server error {e.status_code}, retrying in {delay}s")
                    await asyncio.sleep(delay)
                else:
                    raise

            except (NetworkError, InfrastructureError) as e:
                last_exception = e
                if attempt < self.max_retries - 1:
                    delay = self.retry_delay * (2 ** attempt)
                    self._logger.warning(f"Network error, retrying in {delay}s: {e}")
                    await asyncio.sleep(delay)
                else:
                    raise

            except Exception as e:
                raise InfrastructureError(f"Unexpected error: {str(e)}", original_error=e)

        if last_exception:
            raise last_exception

    async def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        if not self._client:
            raise RuntimeError("The HTTP client is not initialized. Use async with context manager..")

        url = f"{self.base_url}/{endpoint.lstrip('/')}"

        self._logger.info(f"Attempting HTTP {method} to {url}")

        try:
            self._logger.debug(f"HTTP {method} {url}")

            # Logging request data (without sensitive information)
            log_data = {k: v for k, v in kwargs.items() if k != 'json' or not self._contains_sensitive_data(v)}
            self._logger.debug(f"Request data: {log_data}")

            start_time = time.time()
            response = await self._client.request(
                method,
                url,
                params=kwargs.get('params'),
                json=kwargs.get('json'),
                **{k: v for k, v in kwargs.items() if k not in ['params', 'json']}
            )
            response_time = time.time() - start_time

            self._logger.debug(f"Response time: {response_time:.2f}s, Status: {response.status_code}")

            response.raise_for_status()

            result = response.json() if response.content else {}
            self._logger.debug(f"Response data: {result}")

            return result

        except httpx.HTTPStatusError as e:
            error_message = f"HTTP error {e.response.status_code} for {method} {url}: {e.response.text}"

            # We log different levels depending on the status
            if e.response.status_code >= 500:
                self._logger.error(error_message)
            elif e.response.status_code >= 400:
                self._logger.warning(error_message)
            else:
                self._logger.info(error_message)

            # Trying to extract error details from the response
            response_data = None
            if e.response.content:
                try:
                    response_data = e.response.json()
                except:
                    response_data = {"raw_response": e.response.text[:500]}

            raise APIError(
                message=f"API error: {e.response.status_code}",
                status_code=e.response.status_code,
                response_data=response_data
            ) from e

        except httpx.RequestError as e:
            error_message = f"Network error for {method} {url}: {str(e)}"
            self._logger.error(error_message)
            raise NetworkError(f"Network error: {str(e)}") from e

        except Exception as e:
            error_message = f"Unexpected error for {method} {url}: {str(e)}"
            self._logger.error(error_message, exc_info=True)
            raise InfrastructureError(f"Unexpected error: {str(e)}") from e

    def _contains_sensitive_data(self, data: Any) -> bool:
        """
        Checks if the data contains sensitive information
        """
        if not isinstance(data, dict):
            return False

        sensitive_keys = {'password', 'token', 'secret', 'key', 'signature'}
        return any(key in str(data).lower() for key in sensitive_keys)

    async def health_check(self) -> bool:
        """
        Checking API Availability
        """
        try:
            await self.get("/health")
            return True
        except (APIError, NetworkError, InfrastructureError):
            return False

    def get_metrics(self) -> dict[str, Any]:
        """
        Getting customer metrics (can be expanded)
        """
        return {
            "base_url": self.base_url,
            "timeout": self.timeout,
            "max_retries": self.max_retries,
            "has_token": self._current_token is not None
        }