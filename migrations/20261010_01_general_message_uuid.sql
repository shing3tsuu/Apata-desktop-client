BEGIN TRANSACTION;

DROP INDEX IF EXISTS ix_messages_logical_message_id;

ALTER TABLE messages
RENAME COLUMN logical_message_id TO general_message_uuid;

UPDATE messages
SET general_message_uuid = NULL
WHERE chat_id IS NULL;

CREATE INDEX IF NOT EXISTS ix_messages_general_message_uuid
ON messages (general_message_uuid);

COMMIT;
