import asyncio
import base64
import os
import logging
import pytest
from dishka import make_async_container, Scope
from src.providers import AppProvider
from src.adapters.encryption.dao import AbstractEDSignature

from tests.timing_wrapper import timer


@pytest.fixture(params=["ECDSA-SECP256R1", "ED-25519"])
# "ECDSA-SECP256R1", "ED-25519"
async def signer(request):
    signature_cipher = request.param
    logger = logging.getLogger(__name__)
    provider = AppProvider(
        scope=Scope.APP,
        logger=logger,
        symmetric_cipher="AESGCM",
        asymmetric_cipher="X25519",
        signature_cipher=signature_cipher,
        password_cipher="ARGON2",
        base_url="https://test.com",
        verify_ssl=False,
        base_ws_url="wss://test.com",
    )
    container = make_async_container(provider)
    async with container() as request_container:
        signer = await request_container.get(AbstractEDSignature)
        yield signer
    await container.close()


@pytest.mark.asyncio
@timer()
async def test_generate_key_pair(signer):
    private_key, public_key = await signer.generate_key_pair()
    assert private_key.startswith("-----BEGIN PRIVATE KEY-----")
    assert private_key.endswith("-----END PRIVATE KEY-----\n")
    assert public_key.startswith("-----BEGIN PUBLIC KEY-----")
    assert public_key.endswith("-----END PUBLIC KEY-----\n")
    assert private_key != public_key


@pytest.mark.asyncio
@timer()
async def test_sign_and_verify(signer):
    private_key, public_key = await signer.generate_key_pair()
    message = "Test message for signing"
    signature = await signer.sign_string(private_key, message)
    is_valid = await signer.verify_signature(public_key, message, signature)
    assert is_valid
    assert len(signature) > 0


@pytest.mark.asyncio
@timer()
async def test_verify_tampered_message(signer):
    private_key, public_key = await signer.generate_key_pair()
    original_message = "Original message"
    signature = await signer.sign_string(private_key, original_message)
    tampered_message = "Tampered message"
    is_valid = await signer.verify_signature(public_key, tampered_message, signature)
    assert not is_valid


@pytest.mark.asyncio
@timer()
async def test_verify_with_wrong_public_key(signer):
    private_key1, public_key1 = await signer.generate_key_pair()
    private_key2, public_key2 = await signer.generate_key_pair()
    message = "Test message"
    signature = await signer.sign_string(private_key1, message)
    is_valid = await signer.verify_signature(public_key2, message, signature)
    assert not is_valid


@pytest.mark.asyncio
@timer()
async def test_verify_invalid_signature(signer):
    private_key, public_key = await signer.generate_key_pair()
    message = "Test message"
    invalid_signature = base64.b64encode(os.urandom(64)).decode()
    is_valid = await signer.verify_signature(public_key, message, invalid_signature)
    assert not is_valid


@pytest.mark.asyncio
@timer()
async def test_sign_empty_message(signer):
    private_key, public_key = await signer.generate_key_pair()
    message = ""
    with pytest.raises(ValueError, match="Message cannot be empty"):
        await signer.sign_string(private_key, message)


@pytest.mark.asyncio
async def test_sign_large_message(signer):
    private_key, public_key = await signer.generate_key_pair()
    message = "A" * 10000
    signature = await signer.sign_string(private_key, message)
    is_valid = await signer.verify_signature(public_key, message, signature)
    assert is_valid


@pytest.mark.asyncio
@timer()
async def test_deterministic_key_generation(signer):
    key_pairs = []
    for _ in range(5):
        private_key, public_key = await signer.generate_key_pair()
        key_pairs.append((private_key, public_key))
    private_keys = [pair[0] for pair in key_pairs]
    assert len(private_keys) == len(set(private_keys))
    public_keys = [pair[1] for pair in key_pairs]
    assert len(public_keys) == len(set(public_keys))


@pytest.mark.asyncio
@timer()
async def test_concurrent_operations(signer):
    generate_tasks = [signer.generate_key_pair() for _ in range(3)]
    key_pairs = await asyncio.gather(*generate_tasks)
    messages = [f"Message {i}" for i in range(3)]
    sign_tasks = [
        signer.sign_string(key_pairs[i][0], messages[i]) for i in range(3)
    ]
    signatures = await asyncio.gather(*sign_tasks)
    verify_tasks = [
        signer.verify_signature(key_pairs[i][1], messages[i], signatures[i])
        for i in range(3)
    ]
    results = await asyncio.gather(*verify_tasks)
    assert all(results)


@pytest.mark.asyncio
@timer()
async def test_invalid_private_key_format(signer):
    invalid_private_key = "invalid_private_key_format"
    message = "Test message"
    with pytest.raises(Exception):
        await signer.sign_string(invalid_private_key, message)


@pytest.mark.asyncio
@timer()
async def test_invalid_public_key_format(signer):
    private_key, public_key = await signer.generate_key_pair()
    message = "Test message"
    signature = await signer.sign_string(private_key, message)
    invalid_public_key = "invalid_public_key_format"
    is_valid = await signer.verify_signature(invalid_public_key, message, signature)
    assert not is_valid
