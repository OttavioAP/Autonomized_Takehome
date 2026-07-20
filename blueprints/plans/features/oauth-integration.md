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

- **Session-scoped, not persisted across logins.** JIRA/GitHub OAuth tokens
  live only for the lifetime of the session that connected them — never
  written anywhere that outlives the session. Sign-out or session expiry
  destroys them, same as the Azure claims already conceptually are. No
  `oauth_connections` table, no reconnect-across-logins UX to design for. This
  holds regardless of what each provider's own tokens are technically capable
  of (see the expiry asymmetry below) — a deliberate choice for consistency,
  not a limitation either provider forces on us.
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
  short-lived access tokens plus a rotating refresh token that itself dies
  after 90 days of inactivity; the user *must* eventually re-authorize no
  matter what we build. GitHub OAuth Apps (classic), by contrast, issue tokens
  that are genuinely non-expiring by default — "OAuth tokens remain active
  until they're revoked by the customer" (GitHub's own docs) — no forced
  expiry, no refresh cycle, unless the user or an org admin revokes access.
  **This project treats both the same anyway** (session-scoped, discarded at
  logout) for consistency — not because JIRA forces it, but because a
  two-tier model (GitHub persisted, JIRA not) was considered and rejected in
  favor of one predictable connect-each-session UX for both providers (see
  Connect prompt below).
- **Token expiry mid-session**: re-prompt to reconnect, not silent refresh.
  Deliberate simplification given tokens don't outlive the session anyway —
  building rotating-refresh-token handling (JIRA's model) for a credential
  that's discarded within a few hours of being issued isn't worth the
  complexity. If a call 401s, the tool surfaces `ToolExecutionError` same as
  any other upstream failure (per `chat.md`'s error model) and the user
  reconnects via the same flow as a first-time connect.

## Scope discovery, not fixed config

`JIRA_PROJECT_KEY`, `GITHUB_REPO`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `GITHUB_TOKEN`
are removed from `Settings` entirely — there is no longer a single
project/repo the whole app is pointed at. Instead, **pre-fetch discovers scope
per user**, same shape as the existing "fetch the logged-in user's own activity"
pre-fetch in `chat.md`, extended to also resolve *where* to look:

- **JIRA**: pre-fetch reuses `sessions.jira_cloud_id` — already resolved once
  during `GET /oauth/jira/callback` via `accessible-resources` — rather than
  calling that endpoint a second time. (Resolved via direct discussion: this
  is the whole reason that column exists on `sessions` in the first place;
  re-deriving it independently in pre-fetch would be a redundant call for no
  benefit.) For that cloud ID, fetch the user's own recent/assigned-issue
  projects — "top projects" becomes part of the pre-fetched context alongside
  the existing "my tickets" data.
- **GitHub**: the user's own recent repos (`GET /user/repos`, sorted by recent
  push) and recent collaborators/orgs — "top repos" alongside "my commits/PRs."
- **Top-N**: `Settings.discovery_top_n: int = 10` (new config field, env-var
  overridable like `max_tool_call_rounds` in `chat.md`) — applies uniformly to
  JIRA top projects, GitHub top repos, *and* top collaborators/org members
  discovered alongside them (all three use the same cutoff, one config knob,
  not three).
- **Shape**: richer objects, not bare identifier strings — `JiraProjectRef(key:
  str, name: str)` / `GithubRepoRef(full_name: str, description: str | None)`
  (exact fields TBD at implementation time; `key`/`full_name` are the values
  `JiraToolParams.project_key`/`GithubToolParams.repo` expect back from the
  model). Chosen over a flat list of identifiers so the model can reference a
  project/repo by its human name in prose ("in the *My Software Team*
  project") while still citing back the machine key/slug the tools need —
  matches the richer shape already used for `activity_items`/the team roster,
  rather than introducing a second, sparser convention just for this context.

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
  (`read:jira-work read:jira-user offline_access` — `offline_access` requests a
  refresh token, kept even though this spec doesn't build refresh handling, so
  the door isn't closed if that changes later).
- **Authorize URL**: `https://auth.atlassian.com/authorize` with
  `audience=api.atlassian.com`, `client_id`, `scope`, `redirect_uri`, `state`,
  `response_type=code`, `prompt=consent`.
- **Token exchange**: `POST https://auth.atlassian.com/oauth/token` →
  `access_token`, `expires_in`, `refresh_token`.
- **Cloud ID resolution**: `GET https://api.atlassian.com/oauth/token/accessible-resources`
  (Bearer `access_token`) → list of `{id, url, scopes}` per accessible site.
  The resolved cloud ID is stored on the `sessions` row itself (see Token
  storage below — it isn't a secret, so it doesn't need Key Vault) so it isn't
  re-fetched on every tool call within the same session.
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
  into token expiration) — simpler than JIRA's rotating-refresh model, and
  consistent with "re-prompt on 401" being sufficient since the token is
  discarded at session end regardless of its own lifetime.
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
for these session tokens specifically** (a deliberate, narrow exception to
NMVP-NFR-2 still being non-MVP everywhere else — `DATABASE_URL`,
`OPENROUTER_API_KEY`, etc. stay as plain env vars/GitHub Actions secrets,
unchanged).

- **No new persistent table, no new `sessions` columns.** The `sessions` row
  keeps only a reference, not the token itself:

  | Column | Type | Notes |
  |---|---|---|
  | `jira_cloud_id` | text, nullable | Resolved once at connect time via `accessible-resources`; not a secret, safe to keep in Postgres alongside the session row |

  The actual `jira_access_token`/`github_access_token` values live as Key
  Vault secrets, named deterministically from the session id
  (`session-{session_id}-jira`, `session-{session_id}-github`) so no separate
  mapping table is needed — the session id is already the lookup key.
- **Auth to Key Vault**: the App Service uses a **system-assigned Managed
  Identity**, granted `get`/`set`/`delete` on secrets via a Key Vault access
  policy (or RBAC role `Key Vault Secrets Officer`, scoped to just this
  vault) — no separate Key Vault credential to provision, store, or rotate;
  Azure handles the identity. Local dev needs an equivalent: either the
  developer's own `az login` identity (if granted access to the same vault)
  or a local fallback (plaintext env-var-backed in-memory store) so `make up`
  doesn't require live Azure connectivity for every local session — **decide
  at implementation time** which fallback is less friction; not resolved here.
- **Expiry**: Key Vault secrets support a `expires_on` attribute set at
  creation — set to the session's own `expires_at` (8 hours, matching
  `UserSession`), so a token outlives its own session by construction, not
  just by convention. Sign-out (`POST /auth/logout`) additionally issues an
  explicit delete for both secret names, same transaction boundary as marking
  the session `revoked_at` — belt-and-suspenders with the TTL rather than
  relying on TTL alone (Key Vault's soft-delete means an expired secret isn't
  instantly purged, so an explicit delete matters if "gone" needs to mean
  "gone now," not "gone eventually").
- **No refresh-token storage** — still not stored, per the "re-prompt over
  refresh" decision above; this holds regardless of where the access token
  itself lives.

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

## Connect/disconnect UI + routes (`app/api/oauth.py`, new)

Mirrors the shape of `app/api/auth.py`'s Azure flow (login → redirect →
callback → store), but writes into Key Vault (keyed by session id) instead of
a session table column.

- `GET /oauth/jira/connect` — redirect to JIRA's authorize URL, `oauth_state`
  cookie set (reusing the existing mechanism).
- `GET /oauth/jira/callback` — state check, code exchange, resolve cloud ID,
  write the access token to Key Vault as `session-{session_id}-jira`
  (`expires_on` = the session's `expires_at`), `UPDATE sessions SET
  jira_cloud_id = ...` (the only piece that's not itself a secret), redirect
  to `/oauth/connect` (see below) or straight into the conversation if this
  was the second/last provider connected.
- `GET /oauth/github/connect` / `GET /oauth/github/callback` — same shape,
  writing `session-{session_id}-github`.
- `POST /oauth/jira/disconnect` / `POST /oauth/github/disconnect` — CSRF-token
  protected (same pattern as `/auth/logout`), deletes the relevant Key Vault
  secret without touching the Azure session itself.

### Mandatory connect prompt (revised from an earlier "optional, best-effort"
draft — connecting both providers is now a required step of signing in, not
something a user can skip and stay in a degraded state)

`GET /auth/callback` (Azure login) no longer redirects straight to `/` on
success. It redirects to a new interstitial, `GET /oauth/connect`, which:

- Renders "Connect JIRA" / "Connect GitHub" as two explicit actions (buttons
  into `/oauth/jira/connect` / `/oauth/github/connect`), each showing
  Connected/Not connected based on whether that provider's Key Vault secret
  currently exists for this session.
- Only allows proceeding into the app (a "Continue" link/redirect to `/`)
  once **both** are connected — this is a hard gate, not a dismissible
  prompt, since pre-fetch and every tool call need real tokens to do anything
  useful at all (per the isolation model, there is no shared fallback
  credential to fall back to anymore).
- Each `/oauth/{provider}/callback` redirects back to `/oauth/connect` rather
  than `/` directly, so connecting JIRA first naturally lands the user back
  on the same screen to connect GitHub next, and vice versa.
- Session-scoped, so this repeats every login (consistent with tokens never
  persisting past sign-out) — a returning user reconnects both providers each
  time they sign in, not just the first time ever.

`GET /conversations/{id}` (and by extension `GET /`, which redirects into it)
can now assume both tokens exist for any session that reaches it — no
"neither connected, skip pre-fetch" branch to design for, since that state is
unreachable past the gate. Simplifies `chat.md`'s pre-fetch section
accordingly (a partial-connection or no-connection system-prompt fallback is
no longer needed — removed as a design concern here, not deferred).

## Client rework (`app/integrations/jira_client.py`, `github_client.py`)

- `jira_client.build_client` changes signature from
  `(base_url: str, email: str, api_token: str)` to
  `(access_token: str, cloud_id: str)` — Bearer auth against
  `https://api.atlassian.com/ex/jira/{cloud_id}` instead of Basic auth against
  a configured site URL. `find_account_id_by_email`/`get_issues_assigned_to`
  keep their existing shapes; only how the client itself is constructed changes.
- `github_client.build_client` keeps its existing `(token: str)` signature and
  Bearer-auth shape unchanged — only the caller now passes a session's OAuth
  token instead of `Settings.github_token`.
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

- `ActivityTool.execute()` signature gains the session's provider token(s) as
  an explicit argument (passed down from the route via `ChatService`, not
  self-fetched from `Settings` — consistent with the framework-agnostic,
  args-not-globals pattern the integration clients already follow).
- Pre-fetch (`chat.md`'s "Pre-fetch, cached per conversation" section) now
  also discovers and caches the "top projects"/"top repos" scope described
  above, alongside the existing "my tickets"/"my commits" fetch — same
  `prefetched_at` gate, same `activity_items` upsert path, no new caching
  mechanism needed.
- No "not connected" fallback state to design for: the mandatory `/oauth/connect`
  gate (see Connect prompt above) means `GET /conversations/{id}` can only ever
  be reached by a session that already has both provider tokens in Key Vault —
  pre-fetch and every tool call can assume both exist, full stop.

## Explicitly out of scope for this spec

- Refresh-token handling for JIRA's rotating refresh tokens — tokens are
  session-scoped and short-lived by design; re-prompting to reconnect on
  expiry is the whole story.
- Resolving a project/repo the model needs but that wasn't in the pre-fetched
  "top N" — the model can only reach for what pre-fetch discovered; there's no
  live "search my other projects" tool in this pass.
- Multi-site JIRA (a user with access to more than one Atlassian site) beyond
  what `accessible-resources` naturally returns — pre-fetch takes the first/
  most-relevant site if multiple come back; a full multi-site picker UI is not
  built.
- Local-dev Key Vault fallback strategy (plaintext env-var store vs. shared
  dev vault access) — flagged as "decide at implementation time" in the Token
  storage section above, not resolved here.
- Deeper changes to the Azure SSO flow itself beyond the callback redirect
  target — this spec adds two more independent OAuth connections gated behind
  the existing login session and redirects `/auth/callback` through the new
  `/oauth/connect` interstitial before reaching `/`, but doesn't otherwise
  touch how that session is established.

## Trackers to update once implemented

- `blueprints/requirements/features.md`: un-defer NMVP-FR-2 into MVP (or
  re-number if the team prefers keeping the NMVP-FR-2 id but moving it into
  the MVP table — decide at implementation time), rewrite MVP-NFR-3's
  description (service-account language no longer applies).
- `blueprints/plans/features/chat.md`: "Auth model for JIRA/GitHub calls"
  section replaced with a pointer to this file.
- `blueprints/specs/stack-and-infra.md`: `.env.example`/`Settings` inventory
  update once the config changes above land; note the narrow MVP exception to
  the "no vault" stance (Key Vault used for session OAuth tokens specifically).
- `blueprints/deployment.md`: add Key Vault to the provisioned-resources list
  (`scripts/azure/provision.sh`) and the Managed Identity role assignment,
  alongside the existing Postgres/App Service/ACR resources.
- `CHANGELOG.md`: dated entry once this spec lands.
