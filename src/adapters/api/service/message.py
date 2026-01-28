from typing import List, Dict, Any, Optional, Callable
import base64
import asyncio
from datetime import datetime
import logging
import json

from ..dao.message import MessageHTTPDAO
from ..dao.auth import AuthHTTPDAO
from ..dao.websocket import WebSocketDAO
from src.adapters.encryption.service import EncryptionService
from src.exceptions import *

class MessageHTTPService:
    def __init__(
            self,
            message_dao: MessageHTTPDAO,
            auth_dao: AuthHTTPDAO,
            encryption_service: EncryptionService,
            websocket_dao: WebSocketDAO,
            logger: logging.Logger | None = None
    ):
        self._message_dao = message_dao
        self._auth_dao = auth_dao
        self._encryption_service = encryption_service
        self._websocket_dao = websocket_dao
        self._logger = logger or logging.getLogger(__name__)

        self._current_token: str | None = None
        self._user_private_key: str | None = None
        self._message_callback: Optional[Callable] = None
        self._is_listening = False
        self._listening_task: Optional[asyncio.Task] = None

    def set_token(self, token: str):
        """Set authentication token"""
        self._current_token = token

    def clear_token(self):
        """Clear authentication token"""
        self._current_token = None

    async def send_encrypted_message(
            self,
            recipient_id: int,
            message: str,
            content_type: str,
            recipient_ecdsa_public_key: str,
            sender_ecdsa_private_key: str,
            sender_ecdh_private_key: str,
            ephemeral_ecdh_public_key: str,
            recipient_public_key: str | None = None # not using now
    ) -> dict[str, Any]:
        context = {
            "operation": "send_encrypted_message",
            "recipient_id": recipient_id,
            "content_type": content_type,
            "message_length": len(message)
        }

        self._logger.info(
            f"Sending encrypted message to user {recipient_id}",
            extra={"context": context}
        )

        try:
            keys = await self._auth_dao.get_public_keys(recipient_id, self._current_token)
            recipient_ecdh_public_key = keys["ecdh_public_key"]
            recipient_ecdh_signature = keys["ecdh_signature"]
            # Encrypt the message
            encrypted_message, signature = await self._encryption_service.encrypt_message(
                message=message,
                sender_ecdsa_private_key=sender_ecdsa_private_key,
                recipient_ecdsa_public_key=recipient_ecdsa_public_key,
                ephemeral_ecdh_private_key=sender_ecdh_private_key,
                ephemeral_ecdh_public_key=ephemeral_ecdh_public_key,
                recipient_ecdh_public_key=recipient_ecdh_public_key,
                recipient_ecdh_signature=recipient_ecdh_signature
            )

            context["encryption_success"] = True
            context["encrypted_length"] = len(encrypted_message)

            # Send via DAO
            result = await self._message_dao.send_message(
                recipient_id=recipient_id,
                message=encrypted_message,
                content_type=content_type,
                ephemeral_public_key=ephemeral_ecdh_public_key,
                ephemeral_signature=signature,
                token=self._current_token
            )

            self._logger.info(
                f"Encrypted message sent successfully to {recipient_id}",
                extra={"context": {**context, "status": "success"}}
            )

            return result

        except (EncryptionError, DecryptionError) as e:
            self._logger.error(
                "Encryption error while sending message",
                extra={"context": context},
                exc_info=True
            )
            raise MessageDeliveryError(
                f"Message encryption failed: {str(e)}",
                original_error=e,
                context=context
            ) from e

        except AuthenticationError as e:
            self._logger.warning(
                f"Authentication failed while sending message: {str(e)}",
                extra={"context": context}
            )
            self.clear_token()
            raise

        except APIError as e:
            self._logger.error(
                f"API error while sending message: {e.message}",
                extra={"context": {**context, "status_code": e.status_code}}
            )
            raise MessageDeliveryError(
                f"Message delivery API error: {e.message}",
                original_error=e,
                context=context
            ) from e

        except Exception as e:
            self._logger.error(
                "Unexpected error while sending encrypted message",
                extra={"context": context},
                exc_info=True
            )
            raise InfrastructureError(
                f"Failed to send encrypted message: {str(e)}",
                original_error=e,
                context=context
            ) from e

    async def get_undelivered_messages(
            self,
            ecdsa_dict: dict[int, str],
            recipient_ecdh_private_key: str,
    ) -> list[dict[str, Any]]:
        context = {
            "operation": "get_undelivered_messages",
            "has_private_key": bool(recipient_ecdh_private_key)
        }

        self._logger.info(
            "Retrieving undelivered messages",
            extra={"context": context}
        )

        try:
            response = await self._message_dao.get_undelivered_messages(token=self._current_token)

            if not response.get("has_messages") or not response.get("messages"):
                self._logger.debug(
                    "No undelivered messages found",
                    extra={"context": context}
                )
                return []

            encrypted_messages = response["messages"]
            message_ids = []
            decrypted_messages = []
            success_count = 0
            failure_count = 0

            context["total_messages"] = len(encrypted_messages)

            for message in encrypted_messages:
                message_context = {
                    **context,
                    "message_id": message.get("id"),
                    "sender_id": message.get("sender_id")
                }

                try:
                    sender_id = message.get('sender_id')
                    sender_ecdsa_public_key = ecdsa_dict.get(sender_id)

                    decrypted_content = await self._encryption_service.decrypt_message(
                        encrypted_message=message['message'],
                        sender_ecdsa_public_key=sender_ecdsa_public_key,
                        recipient_ecdh_private_key=recipient_ecdh_private_key,
                        ephemeral_ecdh_public_key=message['ephemeral_public_key'],
                        ephemeral_signature=message['ephemeral_signature']
                    )

                    decrypted_message = {
                        **message,
                        "decrypted_content": decrypted_content,
                        "decryption_status": "success"
                    }
                    message_ids.append(message["id"])
                    decrypted_messages.append(decrypted_message)
                    success_count += 1

                    self._logger.debug(
                        f"Successfully decrypted message {message['id']}",
                        extra={"context": message_context}
                    )

                except DecryptionError as e:
                    self._logger.error(
                        f"Decryption failed for message {message.get('id')}, {str(e)}",
                        extra={"context": message_context},
                        exc_info=True
                    )
                    error_message = {
                        **message,
                        "decrypted_content": None,
                        "decryption_status": "failed",
                        "decryption_error": str(e)
                    }
                    message_ids.append(message["id"])
                    decrypted_messages.append(error_message)
                    failure_count += 1

                except Exception as e:
                    self._logger.error(
                        f"Unexpected error processing message {message.get('id')}",
                        extra={"context": message_context},
                        exc_info=True
                    )
                    error_message = {
                        **message,
                        "decrypted_content": None,
                        "decryption_status": "error",
                        "decryption_error": f"Unexpected error: {str(e)}"
                    }
                    message_ids.append(message["id"])
                    decrypted_messages.append(error_message)
                    failure_count += 1

            # Acknowledge processed messages
            if message_ids:
                await self._message_dao.ack_messages(message_ids=message_ids, token=self._current_token)
                context["acknowledged_messages"] = len(message_ids)

            self._logger.info(
                f"Retrieved {success_count} messages ({failure_count} failures)",
                extra={"context": {**context, "success_count": success_count, "failure_count": failure_count}}
            )

            return decrypted_messages

        except AuthenticationError as e:
            self._logger.warning(
                f"Authentication failed while retrieving messages: {str(e)}",
                extra={"context": context}
            )
            self.clear_token()
            return []

        except Exception as e:
            self._logger.error(
                f"Error getting undelivered messages: {str(e)}",
                extra={"context": context},
                exc_info=True
            )
            return []

    async def start_websocket_listener(
            self,
            token: str,
            user_private_key: str,
            message_callback: Callable
    ) -> bool:
        context = {
            "operation": "start_websocket_listener",
            "has_callback": bool(message_callback)
        }

        self._logger.info(
            "Starting WebSocket listener",
            extra={"context": context}
        )

        if self._is_listening:
            self._logger.warning(
                "WebSocket listener is already running",
                extra={"context": context}
            )
            return False

        try:
            self._current_token = token
            self._user_private_key = user_private_key
            self._message_callback = message_callback

            # Connect to WebSocket
            connected = await self._websocket_dao.connect(token)
            if not connected:
                self._logger.error(
                    "Failed to connect to WebSocket",
                    extra={"context": context}
                )
                return False

            self._is_listening = True

            # Start listening task
            self._listening_task = asyncio.create_task(
                self._websocket_listener_loop()
            )

            self._logger.info(
                "WebSocket listener started successfully",
                extra={"context": {**context, "status": "success"}}
            )
            return True

        except AuthenticationError as e:
            self._logger.error(
                f"Authentication failed while starting WebSocket listener: {str(e)}",
                extra={"context": context}
            )
            self.clear_token()
            return False

        except NetworkError as e:
            self._logger.error(
                f"Network error while starting WebSocket listener: {str(e)}",
                extra={"context": context}
            )
            return False

        except Exception as e:
            self._logger.error(
                "Unexpected error while starting WebSocket listener",
                extra={"context": context},
                exc_info=True
            )
            return False

    async def _websocket_listener_loop(self):
        """Main WebSocket listener loop"""
        context = {"operation": "websocket_listener_loop"}

        self._logger.debug(
            "WebSocket listener loop started",
            extra={"context": context}
        )

        try:
            await self._websocket_dao.listen_for_messages(self._handle_websocket_message)
        except Exception as e:
            if self._is_listening:  # Only log if we're supposed to be listening
                self._logger.error(
                    f"WebSocket listener loop error: {str(e)}",
                    extra={"context": context},
                    exc_info=True
                )
            # The loop will exit and we'll set _is_listening to False in stop_websocket_listener

    async def _handle_websocket_message(self, message_str: str):
        context = {"operation": "handle_websocket_message"}

        try:
            message_data = json.loads(message_str)
            message_type = message_data.get("type")

            context["message_type"] = message_type
            self._logger.debug(
                f"Received WebSocket message type: {message_type}",
                extra={"context": context}
            )

            if message_type == "message" or ("message" in message_data and "sender_id" in message_data):
                await self._process_incoming_message(message_data)
            elif message_type == "user_status":
                await self._handle_user_status(message_data)
            elif message_type == "pong":
                # Ignore pong messages
                pass
            else:
                self._logger.warning(
                    f"Unknown WebSocket message type: {message_type}",
                    extra={"context": context}
                )

        except json.JSONDecodeError as e:
            self._logger.error(
                f"Invalid JSON in WebSocket message: {message_str[:100]}... {str(e)}",
                extra={"context": context}
            )
        except Exception as e:
            self._logger.error(
                f"Error handling WebSocket message: {str(e)}",
                extra={"context": context},
                exc_info=True
            )

    async def _process_incoming_message(self, message_data: dict[str, Any]):
        context = {
            "operation": "process_incoming_message",
            "message_id": message_data.get("id"),
            "sender_id": message_data.get("sender_id")
        }

        self._logger.debug(
            f"Processing incoming message {message_data.get('id')}",
            extra={"context": context}
        )

        try:
            user_id = message_data["sender_id"]
            sender_public_keys = await self._auth_dao.get_public_keys(user_id=user_id, token=self._current_token)

            decrypted_content = await self._encryption_service.decrypt_message(
                encrypted_message=message_data["message"],
                sender_ecdsa_public_key=sender_public_keys["ecdsa_public_key"],
                recipient_ecdh_private_key=self._user_private_key,
                ephemeral_ecdh_public_key=message_data["ephemeral_public_key"],
                ephemeral_signature=message_data["ephemeral_signature"]
            )

            processed_message = {
                **message_data,
                "decrypted_content": decrypted_content,
                "decryption_status": "success"
            }

            # Call user callback
            if self._message_callback:
                try:
                    await self._message_callback(processed_message)
                except Exception as e:
                    self._logger.error(
                        f"Error in user message callback: {str(e)}",
                        extra={"context": context},
                        exc_info=True
                    )

            # Acknowledge message delivery
            await self._message_dao.ack_messages([message_data["id"]], token=self._current_token)

            self._logger.debug(
                f"Successfully processed message {message_data['id']}",
                extra={"context": context}
            )

        except DecryptionError as e:
            self._logger.error(
                f"Decryption failed for message {message_data.get('id')}",
                extra={"context": context},
                exc_info=True
            )

            error_message = {
                **message_data,
                "decrypted_content": None,
                "decryption_status": "failed",
                "decryption_error": str(e)
            }

            if self._message_callback:
                try:
                    await self._message_callback(error_message)
                except Exception as callback_error:
                    self._logger.error(
                        f"Error in user error callback: {str(callback_error)}",
                        extra={"context": context},
                        exc_info=True
                    )

        except Exception as e:
            self._logger.error(
                f"Unexpected error processing message {message_data.get('id')}. {str(e)}",
                extra={"context": context},
                exc_info=True
            )

    async def _handle_user_status(self, status_data: dict[str, Any]):
        context = {
            "operation": "handle_user_status",
            "user_id": status_data.get("user_id"),
            "online": status_data.get("online")
        }

        self._logger.debug(
            f"Processing user status update: user {status_data['user_id']} - {status_data['online']}",
            extra={"context": context}
        )

        if self._message_callback:
            try:
                status_message = {
                    "type": "user_status",
                    "user_id": status_data["user_id"],
                    "online": status_data["online"],
                    "timestamp": status_data.get("timestamp")
                }
                await self._message_callback(status_message)
            except Exception as e:
                self._logger.error(
                    f"Error in user status callback: {str(e)}",
                    extra={"context": context},
                    exc_info=True
                )

    async def stop_websocket_listener(self):
        try:
            context = {"operation": "stop_websocket_listener"}

            if not self._is_listening:
                self._logger.debug(
                    "WebSocket listener already stopped",
                    extra={"context": context}
                )
                return

            self._logger.info(
                "Stopping WebSocket listener",
                extra={"context": context}
            )

            self._is_listening = False

            # Cancel listening task
            if self._listening_task and not self._listening_task.done():
                self._listening_task.cancel()
                try:
                    await self._listening_task
                except asyncio.CancelledError:
                    pass
                self._listening_task = None

            # Disconnect WebSocket
            await self._websocket_dao.disconnect()

            # Clear state
            self._message_callback = None

            self._logger.info(
                "WebSocket listener stopped successfully",
                extra={"context": {**context, "status": "success"}}
            )
        except Exception as e:
            self._logger.error(f"Error stopping WebSocket listener: {e}", exc_info=True)
            raise

    def get_connection_status(self) -> dict[str, Any]:
        status = {
            "is_connected": self._websocket_dao.is_connected,
            "is_listening": self._is_listening,
            "has_token": self._current_token is not None,
            "has_callback": self._message_callback is not None,
            "timestamp": datetime.utcnow().isoformat()
        }

        self._logger.debug(
            "Connection status retrieved",
            extra={"context": {"operation": "get_connection_status", "status": status}}
        )

        return status

    async def health_check(self) -> bool:
        """Check if message service is healthy"""
        context = {"operation": "health_check"}

        try:
            # Check if we can access message API
            health_ok = await self._message_dao.health_check()

            self._logger.debug(
                f"Message service health check: {health_ok}",
                extra={"context": context}
            )
            return health_ok

        except Exception as e:
            self._logger.error(
                f"Message service health check failed: {str(e)}",
                extra={"context": context},
                exc_info=True
            )
            return False