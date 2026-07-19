# Deployment Plan (Azure + JIRA/GitHub sandboxes)

Covers timeline.md step 4 ("Deploy hello world to Microsoft Azure") plus the sandbox
JIRA/GitHub accounts needed for MVP-NFR-7 (3 demo users) and MVP-NFR-3 (auth against
JIRA/GitHub/OpenRouter). This is a **throwaway deployment**: not expected to stay live
more than about a week, so several choices below deliberately favor low setup cost and
easy teardown over production-grade rigor.

Status: **Track A (Azure) executed and verified — hello-world is live.** Tracks B/C/D
(JIRA/GitHub sandboxes, fixtures) are in progress; see the sequenced plan below for
current per-step status.

## Decisions locked in (discussed and agreed before implementation)

- **No domain registration.** Azure App Service's free `*.azurewebsites.net` hostname
  is used as-is. No custom domain, no DNS/TLS cert setup.
- **Claude Code's Azure access**: `az login` run interactively by the user in this
  terminal (device-code flow, completed in the user's browser). Claude then drives
  `az` CLI commands directly via Bash under that logged-in identity. No Azure MCP
  server, no separate service principal for Claude's own access.
- **Azure CLI installation**: `pip install azure-cli` into an isolated, gitignored
  `.venv-azure/` at the repo root — not a system package (no `sudo apt`), and not
  added to `pyproject.toml`/`requirements.lock.txt` since it's ops tooling, not an app
  dependency.
- **Provisioning/deploy scripts**: committed to `scripts/azure/` (idempotent shell
  scripts), not run ad hoc and discarded — reusable and reviewable, consistent with
  the repo's existing `Makefile`-driven workflow style.
- **Deploy mechanism, revised mid-project**: initially direct `az`/`docker` deploy
  commands only, with `.github/workflows/deploy.yml` left as a `workflow_dispatch`-
  only stub (no standing Azure credentials in GitHub). **Later changed at the
  user's explicit request**: `deploy.yml` now auto-deploys on every push to `main`,
  gated on a `pytest` job passing first (`needs: test`). This required creating a
  standing Azure service principal credential stored in GitHub Actions secrets — a
  real tradeoff against the original "no standing credentials" position, accepted
  because (a) the SP is scoped to just the throwaway resource group via
  `contributor` role, not the subscription, and (b) the whole deployment is
  ~1-week-lived anyway. See "CI/CD auto-deploy" below for the full inventory.
- **GitHub demo identities**: 3 separate throwaway GitHub accounts, created and
  controlled by the user via 3 distinct ProtonMail addresses — one real GitHub
  account per demo team member. Each account gets its own fine-grained Personal
  Access Token (read-only: Contents, Pull requests, Metadata) scoped to a shared
  throwaway repo (or repos) all 3 accounts contribute to, so commit authorship and
  PR authorship are genuine per-account activity rather than faked `--author`
  identities.
- **JIRA demo identities**: one free JIRA Cloud site (Atlassian free tier supports up
  to 10 users), signed up by the user. Two additional real email addresses the user
  controls are invited as genuine site members, so all 3 demo team members correspond
  to real, distinct JIRA accounts (not just placeholder assignee display names).
- **Azure subscription**: user is signing up for a new Azure account/subscription
  (free tier, browser signup — outside Claude's access, user's action).

## Sequenced plan

### Track A — Azure infrastructure

1. User signs up for Azure (free tier) in browser. *(User action, no dependency on
   anything else below.)*
2. Claude installs Azure CLI into `.venv-azure/` (pip, no sudo).
3. User runs `az login` interactively (device code in browser); Claude verifies
   `az account show` resolves to the right subscription.
4. Claude writes `scripts/azure/provision.sh`:
   - Creates a resource group (name suffixed with a random token to avoid
     collisions, e.g. `team-activity-monitor-<suffix>`), default region `East US`
     unless the user prefers otherwise.
   - Provisions a PostgreSQL Flexible Server, burstable/smallest SKU, matching the
     Postgres major version already pinned in `docker-compose.yml` (16).
   - Provisions an Azure App Service (Linux, container-based) plan, smallest tier
     that supports always-on if needed for demo purposes (Basic B1), pointing at
     the existing `Dockerfile`.
   - Idempotent: safe to re-run without duplicating resources.
5. Claude writes `scripts/azure/deploy.sh`:
   - Builds the existing `Dockerfile` image, pushes to Azure Container Registry (or
     App Service's built-in registry, whichever needs less setup), and points the
     App Service at the new image.
   - Injects required env vars (`DATABASE_URL` pointed at the Flexible Server,
     `OPENROUTER_API_KEY`, JIRA/GitHub tokens) as App Service application settings —
     not committed anywhere, read from the user's local `.env` at deploy time.
6. Claude writes `scripts/azure/teardown.sh`:
   - Deletes the whole resource group in one command, cascading to every resource
     inside it. This is the "we're done after a week" button.
7. Deploy the **existing hello-world route** (already scaffolded per
   `blueprints/specs/stack-and-infra.md`) to Azure via `deploy.sh` — proves the path
   end-to-end before any further feature work, per timeline.md step 4's intent.
8. Manually verify the deployed hello-world route responds correctly over the
   `*.azurewebsites.net` URL.

### Track B — JIRA sandbox (independent of Track A)

1. User signs up for a free JIRA Cloud site and invites 2 additional real email
   addresses as site members.
2. User generates a JIRA API token
   (id.atlassian.com/manage-profile/security/api-tokens) and shares the site URL,
   login email, and token via `.env` (not committed).
3. Claude seeds demo issues across the 3 JIRA users via the JIRA REST API, enough to
   exercise MVP-FR-9 (assigned issues, status, recent updates) once that feature is
   implemented.

### Track C — GitHub sandbox (independent of Track A)

1. User creates 3 ProtonMail addresses and signs up 3 separate GitHub accounts, one
   per demo team member (browser signup, user's action — Claude cannot create
   GitHub accounts).
2. User (or one of the 3 new accounts) creates one throwaway public repo that all 3
   accounts have write/contributor access to.
3. User generates a fine-grained PAT per account, scoped to just that repo
   (read-only: Contents, Pull requests, Metadata — read-only is sufficient for
   Claude's later API calls even though the accounts themselves need write access
   to seed the data), and shares all 3 via `.env` (not committed). Only one token is
   actually needed at query-time (MVP-FR-10 fetches read-only), but seeding requires
   push access from each account.
4. Claude seeds genuine commits and a couple of PRs from each of the 3 accounts into
   the shared repo, enough to exercise MVP-FR-10 (recent commits, active PRs,
   contributed repos) once that feature is implemented.

### Track D — Fixtures & documentation

1. Add JIRA/GitHub env var placeholders to `.env.example` (done).
2. Build/extend `local-dev-data/team_members.json` — the identity-mapping fixture
   (MVP-FR-8) — resolving each of the 3 demo team members to their Azure identity
   (not applicable yet, pre-auth-implementation), JIRA account, and GitHub identity
   used in Tracks B/C.
3. Update `blueprints/requirements/timeline.md` (step 4 → Implemented/Tested/
   Deployed as appropriate) and `blueprints/requirements/features.md` (MVP-NFR-1,
   MVP-NFR-7, relevant rows) once each piece is genuinely done, not aspirationally.
4. Update `blueprints/specs/stack-and-infra.md` if any decision here changes or
   extends what's already recorded there (e.g. confirming App Service vs. other
   compute choice, actual Postgres SKU used).
5. Add a dated `CHANGELOG.md` entry summarizing what was actually deployed/created.

## Explicitly out of scope for this pass

- Custom domain / DNS / TLS certificates.
- Azure Key Vault / managed secrets vaulting (NMVP-NFR-2, non-MVP) — plain env vars
  via App Service application settings only, consistent with MVP-NFR-9.
- Real CI/CD wiring of `.github/workflows/deploy.yml` (NMVP-NFR-7, non-MVP).
- RBAC/multi-tenancy for the JIRA/GitHub sandbox accounts.
- Azure AD/Entra SSO app registration — that's a separate, already-specced piece of
  work (MVP-FR-1/MVP-NFR-2) tracked in `blueprints/specs/stack-and-infra.md`, not
  part of this deployment pass.

## CI/CD auto-deploy (added after initial deploy, at user request)

`.github/workflows/deploy.yml` has two jobs:
- **`test`**: builds the Docker image, runs `pytest` inside it (`docker run --rm
  <image> pytest`) — no compose stack needed since current tests don't touch a
  real DB.
- **`deploy`** (`needs: test`, so it never runs if tests fail): builds/pushes the
  image to ACR tagged with `${{ github.sha }}`, points the Web App at it, sets app
  settings, and restarts (twice — see the interrupted-pull note above, ported into
  this workflow too).

Triggers on push to `main` and manual `workflow_dispatch`.

**GitHub Actions secrets set on `OttavioAP/Autonomized_Takehome`:**
- `AZURE_CREDENTIALS` — service principal JSON (`az ad sp create-for-rbac
  --sdk-auth`), `contributor` role scoped to just the
  `team-activity-monitor-a8b9a7` resource group, not the subscription.
- `AZURE_RESOURCE_GROUP`, `AZURE_WEBAPP_NAME`, `ACR_NAME`, `ACR_LOGIN_SERVER` —
  plain identifiers, mirror `scripts/azure/.state`.
- `DATABASE_URL` — same connection string `deploy.sh` uses locally (includes the
  Postgres admin password).
- `OPENROUTER_API_KEY` — copied from local `.env`.
- `JIRA_BASE_URL`/`JIRA_EMAIL`/`JIRA_API_TOKEN`, `GH_INTEGRATION_TOKEN`/
  `GH_INTEGRATION_REPO` — referenced in the workflow but **not yet set** as of this
  writing (Tracks B/C still in progress); they'll inject as empty strings until
  set, which doesn't break the hello-world app.

The GitHub PAT used to authenticate `gh` for this (`My_Github_PAT`, stored in
local `.env`) is a broad classic PAT with far more scope (`admin:org`,
`delete_repo`, `admin:enterprise`, etc.) than this task needs — worth rotating to
a fine-grained PAT scoped to just this repo with `repo`+`workflow` permissions if
this setup outlives the throwaway week.

**Two real bugs hit and fixed while getting the first CI run green** (verified
live at `https://team-activity-monitor-a8b9a7.azurewebsites.net/`, both `/` and
`/ping` returning 200 with correct `https://` asset links, after 4 failed runs):

1. `ACR_NAME`, `ACR_LOGIN_SERVER`, `AZURE_RESOURCE_GROUP`, and `AZURE_WEBAPP_NAME`
   were originally set via `echo "$VAR" | gh secret set ...` — plain `echo`
   appends a trailing newline, which got baked into the secret value. This broke
   `az acr login --name "tamacra8b9a7\n"` with a misleading "resource could not be
   found in subscription" error (looked like an RBAC/permissions problem, wasted
   time chasing an `AcrPush` role grant that turned out to be unnecessary — plain
   `contributor` on the resource group is sufficient). The tell: GitHub's log
   masking (`***`) rendered the secret across two log lines instead of one,
   which is what actually gave it away. **Fix: always use `printf '%s' "$VAR" |
   gh secret set ...`, never `echo`, for secrets that get shell-interpolated
   downstream.**
2. While locally testing whether the service principal's role assignment was the
   problem, `az ad app credential reset --append` was run twice to generate test
   secrets, then the credentials were deleted in the wrong order — ending up
   deleting the *original* credential (the one whose value was already stored in
   the `AZURE_CREDENTIALS` GitHub secret) rather than the test ones. This
   surfaced as `AADSTS7000215: Invalid client secret provided` on the *next* run,
   a completely different error from bug #1, right after #1 seemed fixed — easy
   to mistake for a new, unrelated failure. Fix: generated one fresh credential,
   rebuilt the full `--sdk-auth`-shaped JSON around it, re-uploaded to
   `AZURE_CREDENTIALS`. **Lesson: don't test a service principal's credentials by
   resetting/deleting them ad hoc once a real secret already depends on the
   current value — reset, capture the new value, and immediately re-sync
   wherever it's stored, in the same breath.**

## Azure AD SSO provisioning (MVP-FR-1/FR-2, MVP-NFR-2 prerequisite)

Provisioned ahead of implementing the actual login/logout routes, since
`stack-and-infra.md` calls out a working Azure AD app registration as a real local-dev
prerequisite, not an afterthought.

- **3 Azure AD user accounts** created in the tenant (`ottavioantperuzzigmail.onmicrosoft.com`,
  a personal "Default Directory" where the signed-in `az` user already holds Global
  Administrator — confirmed via `az rest GET /me/memberOf` before creating anything):
  `john@`, `sarah@`, `mike@ottavioantperuzzigmail.onmicrosoft.com`, matching the
  John/Sarah/Mike identities already seeded in `local-dev-data/team_members.json`.
  Each has its own generated password, deliberately separate from the
  Protonmail/JIRA/GitHub credentials — so anyone demoing the app (e.g. an interviewer)
  logs in with a throwaway Azure identity, not a real inbox's credentials. Credentials
  are in `.env` (`Azure_{John,Sarah,Mike}_{UPN,Password}`), not committed.
- **App registration** "Team Activity Monitor - Local Dev" (confidential client,
  `AzureADMyOrg` single-tenant audience), with **two** redirect URIs:
  `http://localhost:8000/auth/callback` (local dev) and
  `https://team-activity-monitor-a8b9a7.azurewebsites.net/auth/callback` (deployed
  instance). Client secret generated (1 year validity). `AZURE_TENANT_ID`,
  `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, `AZURE_REDIRECT_URI` added to `.env` and
  `app.config.Settings`; the deployed app gets its own `AZURE_REDIRECT_URI` value
  (`AZURE_REDIRECT_URI_PROD` secret) via `deploy.yml`'s appsettings step, since the two
  environments need different callback URLs registered against the same app.
- **Delegated Graph permissions** (`openid`, `profile`, `email`, `User.Read`) added and
  admin-consented tenant-wide (`AllPrincipals`), so all 3 users can complete the OIDC
  flow without an individual per-user consent prompt.
- **Login/logout routes implemented** (`app/api/auth.py`, `app/auth/oidc.py`,
  `app/auth/dependency.py`): `GET /auth/login` redirects to Azure with a CSRF-safe
  `state` param stored in a short-lived cookie; `GET /auth/callback` validates that
  state, exchanges the code for tokens, validates the ID token's signature against
  JWKS (issuer/audience/expiry), creates a `sessions` row, and sets the opaque session
  cookie; `POST /auth/logout` is CSRF-token-protected and marks the session revoked.
  `get_current_user` (the single shared enforcement dependency) protects `/` and
  redirects unauthenticated HTML requests to `/login` rather than raising a raw 401.
  17 automated tests pass, including a regression test that hits Microsoft's real
  authorize endpoint (caught a real bug during development: `authority()` and
  `issuer()` need to be different base URLs — `/oauth2/v2.0/authorize` hangs off the
  tenant root, not off `/v2.0`, which is only the OIDC issuer claim's own path).
- **CI updated to match**: `deploy.yml`'s `test` job previously ran
  `docker run --rm image pytest` with zero env vars and no Postgres — it happened to
  pass before only because no test exercised `Settings()`/the DB at import time. Once
  `get_current_user` made that import-time `Settings()` load unavoidable, CI started
  failing. Fixed by adding a `postgres:16` service container, running
  `alembic upgrade head` before `pytest` inside the built image (connected via
  `--network=host`), and passing all required env vars from secrets. Also added the 10
  JIRA/GitHub/Azure secrets that were missing from GitHub Actions (the `deploy` job's
  appsettings step was already referencing several of these secrets before they
  existed — a pre-existing gap, not something introduced here).

## Open items / risks

- JIRA free tier's 10-user cap is not a concern at 3 users, but worth noting if the
  roster ever grows (see NMVP-FR-9 in features.md).
- Teardown must actually be run at the end of the week — this plan does not include
  an automated reminder/expiry; flagging here so it isn't forgotten. **Now also covers
  the 3 Azure AD users and the app registration created for SSO** — not just the
  webapp/Postgres/ACR resources from Track A.

## Execution notes (what actually happened, Track A)

- **New Azure subscriptions start on `FreeTrial_2014-09-01` quota**, which silently
  blocks Postgres Flexible Server creation in `eastus` with an opaque "location is
  restricted" error (no useful detail from `az`). Fix: upgrade the subscription to
  Pay-As-You-Go billing in the Azure Portal (still draws down the free credit first;
  no cost unless the credit is exceeded). This unblocked Postgres, but not compute.
- **Separately, this subscription has a 0-VM App Service/compute quota in `eastus`**
  (and `eastus2`/`westus`), confirmed via `Operation cannot be completed without
  additional quota` on both B1 and F1 (free) App Service plan tiers — a distinct
  restriction from the Postgres one above, not fixed by the billing upgrade alone.
  Trial-and-error across regions found **`centralus` and `westus2` have working
  compute quota** on this subscription; `centralus` was chosen since Postgres also
  landed there. **Resolution: the resource group and ACR stay in `eastus`
  (`LOCATION`), but Postgres Flexible Server and the App Service plan/webapp are
  pinned to `centralus` (`COMPUTE_LOCATION`)** — see `scripts/azure/lib.sh`. A
  resource group can hold resources from multiple regions, so this is not a
  functional problem, just a naming/tracking one now captured in
  `scripts/azure/.state`.
- `az postgres flexible-server db create` takes `--name`, not `--database-name` as
  originally drafted in `provision.sh` — fixed.
- `--deployment-container-image-name` is deprecated in favor of
  `--container-image-name` on `az webapp create` — fixed.
- **`deploy.sh` originally `source`d `.env` directly**, which shell-evaluates its
  contents — real secret values containing `$`, `` ` ``, or `#` (e.g. a GitHub
  account password like `gwefjweas#$3`) broke this under `set -u` ("unbound
  variable: $3"). Fixed by parsing `.env` line-by-line as inert `KEY=VALUE` text
  instead of sourcing it as shell.
- Docker required `sudo`/group membership on this machine (`oz` wasn't in the
  `docker` group). `sg docker -c "<command>"` runs a command under the `docker`
  group within the current session without needing a fresh login shell — used this
  instead of blocking on a new terminal session after `usermod -aG docker oz`.
- End-to-end result: hello-world deployed and verified live at
  `https://team-activity-monitor-a8b9a7.azurewebsites.net/` (200 OK, htmx `/ping`
  fragment route also verified working) via `scripts/azure/provision.sh` +
  `scripts/azure/deploy.sh`.
- **Mixed-content bug**: the deployed page initially rendered `<link>`/`<script>`
  tags with `http://` URLs on an `https://`-served page (browser blocked them,
  breaking both styling and htmx). Root cause: Azure App Service terminates TLS at
  its edge and forwards to the container over plain HTTP, so Uvicorn/Starlette's
  `url_for()` saw every request as `http://` by default. Fixed by adding
  `--proxy-headers --forwarded-allow-ips=*` to the Dockerfile's `uvicorn` CMD, so
  Uvicorn honors Azure's `X-Forwarded-Proto: https` header when building absolute
  URLs. Confirmed via a temporary `/debug-headers` diagnostic route (added, used to
  inspect `request.scope["scheme"]` and the raw incoming headers, then removed) —
  Azure does send `x-forwarded-proto: https` on every request, once at the
  `centralus` App Service reached by the fix.
- **Intermittent interrupted-pull-on-restart**: twice observed, after
  `az webapp config container set` + the restart deploy.sh triggers, the Docker log
  shows `Container pull image interrupted. Revert by terminate.` — the site then
  reports `state=Running` via `az webapp show` while actually serving nothing
  (every request times out). A second `az webapp restart` reliably recovers it both
  times. Root cause not fully understood (possibly the config-triggered restart and
  the explicit restart racing each other); `deploy.sh` now issues a second restart
  automatically as cheap insurance. If this recurs and a third restart is ever
  needed, treat that as a signal to investigate further rather than keep adding
  restarts.
