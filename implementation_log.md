# Implementation Log

Running record of decisions, ambiguities, and bugs found while implementing
`blueprints/plans/implementation-handoff.md`'s Build Phases — anything beyond
"implemented the spec exactly as written." Most recent entry at the bottom.

## Phase -1 (review and question, before writing any code)

Read all three specs (`chat.md`, `oauth-integration.md`, `openrouter-integration.md`),
both trackers, `stack-and-infra.md`, `deployment.md`, `CLAUDE.md`, the handoff doc,
`rubric.md`, the source PDF (identical to `rubric.md`, confirmed), `thought_process.md`,
and the entire current `app/`/`tests/`/`migrations/`/config/Docker/CI tree.

### Findings surfaced to the user, with resolutions

1. **`.env.example`/`.env` sequencing**: the handoff's Phase 0 scope ("remove `.env`'s
   dead `Autonomized_Test_*`/service-account block") is narrower than the diff that was
   sitting uncommitted in the working tree when I started, which also stripped the real
   JIRA/GitHub/Azure vars `app/config.py`'s `Settings` still requires until Phase 1
   reworks it. **Resolution (mine, not re-asked)**: reverted that broader diff; Phase 0
   only removes the genuinely dead block (`My_Github_PAT`, `Autonomized_Test_Repo_URL`,
   the `Autonomized_Test_{1,2,3}_Protonmail_Password/Jira_Password/Github_Username/
   Github_Password` lines never read by any script) from both `.env` and `.env.example`.
   The real `JIRA_*`/`GITHUB_*`/`AZURE_*` vars stay until Phase 1 actually removes the
   `Settings` fields that need them. Verified via `grep` which vars `utils/*_seed_data.py`/
   `*_connect_check.py` actually read (`Autonomized_Test_{n}_Protonmail_Email`,
   `_Jira_API_Key`, `_Github_PAT`) before trimming `.env`, and caught a mistake where I
   first deleted `Protonmail_Email` (it's used) — restored it. `.env` is gitignored, not
   committed; `.env.example` is the file that actually ships.
2. **`llm_router.py` has no tool-calling support yet** (current code: bare
   `AsyncIterator[str]`, `ChatMessage` with no `tool`/`tool_calls` fields) — confirmed
   this is expected (Phase 4 work), the spec describes the target state, not current code.
3. **`test_user_accounts.txt`/`.env` plaintext secrets**: initially looked like a real
   leak (real passwords/tokens for the 3 demo accounts). Checked `git ls-files` — neither
   is tracked, both are correctly gitignored. False alarm, no action taken.
4. **JIRA client rework scope** (user-confirmed): only `build_client`'s signature/base-URL
   construction changes (`(access_token, cloud_id)`, Bearer auth, base URL
   `https://api.atlassian.com/ex/jira/{cloud_id}`); `find_account_id_by_email`/
   `get_issues_assigned_to`'s relative paths (`/rest/api/3/...`) stay untouched since the
   cloud-ID prefix lives in the client's `base_url`, not in each call's path.
5. **Project/repo hallucination risk** (tool call succeeds against a real but wrong/
   unlisted project or repo key the model supplies, since neither spec validates the
   model's `project_key`/`repo` args against the pre-fetched top-10 list) — user-confirmed
   out of scope, implement exactly as specced (no allowlist check).
6. **Local-dev Key Vault fallback** — `oauth-integration.md` explicitly left this open
   ("decide at implementation time"). **User decision: no fallback — local dev uses the
   real Azure Key Vault too**, via the developer's own `az login` identity (same as prod's
   Managed Identity path via `DefaultAzureCredential`). Implication: Phase 1's Key Vault
   provisioning must also grant the current `az login` identity `get`/`set`/`delete` on
   the vault (access policy or `Key Vault Secrets Officer` RBAC), and `deployment.md`
   needs a note that this is now a hard local-dev prerequisite, same posture as the
   existing Azure AD SSO local-dev prerequisite.
7. **GitHub "top collaborators" discovery** — `oauth-integration.md` mentions
   `discovery_top_n` applying uniformly to JIRA top projects / GitHub top repos / top
   collaborators, but no schema type or prompt section anywhere consumed a collaborators
   list. **User clarified intent**: it's pre-fetched system-prompt context only — for the
   logged-in user, giving the model pre-awareness of who they're likely to be asked about
   next, same role as top projects/repos (not a tool parameter, not something the model
   calls a tool with). Will build a `GithubCollaboratorRef`-shaped list injected into the
   system prompt alongside `JiraProjectRef`/`GithubRepoRef`, capped at `discovery_top_n`,
   sourced from recent co-committers/collaborators on the user's top repos.
8. **Citation ordinal assignment** — `chat.md` says both "the model writes sequential
   ordinals into the sentinel" and "the route assigns the next ordinal on validation,"
   which are two different sources of truth. **User decision: model-authoritative** — trust
   the model's own sequential numbering directly for `message_citations.ordinal` and pill
   rendering, no route-side recounting/renumbering.
9. **`MVP-NFR-6` (flat authorization) Specced column** was `⬜` despite `timeline.md`'s own
   dependency tree calling it "a documented non-decision" (i.e. its spec *is* that one
   sentence, no code, no dedicated doc). **User decision: flip to ✅** — done in this
   Phase -1 pass, see below.
10. **`NMVP-FR-2` un-defer** — user confirmed: un-defer into MVP, keep the id (don't
    renumber to avoid breaking cross-references in `oauth-integration.md`/`chat.md`).
    **Follow-up ambiguity caught while actually doing the move** (not part of the original
    Phase -1 batch — found during the tracker edit itself): `NMVP-FR-2`'s *existing written
    description* is "self-service onboarding workflow for linking JIRA/GitHub accounts to
    Azure identity" — i.e. an account-linking UI. That is **not** what `oauth-integration.md`
    builds. `oauth-integration.md` builds session-scoped per-user OAuth *for making API
    calls as the logged-in user* — identity mapping (`team_members`, MVP-FR-8) stays the
    static seed table, completely unchanged. Un-deferring the row with its current text
    would misdescribe the shipped feature. **Resolution (mine — the user's "everything I
    didn't refer to explicitly, I trust you to reconcile" covers this)**: moved the row into
    the MVP table under the `NMVP-FR-2` id, but rewrote its description to describe what's
    actually being built (per-user OAuth for API auth), with an explicit
    note that self-service identity-linking UI itself remains unbuilt. Also rewrote
    `NMVP-FR-4`'s description, which referenced the old `NMVP-FR-2` text ("distinct from
    NMVP-FR-2, which is about linking JIRA/GitHub") — updated it to flag that
    identity-*linking* (as opposed to the narrower per-call-OAuth scope NMVP-FR-2 now
    covers) is a real, currently-untracked gap, rather than leaving a cross-reference to
    a description that no longer exists.

## Mid-Phase-1-prep: token persistence (user-directed spec revision, before any Phase 1 code)

Before starting Phase 1 code, the user asked directly: "if we're vaulting these
credentials with azure, then we could persist them past a single session, and in fact
should we?" — a legitimate challenge to `oauth-integration.md`'s original session-scoped
design, since Key Vault already solves the storage-safety problem that motivated
session-scoping in the first place; session-scoping's real remaining justification was
UX-consistency (avoiding a two-tier GitHub-persists/JIRA-doesn't model), not safety.

I initially sized "persist + build JIRA refresh" as a large addition and offered a
smaller "persist GitHub only" middle option; user pushed back ("how bad is the refresh?
isn't this just an extension of the jira integration?"). Re-sized it properly: `oidc.py`
already has the exact request-shape pattern JIRA's refresh grant needs
(`exchange_code_for_tokens`'s POST-with-grant_type shape), the trigger point is the
already-designed 401-handling path in `JiraTool.execute()`, and it's one new function +
one retry wrapper + one extra Key Vault secret — genuinely an extension of the existing
JIRA client, not a new subsystem. Confirmed this sizing before proceeding; user chose to
persist both providers and build real JIRA refresh handling.

**Rewrote `oauth-integration.md` in place** (not just logged the decision and built
something different from what the spec says) since Phase 1 will be built directly against
this spec and it needs to be the accurate source of truth:
- Isolation model: tokens now keyed by `team_members.id`, survive logout; added the JIRA
  silent-refresh design (`jira_client.refresh_access_token`, refresh-token rotation,
  retry-once-on-401 wrapped around the existing `ToolExecutionError` path — no new
  exception type). GitHub needs no refresh logic (non-expiring token); a GitHub 401 now
  means real revocation, not routine expiry.
- Token storage: `jira_cloud_id` moved from `sessions` to `team_members` (connection
  state is per-user now, not per-session). Key Vault secret names changed from
  `session-{session_id}-{provider}` to `user-{team_member_id}-jira-access` /
  `-jira-refresh` / `-github`. Local-dev Key Vault fallback question is now moot — user
  separately confirmed (in response to my carried-over Phase -1 question about it) no
  fallback is needed, local dev uses the real vault via the developer's own `az login`
  identity, since there are no future developers to optimize that friction away for.
- Connect gate: revised from "mandatory every login" to "fires once per user" (first
  login, or after an explicit disconnect/revocation) — a returning user with existing
  connections skips straight past `/oauth/connect` to `/`.
- **New consequence surfaced and written up explicitly**: `POST /auth/logout` no longer
  revokes JIRA/GitHub access at all (only the Azure session) — added a dedicated section
  in `oauth-integration.md` calling this out, since it's a real behavior change someone
  could otherwise be surprised by later (sign-out no longer being a full credential reset
  the way it used to be / the way Azure's own session still is).
- Propagated the `GithubCollaboratorRef` decision (from the original Phase -1 batch,
  question #8 — building top-collaborators discovery as system-prompt-only context, no
  tool parameter) into both `oauth-integration.md`'s Scope discovery section and
  `chat.md`'s Schemas intro paragraph, since I hadn't actually written that into either
  spec yet when it was originally decided — it was only in my own Phase -1 summary.
- Updated `chat.md`: `team_members` schema table gains `jira_cloud_id`; the "Auth model"
  pointer section rewritten (was still saying "session-scoped... never persisted past
  sign-out"); `ActivityTool.execute()`/`JiraTool`/`GithubTool` prose changed "the
  session's provider token(s)" → "the current user's provider token(s)" for accuracy;
  `JiraTool`'s description now mentions the retry-after-refresh behavior.
- Updated `timeline.md`'s Phase 1 build-order list: step 1 now also covers granting the
  local `az` identity Key Vault access; step 4 mentions `refresh_access_token`; step 6
  (local-dev fallback decision) removed as moot; the phase's gate description now
  includes testing refresh-token rotation and a sign-out/sign-in-without-reconnect manual
  check.
- Did **not** touch `stack-and-infra.md`/`deployment.md` yet — both are listed in
  `oauth-integration.md`'s own "Trackers to update once implemented" section, correctly
  scoped to update *once Phase 1 actually lands*, not during this pre-implementation spec
  revision.
- Did a full re-read of the revised `oauth-integration.md` end-to-end afterward
  specifically looking for missed "session-scoped" leftovers my targeted edits might have
  skipped — found and fixed 5 more: the JIRA app-registration scope note ("kept even
  though this spec doesn't build refresh handling" — now false), cloud-ID resolution
  still saying it's stored on `sessions`, GitHub's OAuth-app note still framing
  non-expiring tokens as "simpler than JIRA... discarded at session end," the Token
  storage section's "session tokens" framing, and the Tool/pre-fetch rework section still
  saying "the session's provider token(s)" / "mandatory... reached by a session that
  already has both provider tokens." Worth noting for future passes: a scope-changing
  edit like this needs a full-file re-read afterward, not just editing the sections that
  obviously reference the changed concept — stale references hide in adjacent prose that
  wasn't the direct target of the edit.

### Confirmed correct, no action needed (stated for the record in the original Phase -1 batch)

- `MVP-NFR-3`'s OpenRouter leg (Bearer-token service credential, no per-user concept) —
  already correct in current `llm_router.py`, untouched by the OAuth rework.
- `utils/*_seed_data.py`, `utils/*_connect_check.py` exempt from OAuth rework — confirmed,
  left untouched.
- Tool-role messages never persisted, no 4th `role` value — will build `messages.role` as
  the 3-value `Literal` exactly as specced.
- `ChatService.run(query: str)` vs. `ChatService(session, conversation_id)` construction —
  not actually contradictory, just spread across two spec sections; `session`/
  `conversation_id` bind at construction, `run()` only takes the new message text.

## Phase 0 (housekeeping)

- Deleted the dead `.env`/`.env.example` block (see finding #1 above). Kept the real
  JIRA/GitHub/Azure config vars intact in both files pending Phase 1.
- `app/db/models/smoke_test.py` was already deleted in a prior session (confirmed via
  `grep` — only appears in historical migration files, which are correctly left alone as
  migrations are append-only).
- Ran full suite in-container (`sg docker -c "make up && make migrate && make test"`):
  19/19 passed. `ruff check .`: clean. `mypy app/`: 12 pre-existing `Settings()` call-arg
  false positives (pydantic-settings resolves required fields from env at runtime; mypy
  can't see that) — confirmed via `git stash` this count is identical before/after Phase
  0's changes, not a regression.
