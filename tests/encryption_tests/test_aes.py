import pytest
import os
import base64
from dishka import make_async_container

from src.providers import AppProvider
from src.adapters.encryption.service import AbstractAES256Cipher


async def get_aes_cipher():
    container = make_async_container(AppProvider())
    async with container() as request_container:
        cipher = await request_container.get(AbstractAES256Cipher)
        return cipher, container


async def close_container(container):
    await container.close()


@pytest.mark.asyncio
async def test_encrypt_decrypt():
    cipher, container = await get_aes_cipher()

    try:
        plaintext = "Secret message"
        key = os.urandom(32)

        encrypted = await cipher.encrypt(plaintext, key)
        decrypted = await cipher.decrypt(encrypted, key)

        assert decrypted == plaintext
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_invalid_key():
    cipher, container = await get_aes_cipher()

    try:
        plaintext = "Secret message"
        key1 = os.urandom(32)
        encrypted = await cipher.encrypt(plaintext, key1)

        key2 = os.urandom(32)

        with pytest.raises(ValueError):
            await cipher.decrypt(encrypted, key2)
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_tampered_ciphertext():
    cipher, container = await get_aes_cipher()

    try:
        plaintext = "Secret message"
        key = os.urandom(32)
        encrypted = await cipher.encrypt(plaintext, key)

        # Подменяем байт в ciphertext
        tampered = bytearray(base64.b64decode(encrypted))
        tampered[15] ^= 0x01
        tampered_encrypted = base64.b64encode(tampered).decode()

        with pytest.raises(ValueError):
            await cipher.decrypt(tampered_encrypted, key)
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_encrypt_with_wrong_key_length():
    cipher, container = await get_aes_cipher()

    try:
        plaintext = "Secret message"
        invalid_key = os.urandom(16)  # 16 bytes instead of required 32

        with pytest.raises(ValueError, match="AES key must be 32 bytes long"):
            await cipher.encrypt(plaintext, invalid_key)
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_decrypt_with_wrong_key_length():
    cipher, container = await get_aes_cipher()

    try:
        plaintext = "Secret message"
        valid_key = os.urandom(32)
        encrypted = await cipher.encrypt(plaintext, valid_key)

        invalid_key = os.urandom(16)  # 16 bytes instead of required 32

        with pytest.raises(ValueError, match="AES key must be 32 bytes long"):
            await cipher.decrypt(encrypted, invalid_key)
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_empty_plaintext():
    cipher, container = await get_aes_cipher()

    try:
        plaintext = ""
        key = os.urandom(32)

        encrypted = await cipher.encrypt(plaintext, key)
        decrypted = await cipher.decrypt(encrypted, key)

        assert decrypted == plaintext
    finally:
        await close_container(container)