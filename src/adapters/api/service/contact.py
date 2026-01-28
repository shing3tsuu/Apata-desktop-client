from typing import Any, List, Dict
import logging

from ..dao.contact import ContactHTTPDAO
from ..dao.auth import AuthHTTPDAO
from src.adapters.database.dto import ContactRequestDTO
from src.adapters.encryption.service import EncryptionService
from src.exceptions import *

class ContactHTTPService:
    def __init__(
            self,
            contact_dao: ContactHTTPDAO,
            auth_dao: AuthHTTPDAO,
            encryption_service: EncryptionService,
            logger: logging.Logger = None
    ):
        self._contact_dao = contact_dao
        self._auth_dao = auth_dao
        self._encryption_service = encryption_service
        self._logger = logger or logging.getLogger(__name__)
        self._current_token: str | None = None

    def set_token(self, token: str):
        if not token:
            raise ValidationError("Token cannot be empty")
        self._current_token = token
        self._logger.debug("Contact service token set")

    def clear_token(self):
        self._current_token = None
        self._logger.debug("Contact service token cleared")

    def _validate_session(self):
        if not self._current_token:
            raise AuthenticationError(
                "Authentication required for contact operations",
                context={"operation": "contact_service"}
            )

    async def search_users(self, username: str) -> List[Dict[str, Any]]:
        self._validate_session()

        if not username or len(username) < 2:
            raise ValidationError(
                "Username must be at least 2 characters",
                field="username"
            )

        self._logger.info(f"Searching users with query: '{username}'")

        try:
            result = await self._contact_dao.search_users(
                username=username,
                token=self._current_token
            )

            self._logger.info(f"Found {len(result)} users for query: '{username}'")
            return result

        except AuthenticationError as e:
            self.clear_token()
            raise AuthenticationError(
                "Session expired, please login again",
                original_error=e
            )

        except (APIError, NetworkError) as e:
            self._logger.warning(
                f"Search failed for query '{username}': {e.message}",
                extra={"error_type": e.__class__.__name__}
            )
            return []

        except Exception as e:
            self._logger.error(
                f"Unexpected error during user search: {e}",
                exc_info=True
            )
            return []

    async def contact_data_synchronization(self, users_ids: List[int]) -> list[dict[str, Any]]:
        self._validate_session()

        if not users_ids:
            self._logger.debug("No user IDs provided for synchronization")
            return []

        self._logger.info(f"Synchronizing data for {len(users_ids)} users")

        try:
            result = await self._contact_dao.get_users_data(
                users_ids=users_ids,
                token=self._current_token
            )

            self._logger.info(f"Synchronized {len(result)} users successfully")
            return result

        except AuthenticationError as e:
            self.clear_token()
            raise AuthenticationError(
                "Session expired during contact sync",
                original_error=e
            )

        except (APIError, NetworkError) as e:
            self._logger.warning(
                f"Contact sync failed for {len(users_ids)} users: {e.message}"
            )
            return []

        except Exception as e:
            self._logger.error(
                f"Unexpected error during contact sync: {e}",
                exc_info=True
            )
            return []

    async def get_contacts(
            self,
            local_user_id: int,
            server_user_id: int,
            ecdsa_dict: dict[int, str]
    ) -> list[ContactRequestDTO]:
        self._validate_session()

        try:
            contacts = await self._contact_dao.get_contacts(token=self._current_token)
            if not contacts:
                return []

            status_map = {}
            contact_ids = []
            for c in contacts:
                other_id = c['receiver_id'] if c['sender_id'] == server_user_id else c['sender_id']
                if other_id:
                    status_map[other_id] = c['status']
                    contact_ids.append(other_id)

            users_data = await self._contact_dao.get_users_data(contact_ids, self._current_token) if contact_ids else []

            return [
                ContactRequestDTO(
                    local_user_id=local_user_id,
                    server_user_id=ud['id'],
                    username=ud.get('username', ''),
                    status=status_map.get(ud['id'], 'none'),
                    ecdsa_public_key=ecdsa_dict.get(ud['id']) or ud.get('ecdsa_public_key', ''),
                    ecdh_public_key=ud.get('ecdh_public_key', ''),
                    last_seen=ud.get('last_seen', ''),
                    online=ud.get('online', False),
                )
                for ud in users_data
                if ud.get('id') and await self._validate_signature(ud, ecdsa_dict)
            ]

        except AuthenticationError:
            self.clear_token()
            raise
        except (APIError, NetworkError):
            return []
        except Exception as e:
            self._logger.error(f"Contact loading error: {e}")
            return []

    async def _validate_signature(self, user_data: dict, ecdsa_dict: dict[int, str]) -> bool:
        try:
            ecdsa_key = ecdsa_dict.get(user_data['id']) or user_data.get('ecdsa_public_key')
            return bool(ecdsa_key and await self._encryption_service.verify_signature(
                public_key_pem=ecdsa_key,
                string=user_data.get('ecdh_public_key', ''),
                signature=user_data.get('ecdh_signature', '')
            ))
        except:
            return False

    async def send_contact_request(self, receiver_id: int) -> dict[str, Any]:
        self._validate_session()

        if not receiver_id or receiver_id <= 0:
            raise ValidationError(
                "Invalid receiver ID",
                field="receiver_id"
            )

        self._logger.info(f"Sending contact request to user {receiver_id}")

        try:
            result = await self._contact_dao.send_contact_request(
                receiver_id=receiver_id,
                token=self._current_token
            )

            self._logger.info(
                f"Contact request sent to user {receiver_id}",
                extra={"request_id": result.get('id')}
            )
            return result

        except AuthenticationError as e:
            self.clear_token()
            raise AuthenticationError(
                "Session expired while sending contact request",
                original_error=e
            )

        except APIError as e:
            if e.status_code == 404:
                raise UserNotFoundError(
                    f"User {receiver_id} not found",
                    context={"receiver_id": receiver_id}
                )
            elif e.status_code == 409:
                raise ValidationError(
                    "Contact request already exists or user is already a contact",
                    context={"receiver_id": receiver_id}
                )
            else:
                self._logger.warning(
                    f"Failed to send contact request: {e.message}",
                    extra={"receiver_id": receiver_id}
                )
                return {}

        except (NetworkError, Exception) as e:
            self._logger.warning(
                f"Failed to send contact request: {e}",
                extra={"receiver_id": receiver_id}
            )
            return {}

    async def get_pending_contact_requests(self, user_id: int) -> list[dict[str, Any]]:
        self._validate_session()

        if not user_id or user_id <= 0:
            raise ValidationError("Invalid user ID")

        self._logger.info(f"Getting pending contact requests for user {user_id}")

        try:
            requests = await self._contact_dao.get_contact_requests(
                user_id=user_id,
                token=self._current_token
            )

            self._logger.info(f"Found {len(requests)} pending requests")
            return requests

        except AuthenticationError as e:
            self.clear_token()
            raise AuthenticationError(
                "Session expired while fetching contact requests",
                original_error=e
            )

        except (APIError, NetworkError) as e:
            self._logger.warning(
                f"Failed to get pending requests: {e.message}"
            )
            return []

        except Exception as e:
            self._logger.error(
                f"Unexpected error getting pending requests: {e}",
                exc_info=True
            )
            return []

    async def accept_contact_request(self, receiver_id: int) -> dict[str, Any]:
        self._validate_session()

        if not receiver_id or receiver_id <= 0:
            raise ValidationError("Invalid receiver ID")

        self._logger.info(f"Accepting contact request from user {receiver_id}")

        try:
            result = await self._contact_dao.accept_contact_request(
                receiver_id=receiver_id,
                token=self._current_token
            )

            self._logger.info(f"Accepted contact request from user {receiver_id}")
            return result

        except AuthenticationError as e:
            self.clear_token()
            raise AuthenticationError(
                "Session expired while accepting contact request",
                original_error=e
            )

        except APIError as e:
            if e.status_code == 404:
                raise UserNotFoundError(
                    f"Contact request from user {receiver_id} not found"
                )
            else:
                self._logger.warning(
                    f"Failed to accept contact request: {e.message}"
                )
                return {}

        except (NetworkError, Exception) as e:
            self._logger.warning(
                f"Failed to accept contact request: {e}"
            )
            return {}

    async def reject_contact_request(self, receiver_id: int) -> dict[str, Any]:
        self._validate_session()

        if not receiver_id or receiver_id <= 0:
            raise ValidationError("Invalid receiver ID")

        self._logger.info(f"Rejecting contact request from user {receiver_id}")

        try:
            result = await self._contact_dao.reject_contact_request(
                receiver_id=receiver_id,
                token=self._current_token
            )

            self._logger.info(f"Rejected contact request from user {receiver_id}")
            return result

        except AuthenticationError as e:
            self.clear_token()
            raise AuthenticationError(
                "Session expired while rejecting contact request",
                original_error=e
            )

        except APIError as e:
            if e.status_code == 404:
                raise UserNotFoundError(
                    f"Contact request from user {receiver_id} not found"
                )
            else:
                self._logger.warning(
                    f"Failed to reject contact request: {e.message}"
                )
                return {}

        except (NetworkError, Exception) as e:
            self._logger.warning(
                f"Failed to reject contact request: {e}"
            )
            return {}