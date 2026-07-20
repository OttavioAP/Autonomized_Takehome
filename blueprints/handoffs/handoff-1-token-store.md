# Handoff: build `app/services/token_store.py` (Azure Key Vault wrapper)

Paste this whole file to a fresh Claude Code session opened at the repo root
(`/home/oz/Autonomized_Takehome`). It has no memory of any prior conversation
about this project — everything you need is below or in the referenced files.

## Context

This is the Team Activity Monitor project — a FastAPI app with per-user JIRA/
GitHub OAuth. You're building one specific, self-contained piece: the module
that reads/writes/deletes OAuth tokens in Azure Key Vault, keyed by
`team_member_id`.

**Read first, in this order:**
1. `CLAUDE.md` — binding invariants (routes own the DB transaction, services/
   repositories are plain functions, no `Depends()` outside routes).
2. `implementation_log.md` — a running record of every decision, ambiguity,
   and bug found so far while implementing this project's Build Phases,
   written by the agent driving this work. It documents things not in the
   specs themselves: e.g. the OAuth spec was revised mid-flight (tokens now
   persist per-user instead of per-session — read the "Mid-Phase-1-prep"
   entry for the full reasoning) and `team_members` was pulled forward into
   Phase 1 ahead of schedule (read the "Phase 1 prep: real dependency-order
   bug found" entry). Skim the whole file for context before starting.
   **When you're done, append your own entry to this same file** (don't
   create a separate log) — record what you built, what you had to guess or
   assume, any bugs/gaps you found, and anything a future reader would need
   to know that isn't obvious from the code/spec alone. Follow the file's
   existing structure (`## <phase/topic>` headers, most recent at the
   bottom). This file is shared across multiple agents working on this
   project in parallel, so keep your entry self-contained and clearly
   labeled with what you actually did.
3. `blueprints/plans/features/oauth-integration.md`, specifically the "Token
   storage: Azure Key Vault" section and the "JIRA silent refresh on
   access-token expiry" bullet under "Isolation model". This is your spec.
   Read the whole file for context, but those two sections are what this
   module has to satisfy.
4. `blueprints/plans/implementation-handoff.md`'s "Best practices" section
   (Pydantic for every data shape, full type hints/mypy-clean, comment the
   WHY not the WHAT, errors are loud never silent, all magic numbers in
   `config.py`).
5. The actual current code: `app/config.py` (already has `key_vault_uri: str`
   in `Settings` — already done, don't touch it), `app/auth/oidc.py` (the
   existing OIDC helper module — framework-agnostic plain functions taking
   config as arguments, no FastAPI imports; this is the exact style/shape
   convention to match), `app/db/models/team_member.py` (already exists,
   has `id: Mapped[uuid.UUID]`).

## What to build

`app/services/token_store.py` — plain async functions, no FastAPI imports, no
`Depends()`, framework-agnostic exactly like `app/auth/oidc.py` and
`app/integrations/*_client.py` already are. This is a **service**, so it goes
in `app/services/`, matching where `llm_router.py` already lives.

### Functions needed

```python
async def store_jira_tokens(
    team_member_id: UUID, access_token: str, refresh_token: str
) -> None: ...

async def get_jira_tokens(team_member_id: UUID) -> JiraTokens | None:
    """Returns None if not connected (no secrets exist for this user)."""

async def store_github_token(team_member_id: UUID, access_token: str) -> None: ...

async def get_github_token(team_member_id: UUID) -> str | None:
    """Returns None if not connected."""

async def delete_jira_tokens(team_member_id: UUID) -> None:
    """No-op if nothing exists (idempotent disconnect)."""

async def delete_github_token(team_member_id: UUID) -> None:
    """No-op if nothing exists (idempotent disconnect)."""
```

`JiraTokens` should be a Pydantic `BaseModel` (`access_token: str`,
`refresh_token: str`) — this codebase uses a `BaseModel` for every data
shape, not bare tuples/dicts (see the Best practices doc, point 1).

### Key Vault secret naming (from the spec)

- `user-{team_member_id}-jira-access`
- `user-{team_member_id}-jira-refresh`
- `user-{team_member_id}-github`

`team_member_id` is a `UUID` — stringify it (`str(team_member_id)`) when
building the secret name.

### Client construction

Use `azure-identity`'s `DefaultAzureCredential` (resolves to the App
Service's Managed Identity in Azure, and to the developer's own `az login`
session locally — this is why the spec calls this "one code path for both
environments"). Use `azure-keyvault-secrets`' async client
(`azure.keyvault.secrets.aio.SecretClient`), constructed once against
`Settings.key_vault_uri` and reused across calls — don't reconstruct a new
client per function call. Follow the pattern `app/db/session.py` already
uses for the DB engine: a small class or module-level singleton, NOT
constructed inside every function.

**New dependencies to add to `pyproject.toml`** (the spec calls these out
explicitly — "New dependency" in the Token storage section):
```
"azure-keyvault-secrets>=4.8",
"azure-identity>=1.17",
```
Add them to the main `dependencies` array (not `dev`). After adding, you'll
need to regenerate `requirements.lock.txt` — see Testing section below for
how, since the Docker build installs from the lockfile, not live from
`pyproject.toml` (a stale lockfile means the dependency silently isn't
actually present in the container — this bit a previous session, see
`CHANGELOG.md`'s entry for "Regenerated `requirements.lock.txt`").

### Error handling (per the Best practices doc: errors are loud, never silent)

- `get_jira_tokens`/`get_github_token` returning `None` for "not connected"
  is the ONE legitimate not-found case — Key Vault's SDK raises
  `azure.core.exceptions.ResourceNotFoundError` when a secret doesn't exist;
  catch that specific exception and return `None`. Do NOT use a bare
  `except:` — catch that one exception type by name.
- Any other exception (auth failure, network error, etc.) should propagate,
  not be swallowed.
- `delete_*` functions being idempotent (no-op if already gone) also means
  catching `ResourceNotFoundError` specifically and treating it as success,
  same reasoning.

### Expiry (from the spec's "Expiry" bullet)

- GitHub's secret: no `expires_on` set at creation.
- JIRA's access-token secret: `expires_on` can be set to roughly 1 hour from
  now (matches the token's own short lifetime) as a hygiene measure — pass
  `expires_on` as a parameter to the underlying Key Vault `set_secret` call.
  Check the `azure-keyvault-secrets` SDK's actual parameter name/shape for
  this (it may be `SecretProperties(expires_on=...)` passed via a
  `set_secret` call, or a separate `update_secret_properties` call — verify
  against the SDK's actual API, don't guess the shape).
- JIRA's refresh-token secret: no `expires_on` (per the spec: "its real
  expiry is Atlassian's own 90-day-idle rule, which Key Vault has no way to
  reset on each use, so an artificial TTL here would just be wrong").

## What NOT to build

- No routes (`app/api/oauth.py` is separate work, being done in parallel —
  don't create this file).
- No `jira_client.py`/`github_client.py` changes (also separate parallel
  work).
- No refresh-token *logic* (the actual "call Atlassian's refresh endpoint"
  code) — that's `jira_client.py`'s job in the other parallel handoff. This
  module only stores/retrieves/deletes whatever tokens it's given; it has no
  opinion on how they were obtained or refreshed.
- No local-dev fallback / in-memory store — the spec is explicit there is
  none; local dev uses the real Key Vault via `DefaultAzureCredential`
  resolving to the developer's own `az login` identity. Don't add one.

## Testing

Write `tests/integrations/test_token_store.py` (real integration test
against the live Key Vault, no mocks — this project has a deliberate
no-mocks-for-integrations convention, see `tests/integrations/` for the
existing pattern in `test_jira_client.py`/`test_github_client.py`). The vault
already exists and is provisioned; `Settings.key_vault_uri` in `.env` should
already point at it (check `.env` — if `KEY_VAULT_URI` is missing or empty,
STOP and report back rather than guessing a value).

Test cases:
- Store JIRA tokens for a random UUID, retrieve them back, assert they match.
- Store a GitHub token, retrieve it back, assert it matches.
- `get_jira_tokens`/`get_github_token` for a UUID that was never stored
  returns `None`.
- Delete JIRA tokens, then `get_jira_tokens` for that same UUID returns
  `None`.
- Deleting twice (already-deleted) doesn't raise.

You will NOT be able to run `make test`'s Docker-based flow if
`requirements.lock.txt` needs regenerating and you don't have a way to do
that inside this sandboxed session — if `pip install` isn't available to
you, regenerate it as best you can (`pip freeze` from an environment with
the new deps installed) and clearly flag in your final report if you
couldn't verify the lockfile is actually correct/complete, so it can be
double-checked before merging. Try `sg docker -c "docker compose up -d
--build"` — if permission errors happen (`docker.sock` permission denied),
try prefixing every docker-compose command with `sg docker -c "..."` — this
project's dev machine requires that workaround. Run:
```
sg docker -c "docker compose up -d --build"
sg docker -c "docker compose exec fastapi pytest tests/integrations/test_token_store.py"
sg docker -c "docker compose exec fastapi ruff check ."
sg docker -c "docker compose exec fastapi mypy app/"
```

If tests fail because Docker/compose genuinely isn't available in your
environment, say so clearly in your final report rather than claiming
success — don't fabricate a passing result.

## When done

Report back: what you built, the exact function signatures you ended up
with (in case they differ from the sketch above — you may discover the SDK
needs a different shape), whether tests passed, and anything you had to
guess or assume (especially around the `azure-keyvault-secrets` SDK's exact
async API surface, since this project hasn't used that package before).
