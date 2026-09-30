import asyncio
import logging
import os
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from dishka import Scope, make_async_container

from src.adapters.api.dao import ContactHTTPDAO
from src.adapters.api.dto import ContactPageDTO, ContactPublicDTO
from src.adapters.api.service import AuthHTTPService, ContactHTTPService
from src.providers import AppProvider
from tests.timing_wrapper import timer

DEFAULT_API_BASE_URL = "http://127.0.0.1:8000"


def test_contact_http_service_token_property() -> None:
    service = ContactHTTPService(
        contact_dao=MagicMock(spec=ContactHTTPDAO),
        auth_dao=MagicMock(),
        encryption_service=MagicMock(),
    )

    assert service.token is None

    with pytest.raises(ValueError):
        service.token = ""

    service.token = "access-token"
    assert service.token == "access-token"

    del service.token
    assert service.token is None


def api_base_url() -> str:
    explicit_url = os.getenv("APATA_API_BASE_URL") or os.getenv("API_BASE_URL")
    if explicit_url is not None and explicit_url:
        return explicit_url.rstrip("/")
    return DEFAULT_API_BASE_URL


def _make_container():
    return make_async_container(
        AppProvider(
            scope=Scope.APP,
            logger=logging.getLogger(__name__),
            symmetric_cipher="AESGCMSIV",
            asymmetric_cipher="X25519",
            signature_cipher="ED-25519",
            password_cipher="BCRYPT",
            base_url=api_base_url(),
            verify_ssl=False,
            base_ws_url="ws://127.0.0.1:8001",
        )
    )


def _unique_username() -> str:
    return f"ct{uuid4().hex[:12]}"


async def _register_and_login(
    auth_service: AuthHTTPService,
) -> dict[str, Any]:
    username = _unique_username()
    register_response = await auth_service.register(username)
    login_response = await auth_service.login(
        username=username,
        ed_private_key=register_response.ed_private_key,
    )
    return {
        "id": register_response.id,
        "username": username,
        "access_token": login_response.access_token,
    }


def _find_contact(page: ContactPageDTO, user_id: str) -> ContactPublicDTO:
    matches = [item for item in page.items if item.user_id == user_id]
    assert len(matches) == 1
    return matches[0]


@timer()
def test_contact_service_live_request_flow() -> None:
    async def scenario() -> None:
        container = _make_container()
        try:
            async with container() as request_container:
                auth_service = await request_container.get(AuthHTTPService)
                contact_service = await request_container.get(ContactHTTPService)

                sender = await _register_and_login(auth_service)
                receiver = await _register_and_login(auth_service)

                contact_service.token = sender["access_token"]
                search_page = await contact_service.search_contacts(
                    receiver["username"]
                )
                search_contact = _find_contact(search_page, receiver["id"])

                outgoing = await contact_service.create_contact_request(receiver["id"])

                contact_service.token = receiver["access_token"]
                receiver_page = await contact_service.list_contacts()
                incoming = _find_contact(receiver_page, sender["id"])
                assert outgoing.contact_id is not None
                accepted = await contact_service.answer_contact_request(
                    contact_id=outgoing.contact_id,
                    action="accept",
                )

                contact_service.token = sender["access_token"]
                sender_page = await contact_service.list_contacts()
                sender_contact = _find_contact(sender_page, receiver["id"])

                blocked = await contact_service.blacklist_contact(receiver["id"])

                contact_service.token = receiver["access_token"]
                blocked_user_page = await contact_service.list_contacts()
                blocked_user_view = _find_contact(
                    blocked_user_page,
                    sender["id"],
                )
        finally:
            await container.close()

        assert search_contact.contact_id is None
        assert search_contact.status == "blank"
        assert search_contact.online is None
        assert search_contact.last_seen is None
        assert outgoing.user_id == receiver["id"]
        assert outgoing.status == "pending(outgoing)"
        assert outgoing.contact_id
        assert outgoing.online is None
        assert outgoing.last_seen is None
        assert incoming.user_id == sender["id"]
        assert incoming.status == "pending(incoming)"
        assert incoming.online is None
        assert incoming.last_seen is None
        assert accepted.user_id == sender["id"]
        assert accepted.status == "accepted"
        assert accepted.online is not None
        assert accepted.last_seen is not None
        assert sender_contact.status == "accepted"
        assert sender_contact.online is not None
        assert sender_contact.last_seen is not None
        assert blocked.status == "blacklist"
        assert blocked.online is None
        assert blocked.last_seen is None
        assert blocked_user_view.status == "blank"
        assert blocked_user_view.online is None
        assert blocked_user_view.last_seen is None

    asyncio.run(scenario())
