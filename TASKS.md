# Tasks

## Task 1 — Track Message Decryption Failures

Add a nullable boolean `failed` field to server-side messages. The field records the result of message processing by the recipient client.

Field states:

- `NULL` — the recipient has not attempted to process and acknowledge the message yet;
- `FALSE` — the message was received and decrypted successfully;
- `TRUE` — the message was received, but decryption failed, for example because of `InvalidTag`.

After attempting decryption, the client must acknowledge the message by its ID regardless of the result and report whether decryption succeeded. Currently, a message is not acknowledged when decryption fails; this behavior must be changed.

Add a separate `/failed` API endpoint for senders. It must return messages sent by the requesting user that recipients marked as failed to decrypt. The sender client must synchronize this result with its local database. In the UI, a failed message must display a cross instead of the successful-delivery indicator.

Constraints:

- do not block key rotation because of messages that failed to decrypt;
- do not add a separate `nack` mechanism;
- do not infer failures indirectly from timestamps or acknowledgement order; the result belongs to a specific `message_id`;
- preserve the distinction between a message that has not been processed (`NULL`), one that was decrypted successfully (`FALSE`), and one that failed to decrypt (`TRUE`).

Implementation notes:

- the server stores `failed` as a nullable boolean and enforces that a non-null processing result belongs to an acknowledged message;
- `POST /ack` accepts per-message processing results, and `GET /failed` returns failed messages sent by the authenticated user;
- the client acknowledges every message with a valid ID after a processing attempt, including decryption failures;
- message synchronization stores sender-side failures in the local database and conversation cache;
- outgoing failed messages use the existing failed bubble state and display a cross;
- the PostgreSQL Alembic migration and the local SQLite schema update were applied during verification.

closed: true

## Task 2 — Connect Local Projects to Their GitHub Repositories

Connect the local APATA client and server projects to the corresponding GitHub repositories that were provided earlier:

- `https://github.com/shing3tsuu/Apata-desktop-client`;
- `https://github.com/shing3tsuu/Apata-router`.

Before configuring remotes, identify the exact local directory that corresponds to each repository and inspect both the local and remote Git histories. Preserve all existing source code, uncommitted work, branches, and useful history. After the repositories are connected safely, upload all intended current project changes to their corresponding repositories.

Establish a task-based Git workflow for future work. After a task is fully implemented, verified, and marked as closed, create a commit in every affected repository and push it to the configured remote. Commit messages must include the task number and exact task title using this format:

`Task <number> — <title>`

Record this Git workflow in `AGENTS.md` after the repository setup has been verified, so future agents consistently commit and push completed tasks.

Constraints:

- verify the local-to-remote repository mapping before changing any remote configuration;
- do not overwrite unrelated local or remote history;
- do not use force push unless the user explicitly requests it after reviewing the exact reason;
- do not commit secrets, credentials, local databases, caches, build output, or other machine-specific artifacts;
- review and update `.gitignore` files before uploading the existing changes;
- keep changes for different task numbers in separate commits whenever practical;
- if a task affects both client and server, use the same task number and title in both repositories.

Implementation notes:

- `apata_frontend` is connected to `Apata-desktop-client`, and `apata-router` is connected to `Apata-router`;
- both local `main` branches track `origin/main`, and the previous remote histories were preserved through non-destructive merge commits without force pushing;
- Git uses the GitHub no-reply author identity and Git Credential Manager with encrypted DPAPI storage;
- global safety settings include fast-forward-only pulls, automatic pruning on fetch, and simple push behavior;
- project `.gitignore` files exclude secrets, databases, virtual environments, caches, build output, logs, and machine-specific files;
- the real server JWT secret was removed from `.env.example` before the first push and replaced with a safe placeholder.

closed: true
