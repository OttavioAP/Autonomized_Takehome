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
| 8 | Create seed/demo data & identity mappings | Build the 3 demo accounts and the static team-member-to-JIRA/GitHub identity mapping (MVP-FR-8, MVP-NFR-7). Sequenced ahead of implementation since nearly every MVP feature depends on this data existing. First-pass seed data already exists (step 5); the real `team_members` table + `make seed` wiring is Build Phase 2 below, since the table itself doesn't exist until then. | ⬜ | 🟡 | ⬜ | N/A | N/A |
| 9 | Implement MVP features | Implement features in dependency-tree order. Cyclical process — spec, code, and plan get revised against each other as implementation surfaces gaps. Started out of sequence (ahead of steps 6-8) at explicit user request: MVP-FR-1/FR-2/MVP-NFR-2/MVP-NFR-5 (Azure SSO login/logout) implemented and automated-tested; see `blueprints/deployment.md`'s SSO section. Broken into Build Phases 0-8 below, each with its own test-and-commit gate. | N/A | 🟡 | N/A | N/A | N/A |
| 10 | Local QA | QA pass per feature or group of features, run locally, before any deployment of the full app. | N/A | N/A | ⬜ | N/A | ⬜ |
| 11 | Deploy full MVP app | Single deployment of the completed MVP to Azure — not a CI/CD pipeline, a deliberate one-time deploy once local QA passes. | N/A | N/A | N/A | ⬜ | N/A |
| 12 | Deployment QA | Full-system QA pass against the deployed app, done in one fell swoop rather than per-feature. | N/A | N/A | N/A | N/A | ⬜ |
| 13 | Choose non-MVP features to implement | With a working, QA'd MVP live, decide which non-MVP features from `features.md` to pursue next. | N/A | ⬜ | N/A | N/A | N/A |

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
        │                       renders; "no recent activity" prompt wording
        │                       explicitly deferred to last in chat.md
        ▼
MVP-NFR-4 (AI input/output validation) — cross-cutting, largely satisfied
                                          incrementally as FR-9/10/11 land
                                          (ChatRequest, ToolDefinition/ToolCall
                                          validation) rather than a separate step
```

MVP-NFR-1 (Azure deploy), MVP-NFR-6 (flat authz — no code, a documented non-decision), MVP-NFR-8 (integration tests — grows incrementally alongside every phase, not a discrete step), MVP-NFR-9 (env-var config — already true), MVP-NFR-10 (docs) aren't in the chain above because they're not prerequisites for other features; MVP-NFR-10 gets its own tail phase (see Build Phases below), MVP-NFR-9 just needs a formal Specced mark (no code change).

## Build Phases (implementation order, step 9's detailed breakdown)

Each phase below ends with a **hard gate**: write tests for that phase's code (pytest — unit tests for anything with no external dependency, integration tests for anything touching JIRA/GitHub/OpenRouter/Azure, matching the existing `tests/integrations/` pattern), run the full suite, and only commit + push if everything passes. **If a push triggers a deploy failure in `deploy.yml`, stop and do not continue to the next phase** — fix forward on the current phase until the deploy is green again before starting new feature work. Never skip ahead with a known-broken deploy.

### Phase 0 — Housekeeping (prerequisite to everything below)

- Remove `.env`'s dead `Autonomized_Test_*`/service-account block (the purge already discussed) and `.env.example` to match — the new OAuth-based `.env` shape has ~10 vars, not the ~40 currently present. Confirm `docker-compose.yml`/`deploy.yml`/`app/config.py` don't reference anything being removed before deleting.
- Delete `app/db/models/smoke_test.py` (already dead — not imported, not on `Base.metadata`, its table already dropped by an earlier migration; done as part of this review, not left for the implementing agent).
- Gate: no tests to write (pure deletion); run the existing suite to confirm nothing broke, commit, push, confirm deploy green before Phase 1.

### Phase 1 — JIRA/GitHub OAuth (`oauth-integration.md`)

Everything else depends on this — no tool can execute without a real per-user token. Build in this order within the phase:
1. Azure Key Vault provisioning (`scripts/azure/provision.sh` extended) + Managed Identity role assignment.
2. JIRA 3LO app registration + GitHub OAuth App registration (external, via each provider's console — same pattern as the Azure AD app registration already done).
3. `app/config.py` changes (remove old JIRA/GitHub fields, add OAuth client id/secret/redirect-uri fields + `discovery_top_n`).
4. `jira_client.py`/`github_client.py` rework (new `build_client` signatures).
5. `app/api/oauth.py` (connect/disconnect routes) + the `/oauth/connect` mandatory gate, wired into `/auth/callback`'s redirect target.
6. Local-dev Key Vault fallback (decide the open question from `oauth-integration.md`'s Explicitly-out-of-scope list, then implement it).

Gate: integration tests hitting real JIRA/GitHub OAuth flows where feasible (the interactive authorize-code exchange can't be fully automated — test what can be tested headlessly: token storage/retrieval from Key Vault, client construction against a resolved cloud ID, disconnect clearing the secret) + a manual browser round-trip (connect both providers, confirm the gate blocks entry until both are connected, confirm disconnect works) before considering this phase done, mirroring how Azure SSO's own live-endpoint regression test + manual browser check worked earlier in this project.

### Phase 2 — Schema (`chat.md`'s Schema section)

`team_members`, `conversations`, `messages`, `activity_items`, `message_citations` — five new tables/models + one Alembic migration. Also `local-dev-data/team_members.json` becomes the real seed source for `team_members` (wired into `scripts/seed.py`, per `stack-and-infra.md`'s existing convention).

Gate: `make revision && make migrate` produces a clean migration; a seed round-trip test (seed → query back → matches fixture) for `team_members`; no other tests needed yet since nothing queries these tables until Phase 3.

### Phase 3 — JIRA/GitHub tools + pre-fetch (`chat.md`'s Tools + Pre-fetch sections)

`JiraTool`/`GithubTool` (with `JiraToolParams`/`GithubToolParams`), `activity_item_repo.py`, `team_member_repo.py`, pre-fetch's discovery logic (top-10 projects/repos/collaborators via `Settings.discovery_top_n`). Depends on Phase 1 (real tokens to call with) and Phase 2 (tables to upsert into).

Gate: integration tests exercising each tool's `execute()` against live JIRA/GitHub data (extending the existing `tests/integrations/test_jira_client.py`/`test_github_client.py` pattern to the tool layer, not just the raw client functions) + a pre-fetch test that runs it twice and confirms the second run is a no-op (cache hit via `prefetched_at`).

### Phase 4 — OpenRouter tool-calling (`openrouter-integration.md`'s revised `query()`)

The `QueryEvent` union, `ToolDefinition`/`ToolCall`, streaming tool-call-delta accumulation. Independent of Phases 2/3's *data* but depends on Phase 3 existing conceptually (tools to define `ToolDefinition`s from) for a realistic end-to-end test — can be built in parallel with Phase 3 if useful, but tested together.

Gate: the three test cases already specified in `openrouter-integration.md`'s Testing section (plain text completion, unauthorized-request error, live tool-call round-trip with argument parsing) — all against the real OpenRouter API, no mocks, matching existing project convention.

### Phase 5 — `ChatService` + conversation routes (`chat.md`'s ChatService + Routes sections)

The agentic loop itself: `CitationStreamParser`, the tool-call round-trip loop, citation validation, `GET /`, `GET /conversations/{id}`, `POST /conversations`, `POST /conversations/{id}/chat`. This is the single largest phase — depends on everything before it (OAuth for tokens, schema for persistence, tools for data, `llm_router` for the model round-trip).

Gate: this is where MVP-FR-5/FR-7/FR-9/FR-10/FR-11 all actually come together — write both unit tests (`CitationStreamParser` against synthetic delta sequences, no live API needed) and integration tests (a full `ChatService.run()` call against real OpenRouter + real JIRA/GitHub data, asserting a real citation round-trips correctly end to end). Manually exercise via `POST /conversations/{id}/chat` with curl/httpx before considering this "working," since this is the core of the whole app and deserves more than automated coverage alone.

### Phase 6 — Chat UI (`chat.md`'s Templates + Static sections)

`_message.html`, `_activity_pill.html`, `_tool_status.html`, `_cite_error.html`, `chat.css`, wiring `htmx-ext-sse` to `POST /conversations/{id}/chat`'s SSE stream. This is MVP-FR-3/FR-4/FR-12 (streaming UI specifically, not the upstream half already done in Phase 4).

Gate: manual browser verification is the primary gate here (this is UI — per the project's own working-agreement to actually exercise UI changes in a browser, not just typecheck them) — ask a real question through the real UI, confirm streaming renders progressively, confirm a citation pill deep-links correctly. Automated tests where they add real value (e.g. a route-level test asserting the SSE response has the right `event:`/`data:` framing), not for their own sake.

### Phase 7 — Error/empty states (`chat.md`'s Errors section + the deferred "no recent activity" prompt wording)

MVP-FR-6 in full: member-not-found, no-recent-activity, upstream-failure, all three distinct and legible in the UI. This is explicitly sequenced last per `chat.md`'s own note ("addressed after the rest of this spec is implemented and there's a real response to look at, not guessed at now") — by this phase there's real model output to look at when writing the "no recent activity" system-prompt instruction, rather than guessing at it in the abstract.

Gate: test each of the three states deliberately (a query for a nonexistent name, a query for a real user with genuinely no activity, a forced upstream failure e.g. via an invalid token) — both automated (assert the right SSE event/error path fires) and manual (confirm the UI actually reads as intended, not just "didn't crash").

### Phase 8 — Documentation + final formal tracker cleanup (MVP-NFR-9, MVP-NFR-10)

README covering setup instructions and JIRA/GitHub/OAuth API usage (MVP-NFR-10 — genuinely nothing exists yet). Mark MVP-NFR-9 Specced (config is already env-var-based; this is a tracker formality, not new code — confirm the final `.env.example` shape matches what's actually required post-Phase-1's config changes before marking it done).

Gate: no code to test; the "test" here is a fresh clone + README-only setup actually working (`git clone` → follow the README verbatim → `make up-dev` → app runs) — the closest thing to an automated test is `make test` passing in a genuinely fresh environment, which is also a good final sanity check that nothing in the repo silently depends on undocumented local state.

### After Phase 8: timeline steps 10-12 (local QA, deploy, deployment QA)

Not further broken down here — these are full-system QA passes across everything built in Phases 0-8, not per-feature work. Pick up `timeline.md`'s existing step 10/11/12 descriptions once Phase 8's gate passes.
