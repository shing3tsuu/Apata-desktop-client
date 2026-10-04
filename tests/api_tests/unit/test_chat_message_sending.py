import logging
from datetime import UTC, datetime
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from src.adapters.api.dao import AuthHTTPDAO, MessageHTTPDAO
from src.adapters.api.service import MessageHTTPService
from src.adapters.encryption.dao import AbstractECDHCipher, AbstractEDSignature
from src.adapters.encryption.dao.aes import AbstractCipherWithMessageUUID
from src.adapters.encryption.service import EncryptionService
from src.adapters.encryption.service.dto import EncryptMessageToChatResult
from src.exceptions import APIError, SecurityError

pytestmark = pytest.mark.asyncio


async def test_chat_message_service_builds_one_validated_fan_out_batch() -> None:
    first_recipient_id = uuid4()
    second_recipient_id = uuid4()
    first_delivery_id = uuid4()
    second_delivery_id = uuid4()
    timestamp = datetime.now(UTC)
    auth_dao = AsyncMock(spec=AuthHTTPDAO)
    auth_dao.get_ecdh_public_keys_batch.return_value = [
        {
            "user_id": str(first_recipient_id),
            "ecdh_public_key": "first-ecdh-key",
            "ecdh_signature": "first-ecdh-signature",
        },
        {
            "user_id": str(second_recipient_id),
            "ecdh_public_key": "second-ecdh-key",
            "ecdh_signature": "second-ecdh-signature",
        },
    ]
    encryption_service = AsyncMock(spec=EncryptionService)
    encryption_service.encrypt_message_to_chat.return_value = [
        EncryptMessageToChatResult(
            recipient_uuid=first_recipient_id,
            encrypted_message="first-ciphertext",
            ephemeral_signature="sender-signature",
            message_uuid=first_delivery_id,
        ),
        EncryptMessageToChatResult(
            recipient_uuid=second_recipient_id,
            encrypted_message="second-ciphertext",
            ephemeral_signature="sender-signature",
            message_uuid=second_delivery_id,
        ),
    ]
    message_dao = AsyncMock(spec=MessageHTTPDAO)

    async def return_batch(*, chat_id, batch, token):
        assert chat_id == server_chat_id
        assert token == "access-token"
        assert {item.message for item in batch.deliveries} == {
            "first-ciphertext",
            "second-ciphertext",
        }
        return [
            {
                "id": str(item.message_id),
                "logical_message_id": str(batch.logical_message_id),
                "recipient_id": str(item.recipient_id),
                "timestamp": timestamp.isoformat(),
            }
            for item in batch.deliveries
        ]

    message_dao.send_chat_message_text.side_effect = return_batch
    service = MessageHTTPService(
        message_dao=message_dao,
        auth_dao=auth_dao,
        encryption_service=encryption_service,
        logger=logging.getLogger(__name__),
    )
    service.token = "access-token"
    server_chat_id = uuid4()

    result = await service.send_encrypted_chat_message_text(
        chat_id=server_chat_id,
        message="hello chat",
        recipient_ed_public_keys={
            first_recipient_id: "first-ed-key",
            second_recipient_id: "second-ed-key",
        },
        sender_ed_private_key="sender-ed-private-key",
        sender_ecdh_private_key="sender-ecdh-private-key",
        sender_ecdh_public_key="sender-ecdh-public-key",
    )

    assert {item.id for item in result} == {
        first_delivery_id,
        second_delivery_id,
    }
    assert len({item.logical_message_id for item in result}) == 1
    assert len({item.timestamp for item in result}) == 1
    auth_dao.get_ecdh_public_keys_batch.assert_awaited_once()
    encryption_service.encrypt_message_to_chat.assert_awaited_once()
    message_dao.send_chat_message_text.assert_awaited_once()


@pytest.mark.parametrize("duplicate", [False, True])
async def test_chat_message_service_rejects_invalid_bulk_key_results(
    duplicate: bool,
) -> None:
    first_recipient_id = uuid4()
    second_recipient_id = uuid4()
    returned_ids = (
        [first_recipient_id, first_recipient_id] if duplicate else [first_recipient_id]
    )
    auth_dao = AsyncMock(spec=AuthHTTPDAO)
    auth_dao.get_ecdh_public_keys_batch.return_value = [
        {
            "user_id": str(user_id),
            "ecdh_public_key": "ecdh-key",
            "ecdh_signature": "ecdh-signature",
        }
        for user_id in returned_ids
    ]
    encryption_service = AsyncMock(spec=EncryptionService)
    message_dao = AsyncMock(spec=MessageHTTPDAO)
    service = MessageHTTPService(
        message_dao=message_dao,
        auth_dao=auth_dao,
        encryption_service=encryption_service,
        logger=logging.getLogger(__name__),
    )
    service.token = "access-token"

    with pytest.raises(APIError, match="does not match"):
        await service.send_encrypted_chat_message_text(
            chat_id=uuid4(),
            message="hello chat",
            recipient_ed_public_keys={
                first_recipient_id: "first-ed-key",
                second_recipient_id: "second-ed-key",
            },
            sender_ed_private_key="sender-ed-private-key",
            sender_ecdh_private_key="sender-ecdh-private-key",
            sender_ecdh_public_key="sender-ecdh-public-key",
        )

    encryption_service.encrypt_message_to_chat.assert_not_awaited()
    message_dao.send_chat_message_text.assert_not_awaited()


async def test_chat_encryption_signs_once_and_uses_distinct_delivery_ids() -> None:
    first_recipient_id = uuid4()
    second_recipient_id = uuid4()
    aes_cipher = AsyncMock(spec=AbstractCipherWithMessageUUID)
    aes_cipher.encrypt_with_message_uuid.side_effect = (
        lambda *, plaintext, key, message_uuid: (
            f"{plaintext}:{key.hex()}:{message_uuid}"
        )
    )
    ecdh_cipher = AsyncMock(spec=AbstractECDHCipher)
    ecdh_cipher.derive_shared_key.side_effect = [b"first-key", b"second-key"]
    ed_signer = AsyncMock(spec=AbstractEDSignature)
    ed_signer.sign_string.return_value = "sender-signature"
    ed_signer.verify_signature.return_value = True
    service = EncryptionService(
        aes_cipher=aes_cipher,
        ecdh_cipher=ecdh_cipher,
        ed_signer=ed_signer,
        logger=logging.getLogger(__name__),
    )

    result = await service.encrypt_message_to_chat(
        message="hello chat",
        sender_ed_private_key="sender-ed-private-key",
        recipient_ed_public_keys={
            first_recipient_id: "first-ed-key",
            second_recipient_id: "second-ed-key",
        },
        ephemeral_ecdh_private_key="sender-ecdh-private-key",
        ephemeral_ecdh_public_key="sender-ecdh-public-key",
        recipient_ecdh_public_keys={
            first_recipient_id: "first-ecdh-key",
            second_recipient_id: "second-ecdh-key",
        },
        recipient_ecdh_signatures={
            first_recipient_id: "first-ecdh-signature",
            second_recipient_id: "second-ecdh-signature",
        },
    )

    assert {item.recipient_uuid for item in result} == {
        first_recipient_id,
        second_recipient_id,
    }
    assert len({item.message_uuid for item in result}) == 2
    assert len({item.encrypted_message for item in result}) == 2
    assert {item.ephemeral_signature for item in result} == {"sender-signature"}
    ed_signer.sign_string.assert_awaited_once()
    assert ed_signer.verify_signature.await_count == 2


async def test_chat_encryption_rejects_invalid_recipient_signature_atomically() -> None:
    recipient_id = uuid4()
    aes_cipher = AsyncMock(spec=AbstractCipherWithMessageUUID)
    ecdh_cipher = AsyncMock(spec=AbstractECDHCipher)
    ecdh_cipher.derive_shared_key.return_value = b"shared-key"
    ed_signer = AsyncMock(spec=AbstractEDSignature)
    ed_signer.sign_string.return_value = "sender-signature"
    ed_signer.verify_signature.return_value = False
    service = EncryptionService(
        aes_cipher=aes_cipher,
        ecdh_cipher=ecdh_cipher,
        ed_signer=ed_signer,
        logger=logging.getLogger(__name__),
    )

    with pytest.raises(SecurityError, match="signature is invalid"):
        await service.encrypt_message_to_chat(
            message="hello chat",
            sender_ed_private_key="sender-ed-private-key",
            recipient_ed_public_keys={recipient_id: "recipient-ed-key"},
            ephemeral_ecdh_private_key="sender-ecdh-private-key",
            ephemeral_ecdh_public_key="sender-ecdh-public-key",
            recipient_ecdh_public_keys={recipient_id: "recipient-ecdh-key"},
            recipient_ecdh_signatures={recipient_id: "invalid-signature"},
        )

    aes_cipher.encrypt_with_message_uuid.assert_not_awaited()
