# Handoff: Phase 7 (error/empty states), Phase 8 (README), test-data expansion, UI polish, small cleanups

Paste this whole file to a fresh Claude Code session opened at the repo root
(`/home/oz/Autonomized_Takehome`). It has no memory of any prior conversation
about this project — everything you need is below or in the referenced
files.

## Context

This is the Team Activity Monitor project — a FastAPI + htmx + Jinja2 chat app where
an LLM answers "what is X working on" by combining JIRA/GitHub data via tool-calling
(`ChatService`, `app/services/chat_service.py`). **The core product is done and
verified working in production**: real Azure AD login, real chat, real streaming
citations that deep-link correctly — confirmed by the user logging in live as John
(`Autonomized_Test_1`) on the deployed site and exercising it end to end. Phases 1-6
are complete. What's left is polish, error handling, richer demo data, and docs —
none of it changes the core architecture, all of it is real, scoped work.

**Read first, in this order:**
1. `CLAUDE.md` — binding invariants (routes own the DB transaction; services/
   repositories are plain functions, no `Depends()`, no FastAPI imports).
2. `implementation_log.md` — read the WHOLE file, it's long but every entry matters.
   Pay special attention to the last ~4 entries (Phase 3/5 completion, and two real
   production incidents found and fixed via live testing after the "green" deploy —
   a seed-data bug and a Managed Identity credential-resolution bug). **When you're
   done, append your own entries to this same file** — one per work item below, not
   one giant entry. Follow the existing structure (`## <phase/topic>` headers, most
   recent at the bottom).
3. `blueprints/plans/features/chat.md` — the authoritative spec. Its Errors section is
   what Phase 7 (below) implements. Its Prompts section has the exact citation-sentinel
   format `chat_system_prompt.md` already implements — don't change the citation
   mechanism, it works and is regression-tested (`tests/test_citation_parser.py`).
4. `blueprints/requirements/timeline.md` — Phases 6/7/8's exact descriptions and gates
   (search for `### Phase 6`, `### Phase 7`, `### Phase 8`). Phase 6's gate (real
   browser verification) is now satisfied — update its progress note to say so, citing
   this handoff, before starting new work.
5. `blueprints/requirements/features.md` — current status of every tracked feature.
   Check this before touching any MVP-FR-*/MVP-NFR-* row so you don't regress a
   status that's already accurate.
6. The actual current code for whatever item you're working on — this file points you
   at the right places per item below, don't assume signatures, read them.

## Working agreement (same as every prior phase in this project)

- Real, live verification wherever possible — this project has zero mocking
  libraries by design. `tests/integrations/` and the top-level `tests/test_*.py`
  files are full of live-API/live-DB integration tests; match that pattern.
- Update `blueprints/requirements/features.md`/`timeline.md`, `CHANGELOG.md`, and
  `implementation_log.md` at the end of each work item, not just at the very end of
  the session — per `CLAUDE.md`'s own working agreement.
- Run `ruff check .`, `mypy app/`, `djlint app/templates/ --check`, and the full
  `pytest` suite before considering any item done (`sg docker -c "docker compose exec
  fastapi <command>"` — this dev machine needs the `sg docker` prefix for Docker
  socket permissions).
- Commit, push, watch `deploy.yml` (`gh run watch <run-id> --repo
  OttavioAP/Autonomized_Takehome --exit-status`), and **verify the live site
  actually works after deploying**, not just that CI is green — this project has now
  hit two real production-only bugs (documented in `implementation_log.md`'s last two
  entries) that every automated test and a green CI run both missed, because they
  were infrastructure/credential-resolution issues (empty prod DB, a Managed Identity
  client-id collision) invisible to local dev and CI alike. A green pipeline does not
  mean the live site works — load it and check.
- **Known deploy quirk**: the site sometimes reports "running" via `az webapp show`
  while actually unresponsive for ~20-40s after a deploy's automatic restart
  (`deployment.md`'s own notes, hit repeatedly across this project's history). Poll
  with a bounded retry loop before concluding something's broken.
- `az` CLI is available *inside* the running `fastapi` container
  (`sg docker -c "docker compose exec fastapi az ..."`), already authenticated — not
  on the host shell. Useful for `az webapp log download` (works reliably; `az webapp
  log tail` has hung in this environment — prefer download + unzip via Python's
  `zipfile` module, since the container has no `unzip` binary) if you need to debug a
  live production issue.

## Work items

None of these are prescribed as "implement this exact thing" — scope each one
sensibly, but do the actual work (this is not a planning-only handoff).

### 1. Phase 7 — Error/empty states (`chat.md`'s Errors section, MVP-FR-6)

The single biggest scoped item. Three distinct, legible states, currently unhandled
or only handled as incidental model prose:
- **Member not found**: a query naming someone not on the roster and not in
  discovered JIRA people/GitHub collaborators. Currently the model just says so in
  prose (per `chat.md`'s explicit design — no regex/NLP name-parsing) — decide
  whether that's sufficient or whether a distinct UI treatment is warranted (e.g. a
  visually distinct system message vs. a normal assistant bubble).
  `chat_system_prompt.md`'s "Answering" section already tells the model to say when
  it doesn't recognize a name; the current gap is UI treatment, not model behavior.
- **No recent activity**: `chat.md` flags this explicitly as a known, deliberately
  deferred gap — "nothing tells the model to distinguish 'I found nothing' from 'I
  didn't check'" (`app/prompts/chat_system_prompt.md`'s current content doesn't
  address this either). Now that there's real model output to look at (there wasn't
  when that note was written), design the actual prompt wording and/or UI treatment.
- **Upstream failure**: `ToolExecutionError`/`UpstreamProviderError`
  (`app/services/chat_errors.py`) already exist and are wired into `ChatService` —
  the `error` SSE event (`app/schemas/chat.py`'s `ErrorEvent`) already renders via
  `chat.html`'s JS (search for `eventName === "error"`). Verify this actually reads
  well in the UI (currently a bare `<p class="chat-error">`, no dedicated CSS class
  styling in `chat.css` yet) and test it with a real forced failure (e.g. an invalid
  Key Vault secret, a malformed tool-call argument).

Gate per `timeline.md`: test each state deliberately (a query for a nonexistent name,
a query for a real user with genuinely no activity, a forced upstream failure) — both
automated (assert the right SSE event fires) and manual (confirm the UI actually
reads as intended).

### 2. Phase 8 — README (MVP-NFR-10)

Genuinely nothing exists yet. Setup instructions (`make up-dev`, `.env` from
`.env.example`, `make seed`) and JIRA/GitHub/OAuth API usage. Gate per `timeline.md`:
a fresh clone + README-only setup actually working, no undocumented local state
assumed. Also confirm `.env.example` still matches every `Settings` field in
`app/config.py` (several fields were added since `.env.example` was last touched —
`activity_lookback_days`, `max_tool_call_rounds`, `discovery_top_n` all have code
defaults so they're optional, but worth a quick diff check).

### 3. Expand JIRA/GitHub test data for John/Sarah/Mike

Real gap: each seeded user currently has only 1-3 total activity items
(`utils/jira_seed_data.py`, `utils/github_seed_data.py` — read both before adding
more, they're the existing seed pattern, real API calls against
`autonomizedtest1.atlassian.net`/`Autonomized1/Autonomized_Test_Project_1`, not
fixtures). Thin data makes demo answers boring and doesn't exercise the richer
scope-discovery/comments/PR-review/enrichment work built in the Phase 3 session
documented near the end of `implementation_log.md` — right now there's only one
seeded comment-worthy interaction (if any), so `JIRA_COMMENT`/`GITHUB_COMMENT` pills
have barely been exercised against real varied data. Add more issues/commits/PRs/
comments across all three users, varied status/priority/review-state, so a demo
question like "what's Sarah working on" has substantive real material to answer
from. Real API calls, same demo accounts (`test_user_accounts.txt` has the
Protonmail/JIRA/GitHub credentials; `.env`'s `#for claude code: not env vars` section
has the actual API tokens/PATs already — read the full `.env` file, not just
`.env.example`).

### 5. Concurrent JIRA/GitHub fetching (NMVP-NFR-8)

Non-MVP, cheap, real latency win. `ChatService`'s tool-call loop
(`app/services/chat_service.py`, `_execute_tool_call` and the round loop in `run()`)
currently awaits each tool call sequentially even when multiple tool calls arrive in
the same `ToolCallDelta` (`event.calls`, a list — the model can request more than one
call per round). `pre_fetch.py`'s JIRA and GitHub legs are also sequential
(`await JiraTool().execute(...)` then separately `await GithubTool().execute(...)`).
Both are real `asyncio.gather` candidates — check for any shared-session-mutation
hazard first (both legs write to `activity_items` via the same `AsyncSession`; confirm
SQLAlchemy's async session isn't safe for concurrent use from two coroutines sharing
one session before parallelizing anything that touches `session.execute()`
concurrently — if it isn't, this may need two separate sessions/connections, not just
`asyncio.gather` on the existing calls).

### 6. Fix the `_activity_pill.html` / `resolve_citations` markup duplication

Flagged twice now as a known, deliberately-unfixed small inconsistency (once in an
earlier handoff, once in this project's own notes) — never actually consolidated.
`app/templates/chat/_activity_pill.html`'s Jinja macro and `app/templating.py`'s
`resolve_citations()` Python filter both independently know how to render a pill
(kind → CSS class + prefix mapping, `<a class="activity-pill...">` markup) — two
copies of the same rendering logic, already caught drifting once (the Phase 3 session
had to update both when adding `JIRA_COMMENT`/`GITHUB_COMMENT`). Consolidate to one
source of truth — likely making `_activity_pill.html`'s macro the single
implementation and having `resolve_citations()` render via Jinja's macro-import
mechanism (or vice versa, whichever fits this codebase's existing Jinja/Python split
better) — without changing the rendered output (there's a real risk of a subtle CSS
class/prefix regression here; diff rendered HTML before/after for all 5 `ActivityKind`
values, not just eyeball the code).

### 7. UI improvements (open-ended, use judgment)

The chat page (`app/templates/chat.html`) works but was built functionally, not with
a design pass — no animation on new messages, minimal loading/streaming affordance
beyond the tool-status line, no distinct visual treatment for the new Phase 7 error
states once you build them, conversation switcher is a bare `<details>` dropdown. This
is genuinely open-ended (NMVP-FR-7 territory) — use judgment on what's worth doing in
the time available. Don't touch `chat.css`'s existing bubble/pill/tool-status rules
without checking `_message.html`/`_activity_pill.html`/`chat.html`'s JS `pill()`
function all still agree on class names afterward (same drift risk as item 6 above).

## What NOT to do

- Don't touch the citation-sentinel mechanism (`CitationStreamParser` in
  `app/services/chat_service.py`) unless you find a real bug — it went through a
  serious live-testing bug hunt already (see `implementation_log.md`'s Phase 5 entry:
  a real stream-splitting bug that silently dropped citations, only caught via live
  testing, fixed and regression-tested). If you think you see an issue, read that
  entire log entry first before changing anything there.
- Don't re-litigate the scope-discovery/comments/enrichment design from the Phase 3
  session — it's built, live-verified, and documented in `chat.md`/`oauth-integration.md`.
- Don't build NMVP-tier features not listed above (RBAC, multi-tenancy, RAG history,
  caching) — out of scope for this handoff.

## When done

Report back per item: what you built, any real bugs found (this project's convention
is thorough documentation of these — see `implementation_log.md` for the expected
level of detail), what you verified live vs. couldn't, and anything you're unsure
about or had to guess.
