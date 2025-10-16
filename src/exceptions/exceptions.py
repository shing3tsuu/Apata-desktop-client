from typing import Any

class BaseAppError(Exception):
    pass

class UserAlreadyExistsError(BaseAppError):
    pass

class UserNotRegisteredError(BaseAppError):
    pass

class ContactAlreadyExistsError(BaseAppError):
    pass

class AuthenticationError(BaseAppError):
    pass

class InfrastructureError(BaseAppError):
    def __init__(self, message: str, original_error: Exception | None = None):
        self.message = message
        self.original_error = original_error
        super().__init__(self.message)

class NetworkError(InfrastructureError):
    pass

class APIError(BaseAppError):
    def __init__(self, message: str, status_code: int | None = None,
                 response_data: dict[str, Any] | None = None):
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(message)

    @property
    def is_client_error(self) -> bool:
        return self.status_code is not None and 400 <= self.status_code < 500

    @property
    def is_server_error(self) -> bool:
        return self.status_code is not None and 500 <= self.status_code < 600

class ValidationError(BaseAppError):
    def __init__(self, message: str, field: str | None = None):
        self.field = field
        super().__init__(message)

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