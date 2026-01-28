import pytest
import asyncio
from dishka import make_async_container
from random import randint
from unittest.mock import AsyncMock, patch
import time

from src.providers import AppProvider
from src.adapters.api.service import AuthHTTPService, MessageHTTPService
from src.exceptions import *

number1 = randint(1, 1000000)
number2 = randint(1, 1000000)
fake_user_1 = f"fake_user{number1}"
fake_user_2 = f"fake_user{number2}"

async def get_services():
    container = make_async_container(AppProvider())
    async with container() as request_container:
        auth_service = await request_container.get(AuthHTTPService)
        message_service = await request_container.get(MessageHTTPService)
        return auth_service, message_service, container

async def close_container(container):
    await container.close()

@pytest.mark.asyncio
async def test_long_polling_timeout_behavior():
    auth_service, message_service, container = await get_services()

    try:
        # register user
        user_data = await auth_service.register(fake_user_1 + "_timeout")
        login_data = await auth_service.login(user_data["username"], user_data["ecdsa_private_key"])

        received_messages = []
        polling_called = asyncio.Event()

        async def message_callback(decrypted_message):
            received_messages.append(decrypted_message)

        # create a mock for poll_messages that simulates a timeout
        original_poll = message_service._message_dao.poll_messages

        async def mocked_poll(timeout, token):
            polling_called.set()  # signal that polling has been called
            # simulate a timeout by returning an empty result after a short delay
            await asyncio.sleep(0.1)
            return {"has_messages": False, "messages": []}

        # replace the method with mock
        message_service._message_dao.poll_messages = mocked_poll

        # launch polling with a time limit
        polling_task = asyncio.create_task(
            message_service.start_message_polling(
                token=login_data["access_token"],
                user_private_key=user_data["ecdh_private_key"],
                sender_public_keys={},
                message_callback=message_callback
            )
        )

        # wait for the polling call (maximum 5 seconds)
        try:
            await asyncio.wait_for(polling_called.wait(), timeout=5.0)
        except asyncio.TimeoutError:
            pytest.fail("Polling не был вызван в течение 5 секунд")

        # let polling do some work
        await asyncio.sleep(1)

        # stop polling
        await message_service.stop_message_polling()

        # waiting for the task to complete
        try:
            await asyncio.wait_for(polling_task, timeout=2.0)
        except asyncio.TimeoutError:
            # if the task is not completed, cancel it.
            polling_task.cancel()
            try:
                await polling_task
            except asyncio.CancelledError:
                print("✓ Polling задача отменена")
            except Exception as e:
                print(f"Ошибка при отмене задачи: {e}")

        # check that there are no messages (as expected during the timeout)
        assert len(received_messages) == 0, "Не должно быть полученных сообщений при таймауте"

        # check polling status
        status = message_service.get_polling_status()
        assert status["is_polling"] == False, "Polling должен быть остановлен"
        assert status["task_running"] == False, "Polling задача не должна работать"

        # restoring the original method
        message_service._message_dao.poll_messages = original_poll

    except Exception as e:
        import traceback
        traceback.print_exc()
        pytest.fail(f"Long polling timeout test failed with error: {str(e)}")
    finally:
        await close_container(container)


@pytest.mark.asyncio
async def test_postgres_listen_notify_integration():
    auth_service, message_service, container = await get_services()

    try:
        # register two users
        user1_data = await auth_service.register(fake_user_1 + "_postgres")
        user2_data = await auth_service.register(fake_user_2 + "_postgres")

        # login first user
        login_1 = await auth_service.login(user1_data["username"], user1_data["ecdsa_private_key"])
        token_1 = login_1["access_token"]

        # get public keys for second user
        keys_2 = await auth_service.get_public_keys(user2_data["id"])
        ecdh_public_key_2 = keys_2["ecdh_public_key"]

        # preparing long polling for user 2
        login_2 = await auth_service.login(user2_data["username"], user2_data["ecdsa_private_key"])
        token_2 = login_2["access_token"]

        keys_1 = await auth_service.get_public_keys(user1_data["id"])
        ecdh_public_key_1 = keys_1["ecdh_public_key"]

        received_messages = []
        message_received = asyncio.Event()

        async def message_callback(decrypted_message):
            received_messages.append(decrypted_message)
            message_received.set()

        sender_public_keys = {user1_data["id"]: ecdh_public_key_1}

        # run polling BEFORE sending a message (simulating a real scenario)
        polling_task = asyncio.create_task(
            message_service.start_message_polling(
                token=token_2,
                user_private_key=user2_data["ecdh_private_key"],
                sender_public_keys=sender_public_keys,
                message_callback=message_callback
            )
        )

        # give polling time to connect to the channel
        await asyncio.sleep(1)

        # send a message - this should trigger NOTIFY in PostgreSQL
        original_message = "Test PostgreSQL LISTEN/NOTIFY message"
        send_result = await message_service.send_encrypted_message(
            recipient_id=user2_data["id"],
            message=original_message,
            sender_private_key=user1_data["ecdh_private_key"],
            recipient_public_key=ecdh_public_key_2,
            token=token_1
        )

        assert "id" in send_result

        # wait for a message to be received via the NOTIFY mechanism
        try:
            await asyncio.wait_for(message_received.wait(), timeout=10.0)
        except asyncio.TimeoutError:
            pytest.fail("Message not received via PostgreSQL NOTIFY within timeout")

        # stop polling
        await message_service.stop_message_polling()
        await asyncio.sleep(0.5)

        # check that the message was received and decrypted correctly.
        assert len(received_messages) > 0

        success_messages = [
            msg for msg in received_messages
            if msg.get("decryption_status") == "success"
        ]

        assert len(success_messages) > 0
        assert success_messages[0]["decrypted_content"] == original_message
        assert success_messages[0]["sender_id"] == user1_data["id"]
        assert success_messages[0]["recipient_id"] == user2_data["id"]

    except Exception as e:
        import traceback
        traceback.print_exc()
        pytest.fail(f"PostgreSQL LISTEN/NOTIFY test failed with error: {str(e)}")
    finally:
        await close_container(container)