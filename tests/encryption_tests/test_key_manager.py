import pytest
import asyncio
from dishka import make_async_container

from src.providers import AppProvider
from src.adapters.encryption.service import KeyManager


async def get_key_manager():
    container = make_async_container(AppProvider())
    async with container() as request_container:
        key_manager = await request_container.get(KeyManager)
        return key_manager, container


async def close_container(container):
    await container.close()


@pytest.mark.asyncio
async def test_generate_master_key():
    """Test that master key can be generated successfully"""
    key_manager, container = await get_key_manager()

    try:
        master_key = await key_manager.generate_master_key()

        assert master_key is not None
        assert len(master_key) == 32  # 256-bit key
        assert isinstance(master_key, bytes)
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_encrypt_decrypt_with_master_key():
    """Test encryption and decryption with master key"""
    key_manager, container = await get_key_manager()

    try:
        # Generate master key
        master_key = await key_manager.generate_master_key()

        # Test data
        test_data = b"Test data for encryption and decryption"

        # Encrypt data
        encrypted_data = await key_manager.encrypt_with_master_key(test_data, master_key)

        assert encrypted_data is not None
        assert len(encrypted_data) > len(test_data)  # Should include nonce and tag

        # Decrypt data
        decrypted_data = await key_manager.decrypt_with_master_key(encrypted_data, master_key)

        assert decrypted_data == test_data
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_encrypt_decrypt_master_key_with_password():
    """Test encrypting and decrypting master key with password"""
    key_manager, container = await get_key_manager()

    try:
        # Generate master key
        master_key = await key_manager.generate_master_key()

        # Password
        password = "MySecurePassword123!"

        # Encrypt master key
        encrypted_master_key, salt = await key_manager.encrypt_master_key(master_key, password)

        assert encrypted_master_key is not None
        assert salt is not None
        assert len(salt) == 16
        assert len(encrypted_master_key) == 60  # 12 nonce + 16 tag + 32 ciphertext

        # Decrypt master key
        decrypted_master_key = await key_manager.decrypt_master_key(encrypted_master_key, password, salt)

        assert decrypted_master_key == master_key
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_decrypt_master_key_with_wrong_password():
    """Test that decrypting with wrong password fails"""
    key_manager, container = await get_key_manager()

    try:
        # Generate master key
        master_key = await key_manager.generate_master_key()

        # Password
        password = "CorrectPassword123!"
        wrong_password = "WrongPassword456!"

        # Encrypt master key
        encrypted_master_key, salt = await key_manager.encrypt_master_key(master_key, password)

        # Try to decrypt with wrong password
        decrypted_master_key = await key_manager.decrypt_master_key(encrypted_master_key, wrong_password, salt)

        assert decrypted_master_key is None
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_encrypt_decrypt_private_key_legacy():
    """Test legacy encrypt_private_key and decrypt_private_key methods"""
    key_manager, container = await get_key_manager()

    try:
        # Test private key data
        private_key_data = b"-----BEGIN PRIVATE KEY-----\nTestPrivateKeyData\n-----END PRIVATE KEY-----"
        password = "LegacyPassword123!"

        # Encrypt private key
        encrypted_private_key = await key_manager.encrypt_private_key(private_key_data, password)

        assert encrypted_private_key is not None
        assert len(encrypted_private_key) > len(private_key_data)

        # Decrypt private key
        decrypted_private_key = await key_manager.decrypt_private_key(encrypted_private_key, password)

        assert decrypted_private_key == private_key_data
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_decrypt_private_key_with_wrong_password():
    """Test that legacy decrypt fails with wrong password"""
    key_manager, container = await get_key_manager()

    try:
        # Test private key data
        private_key_data = b"Test private key data"
        password = "CorrectPassword123!"
        wrong_password = "WrongPassword456!"

        # Encrypt private key
        encrypted_private_key = await key_manager.encrypt_private_key(private_key_data, password)

        # Try to decrypt with wrong password
        decrypted_private_key = await key_manager.decrypt_private_key(encrypted_private_key, wrong_password)

        assert decrypted_private_key is None
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_derive_key_from_password():
    """Test key derivation from password"""
    key_manager, container = await get_key_manager()

    try:
        password = "TestPassword123"
        salt = b"test_salt_123456"

        # Derive key
        derived_key = key_manager.derive_key_from_password(password, salt)

        assert derived_key is not None
        assert len(derived_key) == 32  # 256-bit key
        assert isinstance(derived_key, bytes)

        # Same password and salt should produce same key
        derived_key2 = key_manager.derive_key_from_password(password, salt)
        assert derived_key == derived_key2

        # Different salt should produce different key
        different_salt = b"different_salt_78"
        derived_key3 = key_manager.derive_key_from_password(password, different_salt)
        assert derived_key != derived_key3

        # Different password should produce different key
        different_password = "DifferentPassword456"
        derived_key4 = key_manager.derive_key_from_password(different_password, salt)
        assert derived_key != derived_key4
    finally:
        await close_container(container)

@pytest.mark.asyncio
async def test_derive_key_with_custom_iterations():
    """Test key derivation with custom iterations"""
    key_manager, container = await get_key_manager()

    try:
        password = "TestPassword123"
        salt = b"test_salt_123456"
        custom_iterations = 100000

        # Derive key with custom iterations
        derived_key = key_manager.derive_key_from_password(password, salt, iterations=custom_iterations)

        assert derived_key is not None
        assert len(derived_key) == 32
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_encrypt_with_invalid_master_key():
    """Test encryption with invalid master key"""
    key_manager, container = await get_key_manager()

    try:
        test_data = b"Test data"
        invalid_master_key = b"invalid_key"  # Wrong length

        # Should handle invalid key gracefully
        encrypted_data = await key_manager.encrypt_with_master_key(test_data, invalid_master_key)

        assert encrypted_data is None
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_decrypt_with_invalid_data():
    """Test decryption with invalid encrypted data"""
    key_manager, container = await get_key_manager()

    try:
        master_key = await key_manager.generate_master_key()

        # Invalid encrypted data (too short)
        invalid_encrypted_data = b"short"

        decrypted_data = await key_manager.decrypt_with_master_key(invalid_encrypted_data, master_key)

        assert decrypted_data is None
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_decrypt_with_tampered_data():
    """Test decryption with tampered encrypted data"""
    key_manager, container = await get_key_manager()

    try:
        master_key = await key_manager.generate_master_key()
        test_data = b"Test data"

        # Encrypt data
        encrypted_data = await key_manager.encrypt_with_master_key(test_data, master_key)

        # Tamper the data
        tampered_data = bytearray(encrypted_data)
        tampered_data[10] ^= 0x01  # Flip one bit

        # Should fail to decrypt
        decrypted_data = await key_manager.decrypt_with_master_key(bytes(tampered_data), master_key)

        assert decrypted_data is None
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_empty_data_encryption():
    """Test encryption and decryption of empty data"""
    key_manager, container = await get_key_manager()

    try:
        master_key = await key_manager.generate_master_key()
        empty_data = b""

        # Encrypt empty data
        encrypted_data = await key_manager.encrypt_with_master_key(empty_data, master_key)

        assert encrypted_data is not None

        # Decrypt empty data
        decrypted_data = await key_manager.decrypt_with_master_key(encrypted_data, master_key)

        assert decrypted_data == empty_data
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_large_data_encryption():
    """Test encryption and decryption of large data"""
    key_manager, container = await get_key_manager()

    try:
        master_key = await key_manager.generate_master_key()
        large_data = b"X" * 100000  # 100KB of data

        # Encrypt large data
        encrypted_data = await key_manager.encrypt_with_master_key(large_data, master_key)

        assert encrypted_data is not None

        # Decrypt large data
        decrypted_data = await key_manager.decrypt_with_master_key(encrypted_data, master_key)

        assert decrypted_data == large_data
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_concurrent_operations():
    """Test that multiple operations can be performed concurrently"""
    key_manager, container = await get_key_manager()

    try:
        # Generate multiple master keys concurrently
        generate_tasks = [key_manager.generate_master_key() for _ in range(3)]
        master_keys = await asyncio.gather(*generate_tasks)

        # Test data
        test_data = [b"Data1", b"Data2", b"Data3"]
        passwords = ["Password1", "Password2", "Password3"]

        # Encrypt data concurrently
        encrypt_tasks = [
            key_manager.encrypt_with_master_key(test_data[i], master_keys[i])
            for i in range(3)
        ]
        encrypted_data_list = await asyncio.gather(*encrypt_tasks)

        # Decrypt data concurrently
        decrypt_tasks = [
            key_manager.decrypt_with_master_key(encrypted_data_list[i], master_keys[i])
            for i in range(3)
        ]
        decrypted_data_list = await asyncio.gather(*decrypt_tasks)

        # All decryptions should match original data
        for i in range(3):
            assert decrypted_data_list[i] == test_data[i]

        # Encrypt master keys concurrently
        encrypt_master_tasks = [
            key_manager.encrypt_master_key(master_keys[i], passwords[i])
            for i in range(3)
        ]
        encrypted_master_results = await asyncio.gather(*encrypt_master_tasks)

        # All encryptions should succeed
        assert all(result[0] is not None and result[1] is not None for result in encrypted_master_results)
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_key_uniqueness():
    """Test that generated master keys are unique"""
    key_manager, container = await get_key_manager()

    try:
        # Generate multiple master keys
        keys = []
        for _ in range(10):
            key = await key_manager.generate_master_key()
            keys.append(key)

        # All keys should be unique
        assert len(keys) == len(set(keys))

        # All keys should be 32 bytes
        assert all(len(key) == 32 for key in keys)
    finally:
        await close_container(container)