import pytest
import asyncio
from unittest.mock import Mock, patch
import base64
from cryptography.exceptions import InvalidTag

from src.adapters.encryption.storage import EncryptedKeyStorage
from src.adapters.encryption.service import KeyManager

# Mock keyring
@pytest.fixture(autouse=True)
def mock_keyring():
    with patch('src.adapters.encryption.storage.keyring_storage.keyring') as mock_keyring:
        yield mock_keyring

@pytest.fixture
def key_manager():
    return KeyManager(600000)

@pytest.fixture
def storage(key_manager):
    return EncryptedKeyStorage(key_manager=key_manager)

@pytest.fixture
def test_username():
    return "test_user"

@pytest.fixture
def test_password():
    return "test_password"

@pytest.fixture
def test_master_key():
    return b"test_master_key_32_bytes_long"

@pytest.fixture
def test_private_key():
    return "test_private_key_pem_data"

def test_is_master_key_registered(storage, mock_keyring, test_username):
    # Test when key exists
    mock_keyring.get_password.return_value = "encrypted_data"
    assert storage.is_master_key_registered(test_username) is True

    # Test when key doesn't exist
    mock_keyring.get_password.return_value = None
    assert storage.is_master_key_registered(test_username) is False

@pytest.mark.asyncio
async def test_register_master_key_success(storage, mock_keyring, test_username, test_password):
    mock_keyring.get_password.return_value = None
    with patch.object(storage.key_manager, 'generate_master_key', return_value=test_master_key), \
            patch.object(storage.key_manager, 'encrypt_master_key', return_value=(b'encrypted', b'salt')):
        result = await storage.register_master_key(test_username, test_password)
        assert result is True
        mock_keyring.set_password.assert_called_once()

@pytest.mark.asyncio
async def test_register_master_key_already_exists(storage, mock_keyring, test_username, test_password):
    mock_keyring.get_password.return_value = "existing_data"
    result = await storage.register_master_key(test_username, test_password)
    assert result is False

@pytest.mark.asyncio
async def test_get_master_key_success(storage, mock_keyring, test_username, test_password):
    encrypted_data = base64.b64encode(b'salt' + b'encrypted_master_key').decode()
    mock_keyring.get_password.return_value = encrypted_data

    with patch.object(storage.key_manager, 'decrypt_master_key', return_value=test_master_key):
        result = await storage._get_master_key(test_username, test_password)
        assert result == test_master_key

@pytest.mark.asyncio
async def test_get_master_key_invalid_password(storage, mock_keyring, test_username, test_password):
    encrypted_data = base64.b64encode(b'salt' + b'encrypted_master_key').decode()
    mock_keyring.get_password.return_value = encrypted_data

    with patch.object(storage.key_manager, 'decrypt_master_key', side_effect=InvalidTag("Invalid password")):
        result = await storage._get_master_key(test_username, test_password)
        assert result is None

@pytest.mark.asyncio
async def test_store_ecdh_private_key_success(storage, mock_keyring, test_username, test_password, test_private_key):
    with patch.object(storage, '_get_master_key', return_value=test_master_key), \
            patch.object(storage.key_manager, 'encrypt_with_master_key', return_value=b'encrypted_data'):
        result = await storage.store_ecdh_private_key(test_username, test_private_key, test_password)
        assert result is True
        mock_keyring.set_password.assert_called_once()

@pytest.mark.asyncio
async def test_get_ecdh_private_key_success(storage, mock_keyring, test_username, test_password):
    mock_keyring.get_password.return_value = base64.b64encode(b'encrypted_data').decode()

    with patch.object(storage, '_get_master_key', return_value=test_master_key), \
            patch.object(storage.key_manager, 'decrypt_with_master_key', return_value=b'decrypted_key'):
        result = await storage.get_ecdh_private_key(test_username, test_password)
        assert result == b'decrypted_key'

@pytest.mark.asyncio
async def test_store_ecdsa_private_key_success(storage, mock_keyring, test_username, test_password, test_private_key):
    with patch.object(storage, '_get_master_key', return_value=test_master_key), \
            patch.object(storage.key_manager, 'encrypt_with_master_key', return_value=b'encrypted_data'):
        result = await storage.store_ecdsa_private_key(test_username, test_password, test_private_key)
        assert result is True
        mock_keyring.set_password.assert_called_once()

@pytest.mark.asyncio
async def test_get_ecdsa_private_key_success(storage, mock_keyring, test_username, test_password):
    mock_keyring.get_password.return_value = base64.b64encode(b'encrypted_data').decode()

    with patch.object(storage, '_get_master_key', return_value=test_master_key), \
            patch.object(storage.key_manager, 'decrypt_with_master_key', return_value=b'decrypted_key'):
        result = await storage.get_ecdsa_private_key(test_username, test_password)
        assert result == 'decrypted_key'

def test_clear_storage(storage, mock_keyring, test_username):
    storage.clear_storage(test_username)
    assert mock_keyring.delete_password.call_count == 3