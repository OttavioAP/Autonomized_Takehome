# Handoff: build chat UI templates + CSS (Phase 6 structure, no live routes)

Paste this whole file to a fresh Claude Code session opened at the repo root
(`/home/oz/Autonomized_Takehome`). It has no memory of any prior conversation
about this project — everything you need is below or in the referenced
files.

## Context

This is the Team Activity Monitor project — a FastAPI + htmx + Jinja2 app
(server-rendered HTML fragments, no JS build step, no React/Vue). You're
building the chat UI's templates and CSS ahead of the routes that will
render them (those routes — `GET /conversations/{id}`, `POST /conversations/
{id}/chat`'s SSE stream — are SEPARATE, later work, not part of this
handoff; someone else is building `ChatService`/the agentic loop that feeds
these templates). Your job is to get the template files and CSS built,
syntactically correct Jinja2, and structurally ready to be wired into real
routes later — you will NOT be able to see them rendering against live data
in a browser, since the data-producing side doesn't exist yet. Say this
explicitly in your final report rather than claiming you verified live
rendering.

**Read first, in this order:**
1. `CLAUDE.md` — binding invariants (mostly not relevant to templates, but
   read it anyway for general project conventions).
2. `implementation_log.md` — a running record of every decision, ambiguity,
   and bug found so far while implementing this project's Build Phases.
   Skim the whole file for context. **When you're done, append your own
   entry to this same file** (don't create a separate log) — record what
   you built, what you had to guess or assume (there will be real guesses
   here, since you're building against a spec without live data to check
   against — be thorough about flagging these), any gaps you found, and
   anything a future reader would need to know. Follow the file's existing
   structure (`## <phase/topic>` headers, most recent at the bottom). This
   file is shared across multiple agents working on this project in
   parallel right now — keep your entry self-contained and clearly labeled.
3. `blueprints/plans/features/chat.md` — read the WHOLE file, but
   specifically: the "Design summary" (top of file, for the overall mental
   model of pills/citations/streaming), "Schemas (`app/schemas/chat.py`)"
   section (the exact shape of `MessageOut`, `ActivityItemOut`,
   `ActivityKind`, and the 5 SSE event types — `ToolStatusEvent`,
   `TokenEvent`, `CiteEvent`, `CiteErrorEvent`, `ErrorEvent` — these are NOT
   built as real Python code yet, but you need to know their field names to
   build templates/JS against the eventual wire shape), "Templates
   (`app/templates/chat/`)" section (exactly what files to build and their
   responsibilities), and "Static" section (`app/static/css/chat.css`).
4. `blueprints/specs/stack-and-infra.md`'s "Streaming (MVP-FR-12)" section —
   SSE via `htmx-ext-sse` (`hx-ext="sse"`, `sse-connect`, `sse-swap`), NOT a
   hand-rolled `EventSource`.
5. The actual current code: `app/templates/base.html` (the layout every
   page extends — note it already loads `htmx.min.js` and
   `htmx-ext-sse.js` from `/static/vendor/` via `<script defer>` tags, and
   Pico.css from `/static/vendor/pico.min.css` — classless CSS, so most
   elements are already reasonably styled by default; you're adding
   chat-specific styling on top, not replacing this), `app/templates/
   index.html` (the current placeholder home page — note its nav bar
   structure with the sign-out form; your chat page will eventually replace
   this file's content per `chat.md`'s Routes section, but that route
   rewiring is NOT part of this handoff — see "What NOT to build"),
   `app/static/vendor/` (confirm `htmx-ext-sse.js` is there — it already
   is), `local-dev-data/team_members.json` (for realistic example
   data — John/Sarah/Mike).

## What to build

### `app/templates/chat/_message.html`

One turn of the conversation: role, `content` with citation sentinels
resolved into inline pills. Per the spec: "shared logic between live
SSE-driven rendering and history replay on `GET /`" — meaning this template
needs to work both as a fragment returned by an SSE event AND as part of a
full-page render of conversation history. It receives a message-shaped
context with (at minimum, based on `MessageOut`'s Pydantic shape in the
spec): `role` (one of `"user"`/`"assistant"`/`"system"`), `content` (raw
text with `{{cite:ordinal:uuid}}` sentinels embedded — **you will need to
resolve these sentinels into rendered pills yourself in this template**,
using each message's `citations` list, where `citations[i]` corresponds to
ordinal `i+1` per the spec's "list index + 1 == ordinal" note). Since Jinja2
doesn't have a clean built-in regex-replace-with-template-rendering
primitive, you'll likely need either (a) a small custom Jinja2 filter
registered in `app/templating.py`, or (b) document clearly in your
`implementation_log.md` entry that sentinel-to-pill resolution needs to
happen in Python before the template receives `content` (i.e., the route/
service layer does the replacement and hands the template pre-resolved
HTML) — **explicitly flag which approach you took and why**, since this is
a real design decision with no single obviously-correct answer from the
spec alone, and the person who builds the real routes later needs to know
which approach your template assumes.

### `app/templates/chat/_activity_pill.html`

A Jinja2 macro: `{% macro activity_pill(kind, label, url) %}` — single JIRA/
GitHub pill, per the spec "whole element is the link." `kind` is one of
`jira_ticket`/`github_commit`/`github_pr` — use it to pick an icon/color/
label prefix (e.g. "JIRA" vs "PR" vs "Commit") in the pill's rendered
output. This is a macro, not a standalone template — it gets `{% import %}`ed
by `_message.html` (and possibly others).

### `app/templates/chat/_tool_status.html`

Transient status line fragment for `tool-status` SSE events (payload shape:
`ToolStatusEvent(message: str)`, e.g. "Checking Sarah's JIRA tickets…") —
per the spec, "replaced (not accumulated) once real prose starts, never
persisted." Simple: render `message` as a small, visually distinct
(muted/italic, e.g.) status line.

### `app/templates/chat/_cite_error.html`

Small inline error marker fragment for `cite-error` SSE events (payload
shape: `CiteErrorEvent(ordinal: int, detail: str = "Couldn't resolve a
citation the assistant made — this may be a bug.")`) — rendered in place of
a pill when a citation fails validation. Keep it visually distinct from a
normal pill (e.g. a small warning-styled inline marker) but not alarming —
per the spec this represents a backend bug, not a user-facing error state
to make a big deal of.

### `app/static/css/chat.css`

Bubble, pill, tool-status, and cite-error styling, vendored locally
alongside Pico (no CDN — this project never pulls CSS/JS from a CDN, see
`stack-and-infra.md`). Since Pico.css is classless (styles bare HTML
elements, not utility classes), your custom CSS should complement it, not
fight it — use semantic class names (`.chat-bubble`, `.chat-bubble--user`,
`.chat-bubble--assistant`, `.activity-pill`, `.activity-pill--jira`,
`.activity-pill--github`, `.tool-status`, `.cite-error`, or similar — your
judgement on exact naming, just be consistent). Needs to be linked from
`base.html`'s `<head>` — check whether to add a conditional/optional
stylesheet link there or handle it differently (e.g. only the eventual chat
page template links it) — note your choice and reasoning in your log entry,
since `base.html` is also used by the login page which doesn't need chat
styling.

**Important layout note from the spec**: "same visual language, now with
pills/errors appearing inline mid-text rather than in a trailing strip" —
pills render INLINE within the flowing text of a message, not as a separate
block/list underneath. Style accordingly (inline-block pill elements that
wrap naturally with surrounding text).

## What NOT to build

- No routes (`GET /conversations/{id}`, `POST /conversations`, `POST /
  conversations/{id}/chat`) — separate, later work. Don't create or modify
  `app/api/pages.py` or any new route file.
- No `ChatService`, no `CitationStreamParser`, no SSE-emitting backend code
  — separate, later work (Phase 5). You're building what CONSUMES that
  output (templates), not what produces it.
- No `app/schemas/chat.py` (the Pydantic schemas) — separate, later work.
  You need to know the SHAPES documented in the spec to build templates
  against, but don't create the actual Python file.
- Do NOT modify `app/templates/index.html` to actually become the chat
  page — that wiring is a routes-layer decision for later work. Build your
  new files under `app/templates/chat/` as their own thing.
- No JavaScript beyond what htmx/htmx-ext-sse already provides declaratively
  via `hx-*` attributes — this project's stack is explicitly "no JS
  bundler/build step," don't introduce custom `<script>` logic beyond
  trivial inline snippets if genuinely unavoidable (there's likely no need
  for any).

## Testing

You cannot manually browser-test this (no routes exist to serve these
templates yet — this is explicitly out of scope for this handoff, the real
Phase 6 gate in `timeline.md` calls for manual browser verification, which
will happen once someone builds the routes). Instead:

1. Confirm every template file is syntactically valid Jinja2 — the project
   has `djlint` configured (`pyproject.toml`'s `[tool.djlint]` section,
   `profile = "jinja"`) as a linter for exactly this. Run:
```
sg docker -c "docker compose up -d --build"
sg docker -c "docker compose exec fastapi djlint app/templates/chat/ --check"
```
   Fix any findings.
2. Write a minimal throwaway Python script (do NOT commit it, use it just
   to self-check, then delete it) that renders each template standalone
   with fabricated example context data matching the documented shapes
   (e.g. a fake `MessageOut`-shaped dict with 2 citations) via
   `app/templating.py`'s `templates` object, to confirm they render without
   raising a Jinja2 `UndefinedError` or similar — this is the closest thing
   to a real test available to you without live routes. Report in your log
   entry that you did this and what you found, but don't leave the
   throwaway script in the repo.
3. Run `sg docker -c "make test"` to confirm the full existing suite still
   passes (should be unaffected, since nothing existing imports these new
   template files yet).
4. Run ruff/mypy — should be unaffected since you're not adding Python
   code (unless you added a custom Jinja2 filter to `app/templating.py`,
   in which case lint/type-check that):
```
sg docker -c "docker compose exec fastapi ruff check ."
sg docker -c "docker compose exec fastapi mypy app/"
```

(If `docker.sock` permission errors happen, prefix commands with `sg docker
-c "..."` as shown.)

## When done

Report back: what you built, the exact context variable names/shapes each
template expects (this is critical — whoever builds the real routes next
needs this contract), which approach you took for citation-sentinel
resolution (Jinja2 filter vs. pre-resolved-in-Python) and why, whether
djlint/your throwaway render-check passed, and anything you had to guess or
assume given you couldn't see this rendering live.
