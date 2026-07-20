# Per-User OAuth Integration Spec

Replaces the shared service-account model in `chat.md`'s "Auth model for JIRA/GitHub
calls" section (that section is now superseded by this file — un-defers NMVP-FR-2
into MVP scope, at the user's explicit request). Every JIRA/GitHub call the app
makes now uses the *logged-in user's own* OAuth token, never a shared credential.

## Why the service account doesn't make sense

Once conversations can be about anyone on the team, "the app has one shared
JIRA/GitHub credential" stops being a simplification and starts being the thing
that makes per-user isolation impossible to reason about — every tool call is
technically capable of seeing everything the one shared account can see,
regardless of who's asking. Per-user OAuth makes "the model can only ever see
what the logged-in user's own credentials permit" a structural property instead
of a policy on paper.

## Isolation model (confirmed via direct discussion, not assumed)

- **User-scoped, persisted across logins — revised from an earlier
  session-scoped draft.** The original version of this spec kept JIRA/GitHub
  tokens session-scoped (discarded at logout/expiry, reconnect every login)
  specifically to avoid a two-tier UX where GitHub's non-expiring token
  persisted but JIRA's didn't. Revisited once Key Vault was already the
  storage layer: the original session-scoping motivation was really "don't
  put raw tokens somewhere unsafe," which Key Vault already solves
  independent of *how long* a secret lives — session-scoping the *lifetime*
  was solving a storage-safety problem with a UX tradeoff (reconnect every
  login) that didn't need to exist once the storage problem was actually
  solved. Tokens now persist keyed by `team_members.id`, survive logout, and
  a returning user only reconnects if they explicitly disconnect or a
  provider revokes access — not every session. This does mean building real
  refresh-token handling for JIRA (see below), which the session-scoped draft
  deliberately avoided; sized and accepted as a reasonable, scoped extension
  of the JIRA client rather than a new subsystem (one refresh function, one
  retry-on-401 wrapper around existing tool execution, one extra Key Vault
  secret per user) — not the "real chunk of new work" it was initially
  flagged as. No `oauth_connections` table — Key Vault secret existence
  keyed by `team_member_id` *is* the connection state, same reasoning as the
  original session-keyed design, just keyed one level up.
- **A user's own token is sufficient to ask about teammates.** Verified against
  both providers' actual permission models, not assumed:
  - **JIRA Cloud**: visibility is project-level, not assignee-level. Any user
    with Browse Projects permission on a project can see and JQL-search *all*
    issues in it, including ones assigned to other people. John's token can
    return Sarah's assigned tickets as long as John has browse access to
    whatever project they're in — Sarah does not need to have connected
    anything herself.
  - **GitHub**: visibility is repo-level. Any collaborator's token (or any
    token at all, for a public repo) can list commits/PRs by any author via
    `?author=`/`?state=` filters — authorship doesn't gate visibility,
    repo access does.
  - **Consequence**: pre-fetch and tool calls always execute with the *asking*
    user's token, never a token belonging to whoever the question is about.
    There is no scenario where the app needs "someone else's" token.
- **Token expiry asymmetry between providers, checked directly rather than
  assumed**: JIRA Cloud OAuth 2.0 (3LO) has no non-expiring option at all —
  short-lived access tokens (~1 hour) plus a rotating refresh token that
  itself dies after 90 days of *inactivity* (i.e. 90 days without a refresh
  actually being used — a token in regular use effectively never expires).
  GitHub OAuth Apps (classic), by contrast, issue tokens that are genuinely
  non-expiring by default — "OAuth tokens remain active until they're
  revoked by the customer" (GitHub's own docs) — no forced expiry, no refresh
  cycle, unless the user or an org admin revokes access. Now that tokens
  persist (see above), this asymmetry is real and has to be handled per
  provider rather than papered over by both being short-lived session
  artifacts: GitHub needs no refresh logic at all (store once, use
  indefinitely); JIRA needs the refresh-token grant actually implemented.
- **JIRA silent refresh on access-token expiry.** `jira_client.py` gains
  `refresh_access_token(client, refresh_token, client_id, client_secret) ->
  dict` — `POST https://auth.atlassian.com/oauth/token` with
  `grant_type=refresh_token`, same request shape `oidc.exchange_code_for_tokens`
  already establishes for the Azure flow. Atlassian **rotates** the refresh
  token on every use (the response includes a new `refresh_token` that must
  overwrite the stored one — using a stale rotated-out refresh token fails
  the next refresh), so the write path always updates both secrets together,
  never just the access token. Trigger point: `JiraTool.execute()`'s existing
  401-handling path (previously a hard failure) becomes try → on 401, refresh
  → retry the call once → only raise `ToolExecutionError` if the refresh
  attempt itself fails (refresh token invalid/expired past its 90-day idle
  window) or the retried call still 401s after a successful refresh. This is
  an extension of the existing tool-execution error path, not a new one — no
  new exception type, `ToolExecutionError`'s existing shape and `chat.md`'s
  existing "fed back to the model as an explicit error string" handling both
  apply unchanged.
- **GitHub still gets no refresh logic** — its token doesn't expire under
  normal operation, so a 401 there means real revocation (user or org admin
  revoked access), not routine expiry. Still surfaces as `ToolExecutionError`
  → the user reconnects via the same flow as a first-time connect, same as
  the original spec's re-prompt behavior, just now genuinely rare instead of
  routine.

## Scope discovery, not fixed config

**Implemented in Phase 3/5, real endpoints verified live** (see `implementation_log.md`)
— the "TBD at implementation time" fields below are now settled:
- JIRA projects: `GET /rest/api/3/project/search` (every project the token can
  browse — chosen over deriving a ranked list from the asking user's own issues,
  since the person being asked about may not be the asker, so ranking by the
  asker's own activity would bias toward the wrong projects).
- JIRA people: `GET /rest/api/3/user/assignable/search?project={key}` on the
  top-ranked discovered project — real project members, not just the 3 seeded
  `team_members`. Returns `accountId`/`displayName`/`emailAddress`, but
  `emailAddress` comes back blank for most non-owner accounts (confirmed live) —
  `account_id`, not email, is the reliable identifier this feeds into
  `JiraToolParams`.
- GitHub repos: `GET /user/repos?sort=pushed&direction=desc` (the token's own
  repos, most-recently-pushed first — not `GET /users/{login}/repos`, a
  different public-listing endpoint with different auth semantics).
- GitHub collaborators: `GET /repos/{repo}/contributors` on the single
  most-recently-pushed discovered repo only (not fanned out across all
  `discovery_top_n` repos) — server-aggregated and sorted by contribution
  count already, one extra call is a better tradeoff than N extra calls for
  prompt-context-only data.

`JIRA_PROJECT_KEY`, `GITHUB_REPO`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `GITHUB_TOKEN`
are removed from `Settings` entirely — there is no longer a single
project/repo the whole app is pointed at. Instead, **pre-fetch discovers scope
per user**, same shape as the existing "fetch the logged-in user's own activity"
pre-fetch in `chat.md`, extended to also resolve *where* to look:

- **JIRA**: pre-fetch reuses `team_members.jira_cloud_id` (moved here from
  `sessions.jira_cloud_id` by the token-persistence revision above — the
  cloud id is per-user connection state now, not per-session) — already
  resolved once during `GET /oauth/jira/callback` via `accessible-resources`
  — rather than calling that endpoint a second time. (Resolved via direct
  discussion: this is the whole reason that column exists in the first
  place; re-deriving it independently in pre-fetch would be a redundant call
  for no benefit.) For that cloud ID, fetch the user's own recent/
  assigned-issue projects — "top projects" becomes part of the pre-fetched
  context alongside the existing "my tickets" data.
- **GitHub**: the user's own recent repos (`GET /user/repos`, sorted by recent
  push) and recent collaborators — "top repos"/"top collaborators" alongside
  "my commits/PRs." Both are pre-fetched **system-prompt context only** — not
  tool parameters, not something the model calls a tool with — giving the
  model pre-awareness of who on the team it's likely to be asked about next
  for this user, the same role top projects/repos play for "where to look."
  See `chat.md`'s Schemas section for the `GithubCollaboratorRef` shape this
  feeds into.
- **Top-N**: `Settings.discovery_top_n: int = 10` (new config field, env-var
  overridable like `max_tool_call_rounds` in `chat.md`) — applies uniformly to
  JIRA top projects, GitHub top repos, *and* top collaborators discovered
  alongside them (all three use the same cutoff, one config knob, not three).
- **Shape**: richer objects, not bare identifier strings — `JiraProjectRef(key:
  str, name: str)` / `GithubRepoRef(full_name: str, description: str | None)`
  (exact fields TBD at implementation time; `key`/`full_name` are the values
  `JiraToolParams.project_key`/`GithubToolParams.repo` expect back from the
  model). Chosen over a flat list of identifiers so the model can reference a
  project/repo by its human name in prose ("in the *My Software Team*
  project") while still citing back the machine key/slug the tools need —
  matches the richer shape already used for `activity_items`/the team roster,
  rather than introducing a second, sparser convention just for this context.
  `GithubCollaboratorRef(login: str, name: str | None)` follows the same
  pattern for top collaborators — unlike `JiraProjectRef`/`GithubRepoRef` it
  isn't a tool-parameter value (no tool accepts a collaborator identifier),
  purely system-prompt context, but kept as a typed Pydantic shape rather
  than a bare string for the same reasons (name in prose, `login` if the
  model ever needs to hand a person identifier to `GithubToolParams.github_login`
  when asking about that person specifically). **Added during implementation**:
  `JiraPersonRef(account_id: str, display_name: str, email: str | None)` — JIRA's
  asymmetric counterpart to `GithubCollaboratorRef`. Unlike GitHub (where
  `github_login` already accepts any login, discovered or rostered, with no
  resolution step), JIRA's tool needs an `account_id` specifically for
  discovered people since `find_account_id_by_email` can't resolve an email
  JIRA never returned — so `JiraPersonRef` *is* a tool-parameter source
  (`JiraToolParams.account_id`), not prompt-context-only like its GitHub
  counterpart.

This pre-fetched project/repo list becomes system-prompt context the LLM
reads, exactly like the team roster already is. `JiraTool`/`GithubTool` gain a
`project_key`/`repo` parameter the model supplies from that context on each
call, rather than a hardcoded single value baked into `Settings`. If the model
needs a project/repo that wasn't in the pre-fetched top 10, that's a live gap
(not solved by this spec) — see Explicitly out of scope.

## OAuth flows

### JIRA Cloud (3LO / OAuth 2.0 authorization code)

- **App registration**: one Atlassian OAuth 2.0 (3LO) app in the developer
  console, distinct from anything already provisioned (the existing
  `JIRA_API_TOKEN` was Basic auth against a fixed site — unrelated mechanism,
  fully replaced, not extended). Configured with a callback URL and scopes
  (`read:jira-work read:jira-user offline_access` — `offline_access` requests
  the refresh token that the silent-refresh design above now actually
  requires and uses, not just a door left open for later).
- **Authorize URL**: `https://auth.atlassian.com/authorize` with
  `audience=api.atlassian.com`, `client_id`, `scope`, `redirect_uri`, `state`,
  `response_type=code`, `prompt=consent`.
- **Token exchange**: `POST https://auth.atlassian.com/oauth/token` →
  `access_token`, `expires_in`, `refresh_token`.
- **Cloud ID resolution**: `GET https://api.atlassian.com/oauth/token/accessible-resources`
  (Bearer `access_token`) → list of `{id, url, scopes}` per accessible site.
  The resolved cloud ID is stored on the `team_members` row itself (see Token
  storage below — it isn't a secret, so it doesn't need Key Vault) so it isn't
  re-fetched on every tool call.
- **API base URL changes**: from `https://{site}.atlassian.net/rest/api/3/...`
  (Basic auth, current `jira_client.py`) to
  `https://api.atlassian.com/ex/jira/{cloudid}/rest/api/3/...` (Bearer auth) —
  a real breaking change to how the client builds its base URL and auth header,
  not just a credential swap. See Client rework below.

### GitHub (OAuth App, classic — not a GitHub App)

- **App registration**: one GitHub OAuth App with a callback URL and `repo`
  scope (read access to private + public repos, commits, PRs — GitHub's OAuth
  scope model is coarser than fine-grained PATs; there is no read-only-scoped
  OAuth scope narrower than `repo` for private repo access). Classic OAuth Apps
  issue non-expiring tokens by default (no `expires_in` unless the app opts
  into token expiration) — no refresh model needed at all, unlike JIRA; store
  once at connect time and use indefinitely until disconnected or revoked.
- **Authorize URL**: `https://github.com/login/oauth/authorize` with
  `client_id`, `redirect_uri`, `scope`, `state`.
- **Token exchange**: `POST https://github.com/login/oauth/access_token` →
  `access_token`.
- **API calls**: `Authorization: Bearer <access_token>` against
  `api.github.com` — same base URL and header shape `github_client.py` already
  uses today, only the token's *source* changes (per-user OAuth grant instead
  of a `Settings`-configured PAT).

## Token storage: Azure Key Vault, not a plaintext Postgres column

Revised after direct discussion — an earlier draft of this spec stored tokens
as plaintext `sessions` columns and flagged encryption-at-rest as an accepted
gap (consistent with the project's otherwise-vault-free posture). Reconsidered
once the question was asked directly: this project *already* has an Azure
tenant and deployment, so real encryption-at-rest is a small addition here,
not a new dependency pulled in from nothing. **Pulls Key Vault into MVP scope
for these OAuth tokens specifically** (a deliberate, narrow exception to
NMVP-NFR-2 still being non-MVP everywhere else — `DATABASE_URL`,
`OPENROUTER_API_KEY`, etc. stay as plain env vars/GitHub Actions secrets,
unchanged).

- **No new persistent table.** `team_members` (see `chat.md`'s Schema
  section) gains one column:

  | Column | Type | Notes |
  |---|---|---|
  | `jira_cloud_id` | text, nullable | Resolved once at connect time via `accessible-resources`; not a secret, safe to keep in Postgres alongside the team member row. Moved here from `sessions` (its location in the original session-scoped draft of this spec) now that connection state is user-scoped, not session-scoped. |

  The actual `jira_access_token`/`jira_refresh_token`/`github_access_token`
  values live as Key Vault secrets, named deterministically from the team
  member id (`user-{team_member_id}-jira-access`,
  `user-{team_member_id}-jira-refresh`, `user-{team_member_id}-github`) so no
  separate mapping table is needed — `team_members.id` is already the lookup
  key, and it's stable across logins (unlike `session_id`, which is what
  session-scoping's original key would have required rotating on every
  login). GitHub has no refresh token to store (see above), hence only one
  secret for that provider.
- **Auth to Key Vault**: the App Service uses a **system-assigned Managed
  Identity**, granted `get`/`set`/`delete` on secrets via a Key Vault access
  policy (or RBAC role `Key Vault Secrets Officer`, scoped to just this
  vault) — no separate Key Vault credential to provision, store, or rotate;
  Azure handles the identity. Local dev uses the same real Key Vault, via the
  developer's own `az login` identity granted the same access — no
  env-var/in-memory fallback; this project has no future developers to
  optimize that friction away for, so the simpler single-code-path answer
  (one `DefaultAzureCredential` resolution, prod and local alike) wins.
- **Expiry**: GitHub's secret gets no `expires_on` (the token itself doesn't
  expire, and the whole point of this revision is that it now outlives any
  single session). JIRA's access-token secret can still set a short
  `expires_on` matching the token's own ~1-hour lifetime as a hygiene measure
  (Key Vault will purge it as expected, and `refresh_access_token` writes a
  fresh one anyway on next use); the refresh-token secret gets no
  `expires_on` — its real expiry is Atlassian's own 90-day-idle rule, which
  Key Vault has no way to reset on each use, so an artificial TTL here would
  just be wrong. Disconnect (`POST /oauth/{provider}/disconnect`) explicitly
  deletes all of a provider's secrets for that user — the only way tokens are
  actually removed now that logout no longer does it.
- **Refresh-token storage**: now stored, reversing the original spec's
  "still not stored" position — required for JIRA's silent-refresh path
  above to work at all once tokens persist past a single short session.

`oauth_state` (already used for the Azure login CSRF-style state check in
`app/api/auth.py`) is reused for these flows too, not duplicated per-provider.

**New dependency**: `azure-keyvault-secrets` + `azure-identity` (for
`DefaultAzureCredential`, which resolves to the Managed Identity in Azure and
to the developer's `az login` session locally — one code path for both
environments, matching how `scripts/azure/*.sh` already uses the logged-in
`az` identity for provisioning). **New infra**: one Key Vault resource,
provisioned via `scripts/azure/provision.sh` alongside the existing
Postgres/App Service/ACR resources, plus the Managed Identity role
assignment.

**Real production incident, found post-deploy**: `AZURE_CLIENT_ID` is set in App
Service config for the *Azure AD SSO app registration* (`app/auth/oidc.py`'s login
flow, unrelated to Key Vault) — but `azure-identity`'s `DefaultAzureCredential`
defaults its `managed_identity_client_id` kwarg to that same env var whenever the
kwarg isn't explicitly passed, causing `ManagedIdentityCredential` to search for a
*user-assigned* identity matching the SSO app's client id instead of falling back to
the real system-assigned identity that's actually role-assigned on the vault — a
real production 500 on every authenticated request, invisible in local dev (the
`az login`-based `AzureCliCredential` fallback never hits this code path the same
way). Fixed in `token_store._credential()` by passing `managed_identity_client_id=None`
explicitly. `exclude_environment_credential=True` (already present, for a related but
distinct reason — see that function's own comments) does NOT suppress this; it only
stops `EnvironmentCredential` itself from misusing the same var.

## Connect/disconnect UI + routes (`app/api/oauth.py`, new)

Mirrors the shape of `app/api/auth.py`'s Azure flow (login → redirect →
callback → store), but writes into Key Vault keyed by `team_member_id`
(resolved from the current session's `user_upn` → `team_members.azure_upn`
lookup, same join `chat.md`'s pre-fetch already uses) instead of session id.

- `GET /oauth/jira/connect` — redirect to JIRA's authorize URL, `oauth_state`
  cookie set (reusing the existing mechanism).
- `GET /oauth/jira/callback` — state check, code exchange, resolve cloud ID,
  write the access token to Key Vault as `user-{team_member_id}-jira-access`
  and the refresh token as `user-{team_member_id}-jira-refresh`, `UPDATE
  team_members SET jira_cloud_id = ...` (the only piece that's not itself a
  secret), redirect to `/oauth/connect` (see below) or straight into the
  conversation if this was the second/last provider connected.
- `GET /oauth/github/connect` / `GET /oauth/github/callback` — same shape,
  writing `user-{team_member_id}-github`.
- `POST /oauth/jira/disconnect` / `POST /oauth/github/disconnect` — CSRF-token
  protected (same pattern as `/auth/logout`), deletes that provider's Key
  Vault secret(s) for the current user without touching the Azure session
  itself. This is now the *only* way a token is removed — logout no longer
  implies disconnect (see below).

### Connect prompt: once per user, not once per login (revised from an
earlier session-scoped draft where this was a mandatory every-login gate)

`GET /auth/callback` (Azure login) redirects to `/` as before *if* the user
already has both providers connected (Key Vault secrets exist for their
`team_member_id`) — this is now the common case for a returning user, since
connections persist. Only a user missing one or both connections (first
login ever, or after an explicit disconnect / provider-side revocation) gets
routed to the `GET /oauth/connect` interstitial, which:

- Renders "Connect JIRA" / "Connect GitHub" as two explicit actions (buttons
  into `/oauth/jira/connect` / `/oauth/github/connect`), each showing
  Connected/Not connected based on whether that provider's Key Vault secret(s)
  currently exist for this user.
- Only allows proceeding into the app (a "Continue" link/redirect to `/`)
  once **both** are connected — still a hard gate on *first* reaching a
  usable state, since pre-fetch and every tool call need real tokens to do
  anything useful (per the isolation model, there's no shared fallback
  credential). The gate now fires rarely (first login, or after a disconnect/
  revocation) rather than on every login.
- Each `/oauth/{provider}/callback` redirects back to `/oauth/connect` rather
  than `/` directly, so connecting JIRA first naturally lands the user back
  on the same screen to connect GitHub next, and vice versa.

`GET /conversations/{id}` (and by extension `GET /`, which redirects into it)
can still assume both tokens exist for any session that reaches it — the
gate is still what makes that assumption hold, just checked against
per-user persisted state instead of re-earned every login. No "neither
connected, skip pre-fetch" branch to design for; `chat.md`'s pre-fetch
section is unaffected by this revision.

## Client rework (`app/integrations/jira_client.py`, `github_client.py`)

- `jira_client.build_client` changes signature from
  `(base_url: str, email: str, api_token: str)` to
  `(access_token: str, cloud_id: str)` — Bearer auth against
  `https://api.atlassian.com/ex/jira/{cloud_id}` instead of Basic auth against
  a configured site URL. `find_account_id_by_email`/`get_issues_assigned_to`
  keep their existing shapes; only how the client itself is constructed changes.
- `github_client.build_client` keeps its existing `(token: str)` signature and
  Bearer-auth shape unchanged — only the caller now passes the current user's
  persisted OAuth token instead of `Settings.github_token`.
- `utils/jira_connect_check.py`, `utils/github_connect_check.py`,
  `utils/jira_seed_data.py`, `utils/github_seed_data.py` (timeline step 5) are
  standalone scripts that read `.env` directly and are **not** part of the
  app's request path — they keep using the demo accounts' real credentials
  (Basic auth / PATs) as-is, since they exist to seed/validate data outside any
  user session. Not affected by this spec.

## `Settings` changes (`app/config.py`)

Removed: `jira_base_url`, `jira_project_key`, `jira_email`, `jira_api_token`,
`github_token`, `github_repo`.

Added: `jira_oauth_client_id`, `jira_oauth_client_secret`,
`jira_oauth_redirect_uri`, `github_oauth_client_id`,
`github_oauth_client_secret`, `github_oauth_redirect_uri`.

## Tool/pre-fetch rework (`chat.md`'s `JiraTool`/`GithubTool`, pre-fetch section)

- `ActivityTool.execute()` signature gains the current user's provider
  token(s) as an explicit argument (resolved from Key Vault by the route,
  passed down through `ChatService`, not self-fetched from `Settings` —
  consistent with the framework-agnostic, args-not-globals pattern the
  integration clients already follow).
- Pre-fetch (`chat.md`'s "Pre-fetch, cached per conversation" section) now
  also discovers and caches the "top projects"/"top repos"/"top collaborators"
  scope described above, alongside the existing "my tickets"/"my commits"
  fetch — same `prefetched_at` gate, same `activity_items` upsert path, no
  new caching mechanism needed.
- No "not connected" fallback state to design for: the `/oauth/connect` gate
  (see Connect prompt above) means `GET /conversations/{id}` can only ever be
  reached by a user who already has both provider tokens in Key Vault —
  pre-fetch and every tool call can assume both exist, full stop.

## Consequence of persisting tokens: logout no longer revokes JIRA/GitHub access

Worth stating plainly since it's a real behavior change from the original
session-scoped draft, not just a storage-location detail: `POST /auth/logout`
still revokes the *Azure* session (`sessions.revoked_at`, per MVP-NFR-5/
MVP-FR-2, unchanged) but no longer touches JIRA/GitHub tokens at all — those
now live independently of any session and are only removed by an explicit
`POST /oauth/{provider}/disconnect` or by the provider itself revoking
access. A user who signs out and back in returns straight to a usable chat
without reconnecting anything. This is the accepted tradeoff of the revision
above (Key Vault already provides encryption-at-rest; the previous
session-tied lifetime was solving a UX-consistency goal, not an additional
safety property) — flagged here so it isn't discovered as a surprise later
by someone expecting sign-out to be a full credential reset the way Azure's
own session is.

## Explicitly out of scope for this spec

- Resolving a project/repo the model needs but that wasn't in the pre-fetched
  "top N" — the model can only reach for what pre-fetch discovered; there's no
  live "search my other projects" tool in this pass.
- Multi-site JIRA (a user with access to more than one Atlassian site) beyond
  what `accessible-resources` naturally returns — pre-fetch takes the first/
  most-relevant site if multiple come back; a full multi-site picker UI is not
  built.
- Local-dev Key Vault fallback strategy — moot as of the token-persistence
  revision above: local dev uses the real Key Vault unconditionally, no
  fallback to design.
- Self-service identity-*linking* UI (a team member connecting their own
  JIRA/GitHub identity to their Azure account, as opposed to authenticating
  API calls) — `MVP-FR-8`'s static `team_members` seed table is unchanged by
  this spec; this remains a real, currently-untracked gap (see
  `implementation_log.md`).
- Deeper changes to the Azure SSO flow itself beyond the callback redirect
  target — this spec adds two more independent OAuth connections gated behind
  the existing login session and redirects `/auth/callback` through the new
  `/oauth/connect` interstitial before reaching `/`, but doesn't otherwise
  touch how that session is established.

## Trackers to update once implemented

- `blueprints/requirements/features.md`: un-defer NMVP-FR-2 into MVP under a
  rewritten description (per-user OAuth for API calls, not identity-linking
  UI — already done during Phase -1/Phase 0, see `implementation_log.md`),
  rewrite MVP-NFR-3's description (service-account language no longer
  applies).
- `blueprints/plans/features/chat.md`: "Auth model for JIRA/GitHub calls"
  section replaced with a pointer to this file.
- `blueprints/specs/stack-and-infra.md`: `.env.example`/`Settings` inventory
  update once the config changes above land; note the narrow MVP exception to
  the "no vault" stance (Key Vault used for OAuth tokens specifically), and
  that local dev now requires live Key Vault access as a hard prerequisite
  (same posture as the existing Azure AD SSO local-dev prerequisite).
- `blueprints/deployment.md`: add Key Vault to the provisioned-resources list
  (`scripts/azure/provision.sh`) and the Managed Identity role assignment
  (plus granting the developer's own `az login` identity the same access, for
  local dev), alongside the existing Postgres/App Service/ACR resources.
- `CHANGELOG.md`: dated entry once this spec lands.
