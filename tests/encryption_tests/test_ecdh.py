import asyncio
import logging
import pytest
from dishka import make_async_container, Scope

from src.adapters.encryption.dao import AbstractECDHCipher
from src.providers import AppProvider
from src.exceptions import KeyGenerationError, CryptographyError, InvalidKeyError

from tests.timing_wrapper import timer

@pytest.fixture(params=["X25519"])
async def ecdh_cipher(request):
    asymmetric_cipher = request.param
    logger = logging.getLogger(__name__)
    provider = AppProvider(
        scope=Scope.APP,
        logger=logger,
        symmetric_cipher="AESGCM",
        asymmetric_cipher=asymmetric_cipher,
        signature_cipher="ED-25519",
        password_cipher="ARGON2",
        base_url="https://test.com",
        verify_ssl=False,
        base_ws_url="wss://test.com",
    )
    container = make_async_container(provider)
    async with container() as request_container:
        cipher = await request_container.get(AbstractECDHCipher)
        yield cipher
    await container.close()


@pytest.mark.asyncio
@timer()
async def test_generate_key_pair(ecdh_cipher):
    private, public = await ecdh_cipher.generate_key_pair()

    assert private.startswith("-----BEGIN PRIVATE KEY-----")
    assert private.endswith("-----END PRIVATE KEY-----\n")
    assert public.startswith("-----BEGIN PUBLIC KEY-----")
    assert public.endswith("-----END PUBLIC KEY-----\n")
    assert private != public


@pytest.mark.asyncio
@timer()
async def test_key_exchange(ecdh_cipher):
    alice_private, alice_public = await ecdh_cipher.generate_key_pair()
    bob_private, bob_public = await ecdh_cipher.generate_key_pair()

    alice_shared = await ecdh_cipher.derive_shared_key(alice_private, bob_public)
    bob_shared = await ecdh_cipher.derive_shared_key(bob_private, alice_public)

    assert alice_shared == bob_shared
    assert len(alice_shared) == 32


@pytest.mark.asyncio
@timer()
async def test_different_keys_produce_different_shared_secrets(ecdh_cipher):
    private1, public1 = await ecdh_cipher.generate_key_pair()
    private2, public2 = await ecdh_cipher.generate_key_pair()

    shared1 = await ecdh_cipher.derive_shared_key(private1, public2)
    shared2 = await ecdh_cipher.derive_shared_key(private2, public1)

    assert shared1 == shared2

    private3, public3 = await ecdh_cipher.generate_key_pair()
    shared3 = await ecdh_cipher.derive_shared_key(private1, public3)
    assert shared1 != shared3


@pytest.mark.asyncio
@timer()
async def test_serialization_deserialization(ecdh_cipher):
    private_pem, public_pem = await ecdh_cipher.generate_key_pair()

    # Проверяем, что из этих ключей можно вывести общий ключ
    private2, public2 = await ecdh_cipher.generate_key_pair()
    shared1 = await ecdh_cipher.derive_shared_key(private_pem, public2)
    shared2 = await ecdh_cipher.derive_shared_key(private2, public_pem)

    assert len(shared1) == 32
    assert len(shared2) == 32


@pytest.mark.asyncio
@timer()
async def test_invalid_private_key(ecdh_cipher):
    _, public = await ecdh_cipher.generate_key_pair()
    invalid_private = "-----BEGIN PRIVATE KEY-----\ninvalid\n-----END PRIVATE KEY-----\n"

    with pytest.raises((ValueError, CryptographyError)):
        await ecdh_cipher.derive_shared_key(invalid_private, public)


@pytest.mark.asyncio
@timer()
async def test_invalid_public_key(ecdh_cipher):
    private, _ = await ecdh_cipher.generate_key_pair()
    invalid_public = "invalid public key"

    with pytest.raises((ValueError, CryptographyError)):
        await ecdh_cipher.derive_shared_key(private, invalid_public)


@pytest.mark.asyncio
@timer()
async def test_empty_keys(ecdh_cipher):
    private, public = await ecdh_cipher.generate_key_pair()

    with pytest.raises(ValueError, match="Keys cannot be empty"):
        await ecdh_cipher.derive_shared_key("", public)

    with pytest.raises(ValueError, match="Keys cannot be empty"):
        await ecdh_cipher.derive_shared_key(private, "")


@pytest.mark.asyncio
@timer()
async def test_deterministic_shared_key(ecdh_cipher):
    private1, public1 = await ecdh_cipher.generate_key_pair()
    private2, public2 = await ecdh_cipher.generate_key_pair()

    shared1 = await ecdh_cipher.derive_shared_key(private1, public2)
    shared2 = await ecdh_cipher.derive_shared_key(private1, public2)
    shared3 = await ecdh_cipher.derive_shared_key(private1, public2)

    assert shared1 == shared2 == shared3


@pytest.mark.asyncio
@timer()
async def test_concurrent_key_generation(ecdh_cipher):
    tasks = [ecdh_cipher.generate_key_pair() for _ in range(5)]
    results = await asyncio.gather(*tasks)

    public_keys = [pub for _, pub in results]
    assert len(public_keys) == len(set(public_keys))


@pytest.mark.asyncio
@timer()
async def test_concurrent_key_exchange(ecdh_cipher):
    pairs = [await ecdh_cipher.generate_key_pair() for _ in range(3)]

    tasks = []
    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            priv_i, pub_i = pairs[i]
            priv_j, pub_j = pairs[j]
            tasks.append(ecdh_cipher.derive_shared_key(priv_i, pub_j))
            tasks.append(ecdh_cipher.derive_shared_key(priv_j, pub_i))

    results = await asyncio.gather(*tasks)

    for k in range(0, len(results), 2):
        assert results[k] == results[k + 1]
        assert len(results[k]) == 32