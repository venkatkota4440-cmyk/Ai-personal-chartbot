# Decisions log

Each entry records a choice the PRD and Technical Documentation did not make,
or a deliberate deviation from them. Newest milestone last.

## M1 — Foundation and auth

### D-001 Where the project lives
None of the repositories attached to this workspace was a personal-agent
project, and `scam-shield` is a separately deployed product that must not be
disturbed. The platform therefore lives in a self-contained
`personal-ai-agent/` folder inside `Uttam-2040/Agentic-workshop`, which was
otherwise nearly empty. The folder can be moved to its own repository later
without changes, because all paths inside it are relative.

### D-002 No third-party agent framework in the core
See [REPOSITORY_EVALUATION.md](REPOSITORY_EVALUATION.md). The core follows the
mandated stack; n8n is the preferred future route to real connectors, behind
our approval service.

### D-003 Server-side sessions, not JWTs
Sessions are random 256-bit tokens in an `HttpOnly`, `SameSite=Lax` cookie
(`Secure` in production). Only the SHA-256 hash is stored in a new
**`sessions`** table. Why: logout and "sign out everywhere" take effect
immediately, and a database leak exposes no usable tokens. A JWT cannot be
revoked before it expires.

### D-004 CSRF: signed double-submit token plus an Origin check
`GET /api/auth/csrf` (not in the API list; required so the browser can get a
token) sets a readable `paa_csrf` cookie of the form `nonce.HMAC(secret,
nonce)`. Every POST/PATCH/PUT/DELETE under `/api` must echo it in
`X-CSRF-Token`, and any `Origin` header must be in `CORS_ORIGINS`. The
signature stops an attacker who can plant cookies (for example from a sibling
subdomain) from forging a pair. Login and register are protected too, which
blocks login CSRF.

### D-005 Rate limiting and client IPs
- Fixed-window limiter. The `memory` backend is for a single process; `redis`
  is shared and is used in docker compose.
- Login: 5/min per (email, IP) and 20/min per IP. Register: 10/hour per IP.
- **Forwarded headers are not trusted.** During M1 verification, Next.js was
  found to pass a client-supplied `X-Forwarded-For` straight through, so a
  client could rotate fake IPs to dodge limits. Now `src/proxy.ts` strips
  forwarding headers from `/api/*`, and uvicorn trusts them only from
  `FORWARDED_ALLOW_IPS` (default `127.0.0.1`). The e2e test
  `security.spec.ts` guards this.
- **Trade-off:** behind the web container, every browser shares one IP
  bucket. For a single-owner app this is acceptable. Per-account limits still
  apply, and an attacker who spams the per-IP limit can delay, but not
  bypass, sign-in. A deployment behind a trusted reverse proxy should set
  `FORWARDED_ALLOW_IPS` to that proxy so real client IPs are used.

### D-006 Portable schema conventions
- IDs are random UUID strings: not guessable, and they reveal no counts.
- Enums are `VARCHAR` + `CHECK` constraints, not native PostgreSQL enums, so
  SQLite and PostgreSQL behave the same and migrations stay simple.
- All timestamps are timezone-aware UTC. A custom `UTCDateTime` type restores
  `tzinfo` that SQLite drops, and rejects naive datetimes.
- Deterministic constraint names (a naming convention) keep migrations
  identical on both databases.
- SQLite runs with `PRAGMA foreign_keys=ON` so cascades match PostgreSQL.

### D-007 Shared types are hand-written for now
`packages/shared-types` mirrors the Pydantic schemas by hand and is imported
type-only (`@shared/types`). Generating it from `/api/openapi.json` is planned
once the API surface is stable (after M5). Until then, a schema change must
update both in the same commit.

### D-008 The browser only talks to the web origin
Next.js rewrites `/api/*` to FastAPI. Cookies stay first-party, no API base
URL or secret appears in the client bundle (an e2e test checks this), and
CORS is only a second line of defence. Next.js fixes rewrite destinations at
**build time**, so in Docker `API_INTERNAL_URL` is a build argument (found
during compose verification, where the first build pointed at `127.0.0.1`).

### D-009 Registration and duplicate emails
`ALLOW_REGISTRATION` (default `true`) lets the owner turn off sign-up after
creating their account. A duplicate email returns `409` with a clear message.
That does reveal that an account exists, which is accepted for a personal,
single-owner app in exchange for a clear message. Login never reveals it:
wrong-password and unknown-email responses are identical, and both run a full
argon2 hash to equalise timing.

### D-010 Visual design and contrast
Dark navy surfaces (`#070b1a`/`#0c1330`), electric purple primary actions
(`#7c3aed`, white text at about 5.7:1), and cyan highlights and focus rings
(`#22d3ee`). Status is always shown as text plus colour, never colour alone.
axe-core (WCAG 2 A/AA rules, including colour contrast) runs in the e2e suite
on the login, register, home, and settings pages with zero serious or
critical violations. System fonts are used, so no third-party font requests
are made.

### D-011 All tables created in M1
The whole data model ships in the first migration, so later milestones add
behaviour rather than churning the schema. Two tables were added beyond the
brief: `sessions` (D-003) and `user_settings` (model, notification, and
retention preferences; the timezone stays on `users` as specified). Columns
added beyond the brief, all needed later:
- `memories.status` and `memories.approved` both exist. The doc names
  `approved`; the brief names `status`. The memory service (M2) will keep
  them in sync.
- `messages.user_id`, `run_steps.user_id`: owner scoping on every user-owned
  table.
- `conversations.memory_enabled`: the per-conversation memory-off toggle.
- `automation_runs`: `automation_version`, `trigger`, `cancel_requested`,
  `locked_by`/`locked_at` (worker lock), `output_summary`.
- `run_steps`: `risk_level`, `attempts`, `error_message_sanitized`.
- `approvals`: `step_id`, `action_type`, `payload_preview` (the "content
  affected" shown to the user), `risk_explanation`, `likely_consequence`, and
  `consumed_at` (which enforces one-time use).
- `notifications.link`.

### D-012 Idempotency key scope (applies in M4)
`automation_runs.idempotency_key` is globally `UNIQUE` as specified. To stop
two users colliding (or one probing another's key), the stored key will be
derived server-side from (user id, automation id, client `Idempotency-Key`)
instead of storing the raw header.

### D-013 Password policy
argon2id via `argon2-cffi` defaults (OWASP parameters), at least 12
characters, at most 256 (which bounds hashing cost), and no leading or
trailing spaces. Hashes are upgraded on login if parameters change.

### D-014 Native `<select>` for long option lists
Timezone and retention pickers use a styled native `<select>` rather than
Radix Select. With about 400 timezones, the native control gives better
keyboard type-ahead, mobile pickers, and screen-reader support for free.
Radix is used for the dialog (mobile navigation), switch, and label.
Chromium lists `Asia/Calcutta` while Python's IANA data prefers
`Asia/Kolkata`; both are accepted, and the picker always includes the user's
saved value.

### D-015 Next.js 16 conventions
Next.js 16 renamed `middleware.ts` to `proxy.ts`, and `next lint` was removed;
ESLint runs directly. `src/proxy.ts` only gives a UX redirect to sign-in and
strips spoofable headers. **It is not the security boundary; the API checks
the session on every request.**

### D-016 Upcoming sections are honest placeholders
Chat, Tasks, Projects, Automations, Approvals, and Files show "Not available
yet — planned for Mx" with what they will do. No fake data is shown, in line
with "never report success falsely".

### D-017 Layout adjustments
- `migrations/` sits at the repository root as specified. `alembic.ini` lives
  in `apps/api/` and points to it, so `alembic` runs from the API folder like
  every other API command.
- Additional docs: `REPOSITORY_EVALUATION.md` and `REPOSITORY_SHORTLIST.md`.
- `services/user_settings.py` and `services/auth.py` were added alongside the
  listed services.
- The services listed in the brief (ai, memory, policy, automation,
  approvals) arrive with their milestones rather than as empty files.

### D-018 Tooling versions
Playwright is pinned to 1.56.1, with `@axe-core/playwright` overridden to the
same `playwright-core`, so the browser API types match. A preinstalled
Chromium can be used via `PLAYWRIGHT_CHROMIUM_EXECUTABLE`.

## M2 — Chat and memory

### D-019 Ideas taken from the shortlisted repositories
Following the "inspect, then integrate the best" step, three design ideas from
**PersonalClaw** (MIT) were adopted. They were re-implemented, not copied:
1. **Recall disclosure.** Every assistant reply stores the IDs of the memories
   that were in its prompt. The API returns them with a server-stated ranking
   mode (`"keyword"`), so the UI never guesses how memory was used. This also
   satisfies PRD FR-02 ("memory use is visible and controllable").
2. **One switch closes both directions.** When memory is off for a
   conversation, nothing is read from memory *and* nothing is proposed, even if
   the model suggests a memory anyway.
3. **Explicit "remember / always / never" cues** are what trigger a memory
   suggestion; the suggestion is still only *proposed*.

No PersonalClaw code is used, so no attribution file is needed.
MIRA/Khoj (AGPL) and Letta were again not used.

### D-020 Provider adapter: official SDK, structured output, strict re-validation
- `MockProvider` is deterministic and offline. It labels itself as demo mode and
  always reports low confidence.
- `AnthropicProvider` uses the official `anthropic` SDK with JSON-schema
  structured output (`output_config.format`) and low effort for chat latency.
  It also sends `fallbacks: "default"` so a safety-classifier refusal is
  retried server-side on Anthropic's recommended fallback model; a final
  refusal is reported as `ai_refused`, never shown as an answer.
- Whatever the provider returns is parsed again by our own `AssistantReply`
  schema (`extra="forbid"`, at most 3 memory suggestions, enum confidence).
  Invalid output is discarded and reported as `ai_invalid_output`; it is never
  stored or acted on.
- Provider selection is allowlisted: a model must be in `ALLOWED_MODELS`, and
  Claude models also need `AI_PROVIDER=anthropic` plus a key. Otherwise the
  chat returns `ai_unavailable`; it does not silently fall back to the mock.
- **Not verified against the live API in this environment** (no key was
  provided, and live calls cost money). The adapter is covered by unit tests
  with a stubbed SDK client: request shape, parsing, refusal, truncation, and
  the timeout, connection, rate-limit, and authentication error mappings.

### D-021 Failure behaviour of a chat turn
The user's message is committed **before** the provider is called. If the
provider fails, the message stays, no assistant message is invented, an audit
event `chat.reply` with result `failed:<kind>` is written, and the client
gets a typed error. The UI says the message was saved.

### D-022 Backend-enforced "human review needed"
For financial, legal, medical, and security-remediation topics, the backend
adds the note from keyword matching on the user's message and the reply. It is
not left to the model. Matching over-triggers on purpose.

### D-023 Memory relevance is keyword overlap (no embeddings yet)
Up to 5 approved memories that share meaningful words (stopwords removed) with
the message. This is cheap, deterministic, explainable, and needs no extra
service. Semantic recall can be added later behind the same function, with the
ranking mode reported as something other than `"keyword"`.

### D-024 Memory deletion erases the text
`DELETE /api/memories/{id}` blanks `content` and sets `deleted_at`. The row
remains only as a tombstone, so past replies can say "deleted memory" and the
audit trail stays consistent. Audit events for memories never include memory
text.

### D-025 Endpoints added beyond the API list
- `PATCH /api/conversations/{id}`: title and the per-conversation memory
  switch (required by the brief, but no route was listed).
- `DELETE /api/conversations/{id}`: deletion path for privacy (PRD §10).
- `GET /api/memories/export`: the export the technical doc requires.

### D-026 Message retention
The `message_retention_days` setting is enforced by deleting expired messages
for that user before any chat read or write. A scheduled background purge
arrives with the M4 worker; until then, expired messages are removed the next
time the user opens chat.

### D-027 Model output is rendered as plain text
Replies are shown with `white-space: pre-wrap` and React's escaping; no
markdown or HTML rendering, so model output cannot inject markup. A unit test
guards this.

### D-028 Memory page placement
Memory lives at `/memories`, linked from Chat and Settings, and highlights
"Chat" in the navigation. This keeps the PRD's seven navigation items
unchanged.

## M3–M5 and the interface change

### D-029 Apple platform interface, replacing the dark navy direction
The owner asked for "Apple platform interface themes and background", which
replaces the PRD's dark-navy / electric-purple direction (D-010). The
interface now follows Apple's design language:
- **Typography:** the system font stack, so it renders as SF Pro on Apple
  devices, with Apple's type ramp (large title 34, body 17, footnote 13).
- **Colour:** Apple's semantic system colours, in light and dark appearance,
  following the device setting.
- **Structure:** inset grouped lists with hairline separators, a segmented
  control for filters, iOS switches, centred alert dialogs, a translucent
  navigation bar, a five-item tab bar on phones and a macOS-style source list
  on desktop. 44pt minimum hit targets throughout.

**Deviation from Apple's own palette, on purpose:** Apple's stock colours do
not meet WCAG AA for small text. Measured against the grouped background,
`secondaryLabel` gives 4.16:1 and `systemBlue` 3.60:1, and white on
`systemBlue` gives 4.02:1, all under the 4.5:1 requirement. The light
appearance therefore uses a darker secondary label (#5c5c61, 5.96:1) and a
darker blue (#0062cc, 5.80:1 under white). The dark appearance keeps Apple's
values, which already pass. axe-core enforces this in the e2e suite.

### D-030 Starter data is seeded at registration
A new account gets the ScamShield AI project with synthetic milestones, a
second starter project, and two demo automations. Reasons: the brief requires
ScamShield as ordinary project data, and an empty app teaches nothing. The
demo automations are created **disabled**, so nothing runs on a schedule
until the user turns it on.

### D-031 The step registry is the whole execution surface
An automation can only run a step that exists in `services/steps.py`. There is
no "run code", "call this URL", or "shell" step, so neither model output nor a
stored workflow can execute arbitrary behaviour. Unknown step types are
refused when the automation is saved and again before each run.

### D-032 High-risk connectors are stubs that admit it
`send_message`, `publish_report`, `publish_social_post` and the rest record
what *would* be sent and return `delivered: False`, with a summary starting
"DEMO MODE … NOT sent". The brief forbids real external connections in the
MVP, and a run must never claim an action happened. Wiring a real connector
means replacing one function, behind the approval gate that already exists.

### D-033 A permission policy can never downgrade a high-risk step
Listing a high-risk step under `auto_allowed` has no effect: the risk table in
`services/policy.py` is the authority, and high risk always stops for
approval. Medium risk runs only when the automation enables it; prohibited
steps cannot even be saved. A test covers the downgrade attempt.

### D-034 Idempotency keys are derived server-side
The stored key is `sha256(user_id:automation_id:client_key)`, not the raw
`Idempotency-Key` header. The column is globally unique as the brief
specifies, and deriving it means two users can send the same key without
colliding, and neither can probe the other's keys.

### D-035 Worker locking and crash recovery
A run carries `locked_by` and `locked_at`. A second worker leaves a live lock
alone; a lock older than 5 minutes is treated as a dead worker and retaken.
Steps that already succeeded are not re-executed on resume, so a crash mid-run
cannot repeat a side effect. Both paths are tested.

### D-036 Inline worker mode as well as Redis
`WORKER_MODE=inline` runs automations in the API process, which keeps local
demos and the test suite working with no Redis, as the brief asks. Docker
compose uses `redis`. If the queue is unreachable, the run executes inline
rather than being lost, and the fallback is logged.

### D-037 The scheduler is its own process
`python -m app.workers.scheduler` evaluates cron expressions once a minute in
**each owner's** timezone. The idempotency key contains the exact minute, so a
restart, a slow tick, or a second scheduler cannot double-fire a slot. The
cron parser supports `*`, `*/n`, ranges and lists, which is what a personal
scheduler needs; it is not a full cron implementation.

### D-038 Approval expiry and the final gate
Approvals expire after 60 minutes. Approving only records the decision; the
worker then re-checks the payload hash, the expiry, the status and the
permission decision immediately before executing, and marks the approval
consumed in the same transaction. A payload changed after approval is blocked
and audited.

### D-039 Notifications page beyond the PRD navigation
The PRD lists seven navigation items. Notifications needed somewhere to live,
so the desktop sidebar has it as an eighth item and phones reach it from the
bell in the navigation bar. The tab bar keeps five items, per Apple's
guidance, with the rest reachable from those sections.
