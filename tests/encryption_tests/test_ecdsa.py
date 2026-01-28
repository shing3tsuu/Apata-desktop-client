import pytest
import asyncio
from dishka import make_async_container

from src.providers import AppProvider
from src.adapters.encryption.service import AbstractECDSASignature


async def get_ecdsa_signer():
    container = make_async_container(AppProvider())
    async with container() as request_container:
        signer = await request_container.get(AbstractECDSASignature)
        return signer, container


async def close_container(container):
    await container.close()


@pytest.mark.asyncio
async def test_generate_key_pair():
    """Test that key pair can be generated successfully"""
    signer, container = await get_ecdsa_signer()

    try:
        private_key, public_key = await signer.generate_key_pair()

        # Verify PEM format
        assert private_key.startswith('-----BEGIN PRIVATE KEY-----')
        assert private_key.endswith('-----END PRIVATE KEY-----\n')
        assert public_key.startswith('-----BEGIN PUBLIC KEY-----')
        assert public_key.endswith('-----END PUBLIC KEY-----\n')

        # Verify keys are different
        assert private_key != public_key
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_sign_and_verify():
    """Test that signing and verification work correctly"""
    signer, container = await get_ecdsa_signer()

    try:
        # Generate key pair
        private_key, public_key = await signer.generate_key_pair()

        # Test message
        message = "Test message for signing"

        # Sign the message
        signature = await signer.sign_message(private_key, message)

        # Verify the signature
        is_valid = await signer.verify_signature(public_key, message, signature)

        assert is_valid == True
        assert len(signature) > 0
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_verify_tampered_message():
    """Test that verification fails with tampered message"""
    signer, container = await get_ecdsa_signer()

    try:
        # Generate key pair
        private_key, public_key = await signer.generate_key_pair()

        # Original message
        original_message = "Original message"

        # Sign the original message
        signature = await signer.sign_message(private_key, original_message)

        # Tampered message
        tampered_message = "Tampered message"

        # Verification should fail
        is_valid = await signer.verify_signature(public_key, tampered_message, signature)

        assert is_valid == False
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_verify_with_wrong_public_key():
    """Test that verification fails with wrong public key"""
    signer, container = await get_ecdsa_signer()

    try:
        # Generate two key pairs
        private_key1, public_key1 = await signer.generate_key_pair()
        private_key2, public_key2 = await signer.generate_key_pair()

        # Sign message with first private key
        message = "Test message"
        signature = await signer.sign_message(private_key1, message)

        # Try to verify with wrong public key
        is_valid = await signer.verify_signature(public_key2, message, signature)

        assert is_valid == False
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_verify_invalid_signature():
    """Test that verification fails with invalid signature"""
    signer, container = await get_ecdsa_signer()

    try:
        # Generate key pair
        private_key, public_key = await signer.generate_key_pair()

        message = "Test message"

        # Create invalid signature (random bytes)
        import base64
        import os
        invalid_signature = base64.b64encode(os.urandom(64)).decode()

        # Verification should fail
        is_valid = await signer.verify_signature(public_key, message, invalid_signature)

        assert is_valid == False
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_sign_empty_message():
    """Test signing and verifying empty message"""
    signer, container = await get_ecdsa_signer()

    try:
        # Generate key pair
        private_key, public_key = await signer.generate_key_pair()

        # Empty message
        message = ""

        # Sign the empty message
        signature = await signer.sign_message(private_key, message)

        # Verify the signature
        is_valid = await signer.verify_signature(public_key, message, signature)

        assert is_valid == True
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_sign_large_message():
    """Test signing and verifying large message"""
    signer, container = await get_ecdsa_signer()

    try:
        # Generate key pair
        private_key, public_key = await signer.generate_key_pair()

        # Large message
        message = "A" * 10000  # 10KB message

        # Sign the large message
        signature = await signer.sign_message(private_key, message)

        # Verify the signature
        is_valid = await signer.verify_signature(public_key, message, signature)

        assert is_valid == True
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_deterministic_key_generation():
    """Test that multiple key generations produce different keys"""
    signer, container = await get_ecdsa_signer()

    try:
        # Generate multiple key pairs
        key_pairs = []
        for _ in range(5):
            private_key, public_key = await signer.generate_key_pair()
            key_pairs.append((private_key, public_key))

        # All private keys should be different
        private_keys = [pair[0] for pair in key_pairs]
        assert len(private_keys) == len(set(private_keys))

        # All public keys should be different
        public_keys = [pair[1] for pair in key_pairs]
        assert len(public_keys) == len(set(public_keys))
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_concurrent_operations():
    """Test that multiple operations can be performed concurrently"""
    signer, container = await get_ecdsa_signer()

    try:
        # Generate multiple key pairs concurrently
        generate_tasks = [signer.generate_key_pair() for _ in range(3)]
        key_pairs = await asyncio.gather(*generate_tasks)

        # Test messages
        messages = [f"Message {i}" for i in range(3)]

        # Sign messages concurrently
        sign_tasks = [
            signer.sign_message(key_pairs[i][0], messages[i])
            for i in range(3)
        ]
        signatures = await asyncio.gather(*sign_tasks)

        # Verify signatures concurrently
        verify_tasks = [
            signer.verify_signature(key_pairs[i][1], messages[i], signatures[i])
            for i in range(3)
        ]
        results = await asyncio.gather(*verify_tasks)

        # All verifications should pass
        assert all(results)
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_invalid_private_key_format():
    """Test that invalid private key format raises exception"""
    signer, container = await get_ecdsa_signer()

    try:
        invalid_private_key = "invalid_private_key_format"
        message = "Test message"

        with pytest.raises(Exception):
            await signer.sign_message(invalid_private_key, message)
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_invalid_public_key_format():
    """Test that invalid public key format returns False"""
    signer, container = await get_ecdsa_signer()

    try:
        # Generate valid key pair and signature
        private_key, public_key = await signer.generate_key_pair()
        message = "Test message"
        signature = await signer.sign_message(private_key, message)

        # Try to verify with invalid public key
        invalid_public_key = "invalid_public_key_format"
        is_valid = await signer.verify_signature(invalid_public_key, message, signature)

        assert is_valid == False
    finally:
        await close_container(container)