# Handoff: verify/finish Phase 3 (tools + pre-fetch), then build Phase 5 (ChatService)

Paste this whole file to a fresh Claude Code session opened at the repo root
(`/home/oz/Autonomized_Takehome`). It has no memory of any prior conversation
about this project — everything you need is below or in the referenced
files.

## Context

This is the Team Activity Monitor project — a FastAPI + htmx chat app where
an LLM answers "what is X working on" by combining JIRA/GitHub data via
tool-calling. Phases 1 (JIRA/GitHub OAuth), 2 (schema), 4 (OpenRouter
tool-calling), and most of 6 (chat UI templates, structure only) are done,
tested, committed, and deployed. Phase 3 (JIRA/GitHub tools + pre-fetch) has
been **drafted but is uncommitted and unverified** — that's your first job.
Phase 5 (`ChatService`, the actual agentic loop) is entirely unbuilt — your
second job.

**Read first, in this order:**
1. `CLAUDE.md` — binding invariants (routes own the DB transaction;
   services/repositories are plain functions, no `Depends()`, no FastAPI
   imports).
2. `implementation_log.md` — read the WHOLE file, it's long but every entry
   matters here; in particular the "Mid-Phase-1-prep" entry (why OAuth
   tokens persist per-user, not per-session — this affects how you resolve
   credentials for tool calls) and every "Phase 1"/"Phase 3" entry near the
   end (the most recent ones describe exactly what's built and unverified
   right now). **When you're done, append your own entries to this same
   file** (don't create a separate log) — one for finishing/verifying
   Phase 3, one for Phase 5. Follow the existing structure (`## <phase/
   topic>` headers, most recent at the bottom).
3. `blueprints/plans/features/chat.md` — read the WHOLE file. This is the
   authoritative spec for both Phase 3 (Tools, Pre-fetch sections) and
   Phase 5 (`ChatService`, Repositories, Routes sections) — you need the
   whole thing, not just your phase's section, since citation validation,
   the schema, and the routes all interconnect.
4. `blueprints/plans/features/openrouter-integration.md` — `llm_router.py`'s
   `query()`/`QueryEvent`/`ToolDefinition`/`ToolCall` shapes, already built
   and tested (Phase 4) — this is what `ChatService` drives.
5. `blueprints/plans/features/oauth-integration.md` — how tokens are
   resolved (Key Vault, keyed by `team_member_id`) — needed to understand
   how tool credentials get resolved.
6. `blueprints/plans/implementation-handoff.md`'s "Best practices" section —
   Pydantic for every data shape, 3-tier route/service/repository
   separation, comment the WHY, errors loud never silent, magic numbers in
   `config.py`, no unrequested abstractions, real integration tests against
   live APIs (no mocks — this project has zero mocking libraries, by
   design).
7. The actual current code, ALL of it, since this is a large surface:
   `app/services/tools/base.py`, `jira_tool.py`, `github_tool.py`,
   `app/services/pre_fetch.py`, `app/services/chat_errors.py`,
   `app/schemas/chat.py`, `app/repositories/activity_item_repo.py`
   (specifically the new `upsert` function), `app/services/llm_router.py`
   (Phase 4's tool-calling, already built), `app/api/auth.py` and
   `app/api/oauth.py` (the existing route patterns to mirror — CSRF
   handling, transaction ownership, `Depends(get_current_user)`),
   `app/repositories/conversation_repo.py`, `message_repo.py`,
   `activity_item_repo.py`, `message_citation_repo.py` (all exist, built in
   Phase 2 — review their exact function signatures before writing
   `ChatService`, don't assume), `app/templates/chat/*.html` +
   `app/templating.py`'s `resolve_citations` filter (Phase 6's structure —
   read this carefully, it documents the exact context-variable contract
   whoever builds routes needs to satisfy), `app/db/models/*.py` (all of
   them — `team_member.py` now has `jira_cloud_id` AND `jira_site_url`,
   both resolved together at OAuth connect time).

## Part 1: Finish and verify Phase 3 (do this first)

### Current state — uncommitted, unverified

`git status` will show these as modified/untracked:
- `app/services/tools/base.py` — `ActivityTool` ABC (`name`, `description`,
  `Params: type[BaseModel]`, a `definition` property building a
  `ToolDefinition`, abstract `execute()`).
- `app/services/tools/jira_tool.py` — `JiraTool`/`JiraToolParams`. Wraps
  `jira_client.find_account_id_by_email` + `get_issues_assigned_to`,
  includes a retry-once-after-silent-refresh-on-401 path calling
  `jira_client.refresh_access_token`. `execute()`'s `**credentials` kwarg
  contract (READ THE DOCSTRING): `team_member_id`, `access_token`,
  `refresh_token`, `cloud_id`, `site_url`, `jira_oauth_client_id`,
  `jira_oauth_client_secret` — all resolved by the CALLER, never
  self-fetched (per `chat.md`'s explicit rule).
- `app/services/tools/github_tool.py` — `GithubTool`/`GithubToolParams`.
  Wraps `github_client.get_recent_commits_by_author` +
  `get_pull_requests_by_author`. `execute()`'s `**credentials` contract:
  just `access_token`.
- `app/services/chat_errors.py` — `ToolExecutionError`, `UpstreamProviderError`.
- `app/schemas/chat.py` — currently only has `ActivityKind`/`ActivityItem`
  (Phase 3's minimum need). You'll add the rest for Phase 5 (see Part 2).
- `app/repositories/activity_item_repo.py` — gained a new `upsert()`
  function (the one both pre-fetch and tool-calling share, per spec).
- `app/services/pre_fetch.py` — **read this file's docstring very
  carefully, it documents a real unresolved design gap**: `pre_fetch.run()`
  requires an explicit `project_key: str` and `repo: str` argument from its
  caller, because `oauth-integration.md`'s "scope discovery" (auto-
  discovering a user's top JIRA projects/GitHub repos) was never built —
  nothing consumes it yet (the system prompt that would render discovered
  projects/repos is what YOU are about to build in Phase 5). You need to
  decide: (a) build real scope discovery now as part of Phase 5's system
  prompt work (the spec's actual intent — `JiraProjectRef`/`GithubRepoRef`/
  `GithubCollaboratorRef` in `chat.md`'s Schemas section, `oauth-
  integration.md`'s "Scope discovery, not fixed config" section has the
  full design), or (b) hardcode a reasonable single project/repo for this
  3-person demo team as a stopgap and flag it as a known shortcut. The spec
  clearly intends (a) — don't take (b) without a good reason, since
  hardcoding a single project/repo is exactly the pattern the whole OAuth
  rework was designed to move away from. This decision affects both
  `pre_fetch.run()`'s signature and what goes in the system prompt.

### What's NOT yet done in Phase 3

- **Zero live verification.** Neither `JiraTool.execute()` nor
  `GithubTool.execute()` has been run against a real API call. Ruff/mypy
  pass, the full existing test suite (40 passed, 3 skipped) still passes
  because nothing new is wired in yet — but that's static checking, not
  proof the tools work.
- No integration tests exist for the tools or pre-fetch at all.
- Scope discovery (see above) isn't built.

### What to do

1. Resolve the `project_key`/`repo` design gap in `pre_fetch.py` (see
   above) — this decision should be made once, consciously, not
   accidentally by whatever's fastest to type.
2. Write real integration tests, live against actual JIRA/GitHub data, no
   mocks (matching `tests/integrations/`'s existing pattern):
   - `GithubTool.execute()` — this one you CAN fully verify: the demo
     account's real fine-grained PAT is readable from `.env` directly
     (`Autonomized_Test_1_Github_PAT`, same pattern
     `tests/integrations/test_github_client.py`'s `_github_token()` already
     uses — read that function, copy the pattern). Real repo:
     `Autonomized1/Autonomized_Test_Project_1`. You'll need a real
     `conversations` row to satisfy the FK (`activity_items.conversation_id`)
     — create a throwaway `team_members` + `conversations` row in the test
     (or reuse the seeded John/Sarah/Mike rows plus a fresh `conversation_repo.create()`
     call), run `GithubTool().execute(session, conversation_id, GithubToolParams(...),
     access_token=<real PAT>)`, assert real `ActivityItem`s come back, assert
     they're actually persisted in `activity_items` via
     `activity_item_repo.get_by_natural_key`.
   - `JiraTool.execute()` — same real gap as `tests/integrations/
     test_jira_client.py`'s already-skipped tests: no real JIRA OAuth
     access_token/cloud_id exists yet (needs a human to complete Atlassian's
     consent screen once via `/oauth/jira/connect` — the route exists and
     works, verified by the user in a real browser earlier in this
     project's history, but the resulting token was purged rather than
     captured into env vars). Follow the EXACT same pattern
     `test_jira_client.py` uses: skip-marked tests reading
     `JIRA_TEST_ACCESS_TOKEN`/`JIRA_TEST_CLOUD_ID`/`JIRA_TEST_PROJECT_KEY`/
     `JIRA_TEST_ACCOUNT_EMAIL`/`JIRA_TEST_SITE_URL` (new: you also need
     `site_url` now, which the earlier skipped tests didn't need since they
     predate `jira_tool.py`'s citation-URL fix) from the environment, real
     reason string, self-unskip once those vars are set. If you want full
     live verification and are able to complete a real browser OAuth
     connect yourself in this session, do it and actually populate those
     vars — don't assume you can't just because a prior session couldn't.
   - `pre_fetch.run()` — test the caching behavior specifically (`chat.md`'s
     own stated Phase 3 gate): run it twice against the same
     `conversation_id`, assert the second run is a no-op (check
     `activity_items` row count doesn't change, or mock/spy that the tools'
     `execute()` isn't called a second time — whichever is cleaner given
     `pre_fetch.run()`'s actual structure).
3. Run `ruff check .`, `mypy app/`, `djlint app/templates/ --check`, full
   `pytest` suite (`sg docker -c "docker compose exec fastapi pytest"` — if
   `docker.sock` permission errors happen, prefix commands with `sg docker
   -c "..."`, this dev machine needs that workaround).
4. Update `blueprints/requirements/features.md` (MVP-FR-9/FR-10's Tested
   column can likely flip once there's real tool-level verification, not
   just client-level — check the exact current wording and CLAUDE.md's
   Tested definition before flipping anything), `blueprints/requirements/
   timeline.md` (Phase 3's row), `CHANGELOG.md`, and `implementation_log.md`
   (append, don't rewrite).
5. Only once Phase 3's own gate passes (tests green, ruff/mypy/djlint
   clean): commit (look at `git log` for this repo's commit-message style
   first) and push to `main`. Watch the triggered `deploy.yml` run
   (`gh run watch <run-id> --repo OttavioAP/Autonomized_Takehome
   --exit-status`) — if it fails, diagnose and fix before moving to Phase
   5, don't start new feature work on a known-broken deploy. **Known
   deploy quirk, already documented three times in this project's
   history**: the site sometimes reports `state=Running` via `az webapp
   show` while actually completely unresponsive for ~30s after a deploy's
   automatic restart — `deploy.yml` already does two restarts
   automatically; if it's still unresponsive after that, one more manual
   `az webapp restart --resource-group team-activity-monitor-a8b9a7 --name
   team-activity-monitor-a8b9a7` reliably fixes it (seen and confirmed this
   exact pattern already, see `implementation_log.md`'s and
   `blueprints/deployment.md`'s notes on this).

## Part 2: Build Phase 5 (`ChatService` + conversation routes)

This is the largest remaining phase — the actual agentic loop that ties
everything together. Full spec: `chat.md`'s `ChatService`, Errors, Prompts,
Repositories, Routes sections (all already read above, re-read them now
with implementation in mind).

### What to build

1. **`app/schemas/chat.py`** — extend the existing file (which currently
   only has `ActivityKind`/`ActivityItem`) with everything else `chat.md`'s
   Schemas section describes: `ActivityItemOut`, `MessageOut`,
   `ChatRequest`, the 5 SSE event Pydantic models
   (`ToolStatusEvent`/`TokenEvent`/`CiteEvent`/`CiteErrorEvent`/`ErrorEvent`),
   `SSEEnvelope`, and — per `oauth-integration.md`'s Scope discovery
   section — `JiraProjectRef`/`GithubRepoRef`/`GithubCollaboratorRef` if you
   decided to build real scope discovery in Part 1.
2. **`app/config.py`** — add `max_tool_call_rounds: int = 5` (chat.md is
   explicit this is this phase's field, not Phase 1's — `discovery_top_n`
   already exists from Phase 1, reuse it, don't re-add).
3. **`app/prompts/loader.py`** + `app/prompts/chat_system_prompt.md` +
   `app/prompts/tool_limit_reached.md` — plain text/markdown files, a small
   loader, not inline string literals. Read `chat.md`'s Prompts section for
   exactly what content each needs (team roster, pre-fetched context,
   citation-sentinel format instructions, tool descriptions).
4. **`app/services/chat_service.py`** — `CitationStreamParser` (stateful
   rolling-buffer regex scanner for `{{cite:ordinal:uuid}}`, handles
   matches split across delta boundaries) and `ChatService` (constructed
   with `session`/`conversation_id`, `run(query: str) ->
   AsyncIterator[SSEEnvelope]`). Follow `chat.md`'s numbered steps 1-6 in
   the `ChatService` section EXACTLY — this is the most detailed part of
   the whole spec, don't improvise around it. Pay special attention to: the
   tool-call round-trip loop bounded at `Settings.max_tool_call_rounds`,
   how `ToolCall.parsed_arguments()` validation errors get handled (MVP-
   NFR-4, never an unhandled exception), tool-role messages NEVER being
   persisted (this repo's `messages.role` DB enum is 3-valued —
   `user`/`assistant`/`system` — not 4, confirmed in `app/db/models/
   message.py`, don't add a 4th value), and citation ordinal handling — a
   past decision in this project (see `implementation_log.md`'s Phase -1
   entry) was **model-authoritative**: trust the model's own sequential
   ordinal numbering in the sentinel directly, don't have the route
   recompute/reassign ordinals.
5. **Routes in `app/api/pages.py`** (extend the existing file — `GET /`
   already exists and already has the `/oauth/connect` gate check wired in
   from Phase 1, don't remove that): `GET /conversations/{id}`,
   `POST /conversations`, `POST /conversations/{id}/chat` (SSE-streaming,
   `event: <name>\ndata: <json>\n\n` frames). All own their transaction per
   CLAUDE.md — `ChatService`/repositories never commit, only routes do.
   `GET /` needs updating too: `chat.md` says it should redirect to
   `GET /conversations/{id}` (the user's most recent conversation, creating
   one if they have none) rather than rendering `index.html` directly —
   this is a real behavior change from what Phase 1 built (Phase 1's `GET
   /` just rendered `index.html` after the oauth gate passed; now it should
   redirect into the real conversation view). Trigger pre-fetch from
   `GET /conversations/{id}` when `prefetched_at IS NULL`, using whatever
   `pre_fetch.run()` signature you settled on in Part 1.
6. **Wire the chat templates** (`app/templates/chat/_message.html` etc.,
   already built in Phase 6) into `GET /conversations/{id}`'s render and
   the SSE route's per-event fragment responses. Read
   `app/templating.py`'s `resolve_citations` filter docstring/Phase 6's
   `implementation_log.md` entry for the exact context-variable contract
   each fragment template expects — it's documented precisely, don't
   guess.

### Testing

- Unit tests for `CitationStreamParser` against synthetic delta sequences
  (no live API needed) — sentinel split across chunk boundaries, valid
  citation, invalid citation (bad uuid), multiple citations in one message.
- A full integration test: real `ChatService.run()` call against real
  OpenRouter + real JIRA/GitHub data (this needs Part 1's live JIRA
  verification to actually be meaningful — if you couldn't get a real JIRA
  token, at least verify the GitHub-only path end to end), asserting a
  real citation round-trips correctly (model cites a real `activity_items`
  UUID, route validates it, `message_citations` row gets the right
  ordinal).
- Manually exercise `POST /conversations/{id}/chat` with curl/httpx before
  considering this "working" — `chat.md`'s own Phase 5 gate description
  says this explicitly: "this is the core of the whole app and deserves
  more than automated coverage alone."

### Gate, same protocol as Part 1

Tests green, ruff/mypy/djlint clean, commit, push, watch `deploy.yml`,
fix forward if it fails, don't start Phase 6-finish/Phase 7 on a broken
deploy. Update trackers (`features.md`: MVP-FR-7/FR-11/FR-12 and
MVP-NFR-4's rows are the ones this phase actually completes — read their
exact current wording before editing), `CHANGELOG.md`,
`implementation_log.md`.

## What NOT to build in either part

- No Phase 6-finish work beyond what's needed to make `ChatService`'s
  output actually render (i.e., wiring the existing templates into your
  new routes IS in scope — but don't build NEW templates/CSS beyond what
  Phase 6 already produced, and don't touch `_activity_pill.html`'s macro
  vs. `resolve_citations`' duplicated-markup situation unless it's
  actually blocking you — that's a known, already-flagged small
  inconsistency, not yours to fix here).
- No Phase 7 (error/empty states) — `chat.md` is explicit this is
  deliberately last, after there's real model output to look at. Don't
  build the "no recent activity" / "member not found" prompt wording now.
- No README/docs (Phase 8).

## When done

Report back: what you built in each part, every real bug you found (this
project's convention is to document these thoroughly — see
`implementation_log.md` for the level of detail expected), what design
gaps you resolved and how (especially the `project_key`/`repo`/scope-
discovery decision), whether both phases' gates fully passed including a
real deploy, and anything you're unsure about or had to guess.
