# Handoff: build the chat schema (Phase 2 — `conversations`/`messages`/`activity_items`/`message_citations`)

Paste this whole file to a fresh Claude Code session opened at the repo root
(`/home/oz/Autonomized_Takehome`). It has no memory of any prior conversation
about this project — everything you need is below or in the referenced files.

## Context

This is the Team Activity Monitor project — a FastAPI app building a chat
feature where an LLM answers "what is X working on" by combining JIRA/GitHub
data. You're building the database schema for conversations, messages, and
citations — pure SQLAlchemy models + one Alembic migration, no route/service
code.

**Read first, in this order:**
1. `CLAUDE.md` — binding invariants (routes own the DB transaction; models/
   repositories are plain, no `Depends()`, no FastAPI imports — mostly not
   directly relevant to pure model definitions, but read it anyway).
2. `implementation_log.md` — a running record of every decision, ambiguity,
   and bug found so far while implementing this project's Build Phases,
   written by the agent driving this work, and now also by other agents
   working on parallel pieces. Read the whole file for context — in
   particular the "Phase 1 prep: real dependency-order bug found" entry,
   which explains why `team_members` (the table your new FKs will reference)
   was already pulled forward into Phase 1 and already exists — check
   `app/db/models/team_member.py` yourself to confirm its exact shape
   (columns, types) before writing your FK. **When you're done, append your
   own entry to this same file** (don't create a separate log) — record what
   you built, what you had to guess or assume, any bugs/gaps you found, and
   anything a future reader would need to know that isn't obvious from the
   code/spec alone. Follow the file's existing structure (`## <phase/topic>`
   headers, most recent at the bottom). This file is shared across multiple
   agents working on this project in parallel — at least two others are
   working on OAuth-related pieces at the same time as you — so keep your
   entry self-contained and clearly labeled with what you actually did.
3. `blueprints/plans/features/chat.md` — read the whole file for context
   (it's the authoritative spec for the whole chat feature, not just
   schema), but the "Schema" section (near the top) is exactly what you're
   building. Also read the "Schemas (`app/schemas/chat.py`)" section
   further down — you're NOT building that Pydantic schemas file in this
   handoff (see "What NOT to build" below), but `ActivityKind` (a `StrEnum`)
   is referenced by the `activity_items` table's `kind` column, so you need
   to know its three values (`jira_ticket`, `github_commit`, `github_pr`) to
   build the column correctly.
4. `blueprints/plans/implementation-handoff.md`'s "Best practices" section
   (Pydantic for every data shape — N/A for pure SQLAlchemy models, but
   still applies to anything else you touch; full type hints/mypy-clean;
   comment the WHY not the WHAT; all magic numbers in `config.py`).
5. The actual current code: `app/db/models/team_member.py` (the table your
   new tables' FKs reference), `app/db/models/session.py` (existing model —
   match its exact style: `Mapped[...]`/`mapped_column`, `uuid.uuid4` default
   for PKs, `DateTime(timezone=True)` for timestamps), `app/db/models/
   __init__.py` (registers every model — you'll add to this),
   `migrations/versions/2026_07_20_0426-b29ec002714c_add_team_members_table.py`
   (the most recent migration, to see the exact autogenerate output shape/
   style this project's Alembic setup produces).

## What to build

Four new SQLAlchemy models, one file each in `app/db/models/`, matching
`chat.md`'s Schema section exactly:

### `app/db/models/conversation.py` — `Conversation`
- `id`: UUID PK, default `uuid.uuid4`
- `team_member_id`: FK → `team_members.id`, not nullable
- `title`: text, nullable (starts `NULL`, set later from first message —
  not this handoff's concern)
- `created_at`: `DateTime(timezone=True)`, not nullable
- `updated_at`: `DateTime(timezone=True)`, not nullable
- `prefetched_at`: `DateTime(timezone=True)`, nullable (NULL = pre-fetch
  hasn't run yet for this conversation)

### `app/db/models/message.py` — `Message`
- `id`: UUID PK, default `uuid.uuid4`
- `conversation_id`: FK → `conversations.id`, not nullable
- `role`: text, not nullable — Python-side this should be typed as
  `Mapped[Literal["user", "assistant", "system"]]` if SQLAlchemy's mapped
  column typing supports a `Literal` cleanly with a plain `String` column
  type (check how this codebase already handles a similar case, e.g.
  `UserSession` doesn't have a Literal-typed column currently, so use your
  judgement — a plain `str` type with the `String` column is also
  acceptable if the `Literal` approach causes friction; note in your
  `implementation_log.md` entry which you chose and why).
- `content`: text, not nullable (raw text with citation sentinels embedded,
  e.g. `{{cite:1:<uuid>}}` — nothing to enforce about this at the DB level,
  it's just a text column)
- `created_at`: `DateTime(timezone=True)`, not nullable

### `app/db/models/activity_item.py` — `ActivityItem`
- `id`: UUID PK, default `uuid.uuid4`
- `conversation_id`: FK → `conversations.id`, not nullable
- `kind`: text, not nullable — the three values are `jira_ticket`,
  `github_commit`, `github_pr` (from `chat.md`'s `ActivityKind` StrEnum,
  defined in the not-yet-built `app/schemas/chat.py`). Since that schemas
  file doesn't exist yet in this repo (separate, later work), just use a
  plain `String` column type here — do NOT import a StrEnum that doesn't
  exist yet, and do NOT create `app/schemas/chat.py` yourself (see "What NOT
  to build"). A future phase will wire the enum type in; this handoff's job
  is just the correct column shape.
- `external_id`: text, not nullable (JIRA key like `"KAN-42"`, or a GitHub
  PR number/commit SHA)
- `label`: text, not nullable (short display text, e.g. `"KAN-42"`)
- `url`: text, not nullable
- `fetched_at`: `DateTime(timezone=True)`, not nullable
- **Unique constraint**: `(conversation_id, kind, external_id)` — use
  SQLAlchemy's `UniqueConstraint` in `__table_args__`.

### `app/db/models/message_citation.py` — `MessageCitation`
- `id`: UUID PK, default `uuid.uuid4`
- `message_id`: FK → `messages.id`, not nullable
- `activity_item_id`: FK → `activity_items.id`, not nullable
- `ordinal`: integer, not nullable
- **Unique constraint**: `(message_id, ordinal)` — use `__table_args__`
  again.

### Registration

Add all four to `app/db/models/__init__.py`'s imports and `__all__` list,
matching the existing pattern (`TeamMember`/`UserSession` are already there).

### Migration

Generate ONE Alembic migration covering all four tables together (not four
separate migrations) — run:
```
sg docker -c "docker compose up -d --build"
sg docker -c "docker compose exec fastapi alembic revision --autogenerate -m 'add conversation/message/activity_item/message_citation tables'"
sg docker -c "make migrate"
```
(If `docker.sock` permission errors happen, prefix commands with `sg docker
-c "..."` as shown — this dev machine needs that workaround. `make migrate`
already wraps the `docker compose exec` call — check the `Makefile` if
unsure.)

Review the generated migration file for correctness (FK constraints, unique
constraints, nullability) before considering this done — don't just trust
autogenerate blindly; `chat.md`'s Schema section is the source of truth to
check the generated SQL against.

## What NOT to build

- Do NOT create `app/schemas/chat.py` (the Pydantic schemas — `ActivityKind`,
  `ActivityItem`, `MessageOut`, SSE event types, etc.) — that's separate,
  later work. This handoff is pure SQLAlchemy models only.
- Do NOT create any repository files (`conversation_repo.py`,
  `message_repo.py`, `activity_item_repo.py`) — separate, later work.
- Do NOT touch `scripts/seed.py` or `local-dev-data/` — these four tables
  have no seed fixtures in `chat.md`'s design (only `team_members` does,
  already done).
- Do NOT modify `app/db/models/team_member.py` or `app/db/models/session.py`.
- Do NOT build any routes, services, or tools.

## Testing

Per `timeline.md`'s Phase 2 gate description: "a clean migration; ... no
other tests needed yet since nothing queries these tables until Phase 3." So
your gate is narrower than a full pytest suite addition:
1. Confirm `alembic revision --autogenerate` produced a clean, correct
   migration (review it yourself against the spec).
2. Confirm `alembic upgrade head` applies cleanly.
3. Run the FULL existing test suite to confirm nothing broke:
```
sg docker -c "make test"
sg docker -c "docker compose exec fastapi ruff check ."
sg docker -c "docker compose exec fastapi mypy app/"
```
All existing tests (20 as of this writing) should still pass — these new
tables aren't queried by any existing code, so nothing should break, but
verify rather than assume.

## When done

Report back: what you built, the exact migration file name/content summary,
whether `make test`/ruff/mypy all passed, and anything you had to guess or
assume (especially the `role` column's typing choice, and how you handled
`activity_items.kind` given the enum type doesn't exist as real Python code
yet).
