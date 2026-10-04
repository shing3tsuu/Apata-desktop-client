ALTER TABLE messages ADD COLUMN logical_message_id CHAR(32);

UPDATE messages
SET logical_message_id = server_message_id
WHERE logical_message_id IS NULL;

CREATE INDEX IF NOT EXISTS ix_messages_logical_message_id
ON messages (logical_message_id);
