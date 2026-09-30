import base64
import os
import logging
import pytest
import asyncio
import uuid
from pathlib import Path

from dishka import make_async_container, Scope

from src.adapters.encryption.dao import Abstract256Cipher
from src.providers import AppProvider
from src.exceptions import InvalidKeyError, DecryptionError, InvalidCiphertextError

from tests.timing_wrapper import timer


@pytest.fixture(params=["AESGCM", "AESGCMSIV"])
async def aes_cipher(request):
    symmetric_cipher = request.param
    logger = logging.getLogger(__name__)
    provider = AppProvider(
        scope=Scope.APP,
        logger=logger,
        symmetric_cipher=symmetric_cipher,
        asymmetric_cipher="X25519",
        signature_cipher="ED-25519",
        password_cipher="ARGON2",
        base_url="https://test.com",
        verify_ssl=False,
        base_ws_url="wss://test.com",
    )
    container = make_async_container(provider)
    async with container() as request_container:
        cipher = await request_container.get(Abstract256Cipher)
        yield cipher
    await container.close()


def _is_with_associated_data(cipher):
    return hasattr(cipher, 'encrypt_with_message_uuid')


@pytest.mark.asyncio
@timer()
async def test_encrypt_decrypt(aes_cipher):
    plaintext = "Secret message"
    key = os.urandom(32)
    encrypted = await aes_cipher.encrypt(plaintext, key)
    decrypted = await aes_cipher.decrypt(encrypted, key)
    assert decrypted == plaintext


@pytest.mark.asyncio
@timer()
async def test_encrypt_decrypt_large_message(aes_cipher):
    emoji = "😀😂😍🥰😘😗😙😚☺️🙂🤗🤩🤔🤨😐😑😶😶‍🌫️😏😒🙄😬🤥😌😔😪🤤😴😷🤒🤕🤢🤮🥴😵🤯🤠🥳😎🤓🧐😕😟🙁☹️😮😯😲😳🥺😦😧😨😰😥😢😭😱😖😣😞😓😩😫🥱😤😡😠🤬"
    plaintext = emoji * 25000
    key = os.urandom(32)
    encrypted = await aes_cipher.encrypt(plaintext, key)
    decrypted = await aes_cipher.decrypt(encrypted, key)
    assert decrypted == plaintext


@pytest.mark.asyncio
@timer()
async def test_encrypt_with_wrong_key_length(aes_cipher):
    plaintext = "Secret message"
    invalid_key = os.urandom(16)
    with pytest.raises(InvalidKeyError, match="AES key must be 32 bytes long"):
        await aes_cipher.encrypt(plaintext, invalid_key)


@pytest.mark.asyncio
@timer()
async def test_decrypt_with_wrong_key_length(aes_cipher):
    plaintext = "Secret message"
    valid_key = os.urandom(32)
    encrypted = await aes_cipher.encrypt(plaintext, valid_key)
    invalid_key = os.urandom(16)
    with pytest.raises(InvalidKeyError, match="AES key must be 32 bytes long"):
        await aes_cipher.decrypt(encrypted, invalid_key)


@pytest.mark.asyncio
@timer()
async def test_decrypt_with_wrong_key(aes_cipher):
    plaintext = "Secret message"
    key1 = os.urandom(32)
    encrypted = await aes_cipher.encrypt(plaintext, key1)
    key2 = os.urandom(32)
    with pytest.raises(DecryptionError, match="Authentication failed: invalid tag"):
        await aes_cipher.decrypt(encrypted, key2)


@pytest.mark.asyncio
@timer()
async def test_tampered_ciphertext(aes_cipher):
    plaintext = "Secret message"
    key = os.urandom(32)
    encrypted = await aes_cipher.encrypt(plaintext, key)
    decoded = bytearray(base64.b64decode(encrypted))
    if len(decoded) > 20:
        decoded[15] ^= 0x01
    tampered = base64.b64encode(decoded).decode()
    with pytest.raises(DecryptionError, match="Authentication failed: invalid tag"):
        await aes_cipher.decrypt(tampered, key)


@pytest.mark.asyncio
@timer()
async def test_empty_plaintext(aes_cipher):
    plaintext = ""
    key = os.urandom(32)
    with pytest.raises(ValueError, match="Data must not be zero length"):
        await aes_cipher.encrypt(plaintext, key)


@pytest.mark.asyncio
@timer()
async def test_large_plaintext(aes_cipher):
    plaintext = "A" * 100000
    key = os.urandom(32)
    encrypted = await aes_cipher.encrypt(plaintext, key)
    decrypted = await aes_cipher.decrypt(encrypted, key)
    assert decrypted == plaintext


@pytest.mark.asyncio
@timer()
async def test_invalid_base64_ciphertext(aes_cipher):
    key = os.urandom(32)
    invalid_ciphertext = "not_base64!@#"
    with pytest.raises(InvalidCiphertextError, match="Invalid base64 encoding"):
        await aes_cipher.decrypt(invalid_ciphertext, key)


@pytest.mark.asyncio
@timer()
async def test_too_short_ciphertext(aes_cipher):
    key = os.urandom(32)
    short_ciphertext = base64.b64encode(b"short").decode()
    with pytest.raises(InvalidCiphertextError, match="Invalid ciphertext length"):
        await aes_cipher.decrypt(short_ciphertext, key)


@pytest.mark.asyncio
@timer()
async def test_concurrent_encryption_decryption(aes_cipher):
    key = os.urandom(32)
    messages = [f"Message {i}" for i in range(5)]
    encrypt_tasks = [aes_cipher.encrypt(msg, key) for msg in messages]
    encrypted_list = await asyncio.gather(*encrypt_tasks)
    decrypt_tasks = [aes_cipher.decrypt(enc, key) for enc in encrypted_list]
    decrypted_list = await asyncio.gather(*decrypt_tasks)
    assert decrypted_list == messages


# ==================== СПЕЦИФИЧНЫЕ ТЕСТЫ ДЛЯ ШИФРОВ С AAD (UUID) ====================

@pytest.mark.asyncio
@timer()
async def test_encrypt_decrypt_with_uuid(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with AAD UUID support")
    plaintext = "Secret message"
    key = os.urandom(32)
    message_id = uuid.uuid7()
    encrypted = await aes_cipher.encrypt_with_message_uuid(plaintext, key, message_id)
    decrypted = await aes_cipher.decrypt_with_message_uuid(encrypted, key, message_id)
    assert decrypted == plaintext


@pytest.mark.asyncio
@timer()
async def test_decrypt_with_wrong_uuid(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with AAD UUID support")
    plaintext = "Secret message"
    key = os.urandom(32)
    correct_uuid = uuid.uuid7()
    wrong_uuid = uuid.uuid7()
    encrypted = await aes_cipher.encrypt_with_message_uuid(plaintext, key, correct_uuid)
    with pytest.raises(DecryptionError, match="Authentication failed: invalid tag"):
        await aes_cipher.decrypt_with_message_uuid(encrypted, key, wrong_uuid)


@pytest.mark.asyncio
@timer()
async def test_uuid_version_validation(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with AAD UUID support")
    plaintext = "Test"
    key = os.urandom(32)
    invalid_uuid = uuid.uuid4()
    with pytest.raises(ValueError, match="Only UUID version 7 is supported"):
        await aes_cipher.encrypt_with_message_uuid(plaintext, key, invalid_uuid)
    valid_uuid = uuid.uuid7()
    encrypted = await aes_cipher.encrypt_with_message_uuid(plaintext, key, valid_uuid)
    with pytest.raises(ValueError, match="Only UUID version 7 is supported"):
        await aes_cipher.decrypt_with_message_uuid(encrypted, key, invalid_uuid)


# ==================== СПЕЦИФИЧНЫЕ ТЕСТЫ ДЛЯ БАЙТОВЫХ МЕТОДОВ ====================

@pytest.mark.asyncio
@timer()
async def test_encrypt_decrypt_bytes_with_uuid(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with bytes support")
    plaintext = b"Secret message as bytes"
    key = os.urandom(32)
    message_id = uuid.uuid7()
    encrypted = await aes_cipher.encrypt_bytes_with_message_uuid(plaintext, key, message_id)
    decrypted = await aes_cipher.decrypt_bytes_with_message_uuid(encrypted, key, message_id)
    assert decrypted == plaintext
    assert isinstance(encrypted, bytes)
    assert len(encrypted) > len(plaintext)


@pytest.mark.asyncio
@timer()
async def test_encrypt_decrypt_bytes_large_with_uuid(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with bytes support")
    plaintext = b"A" * 100000
    key = os.urandom(32)
    message_id = uuid.uuid7()
    encrypted = await aes_cipher.encrypt_bytes_with_message_uuid(plaintext, key, message_id)
    decrypted = await aes_cipher.decrypt_bytes_with_message_uuid(encrypted, key, message_id)
    assert decrypted == plaintext
    assert isinstance(encrypted, bytes)


@pytest.mark.asyncio
@timer()
async def test_encrypt_bytes_wrong_key_length_with_uuid(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with bytes support")
    plaintext = b"Test"
    invalid_key = os.urandom(16)
    message_id = uuid.uuid7()
    with pytest.raises(InvalidKeyError, match="AES key must be 32 bytes long"):
        await aes_cipher.encrypt_bytes_with_message_uuid(plaintext, invalid_key, message_id)


@pytest.mark.asyncio
@timer()
async def test_decrypt_bytes_wrong_key_with_uuid(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with bytes support")
    plaintext = b"Secret data"
    key1 = os.urandom(32)
    key2 = os.urandom(32)
    message_id = uuid.uuid7()
    encrypted = await aes_cipher.encrypt_bytes_with_message_uuid(plaintext, key1, message_id)
    with pytest.raises(DecryptionError, match="Authentication failed: invalid tag"):
        await aes_cipher.decrypt_bytes_with_message_uuid(encrypted, key2, message_id)


@pytest.mark.asyncio
@timer()
async def test_decrypt_bytes_wrong_uuid_with_uuid(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with bytes support")
    plaintext = b"Secret data"
    key = os.urandom(32)
    correct_uuid = uuid.uuid7()
    wrong_uuid = uuid.uuid7()
    encrypted = await aes_cipher.encrypt_bytes_with_message_uuid(plaintext, key, correct_uuid)
    with pytest.raises(DecryptionError, match="Authentication failed: invalid tag"):
        await aes_cipher.decrypt_bytes_with_message_uuid(encrypted, key, wrong_uuid)


@pytest.mark.asyncio
@timer()
async def test_tampered_bytes_ciphertext_with_uuid(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with bytes support")
    plaintext = b"Secret data"
    key = os.urandom(32)
    message_id = uuid.uuid7()
    encrypted = await aes_cipher.encrypt_bytes_with_message_uuid(plaintext, key, message_id)
    tampered = bytearray(encrypted)
    if len(tampered) > 20:
        tampered[15] ^= 0x01
    tampered = bytes(tampered)
    with pytest.raises(DecryptionError, match="Authentication failed: invalid tag"):
        await aes_cipher.decrypt_bytes_with_message_uuid(tampered, key, message_id)


@pytest.mark.asyncio
@timer()
async def test_empty_bytes_plaintext_with_uuid(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with bytes support")
    plaintext = b""
    key = os.urandom(32)
    message_id = uuid.uuid7()
    with pytest.raises(ValueError, match="Data must not be zero length"):
        await aes_cipher.encrypt_bytes_with_message_uuid(plaintext, key, message_id)


@pytest.mark.asyncio
@timer()
async def test_encrypt_decrypt_bytes_concurrent_with_uuid(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with bytes support")
    key = os.urandom(32)
    messages = [f"Message {i}".encode() for i in range(5)]
    message_ids = [uuid.uuid7() for _ in range(5)]
    encrypt_tasks = [
        aes_cipher.encrypt_bytes_with_message_uuid(msg, key, msg_id)
        for msg, msg_id in zip(messages, message_ids)
    ]
    encrypted_list = await asyncio.gather(*encrypt_tasks)
    decrypt_tasks = [
        aes_cipher.decrypt_bytes_with_message_uuid(enc, key, msg_id)
        for enc, msg_id in zip(encrypted_list, message_ids)
    ]
    decrypted_list = await asyncio.gather(*decrypt_tasks)
    assert decrypted_list == messages


@pytest.mark.asyncio
@timer()
async def test_decrypt_bytes_invalid_ciphertext_with_uuid(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with bytes support")
    key = os.urandom(32)
    message_id = uuid.uuid7()
    invalid_ciphertext = b"too_short"
    with pytest.raises(InvalidCiphertextError, match="Invalid ciphertext length"):
        await aes_cipher.decrypt_bytes_with_message_uuid(invalid_ciphertext, key, message_id)


@pytest.mark.asyncio
@timer()
async def test_encrypt_decrypt_image(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with bytes support")

    test_image_path = Path("tests/test_data/images/image_1.png")
    if not test_image_path.exists():
        pytest.skip("Test image not found")

    with open(test_image_path, "rb") as f:
        original_bytes = f.read()

    key = os.urandom(32)
    message_uuid = uuid.uuid7()

    encrypted_bytes = await aes_cipher.encrypt_bytes_with_message_uuid(
        plaintext=original_bytes, key=key, message_uuid=message_uuid
    )

    decrypted_bytes = await aes_cipher.decrypt_bytes_with_message_uuid(
        ciphertext=encrypted_bytes, key=key, message_uuid=message_uuid
    )

    assert decrypted_bytes == original_bytes

    output_path = Path("tests/test_data/output/decrypted_photo_1.jpg")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(decrypted_bytes)


@pytest.mark.asyncio
@timer()
async def test_encrypt_decrypt_video(aes_cipher):
    if not _is_with_associated_data(aes_cipher):
        pytest.skip("Test only for AES with bytes support")

    test_image_path = Path("tests/test_data/video/video_1.mp4")
    if not test_image_path.exists():
        pytest.skip("Test video not found")

    with open(test_image_path, "rb") as f:
        original_bytes = f.read()

    key = os.urandom(32)
    message_uuid = uuid.uuid7()

    encrypted_bytes = await aes_cipher.encrypt_bytes_with_message_uuid(
        plaintext=original_bytes, key=key, message_uuid=message_uuid
    )

    decrypted_bytes = await aes_cipher.decrypt_bytes_with_message_uuid(
        ciphertext=encrypted_bytes, key=key, message_uuid=message_uuid
    )

    assert decrypted_bytes == original_bytes

    output_path = Path("tests/test_data/output/decrypted_video_1.mp4")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(decrypted_bytes)