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

## Task 9 — Send Encrypted Files to Direct Contacts

Add direct-contact file sending through a dedicated messenger interactor and connect it to the existing attachment UI only after the interactor has been implemented and verified. Group-chat file fan-out remains out of scope.

Before implementing the client interactor, complete the existing server file transport semantics:

1. when a direct file upload is completed, create the missing `BLANK` contact relationship between sender and recipient without changing an existing relationship or status;
2. publish the existing `message_available` realtime invalidation to the recipient only after the completed upload and contact relationship have committed;
3. do not introduce another realtime event type or send cryptographic material through WebSocket payloads;
4. keep chat-file behavior unchanged and do not add group-chat file sending in this task.

Create `SendContactFileMessageInteractor` in `src/presentation/interactors/messenger.py`. It must validate the selected direct contact, authentication state, local user, master key, ED/ECDH keys, source path, supported extension, and file metadata. It must send the file through the existing `FileHTTPService.send_encrypted_message_file`, then persist exactly one outgoing local file message through `MessageService.add_message_file`. Local persistence must continue encrypting file bytes with the master key automatically. After successful persistence, append only the file metadata to the matching `ContactCache.messages`; do not retain file bytes in `AppState`.

The interactor must leave the local database and cache unchanged when validation or upload fails. It must return the persisted `MessageDTO` on success so the UI can bind the real server message ID and delivery state. The later UI phase must replace the current optimistic-only attachment bubble with the same pending/sent/failed flow used for text messages, and must keep attachment controls unavailable for group chats.

Current transport limitations must be handled explicitly:

- the client file service currently receives the complete plaintext as `bytes` before chunked network upload, so large files can consume roughly multiple times their size during local encryption and persistence and synchronous file reads can stall the UI;
- do not silently advertise the server's 1 GiB ciphertext limit as a safe client limit on low-memory hardware;
- enforce a 100 MiB plaintext client-side limit in both the file service and, before reading from disk, the interactor; files larger than this require a later streaming refactor of file reading, transport encryption, and local persistence;
- reject unsupported extensions clearly instead of allowing an upload that cannot be represented by `MessageContentMimeTypeEnum` in the local database;
- preserve file names deliberately; do not silently rename multi-dot names to satisfy the current validation contract.

Add focused server tests for missing-contact creation, preservation of existing contact statuses, realtime publication after successful completion, and no publication on failed completion. Add focused client tests for prerequisites, metadata parsing, supported extensions, upload failure without local mutation, automatic encrypted local persistence, cache updates without file bytes, and successful direct-contact sending. Run the relevant server and client tests, Ruff, and mypy before closing the task.

### Implementation progress

- The server now creates missing direct-message `BLANK` relationships during file completion without replacing existing statuses, commits the transaction before publishing `message_available`, and does not publish when completion fails. The focused server unit suite passes (`76 passed`).
- The client file transport rejects plaintext payloads above 100 MiB before encryption and exposes its existing MIME-to-content-type mapping for local persistence.
- `SendContactFileMessageInteractor` validates the source file and application/key prerequisites, reads the file outside the event-loop thread, uploads it through `FileHTTPService`, creates a missing local `BLANK` contact only after the upload succeeds, persists the outgoing file through `MessageService`, and stores only file metadata in `ContactCache`.
- Focused interactor and transport tests cover successful sending, new-contact mapping, upload failure without local mutation, application-state prerequisites, unsupported extensions, dotted base names, and the 100 MiB boundary. The messenger and file unit suites pass (`45 passed`), the existing message database suite passes (`15 passed` with asyncio auto mode), Ruff and Python compilation pass, and the diff whitespace check is clean.
- The shared message send action now chooses exactly one operation: an attached file is sent to the selected direct contact through `SendContactFileMessageInteractor`, while a send without an attachment continues through the existing contact/chat text interactors. Attached files receive real pending, sent, and failed bubble states; attachment controls remain unavailable for chats. Text entered alongside an attachment is preserved for the next send instead of being silently discarded or sent as a second message.
- The attachment dialog's advertised `.jpg` extension is represented by the local MIME enum. Focused UI and interactor coverage verifies exclusive routing, the real interactor connection, successful server-ID binding, failure state, supported extensions, and contact-only availability. The combined relevant suite passes (`57 passed`) and Ruff passes.
- When a direct conversation is opened, image payloads for its cached messages are fetched from the local database in one query, decrypted with the master key, and rendered directly from memory as image bubbles. Decrypted bytes are kept only by the currently displayed panel, are not added to `AppState`, and are discarded when the conversation changes. Image viewer activation is restricted to the rendered angled bubble instead of the full row width. Image and video bubbles expose a shared UI-only context menu with `DELETE`, `FORWARD`, `REPLY`, and `SAVE TO DISK`; the actions emit placeholders for future business logic. Focused database, interactor, and UI coverage passes (`26 passed`), and Ruff passes.
- Text and media message context menus share the contact menu's light palette: the application background color at rest, primary-colored text and border, and a primary hover surface with light text.
- `SaveMessageFileToDiskInteractor` retrieves the selected file message from the local database through `MessageService`, decrypts its ciphertext with the current master key, restores the stored extension, validates the plaintext size, and writes the result atomically to either a selected directory or file path. The media `SAVE TO DISK` action now resolves the local message ID, opens the system save dialog with the original name and extension, and schedules the interactor without blocking the UI. Focused tests cover database-service delegation, dotted destination names, missing messages, corrupted-size rejection, panel routing, dialog cancellation, and successful interactor dispatch.
- A working mypy environment and manual live-client verification are still pending, so this task remains open.

closed: true

## Task 10 — Implement Persistent Message Replies

Implement message replies without introducing a separate sending interactor. Extend the existing direct-message and chat-message interactors with an optional reply reference, and connect the existing reply UI prototype to real persisted and synchronized message data.

### Message identity

Chat fan-out creates several physical server messages: every recipient receives a separately encrypted delivery with its own server message UUID. Add one `general_message_uuid` shared by every delivery that represents the same logical chat message. The sender's single local outgoing record and all recipient delivery records must carry this same value.

The existing `logical_message_id` already represents this concept. Rename and migrate it to `general_message_uuid` throughout the client and server instead of adding a second column with duplicated meaning. Apply explicit database migrations; do not add runtime schema migration workarounds. Direct messages must store `NULL` in this column because their normal message primary key is already their complete identity.

For chat messages, `general_message_uuid` must never be null. Enforce this with a database constraint equivalent to:

`chat_id IS NULL OR general_message_uuid IS NOT NULL`

Use an indexed, uniqueness-protected server lookup key that includes `(recipient_id, chat_id, general_message_uuid)`. This key identifies the exact physical delivery of one general chat message that belongs to one recipient.

The physical message UUID remains the identity of one encrypted delivery and continues to be used for acknowledgement, decryption-failure reporting, and delivery-specific operations. It must not be used as the shared identity of a fan-out chat message.

### Reply transport and resolution

For a chat reply, create a dedicated `GetChatReplyTargetsInteractor` in the messenger interactors. It accepts the selected chat and the quoted message's `general_message_uuid`, calls one authorized server endpoint, and returns an in-memory `dict[UUID, UUID]` whose keys are recipient user UUIDs and whose values are the physical server message UUIDs of those recipients' encrypted copies of the quoted message. The HTTP response should use an explicit list DTO such as `{user_id, message_id}` and the client interactor should construct the dictionary; do not encode UUIDs as JSON object keys.

The server endpoint must resolve this mapping with one bulk query scoped by both `chat_id` and `general_message_uuid`, and it must authorize the caller as an active participant of that chat. It must never expose deliveries from another chat merely because a UUID was supplied.

Pass the resulting mapping into the existing `SendChatTextMessageInteractor`; do not create a separate reply-sending interactor. While building the normal encrypted fan-out deliveries, look up every current `delivery.recipient_id` in the mapping and write the resulting physical quoted-message UUID to that delivery's `reply_to_id`. Every recipient therefore receives a hard reference to their own encrypted copy of the quoted message; never attach another recipient's physical message ID or use the general UUID itself as `reply_to_id`.

Also send `reply_to_general_message_uuid: UUID | None` once as shared batch metadata so the server can validate the client-provided mapping efficiently. For every non-null per-delivery `reply_to_id`, the server must verify in one bulk validation query that the target belongs to the same chat, has the supplied `general_message_uuid`, and belongs to the same recipient as the new delivery. The server must not trust the client-provided dictionary without this validation.

The current participant set may differ from the participant set that received the quoted message. Ignore mapping entries for users who are no longer recipients. If a newly added participant has no historical delivery in the mapping, send their new delivery with `reply_to_id = NULL` while retaining the shared reply identity; this must not fail the whole batch. If membership changes cause the existing chat-send retry path to rebuild the batch, resolve the reply-target mapping again before retrying so it cannot become stale.

The author of a quoted chat message also has no recipient delivery because fan-out excludes the sender. When another participant replies to that message, send the delivery addressed to the original author with `reply_to_id = NULL` and preserve `reply_to_general_message_uuid`. The author's client must resolve `(chat_id, reply_to_general_message_uuid)` to its existing local outgoing message and store that message's local primary key in `reply_to_id`. This is the only logical-identity fallback for an existing historical message; recipients that have physical deliveries must still receive their recipient-specific `reply_to_id`. Do not create a sender self-delivery or a new mapping table.

The server response and later synchronization expose the recipient-specific physical `reply_to_id`. The receiving client resolves that server UUID through the quoted message's `server_message_id` and stores the resulting local message primary key as its local `reply_to_id` relationship. Persist the unresolved server reply UUID separately when necessary so synchronization order or an older message outside the current cache cannot destroy the relationship. Reattempt local resolution when the missing quoted delivery is later stored.

For direct conversations, retain the existing server `reply_to_id` contract based on the quoted direct message's physical server UUID. Use clear, correctly spelled field names such as `reply_to_id` and `reply_to_general_message_uuid`; do not introduce `replyed_*` fields.

### Sending and synchronization

Do not create reply-specific sending interactors. Modify the existing text-message interactors so their normal send operation accepts an optional reply target:

- the direct-message interactor sends the quoted message's server UUID through the existing direct reply field;
- before a chat reply is sent, `GetChatReplyTargetsInteractor` resolves `user_id -> message_id` by the quoted message's `general_message_uuid`;
- the chat-message interactor accepts that mapping, assigns the correct physical `reply_to_id` to each recipient's delivery, and sends the quoted `general_message_uuid` once in the shared fan-out batch metadata for validation and fallback rendering.

The selected reply state must retain the target message identity in addition to the rendered author and preview text. Clear that state only after a successful send or an explicit cancellation; preserve it when sending fails so the user can retry.

Extend API DTOs, database DTOs, local services, synchronization, and conversation caches so incoming and outgoing replies preserve their durable reference. Resolve the quoted message from the current conversation cache first and fall back to the scoped local SQL query. The cache is an optimization only and must not be assumed to contain an older quoted message.

The server must validate that a referenced message belongs to the same direct conversation or chat and that the authenticated sender is allowed to access it. It must reject cross-conversation and cross-chat reply references. A participant added after the quoted chat message may not possess a corresponding historical delivery; this must not invalidate the new fan-out message. That recipient displays the unavailable fallback unless the original message later becomes available locally.

If the quoted message is deleted, unavailable, or has not yet synchronized, render a stable `MESSAGE IS UNAVAILABLE` reply block rather than dropping the reply relation or failing to render the containing message. An encrypted reply snapshot and quote preservation after permanent deletion are outside this task.

### Verification

Add focused client and server coverage for:

- one `general_message_uuid` shared by all physical deliveries in a chat batch;
- database constraints and unique scoped indexes;
- direct replies through the existing physical server message reference;
- chat reply batch lookup through `reply_to_general_message_uuid`;
- the authorized reply-target endpoint and `GetChatReplyTargetsInteractor`, including construction of the `user_id -> message_id` dictionary;
- server-side bulk resolution from the general UUID and recipient UUID to each recipient's concrete quoted-message primary key;
- passing that dictionary into `SendChatTextMessageInteractor` and assigning it by each delivery's `recipient_id`;
- recipient-specific physical `reply_to_id` values across the resulting fan-out deliveries;
- server rejection of a client-provided physical target that belongs to another chat, general message, or recipient;
- successful fan-out when a newly added participant has no physical copy of the older quoted message;
- client-side resolution from the received physical server reply UUID to the matching local message row;
- cache hits and local-database fallback for replies older than the cache window;
- deferred resolution when the quoted message arrives after the reply;
- unavailable and deleted quoted-message rendering;
- rejection of cross-chat and cross-conversation references;
- preserving reply selection after send failure and clearing it after success;
- rendering the real quoted author and content for direct and chat messages after synchronization and application restart.

Run the relevant client and server tests, Ruff, and mypy. Keep this task open until message replies work through the real API for both direct conversations and fan-out chats.

### Implementation progress

- The existing `logical_message_id` field was renamed to `general_message_uuid` across the client, server, API contract, persistence DTOs, caches, and tests. No duplicate identity column was introduced.
- Direct messages now store `NULL` for `general_message_uuid` and continue using their ordinary physical message primary key. Chat fan-out deliveries require one shared non-null `general_message_uuid`.
- Explicit SQLite and Alembic migrations preserve existing chat identities, clear the obsolete value from direct messages, rename indexes and constraints, and were applied to the local client and server databases.
- The client now has `GetChatReplyTargetsInteractor` and its typed HTTP DAO/service contract. It validates the selected chat cache and authenticated session, requests one recipient-target list by `chat_id` and `general_message_uuid`, rejects duplicate user or physical message IDs, and returns `dict[user_id, message_id]`. The server endpoint authorizes active chat membership and scopes its bulk lookup by both identities.
- The focused chat API and messenger interactor suites pass (`47 passed`), and the changed files pass Ruff import and critical-error checks. The available fallback mypy environment reports existing project-wide typing errors but no diagnostic in the new reply-target code.
- Direct-contact replies now use the existing send interactor and `/send` contract. The client resolves the selected target from its local conversation cache, verifies the physical server message against SQLite, persists both the unresolved server reference and resolved local relationship, and keeps the UI reply selection until successful delivery. Incoming synchronization preserves the physical `reply_to_id`, supports deferred resolution when the quoted message arrives later, and reloads quoted content outside the ten-message cache window after an application restart.
- The direct-message server rejects missing, chat-scoped, and cross-conversation targets before persistence. The explicit client SQLite migration was applied, focused client reply coverage passes, and the server passes Ruff, mypy, and its full unit suite.
- Direct outgoing messages now persist the canonical server timestamp returned by `/send`. The frozen SQLAlchemy datetime defaults were replaced with callables, and existing local direct-message copies were repaired from their matching incoming server timestamps so replies and source messages retain their real order.
- Chat replies now use `reply_to_general_message_uuid` as the durable logical target and recipient-specific `reply_to_id` values wherever a physical historical delivery exists. The authorized reply-target endpoint resolves the complete mapping in one scoped bulk query, and the server validates the mapping before persisting the fan-out batch.
- The existing chat sending interactor and messenger UI now carry reply state through lookup, encryption, persistence, synchronization, cache reconstruction, failure retry, and successful clearing. The original author resolves a reply through the shared general UUID to the local outgoing row, while normal recipients resolve their own physical delivery; no sender self-delivery or mapping table was added.
- Explicit client and server migrations add `reply_to_general_message_uuid`. They were applied to the local SQLite and PostgreSQL databases; the SQLite backup is stored as `apata.db.before_task10_chat_reply`, its integrity check passes, and PostgreSQL is at Alembic head `20261010_02`.
- Client Ruff passes, 82 focused unit/UI/database tests pass, and the live three-user integration scenario passes through the running API for both the original-author fallback and recipient-specific physical targets. The server passes Ruff, mypy, and all 85 tests. The copied client environment still cannot provide a meaningful full mypy run: the available isolated runner lacks the project's installed third-party packages and reports the previously known project-wide typing errors rather than reply-specific diagnostics.

closed: true

## Task 11 — Keep the Realtime WebSocket Connected

Keep the authenticated realtime WebSocket listener running for the entire signed-in application session. The existing DAO already reconnects after ordinary network disconnections, but the service currently clears its token and listener state when the listener coroutine returns or crashes unexpectedly. Add a lightweight service-level supervisor that restarts the listener after such exits.

The connection must start during the existing login flow, retain a strong reference to its background task, and keep retrying until the application explicitly stops realtime or WebSocket authentication fails. Explicit logout or shutdown must cancel the supervisor and close the socket without allowing another reconnect. Prevent duplicate supervisors when start is called more than once.

Keep this task limited to connection lifetime and reconnection. Do not change online presence semantics, add window-state messages, add token refresh, or introduce a new general-purpose background-task framework.

Add focused tests proving that an unexpectedly failed listener is restarted, an ordinary premature listener return is restarted, repeated start calls do not create duplicate supervisors, and an explicit stop prevents further reconnects. Run the relevant realtime tests and Ruff before closing the task.

### Implementation progress

- `WebSocketService` now keeps its existing strongly referenced listener task alive as a lightweight supervisor and restarts the DAO listener one second after either an unexpected return or a non-authentication exception.
- Authentication failure still ends the signed-in realtime session, while explicit shutdown cancels the supervisor before disconnecting so it cannot reconnect afterward.
- Focused tests cover exception recovery, premature-return recovery, duplicate-start prevention, and explicit-stop behavior.
- Ruff, Python compilation, and a standalone asynchronous supervisor check pass. The copied project virtual environments reference missing Python installations and the remaining package copy lacks pytest's `pluggy` dependency, so the focused pytest module cannot be executed in the current environment yet.

closed: true

## Task 12 — Report Application Presence over WebSocket

Separate the user's visible online status from the lifetime of the background realtime transport with a simple client-reported presence command. The WebSocket may remain connected for realtime notifications, but connecting it must no longer make the user online by itself.

When the authenticated client starts realtime after login, send a versioned `presence_update` WebSocket command with `online: true`. Before an intentional application shutdown, send the same command with `online: false` before closing the socket. Remember the desired presence state in the WebSocket service and resend it after reconnecting. An unexpected final socket disconnection remains a fallback that marks the user offline.

The server must validate the client command, update the authenticated user only, and publish the existing `presence_changed` event. Update `last_seen` only when the client becomes offline. New registrations must start offline until their client explicitly reports that the application is open.

Keep this implementation intentionally single-status and simple. Do not add Redis leases, per-device presence, a new database table, token refresh, or system-tray behavior in this task.

Add focused client and server tests for the presence command, reconnect reporting, shutdown reporting, registration defaults, and `last_seen` behavior. Run relevant tests and static checks in both repositories before closing the task.

### Implementation progress

- Opening realtime after login sets the client's desired presence to online and sends the versioned `presence_update` command. Every successful reconnect resends that desired state.
- Intentional shutdown sends `online: false` before cancelling the listener and closing the socket. The final socket disconnection remains the server fallback when a client cannot report shutdown cleanly.
- WebSocket connection alone no longer marks a user online. The server validates strict boolean presence commands for the authenticated socket and publishes the existing `presence_changed` invalidation.
- The initial server-to-client readiness event was renamed from `session_ready` to `presence` across both contracts.
- Online updates preserve the previous `last_seen`; offline updates store the current UTC time. Newly registered users now start offline.
- Server realtime tests pass (`4 passed`), server and client Ruff checks pass, both diffs pass whitespace checks, and client compilation plus standalone asynchronous presence/reconnect checks pass. The copied client pytest environment remains unavailable because its Python installation and dependencies are incomplete.

closed: true

## Task 13 — Add Background Tray Notifications

Add a basic system-tray flow for receiving message notifications while the APATA window is hidden or inactive. Keep the application process and authenticated WebSocket running when the signed-in user closes the main window; hide the window in the system tray instead of terminating it. Report offline presence while hidden and restore online presence when the window is reopened.

Create the tray implementation under `src/presentation/pages/tray`. Keep notification discovery separate from the Qt tray controller: compare the already decrypted `AppState` conversation caches after successful realtime synchronization, ignore outgoing and previously known messages, and build a concise notification title and preview for new incoming direct and chat messages. Establish the existing cache as the baseline before realtime starts so login does not generate notifications for message history.

Connect the tray refresh callback to the existing `RealtimeInteractor` listener flow. Notifications must be produced only after `message_available` has triggered contact/chat/message synchronization and cache reconstruction; do not put plaintext or message previews into WebSocket event payloads. Suppress system notifications while the APATA window is active, but still mark those messages as known.

The tray icon must provide actions to reopen APATA and explicitly exit. A normal window close hides the signed-in client without stopping realtime. Explicit exit reports offline, lets normal application cleanup stop the WebSocket and container, and then terminates the process. Clicking a notification restores the main window. Keep strong references to fire-and-forget asyncio tasks until completion.

Use `QSystemTrayIcon` and gracefully fall back to normal window closing when a system tray is unavailable. Add focused tests for initial cache baselining, new direct and chat notification discovery, outgoing-message suppression, duplicate suppression, preview formatting, and presence changes on hide/restore. Run relevant tests, Ruff, and compilation before closing the task.

### Implementation progress

- Added a tray controller with reopen and explicit-exit actions, notification-click restoration, strong references for asynchronous presence operations, and a generated red `Ʌ` application icon.
- Closing a signed-in window now hides it when a system tray is available without stopping realtime. Hidden clients report offline presence; restoring the window reports online presence; explicit exit reports offline before normal application cleanup.
- Added a cache notification tracker that establishes a login baseline, discovers only new incoming direct and chat messages after realtime synchronization, suppresses duplicates and outgoing messages, and formats text and file previews without exposing plaintext in WebSocket payloads.
- Registered the tracker after the existing messenger realtime listener so notifications are based on synchronized, locally decrypted cache data. Notifications are suppressed while the main window is active while their messages are still marked as known.
- Added focused tests for baselining, direct/chat discovery, duplicate and outgoing suppression, preview formatting, and hide/restore presence. Ruff, Python compilation, and whitespace checks pass. The copied project virtual environment is still incomplete and cannot execute pytest because its Python environment and dependencies are missing.
- The Qt application and display names are explicitly set to `APATA` so Windows notifications no longer inherit the Python executable name.

closed: true

## Task 14 — Renew Access Tokens with ED25519 Proof

Add automatic access-token rotation without adding or changing server HTTP routes, request DTOs, or response DTOs. Do not use the existing `/refresh` route and do not introduce a conventional refresh token. Reuse the exact authentication flow already used by normal login: `POST /auth/challenges` with the stored username, sign the returned challenge with the locally held ED25519 private key, then call `POST /auth/login` with that signature to receive a new access token.

Complete the client auth service so every authenticated HTTP operation shares one renewal mechanism. When the API returns the existing expired-access `401`, start one single-flight invocation of the existing challenge/login flow, update `AppState`, `AuthHTTPService`, and the shared HTTP authorization source with the returned access token, and retry the original request exactly once. Concurrent failures must wait for the same rotation instead of requesting multiple challenges. The `/auth/challenges` and `/auth/login` calls must bypass automatic rotation so they cannot recurse. Do not rotate for invalid signatures, revoked tokens, unrelated authentication failures, authorization failures, or a request that already retried. A failed rotation must stop authenticated background work, clear the unusable session safely, and return the user to login without an infinite request loop.

Integrate the same rotation with realtime without adding a token-renewal HTTP endpoint. When a WebSocket handshake fails because its access token expired, or when the server closes an established authenticated socket because the access lifetime ended, the WebSocket DAO/service must invoke the same shared single-flight challenge/login operation, replace its listener token, reconnect, and restore the previously desired presence state. HTTP and WebSocket expiration occurring together must still perform only one ED25519 login. Ordinary network reconnects must continue using the current valid access token and must not request a new challenge.

Do not blacklist an already expired access token: its `exp` already makes it invalid. Preserve the server's existing access-token revocation and logout behavior for tokens that are still valid. Server changes in this task are limited to the internal WebSocket lifetime and expiration signaling needed for automatic client reconnection; do not add, rename, remove, or repurpose HTTP routes.

The ED25519 private key must never leave the client or be logged. Preserve the existing typed challenge/login contracts and the project layering between HTTP DAO, service, interactors, and application state. Prefer the existing structured expired-token response or typed exception over matching arbitrary human-readable error text.

Add client and server unit tests plus a live integration scenario covering:

- initial ED25519 challenge/login returning the access token;
- successful rotation through the existing `/auth/challenges` and `/auth/login` routes without calling `/refresh`;
- wrong keys, invalid signatures, missing local keys, and expired or replayed challenges;
- one HTTP request retry after expiration and no retry for unrelated `401` or `403` responses;
- concurrent HTTP expiration producing exactly one renewal;
- WebSocket expiration, shared renewal, reconnection, and presence restoration;
- simultaneous HTTP and WebSocket expiration producing exactly one renewal;
- renewal failure terminating the authenticated session without a reconnect or retry loop.

Run the relevant client and server test suites, Ruff, and mypy. Keep this task open until both HTTP and realtime continue operating across real access-token expiration without manual login and without any new auth HTTP route.

closed: true

## Task 15 — Navigate from Replies to Original Messages

Make the quoted-message block inside a text message clickable with the left mouse button. Use the existing local `reply_to_id` relation as the stable target identity; do not search by author, text, timestamp, or server-side data. Clicking the quote must smoothly scroll the active conversation to the original message and briefly highlight the destination so it is easy to identify.

When a direct conversation or chat is selected, load its complete local message history from SQLite into that conversation's active cache before rendering it. Replace the previous conversation's loaded message list instead of retaining complete histories for every conversation in memory. Keep the lightweight startup cache for conversation previews, and do not request already synchronized history from the server merely to navigate to a reply. Switching conversations must discard the no-longer-active full-history cache and load the newly selected conversation from the local database.

Keep message lookup scoped to the selected conversation. Missing or deleted reply targets must remain non-navigable and continue rendering the existing unavailable fallback. Preserve right-click message actions, image/video behavior, realtime cache refreshes, chronological ordering, day dividers, and pending outgoing messages.

Add focused tests for full-history loading and cache replacement when switching between direct conversations and chats, clickable reply target identity, smooth-scroll destination lookup, unavailable targets, and preservation of existing message interactions. Run the relevant tests, Ruff, and mypy before closing the task.

### Implementation progress

- Added a local database query and messenger interactor that load the complete selected direct or chat history without loading file payloads. Only the active conversation retains full history; the previous cache returns to its ten-message preview window.
- Added local-message widget indexing for text, image, video, and generic file messages. Reply blocks use `reply_to_id`, remain disabled when the target is unavailable, smoothly center the original message, and briefly highlight the destination.
- Existing pending-message, right-click, media, realtime refresh, and file-loading paths now preserve the active full-history cache and register newly persisted messages as navigation targets.
- Conversation selection renders the existing ten-message preview immediately, then starts the complete local-history interactor as an `asyncio.create_task`. The task returns data without mutating active UI state; the result is applied only if that conversation is still selected.
- Opening a conversation now positions the preview at the bottom immediately without animating through intermediate messages. Applying the complete history or loaded file contents preserves the current distance from the bottom, so background rendering does not fight manual scrolling or jerk the viewport.
- The lightweight ten-message startup preview now includes decrypted payloads only for image messages. Those images render immediately, survive replacement by the complete metadata-only history, and are excluded from duplicate lazy-loading requests; videos and other files remain lazy.
- Added focused database, interactor, and Qt UI coverage, including verification that the ten-message preview remains visible until the background task applies the full history. The targeted database, file-interactor, and UI suites pass with `99 passed`; Ruff, Ruff formatting, Python compilation, and whitespace checks also pass. Mypy remains unavailable because the copied project virtual environment points to a missing Python installation.

closed: true

## Task 16 — Log Out from the Authenticated Client

Add a logout button to the authenticated messenger interface and connect it to a dedicated logout interactor. The interactor must perform an orderly transition from the current authenticated session back to the login interface without requiring an application restart.

Before clearing authentication state, report offline presence when possible and stop the realtime listener, reconnect loop, tray notification flow, and authenticated background synchronization. Clear the access token and all account-specific in-memory state, including active conversation selection, cached contacts, chats, messages, pending reply/file state, and notification baselines. Prevent late background-task results or WebSocket events from repopulating state after logout.

Preserve the user's encrypted local database and long-lived cryptographic keys; logout must not behave like account deletion or local-data reset. Do not add a new server endpoint unless inspection shows that the current API requires one and the change is discussed with the user first. Network failure while reporting offline must not trap the user inside the authenticated interface.

Make repeated clicks and logout during reconnect/synchronization safe. After logout, the login page must be usable immediately, and signing in again—either to the same account or another account—must initialize a clean authenticated UI and start realtime exactly once.

Add focused tests for the logout interactor, presence/realtime shutdown ordering, account-state cleanup, resistance to late callbacks, idempotent repeated logout, login-page transition, and successful login after logout. Run the relevant tests, Ruff, and mypy before closing the task.

### Implementation progress

- Added the logout control as a dark-gray `⍈` symbol in the upper-right corner with comfortable edge margins. Hovering changes it to the primary red and smoothly enlarges the glyph.
- Clicking the logout control opens a centered, contact-card-style hexagonal confirmation panel. Its dark-gray outer frame uses the same side-angle proportions as its inner buttons and contains the spaced dark-gray prompt `A R E  Y O U  S U R E  T O  L O G O U T ?` above separate `Y E S` and `N O` hexagonal buttons. The buttons use the same dark gray for their default text and border and retain the primary-red hover state.
- Added `LogoutInteractor` to the login interactors. It reports offline presence when possible, stops the realtime synchronization and reconnect lifecycle, calls the authenticated server logout endpoint, and always clears account-specific `AppState` data even when the network-side revocation fails.
- Connected confirmation to the application lifecycle with duplicate-click protection. Logout cancels messenger background work, clears selections, pending UI state, conversation caches, search and notification baselines, and returns to the reusable login screen without deleting the encrypted local database or long-lived keys stored on disk.
- Re-entering the login screen now resets its complete transient UI state: username and password input, logs and loading progress, selected registration/login tab, access-button animation, account picker visibility and contents, and the cached local-account list. Local account names are then reloaded asynchronously from the database.
- Implemented real server-side access-token revocation. The server stores only a SHA-256 token fingerprint in Redis with a TTL equal to the JWT's remaining lifetime, rejects revoked tokens with HTTP 401, and issues every new access token with a unique `jti` so logging out one session does not revoke another session of the same account.
- Verified all 91 server unit tests, the client logout/realtime/UI behavior with 25 focused tests, and the complete live contract against the local API: the token succeeds before logout, `DELETE /auth/tokens/current` succeeds, and the same token is rejected afterward with `401 Token revoked`. Ruff, Python compilation, and whitespace checks pass in both repositories. Mypy could not complete because the copied client environment has a broken launcher and the server's installed mypy reports an internal error under Python 3.14.
- Manually verified the complete UI flow: confirming logout returns to the login screen, and the login form, logs, controls, and local-account picker reopen in a clean state.

closed: true
