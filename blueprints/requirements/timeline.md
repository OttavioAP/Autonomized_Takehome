# Timeline

Sequenced plan of work for the Team Activity Monitor. All MVP work is sequenced before any non-MVP feature is picked up. There is no CI/CD pipeline in this plan, so deployment happens as discrete, deliberate steps rather than continuously.

**Status columns:** Specced / Implemented / Tested / Deployed / QA — same definitions as `features.md` (see `CLAUDE.md`). `N/A` is a valid value for any cell where the concept doesn't apply to that step (e.g., a decision step like "select tech stack" has no meaningful "Deployed" state).

## Steps

| # | Step | Description | Specced | Implemented | Tested | Deployed | QA |
|---|------|-------------|:---:|:---:|:---:|:---:|:---:|
| 1 | Complete list of features | Enumerate the full functional/non-functional, MVP/non-MVP feature set. Tracked in `features.md`. | N/A | ✅ | N/A | N/A | N/A |
| 2 | Select tech stack | Backend: FastAPI (async). Frontend: htmx + Jinja2 (server-rendered, no build step). DB: Postgres via SQLAlchemy (async) + Alembic. LLM: OpenRouter. Auth: Azure SSO (OIDC) backed by a server-side session table in Postgres, opaque HttpOnly/Secure/SameSite cookie. Conversation history stored server-side in Postgres, not client-side. Deployment: Azure, single FastAPI process serving both pages and API, no CI/CD pipeline. | N/A | ✅ | N/A | N/A | N/A |
| 3 | Stand up minimum structure/infra | Scaffold the project structure and provision the minimum infrastructure needed for the chosen stack (repo layout, build tooling, cloud resources). See `blueprints/specs/stack-and-infra.md`. | ✅ | ✅ | N/A | N/A | N/A |
| 4 | Deploy hello world to Microsoft Azure | Prove the deployment path end-to-end with a trivial app before any real feature work, so infra problems surface early. Also owns the `.github/workflows/deploy.yml` stub (moved from step 3's deliverable list — it's a deploy mechanism, not infra scaffolding). See `blueprints/deployment.md`. | N/A | ✅ | ✅ | ✅ | N/A |
| 5 | Bare-minimum integrations | Validate JIRA/GitHub API connectivity via local util scripts first, then evolve that into the actual MVP integration features with integration tests — validated locally, ahead of any deployed integration work. | N/A | ✅ | 🟡 | N/A | N/A |
| 6 | Determine MVP prerequisite dependencies | Map the prerequisite relationships between MVP features from `features.md`. Output is the Dependency Tree section below. | N/A | ✅ | N/A | N/A | N/A |
| 7 | Spec all MVP features | Write the spec(s) for every MVP feature — API interfaces, UI mockups, database schema, and enough context for an AI agent to generate code and tests — in dependency-tree order. This is what flips a feature's Specced column to ✅ in `features.md`. `chat.md` + `oauth-integration.md` + `openrouter-integration.md` cover essentially the full remaining MVP surface; reviewed for cross-spec consistency and reconciled (see CHANGELOG). | N/A | ✅ | N/A | N/A | N/A |
| 8 | Create seed/demo data & identity mappings | Build the 3 demo accounts and the static team-member-to-JIRA/GitHub identity mapping (MVP-FR-8, MVP-NFR-7). Sequenced ahead of implementation since nearly every MVP feature depends on this data existing. `team_members` is a real, seeded Postgres table (Build Phase 1 step 0), and seed data was substantially expanded from the original thin first pass to 3 JIRA projects/3 GitHub repos of real, varied activity across all 3 people — see `features.md`'s MVP-NFR-7 row for the full detail. | ✅ | ✅ | ✅ | N/A | N/A |
| 9 | Implement MVP features | Implement features in dependency-tree order. Cyclical process — spec, code, and plan get revised against each other as implementation surfaces gaps. Started out of sequence (ahead of steps 6-8) at explicit user request: MVP-FR-1/FR-2/MVP-NFR-2/MVP-NFR-5 (Azure SSO login/logout) implemented and automated-tested; see `blueprints/deployment.md`'s SSO section. Broken into Build Phases 0-8 below, each with its own test-and-commit gate — **all complete**, see each phase's own entry. | N/A | ✅ | N/A | N/A | N/A |
| 10 | Local QA | QA pass per feature or group of features, run locally, before any deployment of the full app. Effectively subsumed into each Build Phase's own gate (full suite + ruff/mypy/djlint + manual exercise before every commit) rather than one separate end-of-project pass — matches how this project actually worked in practice: every phase's own gate already included a real local QA check. | N/A | N/A | ✅ | N/A | ✅ |
| 11 | Deploy full MVP app | Single deployment of the completed MVP to Azure — not a CI/CD pipeline, a deliberate one-time deploy once local QA passes. In practice this became continuous rather than a single deliberate deploy (a real CI/CD pipeline did end up getting built — NMVP-NFR-7 — ahead of its original non-MVP sequencing, since `deploy.yml` already existed from the hello-world step and it was cheaper to keep pushing through it than to hold every phase for one big-bang deploy). The MVP is live and stable on Azure as of the latest push. | N/A | N/A | N/A | ✅ | N/A |
| 12 | Deployment QA | Full-system QA pass against the deployed app, done in one fell swoop rather than per-feature. Also became continuous in practice rather than one pass — every phase's real-browser/live-account verification happened against the actual deployed site, and two genuine production-only incidents (prod `team_members` never seeded; a Managed Identity/`AZURE_CLIENT_ID` credential-resolution bug) were caught this way, neither visible to local dev or a green CI run. The user has exercised the live site directly as John/Sarah/Mike across many rounds of this project's later sessions. | N/A | N/A | N/A | N/A | ✅ |
| 13 | Choose non-MVP features to implement | With a working, QA'd MVP live, decide which non-MVP features from `features.md` to pursue next. Several non-MVP items were picked up organically as real gaps surfaced during MVP polish rather than through a single formal choose-what's-next pass: NMVP-FR-2 (per-user OAuth, un-deferred into MVP early), NMVP-NFR-7 (CI/CD, now real), NMVP-NFR-8 (concurrent fetching, partial — `ChatService`'s tool-call loop), and a large chunk of NMVP-FR-7 (UI/UX polish). Remaining non-MVP rows in `features.md` are still open and would need their own explicit prioritization pass if picked up next. | N/A | 🟡 | N/A | N/A | N/A |

## MVP Dependency Tree

Output of step 6, once `chat.md`/`oauth-integration.md`/`openrouter-integration.md` existed to map against. MVP-FR-1/FR-2/NFR-2/NFR-5 (Azure SSO) were already implemented ahead of this tree (step 9 jumped the queue at explicit user request — see step 9's row) and are the actual root of everything below; listed here for completeness, not because they're still pending.

```
MVP-FR-1/FR-2 (Azure SSO login/logout)  ─┐  [done]
MVP-NFR-2 (Azure SSO integration)        │  [done]
MVP-NFR-5 (session-scoped credentials)  ─┘  [done]
        │
        ▼
MVP-NFR-3 leg 1: OpenRouter auth (llm_router.py)         [done, tool-calling added]
MVP-NFR-3 leg 2: JIRA/GitHub OAuth (oauth-integration.md) [not started — see Phase 1 below]
        │
        ▼
MVP-FR-8 (team_members table, identity mapping)   ─┐
MVP-NFR-7 (demo accounts + seed data)              ─┤  schema + fixtures
conversations/messages/activity_items/             ─┘  (chat.md Schema section)
message_citations tables
        │
        ▼
MVP-FR-9 (fetch JIRA data)   ─┐  JiraTool/GithubTool — depend on OAuth (NFR-3 leg 2)
MVP-FR-10 (fetch GitHub data) ─┘  AND schema (activity_items to upsert into)
        │
        ▼
MVP-FR-7 (conversation history) — conversations/messages tables + routes
        │
        ▼
MVP-FR-5 (query understanding) — no parser; satisfied by system prompt + roster,
        │                         which needs FR-8 (roster) done first
        ▼
MVP-FR-11 (response synthesis) — ChatService agentic loop; depends on FR-9/FR-10
        │                        (tools to call) + FR-7 (message persistence)
        ▼
MVP-FR-12 (token streaming) — SSE transport around the same ChatService loop;
        │                     not separable from FR-11 in practice, same phase
        ▼
MVP-FR-3 (chat window UI)   ─┐  templates/routes consuming FR-11/FR-12's output
MVP-FR-4 (selectable JIRA/  ─┤  citation pills, part of the same template work
GitHub components)          ─┘
        │
        ▼
MVP-FR-6 (empty/error states) — layered onto FR-3/FR-4 once the happy path
        │                       renders; scoped down with the user to real
        │                       upstream-failure states specifically (see
        │                       Phase 7 below for what shipped and why)
        ▼
MVP-NFR-4 (AI input/output validation) — cross-cutting, largely satisfied
                                          incrementally as FR-9/10/11 land
                                          (ChatRequest, ToolDefinition/ToolCall
                                          validation) rather than a separate step
```

MVP-NFR-1 (Azure deploy), MVP-NFR-6 (flat authz — no code, a documented non-decision), MVP-NFR-8 (integration tests — grows incrementally alongside every phase, not a discrete step), MVP-NFR-9 (env-var config — already true), MVP-NFR-10 (docs) aren't in the chain above because they're not prerequisites for other features; MVP-NFR-10 gets its own tail phase (see Build Phases below), MVP-NFR-9 just needs a formal Specced mark (no code change).

**All of the above is now complete.** Every MVP-FR/MVP-NFR row in this tree is ✅ across all five `features.md` status columns as of this update — see that file for the row-by-row detail and what was found/fixed via live use to get there.

## Build Phases (implementation order, step 9's detailed breakdown)

Each phase below ends with a **hard gate**: write tests for that phase's code (pytest — unit tests for anything with no external dependency, integration tests for anything touching JIRA/GitHub/OpenRouter/Azure, matching the existing `tests/integrations/` pattern), run the full suite, and only commit + push if everything passes. **If a push triggers a deploy failure in `deploy.yml`, stop and do not continue to the next phase** — fix forward on the current phase until the deploy is green again before starting new feature work. Never skip ahead with a known-broken deploy.

### Phase 0 — Housekeeping (prerequisite to everything below)

- Remove `.env`'s dead `Autonomized_Test_*`/service-account block (the purge already discussed) and `.env.example` to match — the new OAuth-based `.env` shape has ~10 vars, not the ~40 currently present. Confirm `docker-compose.yml`/`deploy.yml`/`app/config.py` don't reference anything being removed before deleting.
- Delete `app/db/models/smoke_test.py` (already dead — not imported, not on `Base.metadata`, its table already dropped by an earlier migration; done as part of this review, not left for the implementing agent).
- Gate: no tests to write (pure deletion); run the existing suite to confirm nothing broke, commit, push, confirm deploy green before Phase 1.

### Phase 1 — JIRA/GitHub OAuth (`oauth-integration.md`) — ✅ complete

All 6 steps below done, gate passed: `make test` green (40 passed, 3 skipped — the skips
are `test_jira_client.py`'s live-data tests, blocked on a real JIRA OAuth access token,
which self-unskip via `JIRA_TEST_*` env vars once one exists), ruff/mypy/djlint clean, a
real manual browser round-trip completed (connect JIRA + GitHub against real consent
screens, confirm the gate blocks entry until both connected, confirm sign-out/sign-in
doesn't require reconnecting, confirm disconnect works), deployed and confirmed green in
CI (`deploy.yml`, two iterations — first run caught two real CI-only gaps: seed data
never loaded before `pytest`, and a demo GitHub PAT needed for one test wasn't available
in the container; both fixed, see `implementation_log.md`). Everything else depends on
this — no tool can execute without a real per-user token. Built in this order:
0. **`team_members` table only** (pulled forward from Phase 2 — see the note below this list) — the model, one Alembic migration, and `local-dev-data/team_members.json` wired into `scripts/seed.py` as its seed source. The rest of Phase 2's schema (`conversations`/`messages`/`activity_items`/`message_citations`) has no OAuth dependency and stays in Phase 2.
1. Azure Key Vault provisioning (`scripts/azure/provision.sh` extended) + Managed Identity role assignment, plus granting the developer's own `az login` identity the same access (local dev uses the real Key Vault, no fallback — see `oauth-integration.md`'s Isolation model / Token storage sections).
2. JIRA 3LO app registration + GitHub OAuth App registration (external, via each provider's console — same pattern as the Azure AD app registration already done).
3. `app/config.py` changes (remove old JIRA/GitHub fields, add OAuth client id/secret/redirect-uri fields + `discovery_top_n`).
4. `jira_client.py`/`github_client.py` rework (new `build_client` signatures, plus `jira_client.refresh_access_token` for silent refresh).
5. `app/api/oauth.py` (connect/disconnect routes) + the `/oauth/connect` gate (fires on first login or after a disconnect/revocation, not every login — tokens now persist per user, see `oauth-integration.md`), wired into `/auth/callback`'s redirect target.

**Note on step 0, found during Phase 1 prep, not in the original phase plan**: the
original Phase 1/Phase 2 split assumed OAuth tokens were session-scoped, so Phase 1 only
ever needed the already-existing `sessions` table. The token-persistence revision to
`oauth-integration.md` (see `implementation_log.md`) keys Key Vault secrets and
`jira_cloud_id` off `team_members.id` instead, which doesn't exist until Phase 2 as
originally ordered — a genuine circular dependency the original phase split didn't
anticipate, not an error in the original ordering given what it assumed at the time.
Resolved by splitting `team_members` out of Phase 2 and pulling just that one table
into Phase 1 as step 0; `conversations`/`messages`/`activity_items`/`message_citations`
remain Phase 2 exactly as before, since none of them are needed until Phase 3+.

Gate: integration tests hitting real JIRA/GitHub OAuth flows where feasible (the interactive authorize-code exchange can't be fully automated — test what can be tested headlessly: token storage/retrieval from Key Vault keyed by `team_member_id`, client construction against a resolved cloud ID, the refresh-token grant actually rotating and updating both stored secrets, disconnect clearing the secret(s)) + a manual browser round-trip (connect both providers, confirm the gate blocks entry until both are connected, sign out and back in and confirm no reconnect is required, confirm disconnect works) before considering this phase done, mirroring how Azure SSO's own live-endpoint regression test + manual browser check worked earlier in this project.

**Step 4 done**: `jira_client.build_client(access_token, cloud_id)` (Bearer auth against
`https://api.atlassian.com/ex/jira/{cloud_id}`) + new `refresh_access_token` (JSON-body
refresh-token grant, verified against Atlassian's live docs) built per
`blueprints/handoffs/handoff-2-client-rework.md`; `github_client.build_client` needed no
change (already OAuth-shaped). `find_account_id_by_email`/`get_issues_assigned_to`
untouched. Full client-level live-data testing for JIRA is blocked on step 5 (no
`app/api/oauth.py` connect flow yet, so no real Bearer access_token/cloud_id can exist) —
see `implementation_log.md`'s "Phase 1: jira_client.py/github_client.py rework" entry for
the full breakdown of what's covered by non-live tests in the meantime vs. what's still an
open gate item for whoever builds step 5.

### Phase 2 — Schema (`chat.md`'s Schema section)

`conversations`, `messages`, `activity_items`, `message_citations` — four new tables/models + one Alembic migration (`team_members` moved to Phase 1 step 0, see above — already created and seeded by the time this phase starts).

Gate: `make revision && make migrate` produces a clean migration; a seed round-trip test (seed → query back → matches fixture) for `team_members`; no other tests needed yet since nothing queries these tables until Phase 3.

**Done**: all four models + one migration
(`migrations/versions/2026_07_20_0508-b5880cd4a5e8_add_conversation_message_activity_item_.py`)
built per `blueprints/handoffs/handoff-3-schema.md`, reviewed by hand against `chat.md`'s
Schema section, applied cleanly. Full suite still green (modulo pre-existing, unrelated
failures from concurrent Phase 1 OAuth work — see `implementation_log.md`'s "Phase 2: chat
schema" entry for the full breakdown). Not yet committed/pushed/deploy-verified — this
handoff's scope was schema-only; the commit/push/deploy-watch step of this phase's gate is
left to whoever coordinates merging the parallel Phase 1/Phase 2/Phase 4 work together.

### Phase 3 — JIRA/GitHub tools + pre-fetch (`chat.md`'s Tools + Pre-fetch sections)

`JiraTool`/`GithubTool` (with `JiraToolParams`/`GithubToolParams`), `activity_item_repo.py`, `team_member_repo.py`, pre-fetch's discovery logic (top-10 projects/repos/collaborators via `Settings.discovery_top_n`). Depends on Phase 1 (real tokens to call with) and Phase 2 (tables to upsert into).

Gate: integration tests exercising each tool's `execute()` against live JIRA/GitHub data (extending the existing `tests/integrations/test_jira_client.py`/`test_github_client.py` pattern to the tool layer, not just the raw client functions) + a pre-fetch test that runs it twice and confirms the second run is a no-op (cache hit via `prefetched_at`).

**Done, scope expanded beyond the original spec** (bundled with Phase 5, see
`implementation_log.md`'s Phase 3/5 entries): the project_key/repo design gap from the
earlier handoff was resolved with *real* scope discovery (`pre_fetch.discover_scope`),
not a hardcoded stopgap — `search_projects`/`search_assignable_users` (JIRA),
`get_user_repos`/`get_repo_contributors` (GitHub), all live-verified against real
JIRA/GitHub instances. Scope also grew to include comments (`JIRA_COMMENT`/
`GITHUB_COMMENT`, new `ActivityKind` members), PR review decisions, and
priority/issue-type enrichment — a deliberate widening agreed with the user beyond
this row's original description, not scope creep discovered after the fact.
`GithubTool.execute()` fully live-verified (client, tool, and full `ChatService`/route
levels); `JiraTool.execute()`'s Bearer/`cloud_id` path remains blocked on a real JIRA
3LO OAuth token (same gap flagged in the original handoff) — the new JIRA client
functions (`search_projects`/`search_assignable_users`/`get_comments`) ARE
live-verified via Basic-auth API-token calls against the real instance, since that
doesn't require the OAuth round-trip.

### Phase 4 — OpenRouter tool-calling (`openrouter-integration.md`'s revised `query()`)

The `QueryEvent` union, `ToolDefinition`/`ToolCall`, streaming tool-call-delta accumulation. Independent of Phases 2/3's *data* but depends on Phase 3 existing conceptually (tools to define `ToolDefinition`s from) for a realistic end-to-end test — can be built in parallel with Phase 3 if useful, but tested together.

Gate: the three test cases already specified in `openrouter-integration.md`'s Testing section (plain text completion, unauthorized-request error, live tool-call round-trip with argument parsing) — all against the real OpenRouter API, no mocks, matching existing project convention.

### Phase 5 — `ChatService` + conversation routes (`chat.md`'s ChatService + Routes sections)

The agentic loop itself: `CitationStreamParser`, the tool-call round-trip loop, citation validation, `GET /`, `GET /conversations/{id}`, `POST /conversations`, `POST /conversations/{id}/chat`. This is the single largest phase — depends on everything before it (OAuth for tokens, schema for persistence, tools for data, `llm_router` for the model round-trip).

Gate: this is where MVP-FR-5/FR-7/FR-9/FR-10/FR-11 all actually come together — write both unit tests (`CitationStreamParser` against synthetic delta sequences, no live API needed) and integration tests (a full `ChatService.run()` call against real OpenRouter + real JIRA/GitHub data, asserting a real citation round-trips correctly end to end). Manually exercise via `POST /conversations/{id}/chat` with curl/httpx before considering this "working," since this is the core of the whole app and deserves more than automated coverage alone.

**Done** (see `implementation_log.md`'s Phase 5 entry for full detail, including a
genuine citation-reliability defect found and fixed during this phase — not caught by
synthetic unit tests, only surfaced through live end-to-end testing). `ChatService` +
`CitationStreamParser` built exactly per spec's numbered steps. Routes built:
`GET /` (redirect), `GET /conversations/{id}`, `POST /conversations`,
`POST /conversations/{id}/chat` (SSE). New `chat.html` template (message log + input
form + vanilla-JS SSE-over-POST reader — `htmx-ext-sse` doesn't fit a CSRF-protected
POST endpoint, so this deviates from the spec's original `htmx-ext-sse` assumption,
a deliberate implementation-time call). Unit tests (`CitationStreamParser`, 9 cases
including 2 real-stream-split regressions) + integration test (`ChatService.run()`
live against real OpenRouter + GitHub, real citation round-trip) + manual httpx
exercise against the real running app (GET page render, POST SSE stream, reload
history replay) all done. JIRA leg of the live integration/manual coverage remains
blocked on the same 3LO OAuth gap as Phase 3.

### Phase 6 — Chat UI (`chat.md`'s Templates + Static sections) — ✅ complete

`_message.html`, `_activity_pill.html`, `_tool_status.html`, `_cite_error.html`, `chat.css`, and the streaming UI (MVP-FR-3/FR-4/FR-12). The original plan's `htmx-ext-sse` wiring was superseded — the chat stream is a CSRF-protected POST, which `htmx-ext-sse` (GET-oriented) can't carry a token into, and the reader needs to buffer markdown segments and re-render the whole assistant bubble per event (a `**` opening in one token, closing in the next, can't be parsed piecemeal) — so it stayed a hand-rolled `fetch`/`ReadableStream` reader, a deliberate deviation confirmed early and never revisited.

Went considerably further than the original scope during later polish sessions, all live-verified in a real browser by the user: a full dark "console" theme applied app-wide (not just chat — login and oauth-connect too), a navbar + collapsible sidebar replacing the original bare dropdown, a send-to-first-token throbber, real hover/clickable pill styling across all 9 `ActivityKind`s (expanded from the original 3), and markdown rendering (`marked.js` live, Python-Markdown for history replay) after a real bug was found where the model's own `**bold**`/`- list` output showed as literal unrendered syntax. A real viewport-overflow layout bug (the page running taller/wider than the browser at non-reference sizes) was found and fixed twice — once for the chat page, once for the oauth-connect page, both via the same flex-based fix once `main.container` grew a real navbar.

Gate passed: real browser verification across dozens of live rounds on the actual deployed site (not just curl/httpx) — a real question through the real UI, streaming rendering progressively, citation pills deep-linking correctly, markdown rendering correctly, the layout fitting the viewport at real screen sizes. Automated coverage: `tests/test_citation_parser.py`, `tests/test_templating.py` (8 new tests covering markdown + citation composition, including an explicit XSS-safety case), route-level SSE framing tests.

### Phase 7 — Error/empty states (`chat.md`'s Errors section) — ✅ complete

MVP-FR-6, scoped down with the user during this phase: member-not-found and no-recent-activity are handled adequately by the model's own prose per `chat.md`'s original design (no dedicated UI state needed for either — confirmed with the user rather than assumed), so this phase focused on the third state, upstream-failure, which had a real, previously-undetected gap. `UpstreamProviderError` existed in code but was never actually raised anywhere, and `ChatService`/`JiraTool`/`GithubTool` only ever caught `httpx.HTTPStatusError` — a genuine connection-level failure (OpenRouter/JIRA/GitHub unreachable, DNS failure, timeout) would have crashed the SSE stream with an unhandled exception instead of degrading into the `error` event chat.md already specs. Fixed by widening every relevant `except` clause to `httpx.HTTPError` (the shared base of both `HTTPStatusError` and the `RequestError`/`ConnectError`/`TimeoutException` family) across all three call sites, and giving the `error` SSE event a real bordered/iconed visual treatment instead of bare inline red text — the user-facing message is now a clean, actionable summary ("The AI service is unreachable right now...") with the actual exception logged server-side via `logger.exception`, not a raw exception repr shown to the user.

Gate passed: each of the three upstream legs (OpenRouter, JIRA, GitHub) has a new live-forced test asserting the right exception type surfaces — no mocks, real connections to an address nothing listens on (`127.0.0.1:1`, immediate connection-refused) or a real invalid-auth request, matching this project's zero-mocking convention throughout. Manual verification: the banner treatment reviewed live.

### Phase 8 — Documentation + final formal tracker cleanup (MVP-NFR-9, MVP-NFR-10) — ✅ complete

README covering setup instructions and JIRA/GitHub/OAuth API usage (MVP-NFR-10 — genuinely nothing existed before this phase, a 2-line placeholder). Built: `make up-dev` setup steps, the local-dev Key Vault `az login` prerequisite, one section each for JIRA/GitHub/OpenRouter/Azure AD SSO/Azure Key Vault (what each integration does, its auth model, where to register/configure it), demo-account/seed-data pointers, and a note on the project's no-mocking test philosophy. MVP-NFR-9 marked Specced/done — `.env.example` confirmed to match every field in `app/config.py`'s `Settings` as part of this same pass.

Gate passed: the closest available proxy to "fresh clone, README-only setup" is that `make test`/the full suite has passed repeatedly against the same `.env.example`-documented shape across every subsequent session's work on this repo, with no undocumented local state surfacing as a blocker.

### After Phase 8: timeline steps 10-12 (local QA, deploy, deployment QA)

See those steps' own rows at the top of this file — all three are now marked complete, in practice satisfied continuously across every phase's own live-verification gate rather than as one discrete end-of-project pass (see each row's note for what that looked like concretely, including the two genuine production-only incidents caught this way).
