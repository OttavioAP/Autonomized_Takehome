# Changelog

Most recent entry at the top. One entry per meaningful change — new/updated requirements, architecture decisions, or implementation milestones.

## 2026-07-18

- Reformatted `blueprints/requirements/rubric.md` into clean Markdown, preserving original wording/typos verbatim.
- Built out `blueprints/requirements/features.md`: enumerated MVP/non-MVP functional and non-functional requirements, then converted it into a full tracker (Specced/Implemented/Tested/Deployed/QA per feature).
- Built out `blueprints/requirements/timeline.md`: 13-step sequenced plan from feature list through MVP deployment QA to non-MVP scoping, plus a placeholder for the MVP dependency tree (step 6's output).
- Updated `CLAUDE.md` with working agreements: check/update the trackers and specs at the start/end of every work item, plus the Specced/Tested status definitions.
- Selected the stack: FastAPI + htmx/Jinja2 + PostgreSQL (SQLAlchemy + Alembic) + OpenRouter, deployed to Azure as a single process. Recorded the full rationale — auth (Azure SSO via server-side sessions in Postgres), conversation history storage, CSRF handling, streaming approach — along with the local dev workflow (Makefile targets, `local-dev-data/` seed fixtures) in `blueprints/specs/stack-and-infra.md`.
