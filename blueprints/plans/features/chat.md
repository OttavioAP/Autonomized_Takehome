# Chat Feature Spec

Spec for the chat interface end-to-end: UI (MVP-FR-3, MVP-FR-4), query understanding and data fetching (MVP-FR-5, MVP-FR-9, MVP-FR-10), response synthesis (MVP-FR-11), streaming (MVP-FR-12), conversation history (MVP-FR-7), and identity mapping (MVP-FR-8). This file replaces and deprecates `chat-ui.md` (deleted), which specced only a two-channel (`token` + batch `cards`) SSE shape with no tool-calling, no citation model, and no DB schema — all since redesigned through direct discussion. This is now the sole, authoritative spec for the chat feature.

## Design summary

The chat answers "what is X working on" by combining a **deterministic pre-fetch** (the logged-in user's own JIRA/GitHub activity, fetched once at login) with an **agentic loop**: the LLM gets a system prompt containing the team roster and the pre-fetched context, and can call JIRA/GitHub tools itself (capped at 5 rounds) when it needs data about someone other than the current user, or more than what was pre-fetched. The LLM never constructs links itself — it cites pre-resolved, server-validated objects by UUID, which the route swaps into rendered pills as the response streams.

Three design decisions anchor everything below:

1. **No regex/NLP name-parsing code.** MVP-FR-5 ("extract the member's name and intent") is not implemented as parsing logic — the LLM reads the team roster directly from its system prompt and resolves who's being asked about the same way it resolves everything else in context. There is no `query_parser.py`, no fuzzy-matching, no keyword extraction.
2. **Pre-fetch is about the session's own user, not the query's subject.** Earlier drafts of this design had the *route* resolving "who is this question about" before pre-fetching for that person — but that resolution is the model's job (point 1), which made a route-side pre-fetch step impossible without adding a name-parsing step back in. Resolved by re-scoping pre-fetch entirely: at login, deterministically fetch the logged-in user's *own* JIRA/GitHub activity (no resolution problem — it's whoever just authenticated) and inject that as baseline context on every LLM call in the session. If the question is about someone else, the model reaches for a tool with a real, roster-resolved identifier.
3. **The LLM cites, it does not construct.** The model never emits a URL or builds a card itself. It emits an inline sentinel referencing a UUID from a set of objects the *route* already fetched and validated. The route resolves the UUID against that known-good set and renders the real object. This is a hard trust boundary: a hallucinated or stale UUID can never become a rendered link.

## Auth model for JIRA/GitHub calls (MVP scope)

**Per-user OAuth, persisted per user — see `oauth-integration.md`.** Superseded from
an earlier draft of this spec, which used a single shared service-account
token (`JIRA_API_TOKEN`/`GITHUB_TOKEN` in `Settings`). Un-deferred from
NMVP-FR-2 into MVP at the user's explicit request, once it became clear a
shared credential didn't hold up once conversations could be about anyone on
the team. Every JIRA/GitHub call now uses the logged-in user's own OAuth
token, stored in Key Vault keyed by `team_members.id` and surviving sign-out
(revised mid-implementation from an initial session-scoped design once Key
Vault was already the storage layer — see `oauth-integration.md`'s Isolation
model section for the full reasoning, including JIRA's refresh-token
handling this now requires) — `oauth-integration.md` has the full flow,
schema, and client rework.

## Schema

Five new tables, built across two phases per `timeline.md`'s Build Phases: `team_members` moved to Phase 1 (step 0) since the OAuth token-persistence design now depends on it existing before any OAuth code runs; `conversations`/`messages`/`activity_items`/`message_citations` remain Phase 2, built together as originally planned. `conversations`/`messages` were already anticipated by MVP-FR-7/stack-and-infra.md; `activity_items`/`message_citations` are new, driven by the citation design.

### `team_members`

Backs MVP-FR-8, replacing the current `local-dev-data/team_members.json`-only fixture with a real table (the fixture file still seeds it via `make seed`, per the existing `local-dev-data/` convention — the JSON becomes the seed source, not a runtime dependency).

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `display_name` | text | e.g. `"Sarah"` |
| `azure_upn` | text, unique | matches `UserSession.user_upn` — the join between "who's logged in" and "which team member is that" |
| `jira_account_email` | text | |
| `github_login` | text | |
| `jira_cloud_id` | text, nullable | Resolved once via `accessible-resources` at `GET /oauth/jira/callback` time, reused by pre-fetch. `NULL` until the user connects JIRA. Lives here (per-user) rather than on `sessions` — see `oauth-integration.md`'s Token storage section, revised so JIRA/GitHub connections persist across logins rather than being re-earned every session. |

### `conversations`

A user can have multiple conversations and switch between them (revised from the
original "one conversation per session" design — see Routes below). FK to a user,
not just a session, which is what makes this possible without a schema change:
`team_member_id` already scoped ownership at the person level, not the login event.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `team_member_id` | FK → `team_members.id` | the conversation's owner |
| `title` | text, nullable | Set from the first user message (truncated), for the conversation-switcher list. `NULL` until the first message lands — a brand-new empty conversation shows as "New conversation" in the UI rather than blank. |
| `created_at` | timestamptz | |
| `updated_at` | timestamptz | Bumped on every new message (own transaction, alongside the message insert). Drives "most recent first" ordering in the switcher list — without this, listing would need a `MAX(messages.created_at)` join on every render. |
| `prefetched_at` | timestamptz, nullable | Set once this conversation's login-context pre-fetch has run (see Pre-fetch section). `NULL` means "not yet run" — this is the explicit check the route uses, replacing the vaguer "if it hasn't run yet" from an earlier draft of this spec. Per-conversation rather than per-session because pre-fetch data lives in `activity_items` scoped by `conversation_id`; a second, brand-new conversation in the same session still needs its own pre-fetch. |

### `messages`

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `conversation_id` | FK → `conversations.id` | |
| `role` | `MessageRole` (native DB enum, `app/db/models/message.py`) | `user` \| `assistant` \| `system` |
| `content` | text | Raw text **with citation sentinels embedded** (`{{cite:ordinal:uuid}}`) — not stripped. One source of truth for both live rendering and history replay. |
| `created_at` | timestamptz | Provides message ordering within a conversation |

### `activity_items`

The stable, per-conversation store of every JIRA/GitHub object fetched (pre-fetch or tool-triggered — both paths upsert through the same function, see Tools section). Existence of the unique constraint is what makes "cite the same ticket in turn 3 that was fetched in turn 1" resolve to one stable id.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | The stable id the LLM cites |
| `conversation_id` | FK → `conversations.id` | Citation identity is scoped per-conversation — a UUID from conversation A can never validate in conversation B |
| `kind` | `ActivityKind` (see Schemas) | `jira_ticket` \| `github_commit` \| `github_pr` — encodes both provider and type; no separate `source` column (derived from `kind` as a computed property where needed, to avoid drift) |
| `external_id` | text | JIRA key (`"KAN-42"`) or GitHub PR number / commit SHA |
| `label` | text | Short display text for the pill, e.g. `"KAN-42"`, `"PR #17"` |
| `url` | text | Deep-link to the source system |
| `fetched_at` | timestamptz | |

Unique constraint: `(conversation_id, kind, external_id)`.

### `message_citations`

Join table. Its job is integrity, not positioning — `messages.content` already encodes position via the literal sentinel text. This table is the durable record that a given citation was actually validated by the route, independent of re-parsing `content`.

| Column | Type | Notes |
|---|---|---|
| `id` | UUID PK | |
| `message_id` | FK → `messages.id` | |
| `activity_item_id` | FK → `activity_items.id` | |
| `ordinal` | int | Matches the ordinal embedded in the message's `{{cite:ordinal:uuid}}` sentinel |

Unique constraint: `(message_id, ordinal)` — structurally prevents ordinal collisions within one message; ordinals are scoped per-message, not global, so message 5 and message 8 can both have a citation `1`.

## Schemas (`app/schemas/chat.py`)

Also home to `JiraProjectRef`/`GithubRepoRef`/`GithubCollaboratorRef` (see
`oauth-integration.md`'s Scope discovery section) — the pre-fetched top-10
project/repo/collaborator shapes rendered into the system prompt.
`GithubCollaboratorRef` is prompt context only (no tool accepts a
collaborator identifier as a parameter — it exists so the model has
pre-awareness of who it's likely to be asked about next, not so it can be
handed back to a tool call the way `JiraProjectRef.key`/`GithubRepoRef.full_name`
are). Defined here rather than in `oauth-integration.md`'s own client-rework
code, consistent with `ActivityItem`/`MessageOut` already living in this one
schemas module for anything chat-prompt-facing.

**Expanded during Phase 3/5 implementation** (see `implementation_log.md`): two
citable kinds added (`JIRA_COMMENT`, `GITHUB_COMMENT`) once the tools began fetching
comment threads, plus `JiraPersonRef` added alongside the discovery refs (real project
members discovered via JIRA's assignable-users search, usable as a `JiraToolParams`
argument for people outside the static roster). Priority/issue-type (JIRA) and PR
review decision (GitHub) are folded into each item's pill `label` as enrichment text
rather than new kinds or `ActivityItem` fields — descriptive detail that doesn't need
its own pill.

```python
class ActivityKind(StrEnum):
    JIRA_TICKET = "jira_ticket"
    JIRA_COMMENT = "jira_comment"
    GITHUB_COMMIT = "github_commit"
    GITHUB_PR = "github_pr"
    GITHUB_COMMENT = "github_comment"

class ActivityItem(BaseModel):
    """Service-facing normalized shape both tools return. Feeds citation validation."""
    id: UUID
    kind: ActivityKind
    label: str
    url: str

class ActivityItemOut(BaseModel):
    """Page-render view — same fields as ActivityItem, named separately since the
    two may diverge (e.g. ActivityItemOut gaining render-only fields later)."""
    id: UUID
    kind: ActivityKind
    label: str
    url: str

class MessageOut(BaseModel):
    id: UUID
    role: Literal["user", "assistant", "system"]
    content: str  # raw, sentinels embedded — template resolves them at render
    citations: list[ActivityItemOut]  # pre-joined; list index + 1 == ordinal
    created_at: datetime

class ChatRequest(BaseModel):
    query: str
    csrf_token: str

# SSE event payloads. Each is the JSON `data:` body for its named SSE `event:`.
class ToolStatusEvent(BaseModel):
    message: str  # "Checking Sarah's JIRA tickets…" — ephemeral, never persisted

class TokenEvent(BaseModel):
    text: str

class CiteEvent(BaseModel):
    ordinal: int
    item: ActivityItemOut

class CiteErrorEvent(BaseModel):
    ordinal: int
    detail: str = "Couldn't resolve a citation the assistant made — this may be a bug."

class ErrorEvent(BaseModel):
    detail: str  # OpenRouter/transport failure — no model left to explain itself

class SSEEnvelope(BaseModel):
    """Typing convenience for the Python code building these — not a literal wire
    wrapper. The route still emits real `event: <name>\\ndata: <json>\\n\\n` SSE
    frames; `event` here just drives a single `emit()` dispatch helper."""
    event: Literal["tool-status", "token", "cite", "cite-error", "error"]
    data: ToolStatusEvent | TokenEvent | CiteEvent | CiteErrorEvent | ErrorEvent
```

All five SSE event types carry a uniform JSON envelope (no plain-text-only events) — client-side JS has one parse path regardless of event name.

## Config (`app/config.py`)

Add `max_tool_call_rounds: int = 5` to `Settings` — a code default, env-var overridable, not hardcoded in `ChatService`. Also `discovery_top_n: int = 10` (see `oauth-integration.md`'s Scope discovery section) — the cutoff for pre-fetch's top-projects/top-repos/top-collaborators discovery, one shared knob rather than three.

## Pre-fetch, cached per conversation (deterministic, no LLM involved)

Triggered once per **conversation** — not per session, since a session can now span multiple conversations (see Routes below). Explicit check: `conversations.prefetched_at IS NULL`. Looks up the logged-in user's own `team_members` row (via `azure_upn`), then calls `JiraTool`/`GithubTool`'s underlying fetch for that one identity, upserting results into `activity_items` scoped to this `conversations` row, then sets `prefetched_at = now()` in the same transaction as the route that triggered it. This is the "basic level of context about the user, their tickets, their recent commits/PRs" that goes into the system prompt of every LLM call in this conversation — the model starts every conversation already knowing what the current user has been doing, without spending a tool-call round on it.

Cached, not re-run: once `prefetched_at` is set, every subsequent visit to that conversation (including switching away and back) reads the already-upserted `activity_items` rows rather than re-fetching from JIRA/GitHub. A brand-new conversation (via `POST /conversations`) always starts with `prefetched_at = NULL` and gets its own fresh pre-fetch on first render — the cache is scoped to the conversation record, not the person, so switching between two of a user's own conversations does not share pre-fetched data between them (each conversation's `activity_items` reflects what was true on its own first-access moment, not necessarily today's).

This is genuinely deterministic code (no model call), reusing the same normalize-to-`ActivityItem` function tool execution uses (see below) — one function, two callers, exactly as pre-fetch and tool-calling were designed to share from the start.

## Tools (`app/services/tools/`)

### `base.py` — `ActivityTool` (Protocol/ABC)

Common interface every tool implements: `name: str`, `description: str`, `Params: type[BaseModel]` (the tool's own Pydantic parameters model — see `openrouter-integration.md`'s `ToolDefinition`, which every tool exposes via a `definition: ToolDefinition` property built from these three), `async def execute(self, session: AsyncSession, conversation_id: UUID, params: Params, **credentials) -> list[ActivityItem]`. Per `oauth-integration.md`, `execute()` also takes the current user's provider token(s) as an explicit argument (resolved by the route from Key Vault, keyed by `team_member_id` — see `oauth-integration.md`'s Token storage section) — tools never read credentials from `Settings` or fetch them themselves. `ChatService` resolves which tool's `Params` type to validate a given `ToolCall` against by matching `ToolCall.name` to `ActivityTool.name`.

### `jira_tool.py` — `JiraTool`

`class JiraToolParams(BaseModel): jira_account_email: str | None; account_id: str | None; project_key: str` — **exactly one of** `jira_account_email`/`account_id` must be set (Pydantic `model_validator` enforces this). Email covers the roster's 3 seeded members; `account_id` covers anyone the model learned about via pre-fetch's assignable-users discovery (`JiraPersonRef`) — discovery frequently can't resolve an email at all, since JIRA returns a blank `emailAddress` for most non-owner accounts (confirmed live). Wraps `jira_client.find_account_id_by_email` (only on the email path) + `get_issues_assigned_to` + `get_comments`, called with the current user's JIRA OAuth token/cloud ID. Maps each `JiraIssue` to an `ActivityItem(kind=JIRA_TICKET, ...)` with priority/issue-type folded into the pill label, and each comment to `ActivityItem(kind=JIRA_COMMENT, ...)`; both upsert via `activity_item_repo` keyed on `(conversation_id, kind, external_id)`. Issues are fetched with a `since_days=Settings.activity_lookback_days` JQL `updated >= -Nd` bound. On a 401, retries once after a silent refresh per `oauth-integration.md`'s JIRA refresh section before surfacing `ToolExecutionError`.

### `github_tool.py` — `GithubTool`

`class GithubToolParams(BaseModel): github_login: str; repo: str`, same reasoning (a discovered contributor's `login` from `GithubCollaboratorRef` works here directly, no email-vs-id split needed since GitHub identifies people by login). Wraps `github_client.get_recent_commits_by_author` (with a `since` bound from `Settings.activity_lookback_days`) + `get_pull_requests_by_author` + `get_pr_reviews` + `get_issue_comments`. Maps commits/PRs to `ActivityItem(kind=GITHUB_COMMIT | GITHUB_PR, ...)` — PR review decision folded into the pill label — and PR comments to `ActivityItem(kind=GITHUB_COMMENT, ...)`, upserting the same way.

Neither tool does name resolution, fuzzy matching, or accepts a display name — the model is expected to have already resolved a display name to an email/login/account_id using the roster or discovered people/collaborators lists in context before calling either tool. If it hasn't (no matching name anywhere), that's not a tool failure — the model simply says so in its own prose (MVP-FR-6's "member not found" state is model-generated text, not a thrown error).

**Time-bounded queries** (e.g. the rubric's "What has Mike committed *this week*?") — **resolved during implementation**: `get_recent_commits_by_author` now takes `since`/`until`, `get_issues_assigned_to` takes `since_days` (JQL `updated >= -Nd`), both driven by `Settings.activity_lookback_days` (default 14). The tools scope to that window automatically; the model narrows further to "this week" in its own prose from the real timestamps it receives.

## Errors (`app/services/chat_errors.py`)

No silent failures anywhere in this design — every failure class either becomes explicit model-facing context (so the model explains the limitation in its own words) or a dedicated SSE event, never a swallowed exception or a canned string.

| Class | Where it's used |
|---|---|
| `ToolExecutionError` | Raised when a tool's underlying JIRA/GitHub HTTP call fails. Caught by `ChatService`, turned into an explicit error string appended as the tool result (`"JIRA lookup failed: <reason>"`), fed back to the model — the model decides how to communicate that to the user. |
| `UpstreamProviderError` | OpenRouter itself is unreachable/erroring — no model is available to explain itself, so this maps directly to the `error` SSE event instead. |

Tool-call-limit handling is not a raised exception — see the agentic loop below.

## Prompts (`app/prompts/`)

Plain text/markdown files loaded by a small `app/prompts/loader.py`, not string literals inline in `ChatService`.

- `chat_system_prompt.md` — role framing, the full team roster (rendered in from `team_members` at call time — small enough to inline directly, no retrieval needed), the pre-fetched `activity_items` for the current user, the citation-sentinel instructions (exact `{{cite:ordinal:uuid}}` format and the rule that ordinals are sequential starting at 1 within the response), and the two available tools' existence/purpose in prose. **TODO, deliberately last**: explicit instruction covering the "successful fetch, zero results" case (MVP-FR-6's "no recent activity" state) — right now nothing tells the model to distinguish "I found nothing" from "I didn't check," so a tool/pre-fetch returning an empty list has no specified prompt behavior yet. Addressed after the rest of this spec is implemented and there's a real response to look at, not guessed at now.
- `tool_limit_reached.md` — substituted in as an additional system message on the final forced no-tools call after round 5: tells the model plainly it's out of tool-call budget for this turn and should answer with whatever it has, saying so if that's insufficient — this produces the user-facing "sorry, I couldn't fully check X" in the model's own streamed prose, never a hardcoded string.

## `ChatService` (`app/services/chat_service.py`)

The agentic loop — the single class owning orchestration. Constructed with `session: AsyncSession` passed in explicitly (not self-injected), consistent with CLAUDE.md's transaction-ownership rule: `ChatService` never calls `Depends()` or commits; the route does both.

**`CitationStreamParser`** lives in the same file as a separate class (tightly coupled, always used together, but a distinct responsibility): a stateful rolling-buffer scanner. Consumes `llm_router.TextDelta.text` fragments as they arrive (see `openrouter-integration.md` for the full `QueryEvent` union `ChatService` now consumes — `TextDelta | ToolCallDelta | StreamDone`), regex-scans the buffer for a complete `{{cite:ordinal:uuid}}` match, and yields plain-text spans plus detected matches for `ChatService` to validate and turn into `cite`/`cite-error` events. Handles matches split across delta boundaries by buffering rather than requiring the sentinel to land in a single chunk.

**Real bug found during Phase 5 implementation, not caught by synthetic unit tests**: a real OpenRouter stream splits deltas *inside* the sentinel at boundaries synthetic test fixtures didn't cover — right after the opening `{{` (e.g. `"...PR #1 {{"` then `"cite:1:5bdc6"...`), and right before the final `}` of the closing `}}` (e.g. `"...a43a}"` then `"}.\n\n..."`). The original partial-sentinel regex only held back a tail once it saw a literal `{{c` prefix, so a bare trailing `{{` (or a complete-but-unclosed `{{cite:N:UUID}` with one brace) flushed as plain text instead of being buffered — the sentinel then leaked to the client as raw `{{cite:...}}` text in a `token` event instead of becoming a `cite` event, and the citation was silently lost. Combined with a soft-sounding citation instruction in the prompt, live testing showed the model citing correctly on only 0–1 of 5 identical natural-phrasing queries ("What is Sarah working on these days?") even when it *did* emit a well-formed sentinel — a defect serious enough to have undermined MVP-FR-4 (clickable pills) had it shipped. Fixed by (1) rewriting `_PARTIAL_SENTINEL_RE` to hold back every real prefix of the sentinel including a lone `{`/`{{` and a one-brace-short closing tail, and (2) moving the citation instruction to a "MOST IMPORTANT RULE" section at the top of `chat_system_prompt.md` with a concrete worked example. Verified 5/5 live after the fix, plus regression unit tests using the exact fragment boundaries captured from a real stream (`tests/test_citation_parser.py`).

**`ChatService.run(query: str) -> AsyncIterator[SSEEnvelope]`** — the method the route drives:

1. Persist the incoming user message.
2. Build the system prompt (roster + this session's pre-fetched `activity_items` + citation/tool instructions) via `app/prompts`.
3. Loop, bounded at `Settings.max_tool_call_rounds` (5):
   - Call `llm_router.query()` with `tools=[JiraTool.definition, GithubTool.definition]` (each tool exposes a `ToolDefinition` built from its own Pydantic `Params` model — see `openrouter-integration.md`), consuming the yielded `QueryEvent`s:
     - `TextDelta` events → proceed to step 4 (drive through `CitationStreamParser` as they arrive; a single turn can freely mix text before/after a tool call, so this isn't strictly sequenced before tool-call handling).
     - `ToolCallDelta` → for each `ToolCall` in `.calls`: yield a `tool-status` envelope (e.g. `"Checking Sarah's JIRA tickets…"`, derived from `.name` + `.parsed_arguments(...)`), parse arguments via `call.parsed_arguments(JiraToolParams)` (or the matching tool's params type — resolved by `call.name`), catching a `ValidationError` the same way as `ToolExecutionError` (MVP-NFR-4: a malformed tool-call payload becomes an explicit error string fed back to the model, never an unhandled exception or silently-ignored call), then execute the tool (catching `ToolExecutionError` → feed an error string back as the tool result), append the tool result as a `tool`-role `ChatMessage` (`tool_call_id=call.id`), loop again.
     - `StreamDone(finish_reason="tool_calls")` → all of this turn's tool calls have been yielded (already handled via `ToolCallDelta` above); proceed to next loop iteration.
     - `StreamDone(finish_reason="stop")` → the model's answer is complete; proceed to step 5.
   - If round 5 is reached and the model still wants a tool call: make one final `query()` call with `tools=None` and `tool_limit_reached.md` appended to context, forcing a text answer (a call with no `tools` cannot return `ToolCallDelta` at all, so this is a hard stop, not a soft hint).
4. Drive text deltas through `CitationStreamParser`. For each plain-text span, yield a `token` envelope. For each detected sentinel match, validate the UUID against this conversation's `activity_items` (via `activity_item_repo`); if valid, assign the next ordinal and yield a `cite` envelope; if invalid, yield a `cite-error` envelope instead (sentinel is not rendered as a pill either way — the raw sentinel text itself is never sent to the client).
5. On stream completion: persist the assistant message (raw content, sentinels intact) and insert one `message_citations` row per successfully validated citation.
6. Any `UpstreamProviderError` at any point short-circuits the loop and yields a single `error` envelope.

**Tool-role messages are never persisted** (resolved via direct discussion — not an oversight): the `tool`-role `ChatMessage`s appended in step 3's tool-call branch live only in the in-memory `messages: list[ChatMessage]` passed across repeated `llm_router.query()` calls within one `ChatService.run()` invocation. They're never written to the `messages` table and never shown to the user — the user only ever sees the `tool-status` envelope's ephemeral prose (e.g. "Checking Sarah's JIRA tickets…") while a call is in flight, then the model's actual text answer once it's done. This is why `MessageOut.role`/the `messages` table's `role` column only need `Literal["user", "assistant", "system"]`, not a fourth `"tool"` value — `ChatMessage.role`'s wider `Literal` (including `"tool"`) is `llm_router.py`'s own internal vocabulary for the OpenRouter request/response wire format, not a reflection of what gets persisted.

## Repositories (`app/repositories/`)

Plain functions taking `session: AsyncSession` as an explicit argument — no `Depends()`, no FastAPI imports, per CLAUDE.md.

- `conversation_repo.py` — create a new conversation for a user; get one by id (with ownership check); get a user's most recent (for `GET /`'s redirect target); list all of a user's conversations ordered by `updated_at` (for the switcher); update `title`/`updated_at`/`prefetched_at`. Does **not** own the message+citations join — that query lives in `message_repo.py` (see below), since it's a `messages`-rooted query (join outward to `message_citations`/`activity_items`), not a `conversations`-rooted one.
- `message_repo.py` — insert a message; insert its `message_citations` rows; **owns** `list_for_conversation(conversation_id) -> list[MessageOut]`, the messages-with-citations-pre-joined query used by `GET /conversations/{id}`'s history render (moved here from an earlier, ambiguous draft that also listed this under `conversation_repo.py`).
- `activity_item_repo.py` — upsert-by-`(conversation_id, kind, external_id)`; fetch a conversation's current item set (the citation-validation set).
- `team_member_repo.py` — lookup by `azure_upn` (pre-fetch's login-time entry point) and list-all (roster for the system prompt).

## Routes (`app/api/pages.py`)

All own their transaction per CLAUDE.md — `ChatService`/repositories never commit.
The session cookie identifies *who* is logged in (`team_member_id`, via
`azure_upn`); it no longer identifies a single active conversation — that's now
carried explicitly in the URL path, so a user can hold multiple conversations
open in different tabs without them fighting over "the" session conversation.

### `GET /` (existing, extended)

No longer the conversation view itself. Looks up the current user's most
recently updated conversation (`conversation_repo.get_most_recent(team_member_id)`,
ordered by `updated_at`) and redirects (`302`) to `GET /conversations/{id}`. If
the user has no conversations yet, creates one (equivalent to what
`POST /conversations` does) and redirects into that instead — so a first-time
user never sees an empty/dead-end state, but an explicit "New conversation"
action is still how every *subsequent* conversation gets created.

### `GET /conversations/{id}` (new)

The actual conversation view (previously the body of `GET /`). Loads the
conversation via `conversation_repo` (404 if the id doesn't belong to the
current user — ownership check via `team_member_id`, not just existence),
triggers pre-fetch if `prefetched_at IS NULL`, loads message history, renders
`index.html` with `current_user`, the message list, the active `conversation_id`
(for `POST /conversations/{id}/chat`'s hidden form field and the SSE endpoint
URL), and the sidebar/dropdown list of the user's other conversations
(`conversation_repo.list_for_user`, most-recent-first) for switching.

### `POST /conversations` (new)

Creates an empty `conversations` row (`title = NULL`, `prefetched_at = NULL`)
for the current user, redirects to `GET /conversations/{new_id}` — which
handles the first-visit pre-fetch itself, so this route stays a one-line insert
with no fetch logic duplicated from the `GET` handler.

### `POST /conversations/{id}/chat` (new)

Takes `conversation_id` from the URL path (`/conversations/{id}/chat`, not the
body), so `ChatRequest` no longer needs to carry it — the path is already the
authorization boundary (route re-checks the conversation belongs to the current
user before doing anything else, same ownership check as the `GET` route).
Parses the request body (validated Pydantic, MVP-NFR-4), checks the CSRF token,
constructs `ChatService(session, conversation_id)`, streams its yielded
`SSEEnvelope`s as `event: <name>\ndata: <json>\n\n` SSE frames, updates
`conversations.updated_at` and (if still `NULL`) `title` from the truncated
first user message, commits once the generator is exhausted. This route no
longer creates conversations implicitly — by the time a message is sent, a
conversation id is always already resolved (via `GET /` or `POST /conversations`).

## Templates (`app/templates/chat/`)

- `_message.html` — one turn: role, `content` with sentinels resolved into inline pills using the message's joined citations (shared logic between live SSE-driven rendering and history replay on `GET /`).
- `_activity_pill.html` (macro) — single JIRA/GitHub pill, `{% macro activity_pill(kind, label, url) %}`, whole element is the link. Unchanged in concept from the earlier mockup artifact.
- `_tool_status.html` — transient status line fragment for `tool-status` events; replaced (not accumulated) once real prose starts, never persisted.
- `_cite_error.html` — small inline error marker fragment for `cite-error` events, rendered in place of a pill.

Mockup reference: the standalone HTML artifact built earlier in this design process (bubbles, pills, streaming caret, empty/error states) — same visual language, now with pills/errors appearing inline mid-text rather than in a trailing strip.

## Static

`app/static/css/chat.css` — bubble, pill, tool-status, and cite-error styling, vendored locally alongside Pico per the stack decision (no CDN).

## Explicitly out of scope for this spec

- Deleting/renaming/archiving conversations — creation and switching are in scope (see Routes); lifecycle management beyond that is not.
- Rich/expandable cards beyond the pill (NMVP-FR-3).
- Any regex/NLP-based query parsing — deliberately not built; name resolution is entirely the model's job via in-context roster data.
- Ambiguous-name disambiguation (NMVP-FR-9) — not needed at the 3-user MVP roster size; the model handles "not found" in prose, but does not yet handle "which of two Sarahs did you mean."
- Resolving a project/repo the model needs but that wasn't in the pre-fetched top-10 list — see `oauth-integration.md`'s Explicitly out of scope section.

## Trackers to update once implemented

- `blueprints/requirements/features.md`: MVP-FR-3, MVP-FR-4, MVP-FR-5, MVP-FR-7, MVP-FR-8, MVP-FR-9 (repo-identity dependency), MVP-FR-10 (repo-identity dependency), MVP-FR-11, MVP-FR-12 — Specced column.
- `blueprints/requirements/timeline.md`: step 7 progress note; step 6 (MVP dependency tree) can now be filled in for this cluster of features.
- `CHANGELOG.md`: dated entry once this spec lands.
- See also `oauth-integration.md`'s own trackers section — un-defers NMVP-FR-2 and rewrites MVP-NFR-3, both independent of this file's own tracker updates.
