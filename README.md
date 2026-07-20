# Team Activity Monitor

A chat app that answers "what is X working on these days?" by combining a team member's JIRA and GitHub activity into one conversational answer, with clickable citations back to the source ticket/PR/commit/comment.

**Stack**: FastAPI (async) + htmx/Jinja2 (server-rendered, no build step) + Postgres/SQLAlchemy + Alembic, deployed on Azure. See `blueprints/specs/stack-and-infra.md` for the full rationale.

## Setup

1. **Clone and configure**: `cp .env.example .env`, then fill in every value (see [API integrations](#api-integrations) below for where each credential comes from).
2. **Start everything**: `make up-dev` — brings up Postgres + FastAPI in Docker, applies migrations, and seeds the 3 demo team members (John/Sarah/Mike) plus their JIRA/GitHub activity. Use `make up` for a plain start without the reset/reseed cycle.
3. **Local Azure Key Vault access**: this app has zero secrets-vaulting fallback — local dev talks to a real Azure Key Vault via your own signed-in identity. Run `az login` on the host once; `docker-compose.override.yml` mounts `~/.azure` into the `fastapi` container automatically, and `Dockerfile.dev` (not the production `Dockerfile`) bundles the `az` CLI for this.
4. Visit `http://localhost:8000` — you'll be redirected to Azure AD sign-in, then (on first login) to a one-time JIRA/GitHub connect screen, then into the chat.

Other useful targets: `make test` (pytest in-container), `make migrate` / `make revision name="..."` (Alembic), `make shell` (drop into the container), `make logs`.

## API integrations

- **JIRA** — OAuth 2.0 (3LO), per logged-in user, not a shared service credential: each person connects their own JIRA account once via `/oauth/jira/connect`, and every ticket/comment fetch afterward runs as that person, including a silent access-token refresh on expiry. Register an OAuth 2.0 (3LO) app at [developer.atlassian.com/console/myapps](https://developer.atlassian.com/console/myapps) with the `read:jira-work`/`read:jira-user`/`offline_access` scopes and a redirect URI matching `JIRA_OAUTH_REDIRECT_URI`; the app must be moved out of "Not distributed" status (Distribution tab) before any account outside your own org can complete consent.
- **GitHub** — OAuth App (classic, not a GitHub App), same per-user model as JIRA, used to fetch commits/PRs/reviews/comments as the connecting user. GitHub tokens don't expire, so there's no refresh step — a 401 means real revocation. Register at [github.com/settings/developers](https://github.com/settings/developers); GitHub allows only one callback URL per app, so local dev and production need two separate app registrations (local credentials go in `.env`, prod credentials go in GitHub Actions secrets — see `deploy.yml`).
- **OpenRouter** — the LLM backend (`anthropic/claude-sonnet-4.5` for chat, `google/gemini-2.5-flash` for lighter calls), reached with a single Bearer-token service credential (`OPENROUTER_API_KEY`) rather than per-user auth, since there's no per-user identity concept on the model-provider side. Supports streaming plus tool-calling, which is how the chat model decides to fetch JIRA/GitHub data mid-conversation.
- **Azure AD SSO** — the app's own login. A confidential-client OIDC flow (`app/auth/oidc.py`) authenticates users against your organization's Azure AD tenant rather than a locally-managed password store; register an app in Azure Portal → App registrations with a web redirect URI matching `AZURE_REDIRECT_URI`, and grant it standard `openid`/`profile`/`email` scopes.
- **Azure Key Vault** — stores every user's JIRA/GitHub OAuth tokens (access + refresh), keyed by `team_member_id`, surviving sign-out. Both the deployed app (via its Managed Identity) and local developers (via their own `az login` identity) need `Key Vault Secrets Officer` on the vault; see `scripts/azure/provision.sh` for automated provisioning of the vault and its role assignments.

## Demo accounts

Three seeded team members (John, Sarah, Mike) with mapped JIRA/GitHub identities in `local-dev-data/team_members.json`, backed by real (not mocked) activity across 3 JIRA projects and 3 GitHub repos — see `utils/jira_seed_data.py`/`utils/github_seed_data.py` to regenerate or extend it. Credentials for these demo accounts live in `.env`'s `#for claude code: not env vars` section and `test_user_accounts.txt` (both gitignored).

## Testing

This project has zero mocking libraries by design — `tests/` and `tests/integrations/` run against real JIRA/GitHub/OpenRouter/Postgres/Key Vault, not fixtures or stubs. `make test` runs the full suite in-container.
