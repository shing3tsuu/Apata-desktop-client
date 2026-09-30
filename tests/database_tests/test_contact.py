# tests/database_tests/test_contact.py
import logging
import pytest
from uuid import uuid4
from dishka import make_async_container, Scope

from src.adapters.database.dto import (
    AddContactDTO,
    RequestContactDTO,
    AddLocalUserDTO,
)
from src.adapters.database.service import ContactService, LocalUserService
from src.adapters.database.structures import ContactStatusEnum
from src.adapters.encryption.dao import (
    AbstractEDSignature,
    AbstractPasswordHasher,
    AbstractECDHCipher,
)
from src.providers import AppProvider, StateProvider
from src.providers.state import AppState
from src.presentation.interactors.messenger import SearchContactsLocalInteractor
from src.exceptions import ContactAlreadyExistsError, ContactNotFoundError

from tests.providers import MockDBProvider
from tests.timing_wrapper import timer


@pytest.fixture
async def container():
    container = make_async_container(
        StateProvider(),
        AppProvider(
            scope=Scope.APP,
            logger=logging.getLogger(__name__),
            symmetric_cipher="AESGCMSIV",
            asymmetric_cipher="X25519",
            signature_cipher="ED-25519",
            password_cipher="BCRYPT",
            base_url="https://test.com",
            verify_ssl=False,
            base_ws_url="wss://test.com",
        ),
        MockDBProvider(),
    )
    yield container
    await container.close()


@pytest.fixture
async def local_user_service(container):
    async with container() as request_container:
        service = await request_container.get(LocalUserService)
        yield service


@pytest.fixture
async def contact_service(container):
    async with container() as request_container:
        service = await request_container.get(ContactService)
        yield service


@pytest.fixture
async def ed_signer(container):
    async with container() as request_container:
        signer = await request_container.get(AbstractEDSignature)
        yield signer


@pytest.fixture
async def password_hasher(container):
    async with container() as request_container:
        hasher = await request_container.get(AbstractPasswordHasher)
        yield hasher


@pytest.fixture
async def ecdh_public_key(container):
    async with container() as request_container:
        ecdh_cipher = await request_container.get(AbstractECDHCipher)
        _, public_key = await ecdh_cipher.generate_key_pair()
        return public_key


@pytest.fixture
async def test_user(local_user_service, ed_signer, password_hasher):
    ed_public_key = (await ed_signer.generate_key_pair())[1]
    hashed_password = await password_hasher.hashing("testpass")
    user_data = AddLocalUserDTO(
        server_user_id=uuid4(),
        username="testuser",
        ed_public_key=ed_public_key,
        hashed_password=hashed_password,
        timezone=0,
    )
    user = await local_user_service.add_user(user_data)
    return user


@pytest.fixture
async def test_contact_user(local_user_service, ed_signer, password_hasher):
    ed_public_key = (await ed_signer.generate_key_pair())[1]
    hashed_password = await password_hasher.hashing("testpass")
    user_data = AddLocalUserDTO(
        server_user_id=uuid4(),
        username="contactuser",
        ed_public_key=ed_public_key,
        hashed_password=hashed_password,
        timezone=0,
    )
    user = await local_user_service.add_user(user_data)
    return user


@pytest.mark.asyncio
@timer()
async def test_add_contact_success(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.BLANK,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    contact = await contact_service.add_contact(add_dto)
    assert contact.id is not None
    assert contact.local_user_id == test_user.id
    assert contact.server_user_id == test_contact_user.server_user_id
    assert contact.username == test_contact_user.username
    assert contact.status == ContactStatusEnum.BLANK


@pytest.mark.asyncio
@timer()
async def test_add_contact_normalizes_hidden_presence_for_not_null_columns(
    contact_service,
    test_user,
    test_contact_user,
    ecdh_public_key,
):
    contact = await contact_service.add_contact(
        AddContactDTO(
            local_user_id=test_user.id,
            server_user_id=test_contact_user.server_user_id,
            status=ContactStatusEnum.BLANK,
            username=test_contact_user.username,
            ed_public_key=test_contact_user.ed_public_key,
            ecdh_public_key=ecdh_public_key,
            last_seen=None,
            online=None,
        )
    )

    assert contact.online is False
    assert contact.last_seen is not None


@pytest.mark.asyncio
@timer()
async def test_add_contact_already_exists(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.BLANK,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    await contact_service.add_contact(add_dto)
    with pytest.raises(ContactAlreadyExistsError):
        await contact_service.add_contact(add_dto)


@pytest.mark.asyncio
@timer()
async def test_get_contact_by_id(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.BLANK,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    created = await contact_service.add_contact(add_dto)
    fetched = await contact_service.get_contact_by_id(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.local_user_id == test_user.id


@pytest.mark.asyncio
@timer()
async def test_get_contact_by_username(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.BLANK,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    created = await contact_service.add_contact(add_dto)
    fetched = await contact_service.get_contact_by_username(
        local_user_id=test_user.id,
        username=test_contact_user.username
    )
    assert fetched is not None
    assert fetched.id == created.id


@pytest.mark.asyncio
@timer()
async def test_search_contacts_by_username(
    contact_service,
    test_user,
    test_contact_user,
    ecdh_public_key,
):
    async def add_contact(local_user_id, username):
        return await contact_service.add_contact(
            AddContactDTO(
                local_user_id=local_user_id,
                server_user_id=uuid4(),
                status=ContactStatusEnum.ACCEPTED,
                username=username,
                ed_public_key=test_contact_user.ed_public_key,
                ecdh_public_key=ecdh_public_key,
            )
        )

    await add_contact(test_user.id, "Alice")
    await add_contact(test_user.id, "ALICIA")
    await add_contact(test_user.id, "malice")
    await add_contact(test_user.id, "bob")
    await add_contact(test_user.id, "percent%user")
    await add_contact(test_contact_user.id, "alice_foreign")

    matches = await contact_service.search_contacts_by_username(test_user.id, "ALI")
    assert [contact.username for contact in matches] == [
        "Alice",
        "ALICIA",
        "malice",
    ]
    assert all(contact.local_user_id == test_user.id for contact in matches)

    exact_matches = await contact_service.search_contacts_by_username(
        test_user.id,
        "alice",
    )
    assert exact_matches[0].username == "Alice"

    wildcard_matches = await contact_service.search_contacts_by_username(
        test_user.id,
        "%",
    )
    assert [contact.username for contact in wildcard_matches] == ["percent%user"]
    assert await contact_service.search_contacts_by_username(test_user.id, "   ") == []


@pytest.mark.asyncio
@timer()
async def test_search_contacts_local_interactor(
    container,
    contact_service,
    test_user,
    test_contact_user,
    ecdh_public_key,
):
    await contact_service.add_contact(
        AddContactDTO(
            local_user_id=test_user.id,
            server_user_id=test_contact_user.server_user_id,
            status=ContactStatusEnum.ACCEPTED,
            username=test_contact_user.username,
            ed_public_key=test_contact_user.ed_public_key,
            ecdh_public_key=ecdh_public_key,
        )
    )
    async with container() as request_container:
        app_state = await request_container.get(AppState)
        app_state.local_user_id = test_user.id

    contacts = await SearchContactsLocalInteractor()(
        container=container,
        username="TACT",
    )

    assert [contact.username for contact in contacts] == [test_contact_user.username]
    assert await SearchContactsLocalInteractor()(container, "   ") == []


@pytest.mark.asyncio
@timer()
async def test_get_contacts(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.BLANK,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    await contact_service.add_contact(add_dto)
    contacts = await contact_service.get_contacts(test_user.id)
    assert len(contacts) >= 1
    assert any(c.username == test_contact_user.username for c in contacts)


@pytest.mark.asyncio
@timer()
async def test_update_contact(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.BLANK,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    created = await contact_service.add_contact(add_dto)

    update_dto = RequestContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        username="newusername",
    )
    updated = await contact_service.update_contact(update_dto)
    assert updated is not None
    assert updated.username == "newusername"
    assert updated.last_seen == created.last_seen
    assert updated.online == created.online


@pytest.mark.asyncio
@timer()
async def test_update_contact_normalizes_hidden_presence_for_not_null_columns(
    contact_service,
    test_user,
    test_contact_user,
    ecdh_public_key,
):
    await contact_service.add_contact(
        AddContactDTO(
            local_user_id=test_user.id,
            server_user_id=test_contact_user.server_user_id,
            status=ContactStatusEnum.BLANK,
            username=test_contact_user.username,
            ed_public_key=test_contact_user.ed_public_key,
            ecdh_public_key=ecdh_public_key,
        )
    )

    updated = await contact_service.update_contact(
        RequestContactDTO(
            local_user_id=test_user.id,
            server_user_id=test_contact_user.server_user_id,
            last_seen=None,
            online=None,
        )
    )

    assert updated is not None
    assert updated.online is False
    assert updated.last_seen is not None


@pytest.mark.asyncio
@timer()
async def test_delete_contact(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.BLANK,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    created = await contact_service.add_contact(add_dto)
    deleted = await contact_service.delete_contact(created.id)
    assert deleted is True

    with pytest.raises(ContactNotFoundError):
        await contact_service.get_contact_by_id(created.id)


@pytest.mark.asyncio
@timer()
async def test_send_contact_request(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.BLANK,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    created = await contact_service.add_contact(add_dto)
    updated = await contact_service.send_contact_request(created.id)
    assert updated.status == ContactStatusEnum.PENDING_OUTGOING


@pytest.mark.asyncio
@timer()
async def test_accept_contact_request(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.BLANK,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    created = await contact_service.add_contact(add_dto)
    updated = await contact_service.accept_contact_request(created.id)
    assert updated.status == ContactStatusEnum.ACCEPTED


@pytest.mark.asyncio
@timer()
async def test_reject_contact_request(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.BLANK,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    created = await contact_service.add_contact(add_dto)
    updated = await contact_service.reject_contact_request(created.id)
    assert updated.status == ContactStatusEnum.BLANK


@pytest.mark.asyncio
@timer()
async def test_block_contact(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.BLANK,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    created = await contact_service.add_contact(add_dto)
    updated = await contact_service.block_contact(created.id)
    assert updated.status == ContactStatusEnum.BLACKLIST


@pytest.mark.asyncio
@timer()
async def test_unblock_contact(contact_service, test_user, test_contact_user, ecdh_public_key):
    add_dto = AddContactDTO(
        local_user_id=test_user.id,
        server_user_id=test_contact_user.server_user_id,
        status=ContactStatusEnum.BLACKLIST,
        username=test_contact_user.username,
        ed_public_key=test_contact_user.ed_public_key,
        ecdh_public_key=ecdh_public_key,
    )
    created = await contact_service.add_contact(add_dto)
    updated = await contact_service.unblock_contact(created.id)
    assert updated.status == ContactStatusEnum.BLANK


@pytest.mark.asyncio
@timer()
async def test_contact_not_found(contact_service):
    fake_id = uuid4()
    with pytest.raises(ContactNotFoundError):
        await contact_service.get_contact_by_id(fake_id)
    with pytest.raises(ContactNotFoundError):
        await contact_service.send_contact_request(fake_id)
    with pytest.raises(ContactNotFoundError):
        await contact_service.accept_contact_request(fake_id)
    with pytest.raises(ContactNotFoundError):
        await contact_service.reject_contact_request(fake_id)
    with pytest.raises(ContactNotFoundError):
        await contact_service.block_contact(fake_id)
    with pytest.raises(ContactNotFoundError):
        await contact_service.unblock_contact(fake_id)
