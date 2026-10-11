BEGIN TRANSACTION;

ALTER TABLE messages
ADD COLUMN reply_to_general_message_uuid CHAR(32);

CREATE INDEX IF NOT EXISTS ix_messages_reply_to_general_message_uuid
ON messages (reply_to_general_message_uuid);

COMMIT;
