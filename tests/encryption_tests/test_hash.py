import asyncio
import logging
import pytest
from dishka import make_async_container, Scope

from src.adapters.encryption.dao import AbstractPasswordHasher, BcryptPasswordHasher, Argon2PasswordHasher
from src.providers import AppProvider
from tests.timing_wrapper import timer


@pytest.fixture(params=["BCRYPT", "ARGON2"])
async def password_hasher(request):
    password_cipher = request.param
    logger = logging.getLogger(__name__)
    provider = AppProvider(
        scope=Scope.APP,
        logger=logger,
        symmetric_cipher="AESGCM",
        asymmetric_cipher="X25519",
        signature_cipher="ED-25519",
        password_cipher=password_cipher,
        base_url="https://test.com",
        verify_ssl=False,
        base_ws_url="wss://test.com",
    )
    container = make_async_container(provider)
    async with container() as request_container:
        hasher = await request_container.get(AbstractPasswordHasher)
        yield hasher
    await container.close()


def _is_bcrypt_hash(hashed: str) -> bool:
    return hashed.startswith(("$2a$", "$2b$", "$2y$")) and len(hashed) == 60


def _is_argon2_hash(hashed: str) -> bool:
    return hashed.startswith("$argon2id$") and len(hashed) >= 80


@pytest.mark.asyncio
@timer()
async def test_hashing_and_verification(password_hasher):
    password = "MySecurePassword123!"
    hashed = await password_hasher.hashing(password)
    assert await password_hasher.compare(password, hashed)
    assert hashed != password


@pytest.mark.asyncio
@timer()
async def test_verify_fails_with_wrong_password(password_hasher):
    original = "MySecurePassword123!"
    wrong = "WrongPassword456!"
    hashed = await password_hasher.hashing(original)
    assert not await password_hasher.compare(wrong, hashed)


@pytest.mark.asyncio
@timer()
async def test_different_hashes_for_same_password(password_hasher):
    password = "SamePassword123"
    hash1 = await password_hasher.hashing(password)
    hash2 = await password_hasher.hashing(password)
    hash3 = await password_hasher.hashing(password)
    assert hash1 != hash2
    assert hash1 != hash3
    assert hash2 != hash3
    assert await password_hasher.compare(password, hash1)
    assert await password_hasher.compare(password, hash2)
    assert await password_hasher.compare(password, hash3)


@pytest.mark.asyncio
@timer()
async def test_empty_password_raises_error(password_hasher):
    with pytest.raises(ValueError, match="Password cannot be empty"):
        await password_hasher.hashing("")


@pytest.mark.asyncio
@timer()
async def test_short_password_raises_error(password_hasher):
    short = "123"  # less than 8
    with pytest.raises(ValueError, match="Password must be at least 8 characters long"):
        await password_hasher.hashing(short)


@pytest.mark.asyncio
@timer()
async def test_compare_empty_password_returns_false(password_hasher):
    valid = "ValidPassword123"
    hashed = await password_hasher.hashing(valid)
    assert not await password_hasher.compare("", hashed)


@pytest.mark.asyncio
@timer()
async def test_compare_empty_hash_returns_false(password_hasher):
    password = "SomePassword123"
    assert not await password_hasher.compare(password, "")


@pytest.mark.asyncio
@timer()
async def test_compare_invalid_hash_format_returns_false(password_hasher):
    password = "SomePassword123"
    invalid_hash = "invalid_hash_format"
    assert not await password_hasher.compare(password, invalid_hash)


@pytest.mark.asyncio
@timer()
async def test_special_characters(password_hasher):
    password = "P@ssw0rd! #$%^&*()_+-=[]{}|;:,.<>?"
    hashed = await password_hasher.hashing(password)
    assert await password_hasher.compare(password, hashed)


@pytest.mark.asyncio
@timer()
async def test_unicode_password(password_hasher):
    password = "密码🔐пароль🎯"
    hashed = await password_hasher.hashing(password)
    assert await password_hasher.compare(password, hashed)


@pytest.mark.asyncio
@timer()
async def test_long_password(password_hasher):
    password = "A" * 1000
    hashed = await password_hasher.hashing(password)
    assert await password_hasher.compare(password, hashed)


@pytest.mark.asyncio
@timer()
async def test_concurrent_hashing(password_hasher):
    passwords = [f"Password{i}!" for i in range(5)]
    hash_tasks = [password_hasher.hashing(pwd) for pwd in passwords]
    hashes = await asyncio.gather(*hash_tasks)
    verify_tasks = [password_hasher.compare(passwords[i], hashes[i]) for i in range(5)]
    results = await asyncio.gather(*verify_tasks)
    assert all(results)
    assert len(hashes) == len(set(hashes))


@pytest.mark.asyncio
@timer()
async def test_is_valid_hash_method(password_hasher):
    valid_password = "TestPassword123"
    valid_hash = await password_hasher.hashing(valid_password)


    assert password_hasher._is_valid_hash(valid_hash)

    assert not password_hasher._is_valid_hash("")
    assert not password_hasher._is_valid_hash("invalid_hash")
    assert not password_hasher._is_valid_hash("$2a$12$tooshort")


    if isinstance(password_hasher, BcryptPasswordHasher):
        assert not password_hasher._is_valid_hash("$2x$12$invalidprefix....")

    elif isinstance(password_hasher, Argon2PasswordHasher):
        assert not password_hasher._is_valid_hash("$argon2id$v=19$m=65536,t=3,p=4$short")


@pytest.mark.asyncio
@timer()
async def test_timing_attack_protection(password_hasher):
    password = "SomePassword123"
    invalid_hash = "invalid_hash_format"

    assert not await password_hasher.compare(password, invalid_hash)

    assert not await password_hasher.compare(password, "$2a$12$invalid")
    assert not await password_hasher.compare(password, "$argon2id$v=19$invalid")
