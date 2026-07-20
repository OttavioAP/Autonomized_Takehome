# Handoff: rework `jira_client.py` / `github_client.py` for per-user OAuth

Paste this whole file to a fresh Claude Code session opened at the repo root
(`/home/oz/Autonomized_Takehome`). It has no memory of any prior conversation
about this project — everything you need is below or in the referenced files.

## Context

This is the Team Activity Monitor project — a FastAPI app moving from a
single shared JIRA/GitHub service-account credential to per-user OAuth. You're
building one specific, self-contained piece: reworking the two existing
integration clients to accept per-user OAuth tokens instead of `Settings`-
configured fixed credentials, plus adding JIRA's token-refresh function.

**Read first, in this order:**
1. `CLAUDE.md` — binding invariants (routes own the DB transaction, services/
   repositories are plain functions, no `Depends()` outside routes; not
   directly relevant to this integrations-layer work, but read it anyway).
2. `implementation_log.md` — a running record of every decision, ambiguity,
   and bug found so far while implementing this project's Build Phases,
   written by the agent driving this work. Read the whole file for context —
   in particular the "Mid-Phase-1-prep" entry (why tokens now persist
   per-user, not per-session, and why JIRA needs real refresh-token
   handling as a result) and the "Phase 1: app/config.py + .env" entry
   (exactly what changed in `Settings` and `.env` — this affects your work
   directly, see the Testing section below). **When you're done, append your
   own entry to this same file** (don't create a separate log) — record what
   you built, what you had to guess or assume, any bugs/gaps you found, and
   anything a future reader would need to know that isn't obvious from the
   code/spec alone. Follow the file's existing structure (`## <phase/topic>`
   headers, most recent at the bottom). This file is shared across multiple
   agents working on this project in parallel, so keep your entry
   self-contained and clearly labeled with what you actually did.
3. `blueprints/plans/features/oauth-integration.md` — specifically the "JIRA
   Cloud (3LO / OAuth 2.0 authorization code)" section under "OAuth flows"
   (API base URL, cloud ID resolution shape), the "JIRA silent refresh on
   access-token expiry" bullet under "Isolation model" (the exact behavior
   `refresh_access_token` needs to enable — but note: the actual retry-on-401
   wrapper that CALLS this function lives in `JiraTool.execute()`, which is
   separate, later work — not part of this handoff, see "What NOT to build"
   below), and "Client rework" section (the exact signature changes).
4. `blueprints/plans/implementation-handoff.md`'s "Best practices" section
   (Pydantic for every data shape, full type hints/mypy-clean, comment the
   WHY not the WHAT, errors are loud never silent).
5. The actual current code: `app/integrations/jira_client.py`,
   `app/integrations/github_client.py` (both to be modified), `app/auth/
   oidc.py`'s `exchange_code_for_tokens` function (the exact request-shape
   pattern to mirror for JIRA's refresh grant — same POST-with-grant_type
   idea, different grant_type value and endpoint).

## What to build

### `app/integrations/jira_client.py`

- `build_client(access_token: str, cloud_id: str) -> httpx.AsyncClient` —
  replaces the current `build_client(base_url, email, api_token)`. New base
  URL: `https://api.atlassian.com/ex/jira/{cloud_id}`. New auth: Bearer token
  header (`Authorization: Bearer {access_token}`), not the current
  `auth=(email, api_token)` Basic-auth tuple. Keep the same `timeout=10.0`.
- `find_account_id_by_email` / `get_issues_assigned_to` — **do not change
  their signatures or internal logic at all**. They call relative paths
  (`/rest/api/3/...`) against whatever `client.base_url` is — since the new
  base URL already includes the `/ex/jira/{cloud_id}` prefix, these relative
  paths resolve correctly with zero changes. The spec is explicit: "keep
  their existing shapes; only how the client itself is constructed changes."
- **New function**: `async def refresh_access_token(client: httpx.AsyncClient,
  refresh_token: str, client_id: str, client_secret: str) -> dict[str, Any]`
  — `POST https://auth.atlassian.com/oauth/token` with
  `grant_type=refresh_token`, `refresh_token`, `client_id`, `client_secret`
  in the JSON body (check Atlassian's actual token-refresh API docs for the
  exact required field names/shape — don't guess without checking; the
  existing `oauth-integration.md`'s "Token exchange" bullet under JIRA OAuth
  flows shows the analogous authorization-code exchange endpoint and shape
  as a reference point, but refresh is a different grant_type against a
  similarly-shaped endpoint). Returns the raw response JSON (containing a
  new `access_token`, `expires_in`, and — critically — a NEW rotated
  `refresh_token`; Atlassian rotates the refresh token on every use, so the
  caller MUST persist the new refresh_token, not just the new access_token,
  or the next refresh will fail with a stale token). This function does NOT
  need its own client — take `client: httpx.AsyncClient` as a param like
  every other function in this file (framework-agnostic, no self-construction
  of clients). `resp.raise_for_status()` before returning, consistent with
  how every other function in this file propagates `httpx.HTTPStatusError`
  rather than wrapping it.
- Note: the function this refreshes into "if a call 401s, retry once" is
  `JiraTool.execute()`'s job — that's separate, much later work (Phase 3).
  This handoff only builds the raw client-level refresh capability; it does
  NOT wire it into any retry loop.

### `app/integrations/github_client.py`

- `build_client(token: str)` — **no signature change at all**. The spec is
  explicit: "keeps its existing `(token: str)` signature and Bearer-auth
  shape unchanged — only the caller now passes the current user's persisted
  OAuth token instead of `Settings.github_token`." You may not need to touch
  this file's actual code at all beyond maybe a docstring/comment update
  reflecting the token's new source — check if any change is even needed
  before assuming there is one.

## What NOT to build

- No changes to `find_account_id_by_email`/`get_issues_assigned_to`'s
  internals beyond what's specified above.
- No retry-on-401 loop calling `refresh_access_token` — that lives in
  `JiraTool.execute()`, separate later work (Phase 3, not built yet — the
  `JiraTool` class doesn't exist in this repo yet, don't create it).
- No changes to `utils/jira_connect_check.py`, `utils/github_connect_check.py`,
  `utils/jira_seed_data.py`, `utils/github_seed_data.py` — these are
  explicitly exempt from the OAuth rework (standalone scripts using the demo
  accounts' real Basic-auth/PAT credentials directly, not part of the app's
  request path). Leave them completely alone.
- No `app/services/token_store.py` (separate parallel work — don't create
  this file; if it already exists when you start, don't modify it).
- No `app/api/oauth.py` routes (separate, later work — don't create this
  file).

## Testing — read this section carefully, there's a real gap you can't close

`tests/integrations/test_jira_client.py` and `test_github_client.py`
currently call `build_client(settings.jira_base_url, settings.jira_email,
settings.jira_api_token)` and `build_client(settings.github_token)` — both
referencing `Settings` fields that **no longer exist** (removed from
`app/config.py` in an earlier step of this same phase; check `app/config.py`
yourself to confirm current field names before writing anything).

**GitHub**: `build_client`'s signature is unchanged, so this test file is
fixable — `.env` still has the demo accounts' real fine-grained PATs under
the `Autonomized_Test_{1,2,3}_Github_PAT` keys (see `.env`'s `#for claude
code: not env vars` section — read these directly via `os.environ`/a small
helper, the same way `utils/github_connect_check.py` already reads `.env`
directly, since these aren't real `Settings` fields). Update the test to read
`Autonomized_Test_1_Github_PAT` instead of `settings.github_token`, and
`Autonomized1` (already hardcoded in the test) for the repo... but note
`settings.github_repo` is also now gone — you'll need the actual repo name.
Check `.env`/`local-dev-data/` or ask by checking `CHANGELOG.md`'s entries
for the seed data setup (search for "Shared_Repo_1" or similar) for the real
repo identifier if it's not obvious. Get this test passing for real, against
live GitHub data, same as it did before — just with credentials sourced
differently.

**JIRA**: this is the real gap. `build_client`'s new signature needs a real
OAuth **access_token** (Bearer) and a **cloud_id** — neither of which can be
obtained from the demo account's Basic-auth API token (`
Autonomized_Test_1_Jira_API_Key` in `.env` is a Basic-auth API token, a
completely different auth mechanism, not usable as a Bearer OAuth access
token). Getting a real JIRA OAuth access token requires a live, interactive
browser authorize-code exchange (a human clicking through Atlassian's consent
screen) — there is no way to script this in a sandboxed session, and no JIRA
OAuth app registration may even exist yet at the time you're doing this (check
`.env` for `JIRA_OAUTH_CLIENT_ID` — if it's empty, the app registration
hasn't happened yet either).

**Do this instead**: don't try to force `test_jira_client.py` to pass end-to-
end against live data with real tokens. Instead:
1. Update `find_account_id_by_email`/`get_issues_assigned_to` tests to still
   exist but skip/xfail cleanly with a clear reason
   (`pytest.mark.skip(reason="...")`) if no real JIRA OAuth access token is
   available — do NOT delete the tests, do NOT fake/mock a token (this
   project has zero mocking in its dependency tree, deliberately — don't
   introduce it now).
2. Write unit-level coverage for what CAN be verified without live
   credentials: that `build_client` constructs an `httpx.AsyncClient` with
   the correct `base_url` (`https://api.atlassian.com/ex/jira/{cloud_id}`)
   and the correct `Authorization: Bearer {token}` header, given a fake
   cloud_id/token string — this doesn't need real Atlassian connectivity,
   just inspecting the constructed client's own configured attributes
   (`client.base_url`, `client.headers`).
3. For `refresh_access_token`, same situation — you likely can't get a real
   refresh_token to test against without a live OAuth connect having already
   happened. Write what you can (request shape/URL correctness via a
   lightweight check, NOT a live call) and clearly flag in your final report
   that end-to-end refresh-token verification is blocked on a real OAuth
   connect existing, which is separate, later work.
4. In your `implementation_log.md` entry, be explicit about this gap: JIRA
   client-level integration testing is blocked until a real OAuth connect
   flow exists and someone actually authorizes through Atlassian's consent
   screen once. This is expected, not a failure on your part — flag it
   clearly so whoever picks up `app/api/oauth.py` and the manual browser
   round-trip (Phase 1's gate) knows to circle back and verify
   `jira_client.py`'s real behavior against live data at that point.

Run whatever you can:
```
sg docker -c "docker compose up -d --build"
sg docker -c "docker compose exec fastapi pytest tests/integrations/test_jira_client.py tests/integrations/test_github_client.py -v"
sg docker -c "docker compose exec fastapi ruff check ."
sg docker -c "docker compose exec fastapi mypy app/"
```
(If `docker.sock` permission errors happen, prefix commands with `sg docker
-c "..."` as shown — this dev machine needs that workaround.)

## When done

Report back: what you built, the exact function signatures (flag if you
deviated from the sketch above and why), which tests actually pass against
live data vs. which are skip/xfail pending a real OAuth connect, and
anything you had to guess or assume (especially Atlassian's exact
refresh-token-grant request/response shape if you couldn't verify it against
real docs).
