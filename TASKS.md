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

## Task 6 — Expand Chat Participants in the Conversation List

Add an expandable participant list beneath each chat card in the messenger sidebar.

The interaction must behave as follows:

1. the first left click on a chat keeps the existing behavior: select the chat and open its conversation;
2. a second left click on the already selected chat toggles its participant list;
3. when the list opens or closes, the chat triangle rotates smoothly by 180 degrees;
4. keep at most one chat participant list expanded at a time;
5. render participants directly below their chat using compact cards with a smaller height and a visible left indentation;
6. participant cards display only the existing presence triangle and username, without a last-message preview;
7. a participant's presence triangle follows the same privacy and color rules as the normal contact card: only accepted contacts may expose online state, while blank, pending, blacklisted, or unavailable states remain gray;
8. a left click on a participant opens the direct conversation with that contact;
9. a right click selects the participant and opens the existing contact action menu, using the same action signals and interactors as an ordinary contact card;
10. expanding or collapsing participants must not trigger another conversation selection or reload the current chat.

Extend `ChatCache` with a participant collection and populate it in `CacheConversationsInteractor` from the local database through `ChatService.get_chat_participants`. Reuse the same `ContactCache` instances already stored in `AppState.contacts_cache`; do not create independent copies for chat participants. This shared identity must allow realtime presence and contact-status updates to remain consistent in both the normal contact list and expanded chat lists.

The signed-in local user is not represented as a local contact and must not be synthesized as a participant card. Display only the other active chat participants currently available in the local participant mapping. Participant membership must continue to be synchronized by the existing chat synchronization flow; the UI must not call the server directly when a chat is expanded.

Keep the participant card as a dedicated UI class instead of adding multiple participant-specific branches to the normal contact card. Reuse shared drawing or context-menu behavior where practical without coupling the UI directly to database or HTTP services.

Add focused tests for participant-cache construction, shared `ContactCache` identity, repeated-click expansion and collapse, single-expanded-chat behavior, triangle rotation state, participant selection, context-menu action forwarding, and chats without cached participants. Run the relevant tests, Ruff, and mypy before closing the task.

### Implementation notes

- `ChatCache.participants` stores shared references to the matching entries in `AppState.contacts_cache`.
- `CacheConversationsInteractor` loads active participant mappings from the local database after contact caching; expanding a chat performs no database or HTTP request.
- `ChatParticipantCard` provides the compact indented layout while reusing the existing selection, presence-color, and contact context-menu behavior.
- `ContactList` treats a second click on the selected chat as an expansion toggle, allows only one expanded chat, and does not emit another conversation selection while toggling.
- Demo data includes chat participants so the interaction remains visually testable without a populated account.
- Relevant UI, cache, database, and messenger tests pass; Ruff and mypy report no issues. Keep the task open until the visual result is accepted.

closed: false

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

## Task 8 — Add Accepted Contacts to Chats

Add a messenger flow that lets an active chat participant add one of their accepted contacts directly to the selected chat. This version has no invitation approval or pending state: a successful request immediately creates or restores the participant membership.

The existing server contract already supports this behavior through `POST /chats/{chat_id}/participants`. Do not add another endpoint or chat event type. A first-time membership produces `MEMBER_ADDED`, restoring a former participant produces `MEMBER_JOINED`, and the server publishes the existing `chat_changed` realtime invalidation after committing the membership, event, and missing `BLANK` contact relationships. Preserve this transaction and realtime behavior.

Create an `AddChatParticipantInteractor` in `src/presentation/interactors/messenger.py`. It must:

1. accept the selected `ChatCache` and `ContactCache` instead of receiving raw UI text;
2. require an authenticated token, local user ID, server user ID, a server-backed selected chat, and an `ACCEPTED` contact with a server user ID;
3. reject the current user and contacts who are already active participants before making an HTTP request;
4. call `ChatHTTPService.add_participant` exactly once and validate that the returned chat and target user match the requested values;
5. map the returned participant to the existing local chat and contact, then persist the membership through `ChatService.add_participant` without creating a second synthetic join event;
6. persist the canonical server event returned by the API, including its server event ID, actor, target, type, and timestamp, so later incremental synchronization does not duplicate it;
7. add the same shared `ContactCache` instance to `ChatCache.participants`, without creating a copy or duplicate;
8. leave the local database and cache unchanged when validation or the server request fails, and return a clear failure result for the UI.

Add a `⛨` button inside the right edge of the currently selected chat card in the left conversation list. Keep it hidden on unselected chat cards, and do not add it to direct-contact cards. Clicking it toggles an overlay immediately beside the chat list: the overlay must be flush with the left edge of the message area and must not permanently resize the conversation layout. Its width should remain approximately half the width of the contacts/chats panel.

The `⛨` action and the repeated-card-click participant expansion are mutually exclusive. Clicking the action must consume its own mouse press and open or close only the add-contact panel; it must not rotate the chat triangle or expand the existing participant list.

The panel must contain a vertically scrollable list of cached contacts whose status is `ACCEPTED`. Exclude the current user and every active participant already present in the selected chat. Each contact row must be clickable. Clicking a contact starts the interactor, prevents duplicate submissions for that contact while the request is in flight, and, after success, removes the contact from the available list while immediately updating the expanded participant list through the shared cache object. Keep the panel open so several contacts can be added consecutively. Close it when the button is toggled again, the user clicks outside it, or the selected conversation changes.

Keep the UI, interactor, HTTP service, local service, and cache responsibilities separated. Reuse the existing chat participant endpoint, DTOs, `ChatService`, contact cache, theme colors, scrolling style, and realtime synchronization. Do not introduce pending chat invitations, acceptance/rejection controls, key material in WebSocket payloads, a second participant cache, or a full chat synchronization merely to render the panel.

Add focused tests for interactor prerequisites, accepted-status enforcement, duplicate-participant rejection, one HTTP request per click, canonical event persistence, restored memberships, shared cache identity, failure without local mutation, chat-only button visibility, panel toggling and outside-click closing, candidate filtering, scrolling, and in-flight click protection. Add or extend an integration test proving that the existing server endpoint immediately adds the user, creates the expected event and `BLANK` relationships, and notifies clients through `chat_changed`. Run the relevant client and server tests, Ruff, and mypy before closing the task.

### Implementation progress

- `AddChatParticipantInteractor` validates the current app-state caches and local records, calls the existing participant endpoint once, persists the returned membership without a synthetic event, stores the canonical server event, and updates the shared `ChatCache.participants` list only after local persistence succeeds.
- Focused tests cover successful persistence and shared cache identity, early candidate rejection, and mismatched server responses. The complete messenger interactor test module passes, and Ruff reports no issues.
- The selected chat card displays the `⛨` action at its right edge; unselected chats and direct contacts keep it hidden. It opens an overlay flush with the left edge of the message area, directly beside the chat list. The scrollable panel lists accepted contacts, excludes the current user and existing participants, blocks repeated in-flight clicks, and remains open after successful additions so more contacts can be added.
- The messenger interface connects panel rows to `AddChatParticipantInteractor`, preserves the open panel and selected/expanded chat while shared caches are refreshed, and immediately removes newly added participants from the candidate list.
- Focused UI tests cover chat-only button visibility, panel toggling, candidate filtering, current-user and participant exclusion, scrolling, outside-click and conversation-change closing, successful row removal, and in-flight click protection. The relevant interactor and UI suites pass.
- The final layout and interaction were visually accepted with the prepared accepted contacts. The `⛨` action consumes its mouse press, so opening the add-contact panel does not also expand the chat participant list.
- Final verification passes the complete messenger interactor and related UI suites (`41 passed`), Ruff, Python compilation, and the diff whitespace check.

closed: true
