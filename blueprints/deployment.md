# Deployment Plan (Azure + JIRA/GitHub sandboxes)

Covers timeline.md step 4 ("Deploy hello world to Microsoft Azure") plus the sandbox
JIRA/GitHub accounts needed for MVP-NFR-7 (3 demo users) and MVP-NFR-3 (auth against
JIRA/GitHub/OpenRouter). This is a **throwaway deployment**: not expected to stay live
more than about a week, so several choices below deliberately favor low setup cost and
easy teardown over production-grade rigor.

Status: **plan only, not yet executed.** Nothing in this document has been run against
real infra yet — this is the agreed shape, pending sign-off, before any `az`/`gh`/JIRA
commands are actually issued.

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
- **Deploy mechanism for this pass**: direct `az`/`docker` deploy commands run now.
  The `.github/workflows/deploy.yml` stub (already required by
  `blueprints/specs/stack-and-infra.md`) is left as a `workflow_dispatch`-only stub
  with no real Azure credentials wired into GitHub Secrets — avoids standing
  credentials in GitHub for a one-week app. Wiring real CI/CD deploy is deferred
  (matches NMVP-NFR-7, non-MVP).
- **GitHub demo identities**: one throwaway public repo under the user's own existing
  GitHub account (no new GitHub accounts created). A Personal Access Token
  (fine-grained, read-only: Contents, Pull requests, Metadata) is scoped to just that
  repo. All 3 demo team members map to commits/PRs in this single repo; distinct
  "committers" are represented via `git commit --author` identity per commit, not via
  3 separate real GitHub accounts.
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

1. Claude creates one throwaway public repo under the user's GitHub account (with
   confirmation before creation).
2. User generates a fine-grained PAT scoped to just that repo (read-only: Contents,
   Pull requests, Metadata) and shares it via `.env` (not committed).
3. Claude seeds commits (varied `--author` identities) and a couple of PRs into the
   repo, enough to exercise MVP-FR-10 (recent commits, active PRs, contributed
   repos) once that feature is implemented.

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

## Open items / risks

- Azure free-tier quota limits (vCPU/region availability) are unknown until
  `provision.sh` is actually run — may require a fallback region or SKU.
- JIRA free tier's 10-user cap is not a concern at 3 users, but worth noting if the
  roster ever grows (see NMVP-FR-9 in features.md).
- Teardown must actually be run at the end of the week — this plan does not include
  an automated reminder/expiry; flagging here so it isn't forgotten.
