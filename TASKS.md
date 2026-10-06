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

## Task 3 — Send Fan-Out Encrypted Chat Text Messages

Implement text message sending to chats through a new messenger interactor. A chat message is one logical message represented on the server by a fan-out batch containing one independently encrypted delivery per active recipient. Each delivery must use the recipient-specific ECDH shared secret and its own delivery ID, while all deliveries share one logical message ID.

### Trust and contact establishment

The ED public key is a trust-on-first-use key and must be pinned locally when two users first become known to each other. It must never be refreshed or overwritten from subsequent server responses. The client may accept a server-provided ED public key only when it is creating a previously unknown local contact. Existing contacts must continue using the ED public key stored in the local database, including when the server returns a different value.

When a user is added to a chat, the server must create `BLANK` contact relationships between the new participant and every currently active participant in the same transaction as the membership change. Create all missing relationships with one bulk insert using conflict-safe behavior. Existing relationships and their statuses, including `ACCEPTED` and `BLACKLISTED`, must not be modified. If the users already became known through another chat, reuse the existing relationship.

Publish the existing `chat_changed` WebSocket event only after the membership and contact transaction has committed. Do not introduce another WebSocket event type and do not send key material through WebSocket payloads. The event remains an invalidation notification that makes the client synchronize contacts before chats. The existing `message_available` path must continue synchronizing contacts, then chats, then messages, so a message sent immediately after an invitation can be decrypted without restarting either client.

### Current keys and fan-out encryption

Before sending, the interactor must obtain the current active participant IDs through the existing chat participant API and exclude the authenticated sender. It must compare this authoritative set with locally stored contacts. If any participant is missing locally, run contact synchronization once, reload the contacts from the local database, and stop the entire send if any participant still lacks a pinned ED public key. Never silently omit a participant from the fan-out batch.

Add a bulk operation for retrieving only the current ECDH public key and ECDH signature for a bounded list of user IDs. This may extend the existing public-key API, DAO, and service, but it must not introduce an `encryption-targets` domain or persistence entity. The bulk response must not be used to obtain or replace ED public keys. Verify every returned ECDH signature against the corresponding locally pinned ED public key before encrypting any delivery. Reject incomplete, duplicated, unexpected, or invalid key results as an atomic send failure.

Refine `EncryptionService.encrypt_message_to_chat` so that it returns the declared `list[EncryptMessageToChatResult]`, signs the sender ECDH public key once per logical message, and uses bounded concurrency appropriate for low-end client hardware. Every recipient must receive a unique ciphertext and delivery UUID. Any encryption or signature-verification failure must cancel the complete fan-out operation.

### API contract and server persistence

Use a batch request that contains shared logical-message metadata and a list of recipient deliveries. The shared portion must contain the logical message ID, text content type, sender ECDH public key, and its ED signature. Each delivery must contain its unique delivery ID, recipient ID, and ciphertext. Assign one server-side UTC timestamp to the entire logical message. Do not trust a client-provided sender ID, chat ID, or timestamp.

Keep the existing `POST /chats/{chat_id}/messages` route and existing single-statement message insert, adapting their DTOs rather than creating a parallel message subsystem. Before inserting, the server must verify atomically that:

- the sender is an active chat participant;
- recipient IDs are unique and do not contain the sender;
- the submitted recipient set exactly equals all active participants except the sender;
- every delivery belongs to the same logical message and contains text only;
- configured participant, text-length, and request-size limits are respected.

If membership changes while encryption is in progress, reject the entire batch with a conflict response. The client may synchronize the new participant set and rebuild the whole encrypted batch, but must never submit or retain a partial batch. Database persistence must remain all-or-nothing.

Create missing sender-to-recipient `BLANK` relationships as a bulk conflict-safe operation before inserting the deliveries. This is a safety net for chats created before eager relationship creation and must preserve every existing contact status. Remove the current per-recipient `_ensure_blank_contact` N+1 behavior from the chat batch path. Publish one `message_available` notification to the deduplicated recipient set only after the transaction commits.

Use the shared logical message ID as the idempotency and conversation-level identity. Network retries must reuse the same logical ID and delivery IDs so an uncertain response cannot create a duplicate logical message. Preserve individual delivery IDs for encryption associated data and recipient acknowledgements. Store the logical ID in server and local message data so later reply, delete, or edit operations can address the logical chat message instead of an arbitrary recipient delivery. Apply explicit database migrations; do not add runtime schema-migration workarounds.

### Client interactor and local state

Add `SendChatTextMessageInteractor` to `src/presentation/interactors/messenger.py`, following the existing container and `AppState` conventions. It must:

1. validate non-empty text and all authentication, local-user, master-key, ED, and ECDH prerequisites;
2. resolve the selected local chat and its server chat ID;
3. obtain the authoritative active participant set and ensure all pinned ED keys exist locally, synchronizing contacts once when necessary;
4. bulk-fetch current ECDH keys and signatures and verify all of them using the pinned ED keys;
5. build the complete encrypted fan-out batch and send it with one HTTP request;
6. after a successful server response, persist exactly one outgoing plaintext local chat message and update the corresponding `ChatCache.messages` collection;
7. return a clear failure without saving a successful local message when any prerequisite, participant, key, encryption, validation, or network step fails.

The local outgoing record represents the logical chat message, not one record per recipient. Keep delivery identity and logical identity distinct in local DTOs, structures, cache objects, and deduplication logic. A successful HTTP batch response means that the server accepted the complete message; it does not mean that every recipient decrypted it.

Recipients must continue acknowledging every delivery as successfully or unsuccessfully processed so undelivered messages do not repeat forever. However, chat delivery failures must not be aggregated or displayed to the sender in this task. Sender-side `/failed` synchronization must apply only to direct messages with no `chat_id`. Do not implement per-member delivery indicators or failed-recipient UI for chat messages.

Only text chat messages are in scope. Do not implement fan-out file uploads or connect the new interactor to the messenger UI in this task.

### Verification

Add unit coverage for pinned ED preservation, missing-contact synchronization, bulk ECDH response validation, invalid ECDH signatures, exact recipient-set validation, duplicate recipients, membership conflicts, idempotent retries, bulk contact creation, one-statement message persistence, and the guarantee that a failed fan-out leaves no partial server or local message state.

Add a live integration scenario using the real API and production client interactors and services, without direct server database mutations:

1. register three independent users with separate client state and local databases;
2. have the first user create a chat and add the other two users through the real chat API;
3. verify that the server creates the required `BLANK` relationships and that existing relationships would be reused without changing their statuses;
4. send one text message through `SendChatTextMessageInteractor` before the two recipients perform their next login synchronization;
5. log in each recipient through the normal login flow and run the same contact, chat, and message synchronization used by the application;
6. verify that each recipient pins newly encountered ED keys locally, obtains and verifies the current ECDH data, receives exactly one delivery, decrypts the original plaintext, stores it under the correct local chat, and acknowledges it with `failed = false`;
7. verify that the deliveries have distinct delivery IDs and ciphertexts but the same logical message ID and server timestamp;
8. verify that the sender stores exactly one outgoing local chat message rather than one row per recipient and that no chat delivery appears in sender-side `/failed` results.

Run the relevant client and server tests, Ruff, and mypy. Mark the task closed only after the unit and live integration scenarios pass against the real server contract.

closed: true

## Task 4 — Create Chats from the Messenger Sidebar

Add an inline chat creation flow to the messenger sidebar. When the `CHATS` tab is active, show the existing `✚` action inside the right side of the search field. The action must remain hidden in the `CONTACTS` tab.

Clicking `✚` opens a compact panel directly below the search field containing:

- the regular-weight title `▛ C R E A T I N G  C H A T ▟`;
- a chat-name input with both its placeholder and entered text centered;
- a regular-weight `C R E A T E` button.

Render the title, name input, and submit button as three equal-width and equal-height angled blocks. Their borders and text must all use the same dark-gray inactive-tab color, including while the name field is focused.

Clicking anywhere outside the creation panel and its `✚` anchor closes the panel. Switching back to `CONTACTS` also closes it. The name input must reject blank values and enforce the server's 100-character limit.

Connect the panel to a new messenger interactor that uses the existing authenticated `ChatHTTPService.create_chat` operation, persists the returned chat through the local `ChatService`, adds one `ChatCache` entry to `AppState`, and returns the created chat. On success, refresh the chat list, select the new chat, clear the input, and close the panel. Prevent duplicate submissions while a request is running and keep the panel open when creation fails.

Keep responsibilities separated: chat creation business flow belongs in `src/presentation/interactors/messenger.py`; reusable button and field widgets belong in their existing messenger modules; the composed creation panel belongs in a dedicated messenger UI module. Do not change the server API or add participants in this task.

Add focused tests for interactor persistence/cache behavior and failure behavior, then run the relevant tests, Ruff, and mypy.

closed: true

## Task 5 — Finalize the Chat Creation Interactor

Finalize and verify the chat creation business flow. Task 4 introduced a preliminary `CreateChatInteractor` and connected the messenger creation panel to it, so this task must audit and improve that implementation rather than introduce a duplicate interactor or a parallel creation path.

The interactor must:

1. trim and validate a non-empty chat name with the server's 100-character limit;
2. require an authenticated token and both local and server user IDs from `AppState`;
3. call the existing `ChatHTTPService.create_chat` operation exactly once for a normal submission;
4. validate that the returned owner ID matches the authenticated server user;
5. persist the returned server chat through the existing local `ChatService` using its server UUID as identity;
6. add exactly one matching `ChatCache` entry to `AppState` without deduplicating by name;
7. return the created cached chat so the UI can refresh the chat list and select it;
8. leave local storage and cache unchanged when validation or the server request fails.

Repeated chat names are valid. Neither the server nor the client may treat a name as a unique key; chats are identified exclusively by their server UUID and local UUID.

Keep the existing UI connection from the `C R E A T E` button and retain its in-flight submission guard. Do not add participants, chat settings, or another server endpoint in this task.

### Failure and retry considerations

The normal UI path must prevent rapid double submission. Do not automatically repeat `POST /chats` after an uncertain network outcome: the server may have committed the chat even if the response was lost, and retrying a non-idempotent create request could produce a second chat with a different UUID. If reliable automatic retry is required later, add an explicit client-generated idempotency key and server-side idempotency contract as a separate task. Repeated names alone cannot be used to recover an uncertain request because they are intentionally allowed.

If the server response is received but local persistence fails, retain enough response context for logging and allow normal chat synchronization to recover the server chat. Do not issue another create request merely to repair local state.

Add focused tests for validation, authentication prerequisites, owner mismatch, successful local persistence and caching, duplicate names with distinct UUIDs, server failure without local mutation, local persistence failure without a second HTTP request, and the UI in-flight submission guard. Run the relevant tests, Ruff, and mypy before closing the task.

closed: true

## Task 7 — Prevent Concurrent SQLite Session Conflicts

Fix the local database race where a successful chat creation can overlap with the immediate `chat_changed` realtime synchronization and produce `sqlite3.OperationalError: cannot commit transaction - SQL statements in progress`.

The production client currently creates request-scoped `AsyncSession` instances over a `StaticPool`. For a file-backed SQLite database, this forces otherwise independent request sessions to share one physical connection. A local write and a realtime read may therefore commit against the same connection while another statement is still active.

Implement the following database configuration:

1. remove `StaticPool` from the file-backed production SQLite engine and use SQLAlchemy's normal async pool so concurrent request sessions receive independent connections;
2. enable SQLite WAL journal mode so a realtime reader does not block a short local write transaction;
3. configure a finite SQLite busy timeout so short lock contention waits instead of failing immediately;
4. retain foreign-key enforcement for every connection;
5. keep request-scoped sessions and the existing service/DAO boundaries;
6. do not serialize the whole application, delay realtime notifications, retry `POST /chats`, or suppress database exceptions.

Add a regression test that keeps a read cursor open on one session while a second session writes and commits through another connection. Verify that WAL and the busy timeout are active and that the write succeeds without a statement-in-progress or database-locked error.

Separating read-only transaction handling from the existing `error_handler` commit behavior is a worthwhile later cleanup, but it is outside this task unless the connection and WAL fix proves insufficient.

The running client must be restarted after this change so its existing engine and pool are replaced.

### Implementation notes

- The production file-backed SQLite engine now uses SQLAlchemy's normal async connection pool instead of `StaticPool`.
- A connection hook enables WAL, a 30-second busy timeout, and foreign-key enforcement for every pooled connection.
- The regression test keeps a streaming read cursor open in one session while another session inserts and commits successfully, then verifies the committed row and active PRAGMA values.
- The new regression test, chat API tests, Ruff, and mypy pass. The broader database run has 83 passing tests and two unrelated pre-existing `LocalUserService` expectation failures.
- The restarted client successfully repeated chat creation and realtime synchronization without the SQLite commit error.

closed: true
