# Stack & Infra Setup Spec

Spec for timeline.md step 3 ("Stand up minimum structure/infra"). Scope is a working **local** skeleton — deployment execution to Azure is step 4, a separate task.

## Stack

- **Backend**: FastAPI (async), Python.
- **Frontend**: htmx + Jinja2 templates. Server-rendered HTML fragments, no React/Vue/Angular, no JS bundler/build step. htmx and the `htmx-ext-sse` extension are vendored locally (served via FastAPI's `StaticFiles`), not pulled from a CDN.
- **CSS**: Pico.css (classless), vendored locally alongside htmx.
- **Database**: PostgreSQL, via SQLAlchemy (async engine, `asyncpg` driver) and Alembic for migrations.
- **LLM**: OpenRouter.
- **Not in the stack**: pgvector, Redis, LISTEN/NOTIFY — all explicitly deferred (pgvector/Redis until RAG, NMVP-FR-1, is actually spec'd; LISTEN/NOTIFY dropped, no concrete use case).
- **Deployment target**: Azure, single FastAPI process serving both htmx pages/fragments and API routes — no separate frontend server.
- **CI/CD**: none for MVP. No automated test-on-push pipeline (that's NMVP-NFR-7, non-MVP). Only a manually-triggered (`workflow_dispatch`) GitHub Actions workflow whose sole job is deploy + inject secrets from GH Actions secrets. The `deploy.yml` stub itself is a deliverable of timeline step 4 (deploy hello world to Azure), not this step — see `blueprints/deployment.md`.
- **Config**: environment variables loaded from a single `.env` file at the repo root, `.gitignore`'d, no hardcoded secrets (MVP-NFR-9). `.env` is read both by docker-compose (for compose-level variable substitution and passing through to the containers via `env_file`) and by the FastAPI app at runtime. An `.env.example` with placeholder values is committed so the real `.env` can be recreated from scratch.
- **Testing**: pytest. Because the stack may lean on Postgres-specific features later (row-level security for tenant isolation, pgvector), tests should run against a real Postgres instance from the start — a docker-compose Postgres service, not SQLite.

## Auth architecture (MVP-FR-1, MVP-FR-2, MVP-NFR-2, MVP-NFR-5)

- Azure AD/Entra ID via OIDC, confidential client flow: browser never sees Azure's tokens directly. Unauthenticated request to a protected route → redirect to Azure's authorize endpoint → Azure redirects to `/auth/callback` with an auth code → FastAPI exchanges the code server-side for an ID token → validate the token's signature against Azure's JWKS (check issuer/audience/expiry) → extract the user's identity.
- **Sessions are server-side in Postgres**, not a self-contained signed/stateless cookie — a `sessions` table (session id, user id, created_at, expires_at, revoked_at). This is deliberate: MVP-NFR-5 requires that sign-out actually invalidates the session, which a stateless JWT cookie can't do cleanly without reinventing a revocation list (i.e., a server-side session store) anyway.
- The cookie itself holds only an opaque random session id: `HttpOnly`, `Secure`, `SameSite=Lax`.
- A single shared FastAPI dependency (e.g. `get_current_user`) enforces auth on every protected route — both Jinja2 page routes and htmx fragment routes — via `Depends()`. One enforcement point, not duplicated logic.
- Sign-out: mark the session row revoked (`revoked_at = now()`), clear the cookie. This is the entire implementation of MVP-NFR-5 and MVP-FR-2.
- **CSRF protection is required, not optional**, because cookie auth auto-attaches to any request to the domain, including cross-site ones. `SameSite=Lax` is the first line of defense; additionally, embed a per-session CSRF token in htmx forms (hidden field or `hx-headers`) and validate it server-side on state-changing (POST/PUT/DELETE) requests. Build this in from the start.

## Conversation history (MVP-FR-7)

Stored **server-side in Postgres** (`conversations` + `messages` tables, scoped to session/conversation id) — not client-side storage. This was a deliberate reversal of an earlier client-storage plan once Postgres was already committed to the stack for sessions; it also removes any need to validate a client-supplied history array, since the server is the sole source of truth for what was said. This groundwork also makes the non-MVP RAG history feature (NMVP-FR-1) a smaller lift later — that feature mainly adds user-scoping and embeddings on top of data already being persisted here.

## Identity mapping (MVP-FR-8, MVP-NFR-7)

A static seed dataset resolving each team member's display name to three separate identity namespaces: their Azure identity, JIRA account, and GitHub handle. Include seed data for 3 demo accounts with placeholder JIRA/GitHub identifiers (real activity data is populated later, not part of this infra step).

## Streaming (MVP-FR-12)

Token streaming via Server-Sent Events, consumed client-side via the `htmx-ext-sse` extension (`hx-ext="sse"`, `sse-connect`, `sse-swap`), not a hand-rolled `EventSource` — for consistency with the rest of the htmx-driven frontend. Time-to-first-token is a tracked latency concern, not just a correctness one.

## Validation (MVP-NFR-4)

Basic structural validation on both the AI input and output boundary — reject malformed input, reject malformed output (e.g. invalid JSON) — via Pydantic models. Does not include content moderation or prompt-injection defenses (NMVP-NFR-5, non-MVP).

## Code quality (pre-commit hooks)

- **Linting/formatting**: ruff, configured in `pyproject.toml` — covers both lint and format (replaces flake8/black/isort). Runs over all Python source.
- **Type checking**: mypy, configured in `pyproject.toml`, run over the app package.
- **Templates**: djlint lints and formats the Jinja2 templates.
- All three are wired as `pre-commit` framework hooks (`.pre-commit-config.yaml`) that run on `git commit` — not in CI, since no CI pipeline exists yet (automated CI test running is NMVP-NFR-7, non-MVP). `pre-commit install` is a one-time local setup step, called out in the README setup instructions.
- Deliberately minimal scope: lint + type-check + template-lint only. No security/dependency scanning (bandit, pip-audit), no stylelint, no dependency-lockfile-manager migration — those are separate, deliberate additions to consider later, not part of this step.

## Local dev workflow (Makefile)

A root-level `Makefile` wraps docker-compose (and in-container commands) behind short, memorable targets. Two containers: `fastapi` and `postgres`.

- `make up` — build and start both containers (`docker compose up -d --build`).
- `make down` — stop both containers, **without** touching the Postgres volume.
- `make logs` — tail logs from both containers.
- `make migrate` — run `alembic upgrade head` inside the `fastapi` container.
- `make seed` — load the local dev fixtures (see below) into Postgres.
- `make test` — run pytest inside the `fastapi` container, against the compose Postgres.
- `make shell` — open a shell in the `fastapi` container.
- `make reset` — `docker compose down -v`, i.e. tear down **and drop the Postgres volume**. Kept as a distinct target from `down` specifically so an accidental `make down` never wipes data.
- `make up-dev` — the "we changed something, start clean" button: `reset` → `up` → `migrate` → `seed`, chained. This is the target to reach for after a schema change or when local state feels off, not `up` alone.

Local dev still authenticates against real Azure AD (no local auth bypass/dev session shortcut) — every `up-dev` really does go through the full Azure SSO OIDC round-trip. This means local dev requires a working Azure AD app registration with a `localhost` redirect URI (e.g. `http://localhost:8000/auth/callback`) configured, with its client id/secret/tenant id supplied via `.env`. Note this as a real prerequisite, not an afterthought — without it, nothing past the login screen works locally.

## Local dev seed data

A `local-dev-data/` folder at the repo root holds one JSON file per table that needs seeding for local dev — not a fixed/exhaustive list decided up front, but grown organically as tables need dev fixtures (starting with the identity-mapping/demo-accounts table required by MVP-FR-8/MVP-NFR-7). Filename matches table name (e.g. `local-dev-data/team_members.json`). `make seed` reads every file in the folder and loads it, respecting foreign-key load order where dependencies exist between tables. This folder is committed to the repo (it's fixture data, not secrets) and is distinct from `.env`, which holds actual credentials.

## Deliverable for this step

A working local skeleton, specifically:
- FastAPI project structure with Jinja2 templates directory and a static assets directory containing vendored htmx, `htmx-ext-sse`, and Pico.css.
- SQLAlchemy async engine configured against Postgres; Alembic initialized, with an initial migration covering at least the `sessions`, identity-mapping, `conversations`, and `messages` tables (schema can be refined later at spec/implement time — this just needs the pipeline proven end-to-end).
- A docker-compose file bringing up both containers — `fastapi` and a local Postgres matching whatever version will run on Azure.
- A single hello-world route rendering a Jinja2 template with htmx wired in, proving the whole request path works.
- pytest scaffolded to run against the docker-compose Postgres, and verified to run standalone inside the built image (no bind mount, no compose) since it travels with whatever gets deployed.
- `.env.example` plus `.gitignore` entries so no real secrets are ever committed.
- The root `Makefile` with the targets listed above (`up`, `down`, `logs`, `migrate`, `seed`, `test`, `shell`, `reset`, `up-dev`).
- The `local-dev-data/` folder with at least the identity-mapping/demo-accounts JSON fixture, plus the seed script that loads whatever's in that folder.
- `pyproject.toml` with ruff and mypy configuration, plus `.pre-commit-config.yaml` wiring ruff (lint + format), mypy, and djlint as pre-commit hooks.

## Explicitly out of scope for this step

pgvector, Redis, RBAC/multi-tenancy, self-serve org signup, MCP write access, RAG, automated CI test pipeline, secrets vaulting beyond env vars, caching, rate-limiting, advanced validation, accessibility work, per-tenant usage tracking. All non-MVP — do not build any of this now.

## References

Check `CLAUDE.md`, `blueprints/requirements/features.md`, and `blueprints/requirements/timeline.md` at the start of this work, per the working agreements, and update the relevant row(s) in both trackers when this step is done.
