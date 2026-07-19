# Timeline

Sequenced plan of work for the Team Activity Monitor. All MVP work is sequenced before any non-MVP feature is picked up. There is no CI/CD pipeline in this plan, so deployment happens as discrete, deliberate steps rather than continuously.

**Status columns:** Specced / Implemented / Tested / Deployed / QA — same definitions as `features.md` (see `CLAUDE.md`). `N/A` is a valid value for any cell where the concept doesn't apply to that step (e.g., a decision step like "select tech stack" has no meaningful "Deployed" state).

## Steps

| # | Step | Description | Specced | Implemented | Tested | Deployed | QA |
|---|------|-------------|:---:|:---:|:---:|:---:|:---:|
| 1 | Complete list of features | Enumerate the full functional/non-functional, MVP/non-MVP feature set. Tracked in `features.md`. | N/A | ✅ | N/A | N/A | N/A |
| 2 | Select tech stack | Backend: FastAPI (async). Frontend: htmx + Jinja2 (server-rendered, no build step). DB: Postgres via SQLAlchemy (async) + Alembic. LLM: OpenRouter. Auth: Azure SSO (OIDC) backed by a server-side session table in Postgres, opaque HttpOnly/Secure/SameSite cookie. Conversation history stored server-side in Postgres, not client-side. Deployment: Azure, single FastAPI process serving both pages and API, no CI/CD pipeline. | N/A | ✅ | N/A | N/A | N/A |
| 3 | Stand up minimum structure/infra | Scaffold the project structure and provision the minimum infrastructure needed for the chosen stack (repo layout, build tooling, cloud resources). See `blueprints/specs/stack-and-infra.md`. | ✅ | ✅ | N/A | N/A | N/A |
| 4 | Deploy hello world to Microsoft Azure | Prove the deployment path end-to-end with a trivial app before any real feature work, so infra problems surface early. Also owns the `.github/workflows/deploy.yml` stub (moved from step 3's deliverable list — it's a deploy mechanism, not infra scaffolding). See `blueprints/deployment.md`. | N/A | ✅ | ✅ | ✅ | N/A |
| 5 | Bare-minimum integrations | Validate JIRA/GitHub API connectivity via local util scripts first, then evolve that into the actual MVP integration features with integration tests — validated locally, ahead of any deployed integration work. | N/A | ✅ | 🟡 | N/A | N/A |
| 6 | Determine MVP prerequisite dependencies | Map the prerequisite relationships between MVP features from `features.md`. Output is the Dependency Tree section below. | N/A | ⬜ | N/A | N/A | N/A |
| 7 | Spec all MVP features | Write the spec(s) for every MVP feature — API interfaces, UI mockups, database schema, and enough context for an AI agent to generate code and tests — in dependency-tree order. This is what flips a feature's Specced column to ✅ in `features.md`. | N/A | ⬜ | N/A | N/A | N/A |
| 8 | Create seed/demo data & identity mappings | Build the 3 demo accounts and the static team-member-to-JIRA/GitHub identity mapping (MVP-FR-8, MVP-NFR-7). Sequenced ahead of implementation since nearly every MVP feature depends on this data existing. | ⬜ | ⬜ | ⬜ | N/A | N/A |
| 9 | Implement MVP features | Implement features in dependency-tree order. Cyclical process — spec, code, and plan get revised against each other as implementation surfaces gaps. | N/A | ⬜ | N/A | N/A | N/A |
| 10 | Local QA | QA pass per feature or group of features, run locally, before any deployment of the full app. | N/A | N/A | ⬜ | N/A | ⬜ |
| 11 | Deploy full MVP app | Single deployment of the completed MVP to Azure — not a CI/CD pipeline, a deliberate one-time deploy once local QA passes. | N/A | N/A | N/A | ⬜ | N/A |
| 12 | Deployment QA | Full-system QA pass against the deployed app, done in one fell swoop rather than per-feature. | N/A | N/A | N/A | N/A | ⬜ |
| 13 | Choose non-MVP features to implement | With a working, QA'd MVP live, decide which non-MVP features from `features.md` to pursue next. | N/A | ⬜ | N/A | N/A | N/A |

## MVP Dependency Tree

_To be filled in as the output of Step 6 — will map prerequisite relationships between the MVP features enumerated in `features.md`._
