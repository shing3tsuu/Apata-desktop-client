import asyncio
import logging
import pytest
import uuid
from dishka import make_async_container, Scope

from src.adapters.encryption.dao import (
    Abstract256Cipher,
    AbstractECDHCipher,
    AbstractEDSignature,
)
from src.adapters.encryption.service import EncryptionService
from src.providers import AppProvider
from src.exceptions import SecurityError, DecryptionError, InvalidCiphertextError
from src.adapters.encryption.service.dto import EncryptMessageResult, EncryptMessageToChatResult

from tests.timing_wrapper import timer


@pytest.fixture
async def encryption_service():
    logger = logging.getLogger(__name__)
    provider = AppProvider(
        scope=Scope.APP,
        logger=logger,
        symmetric_cipher="AESGCMSIV",
        asymmetric_cipher="X25519",
        signature_cipher="ED-25519",
        password_cipher="ARGON2",
        base_url="https://test.com",
        verify_ssl=False,
        base_ws_url="wss://test.com",
    )
    container = make_async_container(provider)
    async with container() as request_container:
        aes_cipher = await request_container.get(Abstract256Cipher)
        ecdh_cipher = await request_container.get(AbstractECDHCipher)
        ed_signer = await request_container.get(AbstractEDSignature)
        service = EncryptionService(
            aes_cipher=aes_cipher,
            ecdh_cipher=ecdh_cipher,
            ed_signer=ed_signer,
            logger=logger,
        )
        yield service
    await container.close()


@pytest.fixture
async def alice_keys():
    logger = logging.getLogger(__name__)
    provider = AppProvider(
        scope=Scope.APP,
        logger=logger,
        symmetric_cipher="AESGCMSIV",
        asymmetric_cipher="X25519",
        signature_cipher="ED-25519",
        password_cipher="ARGON2",
        base_url="https://test.com",
        verify_ssl=False,
        base_ws_url="wss://test.com",
    )
    container = make_async_container(provider)
    async with container() as request_container:
        ecdh_cipher = await request_container.get(AbstractECDHCipher)
        ed_signer = await request_container.get(AbstractEDSignature)
        service = EncryptionService(
            aes_cipher=await request_container.get(Abstract256Cipher),
            ecdh_cipher=ecdh_cipher,
            ed_signer=ed_signer,
            logger=logger,
        )
        keys = await service.generate_key_pairs()
        yield {
            "ed_private": keys["ed_private_key"],
            "ed_public": keys["ed_public_key"],
            "ecdh_private": keys["ecdh_private_key"],
            "ecdh_public": keys["ecdh_public_key"],
        }
    await container.close()


@pytest.fixture
async def bob_keys():
    logger = logging.getLogger(__name__)
    provider = AppProvider(
        scope=Scope.APP,
        logger=logger,
        symmetric_cipher="AESGCMSIV",
        asymmetric_cipher="X25519",
        signature_cipher="ED-25519",
        password_cipher="ARGON2",
        base_url="https://test.com",
        verify_ssl=False,
        base_ws_url="wss://test.com",
    )
    container = make_async_container(provider)
    async with container() as request_container:
        ecdh_cipher = await request_container.get(AbstractECDHCipher)
        ed_signer = await request_container.get(AbstractEDSignature)
        service = EncryptionService(
            aes_cipher=await request_container.get(Abstract256Cipher),
            ecdh_cipher=ecdh_cipher,
            ed_signer=ed_signer,
            logger=logger,
        )
        keys = await service.generate_key_pairs()
        signature = await ed_signer.sign_string(
            private_key_pem=keys["ed_private_key"],
            string=keys["ecdh_public_key"],
        )
        yield {
            "ed_private": keys["ed_private_key"],
            "ed_public": keys["ed_public_key"],
            "ecdh_private": keys["ecdh_private_key"],
            "ecdh_public": keys["ecdh_public_key"],
            "ecdh_signature": signature,
        }
    await container.close()


@pytest.fixture
async def charlie_keys():
    logger = logging.getLogger(__name__)
    provider = AppProvider(
        scope=Scope.APP,
        logger=logger,
        symmetric_cipher="AESGCMSIV",
        asymmetric_cipher="X25519",
        signature_cipher="ED-25519",
        password_cipher="ARGON2",
        base_url="https://test.com",
        verify_ssl=False,
        base_ws_url="wss://test.com",
    )
    container = make_async_container(provider)
    async with container() as request_container:
        ecdh_cipher = await request_container.get(AbstractECDHCipher)
        ed_signer = await request_container.get(AbstractEDSignature)
        service = EncryptionService(
            aes_cipher=await request_container.get(Abstract256Cipher),
            ecdh_cipher=ecdh_cipher,
            ed_signer=ed_signer,
            logger=logger,
        )
        keys = await service.generate_key_pairs()
        signature = await ed_signer.sign_string(
            private_key_pem=keys["ed_private_key"],
            string=keys["ecdh_public_key"],
        )
        yield {
            "ed_private": keys["ed_private_key"],
            "ed_public": keys["ed_public_key"],
            "ecdh_private": keys["ecdh_private_key"],
            "ecdh_public": keys["ecdh_public_key"],
            "ecdh_signature": signature,
        }
    await container.close()


@pytest.mark.asyncio
@timer()
async def test_encrypt_decrypt_success(encryption_service, alice_keys, bob_keys):
    message = "Hello, Bob! This is a secret message."
    sender_ed_private = alice_keys["ed_private"]
    recipient_ed_public = bob_keys["ed_public"]
    ephemeral_ecdh_private = alice_keys["ecdh_private"]
    ephemeral_ecdh_public = alice_keys["ecdh_public"]
    recipient_ecdh_public = bob_keys["ecdh_public"]
    recipient_ecdh_signature = bob_keys["ecdh_signature"]

    result = await encryption_service.encrypt_message(
        message=message,
        sender_ed_private_key=sender_ed_private,
        recipient_ed_public_key=recipient_ed_public,
        ephemeral_ecdh_private_key=ephemeral_ecdh_private,
        ephemeral_ecdh_public_key=ephemeral_ecdh_public,
        recipient_ecdh_public_key=recipient_ecdh_public,
        recipient_ecdh_signature=recipient_ecdh_signature,
    )

    assert isinstance(result, EncryptMessageResult)
    assert result.encrypted_message is not None
    assert result.ephemeral_signature is not None
    assert isinstance(result.message_uuid, uuid.UUID)

    decrypted = await encryption_service.decrypt_message(
        message_uuid=result.message_uuid,
        encrypted_message=result.encrypted_message,
        sender_ed_public_key=alice_keys["ed_public"],
        recipient_ecdh_private_key=bob_keys["ecdh_private"],
        ephemeral_ecdh_public_key=ephemeral_ecdh_public,
        ephemeral_signature=result.ephemeral_signature,
    )

    assert decrypted == message


@pytest.mark.asyncio
@timer()
async def test_encrypt_fails_with_invalid_signature(encryption_service, alice_keys, bob_keys):
    message = "Test"
    sender_ed_private = alice_keys["ed_private"]
    recipient_ed_public = bob_keys["ed_public"]
    ephemeral_ecdh_private = alice_keys["ecdh_private"]
    ephemeral_ecdh_public = alice_keys["ecdh_public"]
    recipient_ecdh_public = bob_keys["ecdh_public"]
    invalid_signature = "invalid_signature"

    with pytest.raises(SecurityError, match="Recipient's ECDH key signature is invalid"):
        await encryption_service.encrypt_message(
            message=message,
            sender_ed_private_key=sender_ed_private,
            recipient_ed_public_key=recipient_ed_public,
            ephemeral_ecdh_private_key=ephemeral_ecdh_private,
            ephemeral_ecdh_public_key=ephemeral_ecdh_public,
            recipient_ecdh_public_key=recipient_ecdh_public,
            recipient_ecdh_signature=invalid_signature,
        )


@pytest.mark.asyncio
@timer()
async def test_decrypt_fails_with_invalid_ephemeral_signature(encryption_service, alice_keys, bob_keys):
    message = "Test"
    result = await encryption_service.encrypt_message(
        message=message,
        sender_ed_private_key=alice_keys["ed_private"],
        recipient_ed_public_key=bob_keys["ed_public"],
        ephemeral_ecdh_private_key=alice_keys["ecdh_private"],
        ephemeral_ecdh_public_key=alice_keys["ecdh_public"],
        recipient_ecdh_public_key=bob_keys["ecdh_public"],
        recipient_ecdh_signature=bob_keys["ecdh_signature"],
    )

    with pytest.raises(SecurityError, match="Sender's ephemeral key signature is invalid"):
        await encryption_service.decrypt_message(
            message_uuid=result.message_uuid,
            encrypted_message=result.encrypted_message,
            sender_ed_public_key=alice_keys["ed_public"],
            recipient_ecdh_private_key=bob_keys["ecdh_private"],
            ephemeral_ecdh_public_key=alice_keys["ecdh_public"],
            ephemeral_signature="invalid_signature",
        )


@pytest.mark.asyncio
@timer()
async def test_decrypt_fails_with_wrong_uuid(encryption_service, alice_keys, bob_keys):
    message = "Test"
    result = await encryption_service.encrypt_message(
        message=message,
        sender_ed_private_key=alice_keys["ed_private"],
        recipient_ed_public_key=bob_keys["ed_public"],
        ephemeral_ecdh_private_key=alice_keys["ecdh_private"],
        ephemeral_ecdh_public_key=alice_keys["ecdh_public"],
        recipient_ecdh_public_key=bob_keys["ecdh_public"],
        recipient_ecdh_signature=bob_keys["ecdh_signature"],
    )

    wrong_uuid = uuid.uuid7()

    with pytest.raises(DecryptionError, match="Authentication failed: invalid tag"):
        await encryption_service.decrypt_message(
            message_uuid=wrong_uuid,
            encrypted_message=result.encrypted_message,
            sender_ed_public_key=alice_keys["ed_public"],
            recipient_ecdh_private_key=bob_keys["ecdh_private"],
            ephemeral_ecdh_public_key=alice_keys["ecdh_public"],
            ephemeral_signature=result.ephemeral_signature,
        )


@pytest.mark.asyncio
@timer()
async def test_decrypt_fails_with_wrong_ephemeral_private_key(encryption_service, alice_keys, bob_keys):
    logger = logging.getLogger(__name__)
    provider = AppProvider(
        scope=Scope.APP,
        logger=logger,
        symmetric_cipher="AESGCMSIV",
        asymmetric_cipher="X25519",
        signature_cipher="ED-25519",
        password_cipher="ARGON2",
        base_url="https://test.com",
        verify_ssl=False,
        base_ws_url="wss://test.com",
    )
    container = make_async_container(provider)
    async with container() as request_container:
        ecdh_cipher = await request_container.get(AbstractECDHCipher)
        charlie_private, _ = await ecdh_cipher.generate_key_pair()

    message = "Test"
    result = await encryption_service.encrypt_message(
        message=message,
        sender_ed_private_key=alice_keys["ed_private"],
        recipient_ed_public_key=bob_keys["ed_public"],
        ephemeral_ecdh_private_key=alice_keys["ecdh_private"],
        ephemeral_ecdh_public_key=alice_keys["ecdh_public"],
        recipient_ecdh_public_key=bob_keys["ecdh_public"],
        recipient_ecdh_signature=bob_keys["ecdh_signature"],
    )

    with pytest.raises(DecryptionError, match="Authentication failed: invalid tag"):
        await encryption_service.decrypt_message(
            message_uuid=result.message_uuid,
            encrypted_message=result.encrypted_message,
            sender_ed_public_key=alice_keys["ed_public"],
            recipient_ecdh_private_key=charlie_private,
            ephemeral_ecdh_public_key=alice_keys["ecdh_public"],
            ephemeral_signature=result.ephemeral_signature,
        )


@pytest.mark.asyncio
@timer()
async def test_encrypt_empty_message(encryption_service, alice_keys, bob_keys):
    message = ""
    with pytest.raises(ValueError, match="Data must not be zero length"):
        await encryption_service.encrypt_message(
            message=message,
            sender_ed_private_key=alice_keys["ed_private"],
            recipient_ed_public_key=bob_keys["ed_public"],
            ephemeral_ecdh_private_key=alice_keys["ecdh_private"],
            ephemeral_ecdh_public_key=alice_keys["ecdh_public"],
            recipient_ecdh_public_key=bob_keys["ecdh_public"],
            recipient_ecdh_signature=bob_keys["ecdh_signature"],
        )


@pytest.mark.asyncio
@timer()
async def test_encrypt_message_to_chat_success(encryption_service, alice_keys, bob_keys, charlie_keys):
    message = "Hello everyone!"
    sender_ed_private = alice_keys["ed_private"]
    ephemeral_ecdh_private = alice_keys["ecdh_private"]
    ephemeral_ecdh_public = alice_keys["ecdh_public"]

    bob_uuid = uuid.uuid4()
    charlie_uuid = uuid.uuid4()

    recipient_ed_public_keys = {
        bob_uuid: bob_keys["ed_public"],
        charlie_uuid: charlie_keys["ed_public"],
    }
    recipient_ecdh_public_keys = {
        bob_uuid: bob_keys["ecdh_public"],
        charlie_uuid: charlie_keys["ecdh_public"],
    }
    recipient_ecdh_signatures = {
        bob_uuid: bob_keys["ecdh_signature"],
        charlie_uuid: charlie_keys["ecdh_signature"],
    }

    result = await encryption_service.encrypt_message_to_chat(
        message=message,
        sender_ed_private_key=sender_ed_private,
        recipient_ed_public_keys=recipient_ed_public_keys,
        ephemeral_ecdh_private_key=ephemeral_ecdh_private,
        ephemeral_ecdh_public_key=ephemeral_ecdh_public,
        recipient_ecdh_public_keys=recipient_ecdh_public_keys,
        recipient_ecdh_signatures=recipient_ecdh_signatures,
    )

    assert len(result) == 2
    for item in result:
        assert isinstance(item, EncryptMessageToChatResult)
        assert item.recipient_uuid in (bob_uuid, charlie_uuid)
        assert item.encrypted_message is not None
        assert item.ephemeral_signature is not None
        assert isinstance(item.message_uuid, uuid.UUID)

    for item in result:
        if item.recipient_uuid == bob_uuid:
            recipient_private = bob_keys["ecdh_private"]
            sender_public = alice_keys["ed_public"]
        else:
            recipient_private = charlie_keys["ecdh_private"]
            sender_public = alice_keys["ed_public"]

        decrypted = await encryption_service.decrypt_message(
            message_uuid=item.message_uuid,
            encrypted_message=item.encrypted_message,
            sender_ed_public_key=sender_public,
            recipient_ecdh_private_key=recipient_private,
            ephemeral_ecdh_public_key=ephemeral_ecdh_public,
            ephemeral_signature=item.ephemeral_signature,
        )
        assert decrypted == message


@pytest.mark.asyncio
@timer()
async def test_encrypt_message_to_chat_fails_with_invalid_signature(encryption_service, alice_keys, bob_keys):
    recipient_uuid = uuid.uuid4()
    recipient_ed_public_keys = {recipient_uuid: bob_keys["ed_public"]}
    recipient_ecdh_public_keys = {recipient_uuid: bob_keys["ecdh_public"]}
    recipient_ecdh_signatures = {recipient_uuid: "invalid_signature"}

    with pytest.raises(SecurityError, match="Recipient's ECDH key signature is invalid"):
        await encryption_service.encrypt_message_to_chat(
            message="Test",
            sender_ed_private_key=alice_keys["ed_private"],
            recipient_ed_public_keys=recipient_ed_public_keys,
            ephemeral_ecdh_private_key=alice_keys["ecdh_private"],
            ephemeral_ecdh_public_key=alice_keys["ecdh_public"],
            recipient_ecdh_public_keys=recipient_ecdh_public_keys,
            recipient_ecdh_signatures=recipient_ecdh_signatures,
        )


@pytest.mark.asyncio
@timer()
async def test_encrypt_message_to_chat_mismatched_keys(encryption_service, alice_keys, bob_keys):
    recipient_uuid = uuid.uuid4()
    recipient_ed_public_keys = {recipient_uuid: bob_keys["ed_public"]}
    recipient_ecdh_public_keys = {}

    with pytest.raises(ValueError, match="Mismatched recipient UUID sets"):
        await encryption_service.encrypt_message_to_chat(
            message="Test",
            sender_ed_private_key=alice_keys["ed_private"],
            recipient_ed_public_keys=recipient_ed_public_keys,
            ephemeral_ecdh_private_key=alice_keys["ecdh_private"],
            ephemeral_ecdh_public_key=alice_keys["ecdh_public"],
            recipient_ecdh_public_keys=recipient_ecdh_public_keys,
            recipient_ecdh_signatures={},
        )


@pytest.mark.asyncio
@timer()
async def test_encrypt_message_to_chat_many_recipients(encryption_service, alice_keys, bob_keys):
    message = "Hello everyone!"
    sender_ed_private = alice_keys["ed_private"]
    ephemeral_ecdh_private = alice_keys["ecdh_private"]
    ephemeral_ecdh_public = alice_keys["ecdh_public"]

    num_recipients = 100
    recipient_uuids = [uuid.uuid4() for _ in range(num_recipients)]

    recipient_ed_public_keys = {uid: bob_keys["ed_public"] for uid in recipient_uuids}
    recipient_ecdh_public_keys = {uid: bob_keys["ecdh_public"] for uid in recipient_uuids}
    recipient_ecdh_signatures = {uid: bob_keys["ecdh_signature"] for uid in recipient_uuids}

    result = await encryption_service.encrypt_message_to_chat(
        message=message,
        sender_ed_private_key=sender_ed_private,
        recipient_ed_public_keys=recipient_ed_public_keys,
        ephemeral_ecdh_private_key=ephemeral_ecdh_private,
        ephemeral_ecdh_public_key=ephemeral_ecdh_public,
        recipient_ecdh_public_keys=recipient_ecdh_public_keys,
        recipient_ecdh_signatures=recipient_ecdh_signatures,
    )

    assert len(result) == num_recipients
    for item in result:
        assert isinstance(item, EncryptMessageToChatResult)
        assert item.recipient_uuid in recipient_uuids
        assert item.encrypted_message is not None
        assert item.ephemeral_signature is not None
        assert isinstance(item.message_uuid, uuid.UUID)

    first_item = result[0]
    decrypted = await encryption_service.decrypt_message(
        message_uuid=first_item.message_uuid,
        encrypted_message=first_item.encrypted_message,
        sender_ed_public_key=alice_keys["ed_public"],
        recipient_ecdh_private_key=bob_keys["ecdh_private"],
        ephemeral_ecdh_public_key=ephemeral_ecdh_public,
        ephemeral_signature=first_item.ephemeral_signature,
    )
    assert decrypted == message