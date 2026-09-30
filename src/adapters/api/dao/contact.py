from typing import Any

from src.adapters.api.dto import ContactPageDTO, ContactPublicDTO
from src.exceptions import APIError

from .common import CommonHTTPClient


class ContactHTTPDAO:
    def __init__(self, http_client: CommonHTTPClient):
        self._http_client = http_client

    @staticmethod
    def _expect_object(response: dict[str, Any] | list[Any]) -> dict[str, Any]:
        if isinstance(response, dict):
            return response

        raise APIError(
            "Expected JSON object response from contacts API",
            response_data={"response_type": type(response).__name__},
        )

    async def search_contacts(
        self,
        username: str,
        token: str,
        after_id: str | None = None,
    ) -> ContactPageDTO:
        self._http_client.set_auth_token(token)
        params = {"username": username}
        if after_id is not None:
            params["after_id"] = after_id
        response = self._expect_object(
            await self._http_client.get(
                "/contacts/search",
                params=params,
            )
        )
        return ContactPageDTO.from_mapping(response)

    async def list_contacts(
        self,
        token: str,
        after_id: str | None = None,
    ) -> ContactPageDTO:
        self._http_client.set_auth_token(token)
        params = {"after_id": after_id} if after_id is not None else None
        response = self._expect_object(
            await self._http_client.get("/contacts", params=params)
        )
        return ContactPageDTO.from_mapping(response)

    async def create_contact_request(
        self,
        receiver_id: str,
        token: str,
    ) -> ContactPublicDTO:
        self._http_client.set_auth_token(token)
        response = self._expect_object(
            await self._http_client.post(
                "/contacts",
                {"receiver_id": str(receiver_id)},
            )
        )
        return ContactPublicDTO.from_mapping(response)

    async def answer_contact_request(
        self,
        contact_id: str,
        action: str,
        token: str,
    ) -> ContactPublicDTO:
        self._http_client.set_auth_token(token)
        response = self._expect_object(
            await self._http_client.patch(
                f"/contacts/{contact_id}",
                {"action": action},
            )
        )
        return ContactPublicDTO.from_mapping(response)

    async def search_users(
        self,
        username: str,
        token: str,
        after_id: str | None = None,
    ) -> ContactPageDTO:
        return await self.search_contacts(
            username=username,
            token=token,
            after_id=after_id,
        )

    async def get_contacts(self, token: str) -> ContactPageDTO:
        return await self.list_contacts(token=token)

    async def send_contact_request(
        self,
        receiver_id: str,
        token: str,
    ) -> ContactPublicDTO:
        return await self.create_contact_request(receiver_id=receiver_id, token=token)

    async def accept_contact_request(
        self,
        receiver_id: str,
        token: str,
    ) -> ContactPublicDTO:
        return await self.answer_contact_request(
            contact_id=receiver_id,
            action="accept",
            token=token,
        )

    async def reject_contact_request(
        self,
        receiver_id: str,
        token: str,
    ) -> ContactPublicDTO:
        return await self.answer_contact_request(
            contact_id=receiver_id,
            action="reject",
            token=token,
        )

    async def blacklist_contact(
        self,
        user_id: str,
        token: str,
    ) -> ContactPublicDTO:
        self._http_client.set_auth_token(token)
        response = self._expect_object(
            await self._http_client.put(
                f"/contacts/{user_id}/blacklist",
                {},
            )
        )
        return ContactPublicDTO.from_mapping(response)
