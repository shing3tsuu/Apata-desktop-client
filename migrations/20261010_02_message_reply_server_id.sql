BEGIN TRANSACTION;

ALTER TABLE messages
ADD COLUMN server_reply_to_id CHAR(32);

CREATE INDEX IF NOT EXISTS ix_messages_server_reply_to_id
ON messages (server_reply_to_id);

COMMIT;
