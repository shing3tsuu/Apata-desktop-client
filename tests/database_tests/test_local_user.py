import logging
from uuid import uuid4

import pytest
from dishka import Scope, make_async_container
from pydantic import ValidationError

from src.adapters.database.dto import AddLocalUserDTO, RequestLocalUserDTO
from src.adapters.database.service import LocalUserService
from src.adapters.encryption.dao import AbstractEDSignature, AbstractPasswordHasher
from src.exceptions import UserAlreadyExistsError, UserNotFoundError
from src.providers import AppProvider
from tests.providers import MockDBProvider
from tests.timing_wrapper import timer


@pytest.fixture
async def container():
    container = make_async_container(
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
async def ed_signer(container):
    async with container() as request_container:
        signer = await request_container.get(AbstractEDSignature)
        yield signer


@pytest.fixture
async def password_hasher(container):
    async with container() as request_container:
        hasher = await request_container.get(AbstractPasswordHasher)
        yield hasher


@pytest.mark.asyncio
@timer()
async def test_add_user(local_user_service, ed_signer, password_hasher):
    ed_public_key = (await ed_signer.generate_key_pair())[1]
    hashed_password = await password_hasher.hashing("testpass")

    user_data = AddLocalUserDTO(
        server_user_id=uuid4(),
        username="testuser",
        ed_public_key=ed_public_key,
        hashed_password=hashed_password,
        timezone=3,
    )
    created = await local_user_service.add_user(user_data)
    assert created.id is not None
    assert created.username == "testuser"
    assert created.ed_public_key.strip() == ed_public_key.strip()
    assert created.hashed_password == hashed_password
    assert created.timezone == 3


@pytest.mark.asyncio
@timer()
async def test_add_user_duplicate_raises(local_user_service, ed_signer, password_hasher):
    ed_public_key = (await ed_signer.generate_key_pair())[1]
    hashed_password = await password_hasher.hashing("testpass")

    user_data = AddLocalUserDTO(
        server_user_id=uuid4(),
        username="duplicate",
        ed_public_key=ed_public_key,
        hashed_password=hashed_password,
        timezone=0,
    )
    await local_user_service.add_user(user_data)
    with pytest.raises(UserAlreadyExistsError):
        await local_user_service.add_user(user_data)


@pytest.mark.asyncio
@timer()
async def test_get_user_by_username(local_user_service, ed_signer, password_hasher):
    ed_public_key = (await ed_signer.generate_key_pair())[1]
    hashed_password = await password_hasher.hashing("testpass")

    user_data = AddLocalUserDTO(
        server_user_id=uuid4(),
        username="getuser",
        ed_public_key=ed_public_key,
        hashed_password=hashed_password,
        timezone=2,
    )
    created = await local_user_service.add_user(user_data)

    retrieved = await local_user_service.get_user_by_username("getuser")
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.username == "getuser"
    assert retrieved.ed_public_key.strip() == ed_public_key.strip()


@pytest.mark.asyncio
@timer()
async def test_get_user_by_id(local_user_service, ed_signer, password_hasher):
    ed_public_key = (await ed_signer.generate_key_pair())[1]
    hashed_password = await password_hasher.hashing("testpass")

    user_data = AddLocalUserDTO(
        server_user_id=uuid4(),
        username="iduser",
        ed_public_key=ed_public_key,
        hashed_password=hashed_password,
        timezone=1,
    )
    created = await local_user_service.add_user(user_data)

    retrieved = await local_user_service.get_user_by_id(created.id)
    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.username == "iduser"
    assert retrieved.ed_public_key.strip() == ed_public_key.strip()


@pytest.mark.asyncio
@timer()
async def test_get_user_by_username_not_found(local_user_service):
    with pytest.raises(UserNotFoundError, match="Local user not found"):
        await local_user_service.get_user_by_username("nonexistent")


@pytest.mark.asyncio
@timer()
async def test_update_user_data(local_user_service, ed_signer, password_hasher):
    ed_public_key = (await ed_signer.generate_key_pair())[1]
    hashed_password = await password_hasher.hashing("testpass")
    new_ed_public_key = (await ed_signer.generate_key_pair())[1]
    new_hashed_password = await password_hasher.hashing("newpassword")

    user_data = AddLocalUserDTO(
        server_user_id=uuid4(),
        username="updateuser",
        ed_public_key=ed_public_key,
        hashed_password=hashed_password,
        timezone=1,
    )
    created = await local_user_service.add_user(user_data)

    update_dto = RequestLocalUserDTO(
        id=created.id,
        server_user_id=created.server_user_id,
        username="updateuser",
        ed_public_key=new_ed_public_key,
        hashed_password=new_hashed_password,
        timezone=5,
    )
    updated = await local_user_service.update_user_data(update_dto)
    assert updated is not None
    assert updated.ed_public_key.strip() == new_ed_public_key.strip()
    assert updated.hashed_password == new_hashed_password
    assert updated.timezone == 5


@pytest.mark.asyncio
@timer()
async def test_delete_user(local_user_service, ed_signer, password_hasher):
    ed_public_key = (await ed_signer.generate_key_pair())[1]
    hashed_password = await password_hasher.hashing("testpass")

    user_data = AddLocalUserDTO(
        server_user_id=uuid4(),
        username="deleteuser",
        ed_public_key=ed_public_key,
        hashed_password=hashed_password,
        timezone=0,
    )
    await local_user_service.add_user(user_data)

    deleted = await local_user_service.delete_user("deleteuser")
    assert deleted is True

    with pytest.raises(UserNotFoundError, match="Local user not found"):
        await local_user_service.get_user_by_username("deleteuser")


@pytest.mark.asyncio
@timer()
async def test_add_user_invalid_ed_public_key(local_user_service, password_hasher):
    hashed_password = await password_hasher.hashing("testpass")

    with pytest.raises(ValidationError) as exc_info:
        AddLocalUserDTO(
            server_user_id=uuid4(),
            username="invalidkey",
            ed_public_key="not_a_valid_pem_key",
            hashed_password=hashed_password,
            timezone=0,
        )

    assert "ed_public_key" in str(exc_info.value)
    assert "Invalid ED public key" in str(exc_info.value)


@pytest.mark.asyncio
@timer()
async def test_add_user_invalid_hashed_password(local_user_service, ed_signer):
    ed_public_key = (await ed_signer.generate_key_pair())[1]

    with pytest.raises(ValidationError) as exc_info:
        AddLocalUserDTO(
            server_user_id=uuid4(),
            username="invalidhash",
            ed_public_key=ed_public_key,
            hashed_password="not_a_valid_hash",
            timezone=0,
        )

    assert "hashed_password" in str(exc_info.value)
    assert "Invalid hashed password" in str(exc_info.value)
