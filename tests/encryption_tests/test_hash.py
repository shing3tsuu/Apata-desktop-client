import pytest
import asyncio
from dishka import make_async_container

from src.providers import AppProvider
from src.adapters.encryption.service import AbstractPasswordHasher


async def get_password_hasher():
    container = make_async_container(AppProvider())
    async with container() as request_container:
        hasher = await request_container.get(AbstractPasswordHasher)
        return hasher, container


async def close_container(container):
    await container.close()


@pytest.mark.asyncio
async def test_password_hashing_and_verification():
    """Test that password hashing and verification work correctly"""
    hasher, container = await get_password_hasher()

    try:
        password = "MySecurePassword123!"

        # Hash the password
        hashed_password = await hasher.hashing(password)

        # Verify the password against the hash
        is_valid = await hasher.compare(password, hashed_password)

        assert is_valid == True
        assert hashed_password != password  # Hash should be different from plain text
        assert hashed_password.startswith(('$2a$', '$2b$', '$2y$'))  # Bcrypt format
        assert len(hashed_password) == 60  # Bcrypt hash length
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_password_verification_fails_with_wrong_password():
    """Test that verification fails with incorrect password"""
    hasher, container = await get_password_hasher()

    try:
        original_password = "MySecurePassword123!"
        wrong_password = "WrongPassword456!"

        # Hash the original password
        hashed_password = await hasher.hashing(original_password)

        # Try to verify with wrong password
        is_valid = await hasher.compare(wrong_password, hashed_password)

        assert is_valid == False
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_different_hashes_for_same_password():
    """Test that same password produces different hashes (due to different salts)"""
    hasher, container = await get_password_hasher()

    try:
        password = "SamePassword123"

        # Hash the same password multiple times
        hash1 = await hasher.hashing(password)
        hash2 = await hasher.hashing(password)
        hash3 = await hasher.hashing(password)

        # All hashes should be different
        assert hash1 != hash2
        assert hash1 != hash3
        assert hash2 != hash3

        # But all should verify correctly
        assert await hasher.compare(password, hash1) == True
        assert await hasher.compare(password, hash2) == True
        assert await hasher.compare(password, hash3) == True
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_empty_password():
    """Test that empty password raises error during hashing"""
    hasher, container = await get_password_hasher()

    try:
        empty_password = ""

        with pytest.raises(ValueError, match="Password cannot be empty"):
            await hasher.hashing(empty_password)
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_short_password():
    """Test that short password raises error during hashing"""
    hasher, container = await get_password_hasher()

    try:
        short_password = "123"  # Less than minimum 8 characters

        with pytest.raises(ValueError, match="Password must be at least 8 characters long"):
            await hasher.hashing(short_password)
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_compare_with_empty_password():
    """Test that comparison returns False for empty password"""
    hasher, container = await get_password_hasher()

    try:
        valid_password = "ValidPassword123"
        empty_password = ""

        hashed_password = await hasher.hashing(valid_password)

        # Compare with empty password
        is_valid = await hasher.compare(empty_password, hashed_password)

        assert is_valid == False
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_compare_with_empty_hash():
    """Test that comparison returns False for empty hash"""
    hasher, container = await get_password_hasher()

    try:
        password = "SomePassword123"
        empty_hash = ""

        is_valid = await hasher.compare(password, empty_hash)

        assert is_valid == False
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_compare_with_invalid_hash_format():
    """Test that comparison handles invalid hash format gracefully"""
    hasher, container = await get_password_hasher()

    try:
        password = "SomePassword123"
        invalid_hash = "invalid_hash_format"

        is_valid = await hasher.compare(password, invalid_hash)

        assert is_valid == False
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_special_characters_in_password():
    """Test that passwords with special characters work correctly"""
    hasher, container = await get_password_hasher()

    try:
        password = "P@ssw0rd! #$%^&*()_+-=[]{}|;:,.<>?"

        hashed_password = await hasher.hashing(password)
        is_valid = await hasher.compare(password, hashed_password)

        assert is_valid == True
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_unicode_password():
    """Test that unicode passwords work correctly"""
    hasher, container = await get_password_hasher()

    try:
        password = "密码🔐пароль🎯"

        hashed_password = await hasher.hashing(password)
        is_valid = await hasher.compare(password, hashed_password)

        assert is_valid == True
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_long_password():
    """Test that long passwords work correctly"""
    hasher, container = await get_password_hasher()

    try:
        password = "A" * 1000  # Very long password

        hashed_password = await hasher.hashing(password)
        is_valid = await hasher.compare(password, hashed_password)

        assert is_valid == True
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_concurrent_hashing():
    """Test that multiple hashing operations can be performed concurrently"""
    hasher, container = await get_password_hasher()

    try:
        passwords = [f"Password{i}!" for i in range(5)]

        # Hash multiple passwords concurrently
        hashing_tasks = [hasher.hashing(password) for password in passwords]
        hashes = await asyncio.gather(*hashing_tasks)

        # Verify all hashes concurrently
        verification_tasks = [
            hasher.compare(passwords[i], hashes[i])
            for i in range(len(passwords))
        ]
        results = await asyncio.gather(*verification_tasks)

        # All verifications should pass
        assert all(results)

        # All hashes should be unique
        assert len(hashes) == len(set(hashes))
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_is_valid_hash_method():
    """Test the _is_valid_hash static method"""
    hasher, container = await get_password_hasher()

    try:
        # Test valid bcrypt hash
        valid_password = "TestPassword123"
        valid_hash = await hasher.hashing(valid_password)

        assert hasher._is_valid_hash(valid_hash) == True

        # Test invalid hashes
        assert hasher._is_valid_hash("") == False
        assert hasher._is_valid_hash("invalid_hash") == False
        assert hasher._is_valid_hash("$2a$12$tooshort") == False
        assert hasher._is_valid_hash(
            "$2x$12$invalidprefixK3C8hN5u9Qk7z2v1wY6ZceBp1jH4dE7fG8i9l0m1n2o3p4q5r6s7t8u9v0") == False
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_timing_attack_protection():
    """Test that dummy hash is used for invalid hashes to prevent timing attacks"""
    hasher, container = await get_password_hasher()

    try:
        password = "SomePassword123"
        invalid_hash = "invalid_hash_format"

        # This should use the dummy hash and not raise an exception
        is_valid = await hasher.compare(password, invalid_hash)

        assert is_valid == False

        # Test with another invalid format
        is_valid2 = await hasher.compare(password, "$2a$12$invalid")
        assert is_valid2 == False
    finally:
        await close_container(container)