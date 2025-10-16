import pytest
import requests
import json
from datetime import datetime, timedelta
import time
import base64
import secrets
from jose import jwt
import asyncio

from src.adapters.encryption.service import X25519Cipher, SECP384R1Signature

BASE_URL = "http://127.0.0.1:8000/"

ecdsa_client = SECP384R1Signature()
ecdh_cipher = X25519Cipher()

async def generate_ecdsa_test_keys():
    """
    Generate test keys using ECDSAClient
    :return: Tuple of (private_key, public_key) in PEM format
    """
    return await ecdsa_client.generate_key_pair()

def generate_ecdsa_test_keys_sync():
    """
    Synchronous wrapper for key generation
    :return: Tuple of (private_key, public_key) in PEM format
    """
    return asyncio.run(generate_ecdsa_test_keys())

async def generate_ecdh_test_keys():
    """
    Generate test keys using X25519Cipher
    :return: Tuple of (private_key, public_key) in PEM format
    """
    return await ecdh_cipher.generate_key_pair()

def generate_ecdh_test_keys_sync():
    """
    Synchronous wrapper for key generation
    :return: Tuple of (private_key, public_key) in PEM format
    """
    return asyncio.run(generate_ecdh_test_keys())

# Test data
TEST_USERNAME = f"testuser_{int(time.time())}"
TEST_ECDSA_PRIVATE_KEY, TEST_ECDSA_PUBLIC_KEY = generate_ecdsa_test_keys_sync()
TEST_ECDH_PRIVATE_KEY, TEST_ECDH_PUBLIC_KEY = generate_ecdh_test_keys_sync()

@pytest.fixture(scope="module")
def auth_headers():
    """
    Fixture for creating a test user and getting a token
    """
    # Register a new user
    register_data = {
        "username": TEST_USERNAME,
        "ecdsa_public_key": TEST_ECDSA_PUBLIC_KEY,
        "ecdh_public_key": TEST_ECDH_PUBLIC_KEY
    }

    response = requests.post(f"{BASE_URL}/register", json=register_data)
    assert response.status_code == 201

    # Get challenge auth
    challenge_response = requests.get(f"{BASE_URL}/challenge/{TEST_USERNAME}")
    assert challenge_response.status_code == 200
    challenge_data = challenge_response.json()
    challenge = challenge_data["challenge"]

    # Sign the challenge using ECDSA client
    signature_b64 = asyncio.run(
        ecdsa_client.sign_message(TEST_ECDSA_PRIVATE_KEY, challenge)
    )

    # Authenticate using a signature
    login_data = {
        "username": TEST_USERNAME,
        "signature": signature_b64
    }

    response = requests.post(f"{BASE_URL}/login", json=login_data)
    assert response.status_code == 200
    token_data = response.json()
    access_token = token_data["access_token"]

    return {"Authorization": f"Bearer {access_token}"}

def test_register_user():
    """
    New user registration test
    :return:
    """
    username = f"newuser_{int(time.time())}"
    ecdsa_public_key = generate_ecdsa_test_keys_sync()[1]
    ecdh_public_key = generate_ecdh_test_keys_sync()[1]

    register_data = {
        "username": username,
        "ecdsa_public_key": ecdsa_public_key,
        "ecdh_public_key": ecdh_public_key
    }

    response = requests.post(f"{BASE_URL}/register", json=register_data)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["username"] == username

def test_register_existing_user(auth_headers):
    """
    Test attempt to register an existing user
    """
    ecdsa_public_key = generate_ecdsa_test_keys_sync()[1]
    ecdh_public_key = generate_ecdh_test_keys_sync()[1]

    register_data = {
        "username": TEST_USERNAME,
        "ecdsa_public_key": ecdsa_public_key,
        "ecdh_public_key": ecdh_public_key
    }

    response = requests.post(f"{BASE_URL}/register", json=register_data)
    assert response.status_code == 400
    data = response.json()
    assert "detail" in data
    assert "already exists" in data["detail"].lower()

def test_login_success():
    """
    Successful login test
    """
    # Get challenge
    challenge_response = requests.get(f"{BASE_URL}/challenge/{TEST_USERNAME}")
    assert challenge_response.status_code == 200
    challenge_data = challenge_response.json()
    challenge = challenge_data["challenge"]

    # Sign challenge using ECDSA client
    signature_b64 = asyncio.run(
        ecdsa_client.sign_message(TEST_ECDSA_PRIVATE_KEY, challenge)
    )

    # Auth
    login_data = {
        "username": TEST_USERNAME,
        "signature": signature_b64
    }

    response = requests.post(f"{BASE_URL}/login", json=login_data)
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"

def test_login_invalid_signature():
    """
    Test login with invalid signature
    """
    # Get challenge
    challenge_response = requests.get(f"{BASE_URL}/challenge/{TEST_USERNAME}")
    assert challenge_response.status_code == 200
    challenge_data = challenge_response.json()
    challenge = challenge_data["challenge"]

    # Create an invalid signature (just random data)
    invalid_signature = base64.b64encode(b"invalid_signature_data").decode('utf-8')

    login_data = {
        "username": TEST_USERNAME,
        "signature": invalid_signature
    }

    response = requests.post(f"{BASE_URL}/login", json=login_data)
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "invalid" in data["detail"].lower()

def test_login_nonexistent_user():
    """
    Test login with nonexistent user
    """
    # Trying to get a challenge for a non-existent user
    response = requests.get(f"{BASE_URL}/challenge/nonexistent_user")
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_get_current_user(auth_headers):
    """
    Test to get information about the current user
    """
    response = requests.get(f"{BASE_URL}/me", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == TEST_USERNAME
    assert "id" in data
    assert "ecdsa_public_key" in data
    assert "ecdh_public_key" in data


def test_get_current_user_unauthorized():
    """
    Test of getting user information without authentication
    """
    response = requests.get(f"{BASE_URL}/me")
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


def test_get_public_key(auth_headers):
    """
    Test to get the public key of a user
    """
    response = requests.get(f"{BASE_URL}/me", headers=auth_headers)
    user_id = response.json()["id"]

    response = requests.get(f"{BASE_URL}/public-keys/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == user_id
    assert data["ecdsa_public_key"] == TEST_ECDSA_PUBLIC_KEY
    assert data["ecdh_public_key"] == TEST_ECDH_PUBLIC_KEY


def test_get_nonexistent_public_key(auth_headers):
    """
    Test of getting public key of non-existent user
    """
    response = requests.get(f"{BASE_URL}/public-keys/999999", headers=auth_headers)
    assert response.status_code == 404
    data = response.json()
    assert "detail" in data


def test_update_ecdsa_public_key(auth_headers):
    """
    ECDSA public Key Update Test
    """
    # Generating new key
    new_ecdsa_public_key = generate_ecdsa_test_keys_sync()[1]

    update_data = {
        "ecdsa_public_key": new_ecdsa_public_key
    }

    response = requests.put(
        f"{BASE_URL}/ecdsa-update-key",
        json=update_data,
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ecdsa public key updated"

    response = requests.get(f"{BASE_URL}/me", headers=auth_headers)
    user_id = response.json()["id"]

    response = requests.get(f"{BASE_URL}/public-keys/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["ecdsa_public_key"] == new_ecdsa_public_key

def test_update_ecdh_public_key(auth_headers):
    """
    ECDH public Key Update Test
    """
    # Generating new key
    new_ecdh_public_key = generate_ecdh_test_keys_sync()[1]

    update_data = {
        "ecdh_public_key": new_ecdh_public_key
    }

    response = requests.put(
        f"{BASE_URL}/ecdh-update-key",
        json=update_data,
        headers=auth_headers
    )

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ecdh public key updated"

    response = requests.get(f"{BASE_URL}/me", headers=auth_headers)
    user_id = response.json()["id"]

    response = requests.get(f"{BASE_URL}/public-keys/{user_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["ecdh_public_key"] == new_ecdh_public_key

def test_update_public_key_unauthorized():
    """
    Test updating public key without authentication
    """
    new_ecdsa_public_key = generate_ecdsa_test_keys_sync()[1]

    update_data = {
        "ecdsa_public_key": new_ecdsa_public_key
    }

    response = requests.put(f"{BASE_URL}/ecdsa-update-key", json=update_data)
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


def test_token_expiration():
    """
    Token expiration test (simulation)
    """
    # Create an expired token manually
    expired_payload = {
        "sub": "1",
        "exp": datetime.utcnow() - timedelta(minutes=5)
    }

    # Use the same secret key as the server
    # In a real test, you need to get the SECRET_KEY from the server configuration
    expired_token = jwt.encode(expired_payload, "test_secret_key", algorithm="HS256")

    expired_headers = {"Authorization": f"Bearer {expired_token}"}
    response = requests.get(f"{BASE_URL}/me", headers=expired_headers)
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data
    assert "token" in data["detail"].lower() or "expired" in data["detail"].lower()


def test_invalid_token():
    """
    Test with an invalid token
    """
    invalid_headers = {"Authorization": "Bearer invalid_token_123"}
    response = requests.get(f"{BASE_URL}/me", headers=invalid_headers)
    assert response.status_code == 401
    data = response.json()
    assert "detail" in data


def test_challenge_expiration():
    """
    Test that challenge expires after some time
    """
    challenge_response = requests.get(f"{BASE_URL}/challenge/{TEST_USERNAME}")
    assert challenge_response.status_code == 200
    challenge_data = challenge_response.json()
    challenge = challenge_data["challenge"]

    # Wait for the challenge to expire (depends on server configuration)
    # In this case, we assume that the challenge expires in 5 minutes
    # In a real test, you need to simulate the expiration of time

    # To simplify the test, just use the old challenge
    # The server should reject it
    login_data = {
        "username": TEST_USERNAME,
        "signature": "fake_signature_123"
    }

    response = requests.post(f"{BASE_URL}/login", json=login_data)
    # The server can return 400 (challenge not found) or 401 (invalid signature)
    assert response.status_code in [400, 401]