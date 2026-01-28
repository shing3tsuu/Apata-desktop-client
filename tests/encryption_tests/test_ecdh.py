import pytest
import asyncio
from dishka import make_async_container

from src.providers import AppProvider
from src.adapters.encryption.service import AbstractECDHCipher


async def get_ecdh_cipher():
    container = make_async_container(AppProvider())
    async with container() as request_container:
        cipher = await request_container.get(AbstractECDHCipher)
        return cipher, container


async def close_container(container):
    await container.close()


@pytest.mark.asyncio
async def test_key_exchange():
    """Test that two parties can derive the same shared key"""
    cipher, container = await get_ecdh_cipher()

    try:
        # Generate key pairs for both parties
        alice_private, alice_public = await cipher.generate_key_pair()
        bob_private, bob_public = await cipher.generate_key_pair()

        # Each party derives the shared key
        alice_shared = await cipher.derive_shared_key(alice_private, bob_public)
        bob_shared = await cipher.derive_shared_key(bob_private, alice_public)

        # Both should have the same shared key
        assert alice_shared == bob_shared
        assert len(alice_shared) == 32  # 256-bit key
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_different_keys_produce_different_shared_secrets():
    """Test that different key pairs produce different shared secrets"""
    cipher, container = await get_ecdh_cipher()

    try:
        # Generate two different key pairs
        private1, public1 = await cipher.generate_key_pair()
        private2, public2 = await cipher.generate_key_pair()

        # Derive shared keys
        shared1 = await cipher.derive_shared_key(private1, public2)
        shared2 = await cipher.derive_shared_key(private2, public1)

        # These should be the same (symmetric)
        assert shared1 == shared2

        # Generate another key pair and verify it produces different results
        private3, public3 = await cipher.generate_key_pair()
        shared3 = await cipher.derive_shared_key(private1, public3)

        assert shared1 != shared3
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_key_serialization_deserialization():
    """Test that keys can be serialized and deserialized correctly"""
    cipher, container = await get_ecdh_cipher()

    try:
        # Generate a key pair
        private_pem, public_pem = await cipher.generate_key_pair()

        # Verify PEM format
        assert private_pem.startswith('-----BEGIN PRIVATE KEY-----')
        assert private_pem.endswith('-----END PRIVATE KEY-----\n')
        assert public_pem.startswith('-----BEGIN PUBLIC KEY-----')
        assert public_pem.endswith('-----END PUBLIC KEY-----\n')

        # Test that we can use the serialized keys for key exchange
        private2, public2 = await cipher.generate_key_pair()
        shared1 = await cipher.derive_shared_key(private_pem, public2)
        shared2 = await cipher.derive_shared_key(private2, public_pem)

        # Should be able to derive a shared key
        assert len(shared1) == 32
        assert len(shared2) == 32
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_invalid_key_handling():
    """Test that invalid keys are handled properly"""
    cipher, container = await get_ecdh_cipher()

    try:
        # Generate a valid key pair
        private, public = await cipher.generate_key_pair()

        # Test with invalid public key
        with pytest.raises(Exception):
            await cipher.derive_shared_key(private, "invalid public key")

        # Test with invalid private key
        with pytest.raises(Exception):
            await cipher.derive_shared_key("invalid private key", public)
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_deterministic_shared_key():
    """Test that the same key pairs always produce the same shared key"""
    cipher, container = await get_ecdh_cipher()

    try:
        # Generate key pairs
        private1, public1 = await cipher.generate_key_pair()
        private2, public2 = await cipher.generate_key_pair()

        # Derive shared key multiple times
        shared1 = await cipher.derive_shared_key(private1, public2)
        shared2 = await cipher.derive_shared_key(private1, public2)
        shared3 = await cipher.derive_shared_key(private1, public2)

        # All should be identical
        assert shared1 == shared2 == shared3
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_concurrent_key_generation():
    """Test that multiple key pairs can be generated concurrently"""
    cipher, container = await get_ecdh_cipher()

    try:
        # Generate multiple key pairs concurrently
        tasks = [cipher.generate_key_pair() for _ in range(5)]
        results = await asyncio.gather(*tasks)

        # Verify all keys are different
        public_keys = [public for _, public in results]
        assert len(public_keys) == len(set(public_keys))
    finally:
        await close_container(container)