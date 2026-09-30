import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from src.adapters.api.dto import ContactPageDTO, ContactPublicDTO
from src.adapters.database.dto import RequestContactDTO
from src.adapters.database.structures import ContactStatusEnum
from src.adapters.encryption.service import EncryptionService
from src.exceptions import (
    APIError,
    AuthenticationError,
    UserNotFoundError,
    ValidationError,
)

from ..dao.auth import AuthHTTPDAO
from ..dao.contact import ContactHTTPDAO


class ContactHTTPService:
    def __init__(
        self,
        contact_dao: ContactHTTPDAO,
        auth_dao: AuthHTTPDAO,
        encryption_service: EncryptionService,
        logger: logging.Logger | None = None,
    ):
        self._contact_dao = contact_dao
        self._auth_dao = auth_dao
        self._encryption_service = encryption_service
        self._logger = logger or logging.getLogger(__name__)
        self._current_token: str | None = None

    @property
    def token(self) -> str | None:
        return self._current_token

    @token.setter
    def token(self, value: str) -> None:
        if not value:
            raise ValueError("Token cannot be empty")
        self._current_token = value

    @token.deleter
    def token(self) -> None:
        self._current_token = None

    async def search_contacts(
        self,
        username: str,
        after_id: str | None = None,
    ) -> ContactPageDTO:
        token = self.token
        if token is None:
            raise AuthenticationError(
                "Authentication required for contact operations",
                context={"operation": "contact_service"},
            )

        if not username or len(username) < 2:
            raise ValidationError(
                "Username must be at least 2 characters",
                field="username",
            )

        try:
            return await self._contact_dao.search_contacts(
                username=username,
                token=token,
                after_id=after_id,
            )
        except AuthenticationError:
            del self.token
            raise

    async def search_all_contacts(self, username: str) -> list[ContactPublicDTO]:
        contacts_by_user_id: dict[str, ContactPublicDTO] = {}
        after_id: str | None = None
        visited_cursors: set[str] = set()

        while True:
            page = await self.search_contacts(username, after_id=after_id)
            for contact in page.items:
                contacts_by_user_id.setdefault(contact.user_id, contact)
            next_after_id = page.next_after_id
            if next_after_id is None or next_after_id in visited_cursors:
                return list(contacts_by_user_id.values())
            visited_cursors.add(next_after_id)
            after_id = next_after_id

    async def search_users(self, username: str) -> list[dict[str, Any]]:
        contacts = await self.search_all_contacts(username)
        return [item.as_dict() for item in contacts]

    async def list_contacts(self, after_id: str | None = None) -> ContactPageDTO:
        token = self.token
        if token is None:
            raise AuthenticationError(
                "Authentication required for contact operations",
                context={"operation": "contact_service"},
            )

        try:
            return await self._contact_dao.list_contacts(
                token=token,
                after_id=after_id,
            )
        except AuthenticationError:
            del self.token
            raise

    async def list_all_contacts(
        self,
        after_id: str | None = None,
    ) -> list[ContactPublicDTO]:
        contacts_by_user_id: dict[str, ContactPublicDTO] = {}
        visited_cursors: set[str] = set()

        while True:
            page = await self.list_contacts(after_id=after_id)
            for contact in page.items:
                contacts_by_user_id.setdefault(contact.user_id, contact)
            next_after_id = page.next_after_id
            if next_after_id is None or next_after_id in visited_cursors:
                return list(contacts_by_user_id.values())
            visited_cursors.add(next_after_id)
            after_id = next_after_id

    async def create_contact_request(self, receiver_id: str) -> ContactPublicDTO:
        token = self.token
        if token is None:
            raise AuthenticationError(
                "Authentication required for contact operations",
                context={"operation": "contact_service"},
            )

        if not receiver_id:
            raise ValidationError("Invalid receiver ID", field="receiver_id")

        try:
            return await self._contact_dao.create_contact_request(
                receiver_id=str(receiver_id),
                token=token,
            )
        except AuthenticationError:
            del self.token
            raise
        except APIError as error:
            if error.status_code == 404:
                raise UserNotFoundError(
                    f"User {receiver_id} not found",
                    context={"receiver_id": receiver_id},
                ) from error
            raise

    async def send_contact_request(self, receiver_id: str) -> dict[str, Any]:
        return (
            await self.create_contact_request(receiver_id=str(receiver_id))
        ).as_dict()

    async def answer_contact_request(
        self,
        contact_id: str,
        action: str,
    ) -> ContactPublicDTO:
        token = self.token
        if token is None:
            raise AuthenticationError(
                "Authentication required for contact operations",
                context={"operation": "contact_service"},
            )

        if not contact_id:
            raise ValidationError("Invalid contact request ID", field="contact_id")
        if action not in {"accept", "reject"}:
            raise ValidationError("Invalid contact answer action", field="action")

        try:
            return await self._contact_dao.answer_contact_request(
                contact_id=str(contact_id),
                action=action,
                token=token,
            )
        except AuthenticationError:
            del self.token
            raise

    async def accept_contact_request(self, receiver_id: str) -> dict[str, Any]:
        return (
            await self.answer_contact_request(
                contact_id=str(receiver_id),
                action="accept",
            )
        ).as_dict()

    async def reject_contact_request(self, receiver_id: str) -> dict[str, Any]:
        return (
            await self.answer_contact_request(
                contact_id=str(receiver_id),
                action="reject",
            )
        ).as_dict()

    async def accept_contact_request_dto(self, contact_id: str) -> ContactPublicDTO:
        return await self.answer_contact_request(
            contact_id=str(contact_id),
            action="accept",
        )

    async def reject_contact_request_dto(self, contact_id: str) -> ContactPublicDTO:
        return await self.answer_contact_request(
            contact_id=str(contact_id),
            action="reject",
        )

    async def blacklist_contact(self, user_id: str) -> ContactPublicDTO:
        token = self.token
        if token is None:
            raise AuthenticationError(
                "Authentication required for contact operations",
                context={"operation": "contact_service"},
            )
        if not user_id:
            raise ValidationError("Invalid user ID", field="user_id")

        try:
            return await self._contact_dao.blacklist_contact(
                user_id=str(user_id),
                token=token,
            )
        except AuthenticationError:
            del self.token
            raise

    async def get_contacts(
        self,
        local_user_id: Any,
        server_user_id: Any | None = None,
        ed_dict: dict[Any, str] | None = None,
        after_id: str | None = None,
    ) -> list[RequestContactDTO]:
        contacts = await self.list_all_contacts(after_id=after_id)
        return [
            self._contact_to_request_dto(item, local_user_id) for item in contacts
        ]

    async def get_pending_contact_requests(
        self,
        user_id: Any | None = None,
    ) -> list[dict[str, Any]]:
        contacts = await self.list_all_contacts()
        return [
            item.as_dict() for item in contacts if item.status == "pending(incoming)"
        ]

    async def contact_data_synchronization(
        self,
        users_ids: list[Any],
    ) -> list[dict[str, Any]]:
        contacts = await self.list_all_contacts()
        requested_ids = {str(user_id) for user_id in users_ids}
        return [item.as_dict() for item in contacts if item.user_id in requested_ids]

    def _contact_to_request_dto(
        self,
        item: ContactPublicDTO,
        local_user_id: Any,
    ) -> RequestContactDTO:
        last_seen = (
            datetime.fromisoformat(item.last_seen.replace("Z", "+00:00"))
            if item.last_seen is not None
            else None
        )
        return RequestContactDTO(
            local_user_id=local_user_id,
            server_user_id=UUID(item.user_id),
            username=item.username,
            status=ContactStatusEnum(item.status),
            ed_public_key=item.ed_public_key,
            ecdh_public_key=item.ecdh_public_key,
            last_seen=last_seen,
            online=item.online,
        )
