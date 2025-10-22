from typing import Any
import logging
import traceback

class BaseAppError(Exception):
    """Base exception class with structured logging"""
    def __init__(self, message: str, context: dict[str, Any] | None = None):
        self.message = message
        self.context = context or {}
        self.timestamp = datetime.utcnow().isoformat()
        super().__init__(self.message)
        self._log_error()

    def _log_error(self):
        logger = logging.getLogger(__name__)
        logger.error(
            f"{self.__class__.__name__}: {self.message}",
            extra={
                "exception_type": self.__class__.__name__,
                "exception_message": self.message,
                "context": self.context,
                "timestamp": self.timestamp,
                "stack_trace": traceback.format_exc()
            },
            exc_info=True
        )

class UserAlreadyExistsError(BaseAppError):
    pass

class UserNotRegisteredError(BaseAppError):
    pass

class ContactAlreadyExistsError(BaseAppError):
    pass

class AuthenticationError(BaseAppError):
    pass

class InfrastructureError(BaseAppError):
    def __init__(self, message: str, original_error: Exception | None = None, context: dict[str, Any] | None = None):
        self.original_error = original_error
        context = context or {}
        if original_error:
            context.update({
                "original_error_type": original_error.__class__.__name__,
                "original_error_message": str(original_error)
            })
        super().__init__(message, context)

class NetworkError(InfrastructureError):
    pass

class APIError(BaseAppError):
    def __init__(self, message: str, status_code: int | None = None,
                 response_data: dict[str, Any] | None = None, context: dict[str, Any] | None = None):
        self.status_code = status_code
        self.response_data = response_data
        context = context or {}
        context.update({
            "status_code": status_code,
            "response_data": response_data
        })
        super().__init__(message, context)

    @property
    def is_client_error(self) -> bool:
        return self.status_code is not None and 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        return self.status_code is not None and 500 <= self.status_code < 600

class ValidationError(BaseAppError):
    def __init__(self, message: str, field: str | None = None, context: dict[str, Any] | None = None):
        self.field = field
        context = context or {}
        context.update({"field": field})
        super().__init__(message, context)

class CryptographyError(InfrastructureError):
    pass

class KeyGenerationError(CryptographyError):
    pass

class EncryptionError(CryptographyError):
    pass

class DecryptionError(CryptographyError):
    pass

class SignatureError(CryptographyError):
    pass

class MessageDeliveryError(InfrastructureError):
    pass

class RetryableError(InfrastructureError):
    """Marks errors that can be retried"""
    pass

class NonRetryableError(BaseAppError):
    """Marks errors that should not be retried"""
    pass