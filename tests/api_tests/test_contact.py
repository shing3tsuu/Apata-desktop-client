import pytest
import requests
import time
import random
from test_auth import BASE_URL, generate_ecdsa_test_keys_sync, generate_ecdh_test_keys_sync

@pytest.fixture(scope="function")
def test_user1():
    """Fixture for creating first test user"""
    return create_test_user(f"testuser1_{int(time.time())}_{random.randint(0, 100000)}")

@pytest.fixture(scope="function")
def test_user2():
    """Fixture for creating second test user"""
    return create_test_user(f"testuser2_{int(time.time())}_{random.randint(0, 100000)}")

def create_test_user(username):
    """Helper function to create a test user and return user info"""
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

    # Get user ID
    user_id = response.json()["id"]

    return {"user_id": user_id, "username": username}


def test_get_users(test_user1, test_user2):
    """Test searching for users by name"""
    # Search for user1
    response = requests.get(
        f"{BASE_URL}/search-users?username={test_user1['username']}"
    )
    assert response.status_code == 200
    users = response.json()
    assert len(users) > 0
    assert any(user["username"] == test_user1["username"] for user in users)

    # Search for non-existent user
    response = requests.get(
        f"{BASE_URL}/search-users?username=nonexistentuser123"
    )
    assert response.status_code == 404


def test_send_contact_request(test_user1, test_user2):
    """Test sending a contact request"""
    request_data = {
        "sender_id": test_user1["user_id"],
        "receiver_id": test_user2["user_id"]
    }

    response = requests.post(
        f"{BASE_URL}/send-contact-request",
        json=request_data
    )
    assert response.status_code == 201

    # Try to send duplicate request
    response = requests.post(
        f"{BASE_URL}/send-contact-request",
        json=request_data
    )
    assert response.status_code == 400

    # Try to send request to self
    self_request_data = {
        "sender_id": test_user1["user_id"],
        "receiver_id": test_user1["user_id"]
    }

    response = requests.post(
        f"{BASE_URL}/send-contact-request",
        json=self_request_data
    )
    assert response.status_code == 400


def test_get_contact_requests(test_user1, test_user2):
    """Test getting contact requests"""
    # First send a request
    request_data = {
        "sender_id": test_user1["user_id"],
        "receiver_id": test_user2["user_id"]
    }

    requests.post(
        f"{BASE_URL}/send-contact-request",
        json=request_data
    )

    # Get contact requests for user2
    response = requests.get(
        f"{BASE_URL}/get-contact-requests?user_id={test_user2['user_id']}"
    )
    assert response.status_code == 200
    requests_list = response.json()
    assert len(requests_list) > 0

    # Get contact requests for user with no requests
    response = requests.get(
        f"{BASE_URL}/get-contact-requests?user_id={test_user1['user_id']}"
    )
    assert response.status_code == 200
    assert len(response.json()) == 0


def test_accept_contact_request(test_user1, test_user2):
    """Test accepting a contact request"""
    # First send a request
    request_data = {
        "sender_id": test_user1["user_id"],
        "receiver_id": test_user2["user_id"]
    }

    requests.post(
        f"{BASE_URL}/send-contact-request",
        json=request_data
    )

    # Accept the request
    accept_data = {
        "sender_id": test_user1["user_id"],
        "receiver_id": test_user2["user_id"]
    }

    response = requests.put(
        f"{BASE_URL}/accept-contact-request",
        json=accept_data
    )
    assert response.status_code == 200

    # Try to accept non-existent request
    fake_accept_data = {
        "sender_id": 99999,
        "receiver_id": test_user2["user_id"]
    }

    response = requests.put(
        f"{BASE_URL}/accept-contact-request",
        json=fake_accept_data
    )
    assert response.status_code == 400


def test_reject_contact_request(test_user1, test_user2):
    """Test rejecting a contact request"""
    # First send a request
    request_data = {
        "sender_id": test_user1["user_id"],
        "receiver_id": test_user2["user_id"]
    }

    requests.post(
        f"{BASE_URL}/send-contact-request",
        json=request_data
    )

    # Reject the request
    reject_data = {
        "sender_id": test_user1["user_id"],
        "receiver_id": test_user2["user_id"]
    }

    response = requests.put(
        f"{BASE_URL}/reject-contact-request",
        json=reject_data
    )
    assert response.status_code == 200

    # Try to reject non-existent request
    fake_reject_data = {
        "sender_id": 99999,
        "receiver_id": test_user2["user_id"]
    }

    response = requests.put(
        f"{BASE_URL}/reject-contact-request",
        json=fake_reject_data
    )
    assert response.status_code == 400


def test_contact_request_workflow(test_user1, test_user2):
    """Test complete contact request workflow"""
    # User1 sends request to User2
    request_data = {
        "sender_id": test_user1["user_id"],
        "receiver_id": test_user2["user_id"]
    }

    response = requests.post(
        f"{BASE_URL}/send-contact-request",
        json=request_data
    )
    assert response.status_code == 201

    # User2 checks pending requests
    response = requests.get(
        f"{BASE_URL}/get-contact-requests?user_id={test_user2['user_id']}"
    )
    assert response.status_code == 200
    requests_list = response.json()
    assert len(requests_list) == 1
    request = requests_list[0]
    assert request["sender_id"] == test_user1["user_id"]
    assert request["receiver_id"] == test_user2["user_id"]
    assert request["status"] == "pending"
    assert "created_at" in request

    # User2 accepts the request
    accept_data = {
        "sender_id": test_user1["user_id"],
        "receiver_id": test_user2["user_id"]
    }

    response = requests.put(
        f"{BASE_URL}/accept-contact-request",
        json=accept_data
    )
    assert response.status_code == 200

    # Verify the request is no longer in pending state
    response = requests.get(
        f"{BASE_URL}/get-contact-requests?user_id={test_user2['user_id']}"
    )
    assert response.status_code == 200
    assert len(response.json()) == 0