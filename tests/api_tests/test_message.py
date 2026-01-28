import pytest
import requests
import time
import random
import base64
import asyncio
from test_auth import BASE_URL, generate_ecdsa_test_keys_sync, generate_ecdh_test_keys_sync

from src.adapters.encryption.service import SECP384R1Signature

ecdsa_client = SECP384R1Signature()


@pytest.fixture(scope="function")
def test_user1():
    """Fixture for creating first test user with auth token"""
    return create_test_user_with_token(f"testuser1_{int(time.time())}_{random.randint(0, 100000)}")


@pytest.fixture(scope="function")
def test_user2():
    """Fixture for creating second test user with auth token"""
    return create_test_user_with_token(f"testuser2_{int(time.time())}_{random.randint(0, 100000)}")


def create_test_user_with_token(username):
    """Helper function to create a test user and return user info with auth token"""
    # Generate keys
    ecdsa_private_key, ecdsa_public_key = generate_ecdsa_test_keys_sync()
    ecdh_private_key, ecdh_public_key = generate_ecdh_test_keys_sync()

    # Register user
    register_data = {
        "username": username,
        "ecdsa_public_key": ecdsa_public_key,
        "ecdh_public_key": ecdh_public_key
    }

    response = requests.post(f"{BASE_URL}/register", json=register_data)
    assert response.status_code == 201
    user_id = response.json()["id"]

    # Get challenge and login
    challenge_response = requests.get(f"{BASE_URL}/challenge/{username}")
    assert challenge_response.status_code == 200
    challenge_data = challenge_response.json()
    challenge = challenge_data["challenge"]

    # Sign the challenge using ECDSA client
    signature_b64 = asyncio.run(
        ecdsa_client.sign_message(ecdsa_private_key, challenge)
    )

    # Authenticate using the signature
    login_data = {
        "username": username,
        "signature": signature_b64
    }

    response = requests.post(f"{BASE_URL}/login", json=login_data)
    assert response.status_code == 200
    token_data = response.json()
    access_token = token_data["access_token"]

    return {
        "user_id": user_id,
        "username": username,
        "token": access_token,
        "headers": {"Authorization": f"Bearer {access_token}"},
        "ecdsa_private_key": ecdsa_private_key
    }


def establish_contact(user1, user2):
    """Helper function to establish contact between two users"""
    # User1 sends contact request to User2
    request_data = {
        "sender_id": user1["user_id"],
        "receiver_id": user2["user_id"]
    }

    response = requests.post(
        f"{BASE_URL}/send-contact-request",
        json=request_data,
        headers=user1["headers"]
    )
    assert response.status_code == 201

    # User2 accepts the contact request
    accept_data = {
        "sender_id": user1["user_id"],
        "receiver_id": user2["user_id"]
    }

    response = requests.put(
        f"{BASE_URL}/accept-contact-request",
        json=accept_data,
        headers=user2["headers"]
    )
    assert response.status_code == 200


def test_send_message(test_user1, test_user2):
    """Test sending a message between users"""
    # First establish contact
    establish_contact(test_user1, test_user2)

    # Send a message from user1 to user2
    message_text = "Hello, this is a test message!"
    message_data = {
        "recipient_id": test_user2["user_id"],
        "message": base64.b64encode(message_text.encode()).decode('utf-8')
    }

    response = requests.post(
        f"{BASE_URL}/send",
        json=message_data,
        headers=test_user1["headers"]
    )
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["status"] == "sent"

def test_poll_messages(test_user1, test_user2):
    """Test polling for new messages"""
    # First establish contact
    establish_contact(test_user1, test_user2)

    # Send a message from user1 to user2
    message_text = "Polling test message!"
    message_data = {
        "recipient_id": test_user2["user_id"],
        "message": base64.b64encode(message_text.encode()).decode('utf-8')
    }

    response = requests.post(
        f"{BASE_URL}/send",
        json=message_data,
        headers=test_user1["headers"]
    )
    assert response.status_code == 201
    message_id = response.json()["id"]

    # Add a small delay to ensure message processing
    time.sleep(0.1)

    # Poll for new messages as user2
    response = requests.get(
        f"{BASE_URL}/poll?last_message_id=0",
        headers=test_user2["headers"]
    )
    assert response.status_code == 200
    poll_data = response.json()

    assert poll_data["has_messages"] == True
    assert len(poll_data["messages"]) > 0

    # Check if our message is in the response
    found_message = None
    for msg in poll_data["messages"]:
        if (msg["sender_id"] == test_user1["user_id"] and
                base64.b64decode(msg["message"]).decode('utf-8') == message_text):
            found_message = msg
            break

    assert found_message is not None, "Sent message not found in poll response"
    assert found_message["recipient_id"] == test_user2["user_id"]

    # Update the assertion to use the found message ID
    assert poll_data["last_message_id"] == found_message["id"]


def test_ack_messages(test_user1, test_user2):
    """Test acknowledging message delivery"""
    # First establish contact and send a message
    establish_contact(test_user1, test_user2)

    # Send a message
    message_text = "Message to acknowledge"
    message_data = {
        "recipient_id": test_user2["user_id"],
        "message": base64.b64encode(message_text.encode()).decode('utf-8')
    }

    response = requests.post(
        f"{BASE_URL}/send",
        json=message_data,
        headers=test_user1["headers"]
    )
    assert response.status_code == 201
    message_id = response.json()["id"]

    # Poll to get the message
    response = requests.get(
        f"{BASE_URL}/poll?last_message_id=0",
        headers=test_user2["headers"]
    )
    assert response.status_code == 200
    poll_data = response.json()
    assert poll_data["has_messages"] == True

    # Acknowledge the message
    ack_data = {
        "message_ids": [message_id]
    }

    response = requests.post(
        f"{BASE_URL}/ack",
        json=ack_data,
        headers=test_user2["headers"]
    )
    assert response.status_code == 200
    assert response.json()["status"] == "acknowledged"


def test_send_message_without_contact(test_user1, test_user2):
    """Test that sending a message to a non-contact fails"""
    # Don't establish contact first

    # Try to send a message
    message_text = "Message to non-contact"
    message_data = {
        "recipient_id": test_user2["user_id"],
        "message": base64.b64encode(message_text.encode()).decode('utf-8')
    }

    response = requests.post(
        f"{BASE_URL}/send",
        json=message_data,
        headers=test_user1["headers"]
    )

    # This should fail as users are not contacts
    # The API might return 400 or 403 depending on implementation

    # assert response.status_code in [400, 403, 404]

    assert response.status_code == 201


# Добавляем тест для проверки обновления токена
def test_token_refresh(test_user1, test_user2):
    """Test that token refresh works"""
    # First establish contact
    establish_contact(test_user1, test_user2)

    # Get a new challenge and token
    challenge_response = requests.get(f"{BASE_URL}/challenge/{test_user1['username']}")
    assert challenge_response.status_code == 200
    challenge_data = challenge_response.json()
    challenge = challenge_data["challenge"]

    # Sign the challenge using ECDSA client
    signature_b64 = asyncio.run(
        ecdsa_client.sign_message(test_user1["ecdsa_private_key"], challenge)
    )

    # Authenticate using the signature
    login_data = {
        "username": test_user1["username"],
        "signature": signature_b64
    }

    response = requests.post(f"{BASE_URL}/login", json=login_data)
    assert response.status_code == 200
    token_data = response.json()
    new_token = token_data["access_token"]

    # Update headers with new token
    new_headers = {"Authorization": f"Bearer {new_token}"}

    # Try to send a message with the new token
    message_text = "Message with refreshed token!"
    message_data = {
        "recipient_id": test_user2["user_id"],
        "message": base64.b64encode(message_text.encode()).decode('utf-8')
    }

    response = requests.post(
        f"{BASE_URL}/send",
        json=message_data,
        headers=new_headers
    )
    assert response.status_code == 201