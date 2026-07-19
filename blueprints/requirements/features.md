# Features

Feature tracker for the Team Activity Monitor, split along two axes — **functional vs. non-functional**, and **MVP vs. non-MVP** — with a status column per lifecycle stage. Order of implementation, priority, and tech stack are deliberately out of scope for this document.

**Status columns:** Specced / Implemented / Tested / Deployed / QA. Mark ✅ when done, ⬜ when not. See `CLAUDE.md` for the exact definition of each status and for when this file should be checked and updated.

## MVP

### Functional Requirements

| # | Feature | Description | Specced | Implemented | Tested | Deployed | QA |
|---|---------|-------------|:---:|:---:|:---:|:---:|:---:|
| MVP-FR-1 | Login screen (Azure SSO) | Authenticated entry point to the app; users sign in with their organization's Azure identity rather than a locally-managed credential store. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-FR-2 | Sign-out | Ends the user's session and invalidates any tokens/credentials derived from it, rather than only clearing client-side state (see MVP-NFR-5). | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-FR-3 | Chat window | The primary interface: free-text input and conversational output where users type natural-language questions and receive synthesized answers. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-FR-4 | Basic selectable components for JIRA/GitHub items | Chat responses render referenced JIRA tickets and GitHub commits/PRs as simple clickable elements (object type + object name) that deep-link out to the source system. Richer inline summaries are deferred to NMVP-FR-3. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-FR-5 | Natural-language query parsing | Extracts the target team member's name and the intent of the question (JIRA-only, GitHub-only, or combined) from a free-text query, so the right data-fetching path can be invoked. Handling multiple phrasings/formats robustly is deferred to NMVP-FR-6. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-FR-6 | Empty/error states in UI | Distinct, user-legible states for "member not found," "no recent activity," and "upstream API failure," so the chat never silently fails or returns a blank/garbled response. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-FR-7 | Conversational query history within a single conversation | The chat retains context across turns within one session (e.g., follow-up questions about the same person), but does not persist across sessions — that's NMVP-FR-1. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-FR-8 | Static mapping of team members to JIRA/GitHub identities | A seed dataset (not a self-service flow) resolving each team member's display name to their JIRA account and GitHub handle, since Azure SSO identity, JIRA identity, and GitHub identity are three separate namespaces. Self-service linking is deferred to NMVP-FR-2. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-FR-9 | Fetch JIRA data for a user | Retrieves a user's assigned issues plus issue status and recent updates from the JIRA REST API, using the static identity mapping (MVP-FR-8) to resolve the JIRA account. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-FR-10 | Fetch GitHub data for a user | Retrieves a user's recent commits, active pull requests, and repositories contributed to recently, from the GitHub REST API. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-FR-11 | Response synthesis | Combines the fetched JIRA and GitHub data into a single, coherent, human-readable chat answer — the core deliverable the whole system exists to produce. Surfacing secondary metadata (priority, estimates, etc.) is deferred to NMVP-FR-8. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-FR-12 | Token streaming for chat responses | The chat displays partial response content as it is generated rather than waiting for the full answer, with time-to-first-token treated as a tracked latency target. Streaming transport (SSE, WebSockets, chunked HTTP, etc.) is a tech-stack decision, deliberately left open here. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

### Non-Functional Requirements

| # | Feature | Description | Specced | Implemented | Tested | Deployed | QA |
|---|---------|-------------|:---:|:---:|:---:|:---:|:---:|
| MVP-NFR-1 | Deployment to Microsoft Azure | The application is hosted on Azure infrastructure rather than run only locally, enabling shared/team access to the demo instance. | ✅ | ✅ | ✅ | ✅ | ⬜ |
| MVP-NFR-2 | Azure SSO integration | Authentication is backed by the organization's real Azure identity provider rather than a mock or locally-managed login; underlies MVP-FR-1. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-NFR-3 | Authentication with JIRA, GitHub, and OpenRouter APIs | The backend holds and uses valid API credentials/tokens to call all three third-party services on the user's behalf. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-NFR-4 | Basic validation of AI inputs/outputs | Guards against malformed input reaching the AI layer and malformed output (e.g., invalid JSON) leaving it. Does not include content moderation or prompt-injection defenses — those are deferred to NMVP-NFR-5. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-NFR-5 | Session-scoped credential lifecycle | Tokens and credentials issued for a session are tied to that session's lifetime; signing out invalidates them rather than merely hiding the UI. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-NFR-6 | Explicit flat-authorization model (no RBAC) | A deliberate design decision, not an oversight: any authenticated user may query any other team member's activity; there is no per-user, per-role, or per-tenant access boundary in MVP. Superseded at non-MVP tier by NMVP-NFR-6 (RBAC + multi-tenancy). | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-NFR-7 | Demo accounts + seed activity data for 3 users | A fixed set of three demo team members with pre-populated JIRA/GitHub activity, backing the static identity mapping (MVP-FR-8) and used for demoing/testing the system end-to-end. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-NFR-8 | Automated tests covering the JIRA and GitHub integrations | Unit/integration test coverage (e.g., pytest, gtest, or equivalent for the chosen stack) verifying the JIRA and GitHub clients work correctly in isolation. Wiring this into a CI pipeline is deferred to NMVP-NFR-7. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-NFR-9 | Lightweight environment-variable configuration | Configuration and secrets are supplied via environment variables, excluded from version control via `.gitignore`, and injected at deploy time via GitHub Actions secrets — no credentials are ever hardcoded or committed. A managed vault is deferred to NMVP-NFR-2. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| MVP-NFR-10 | Basic documentation | A README or equivalent covering setup instructions and how to use/call the JIRA and GitHub integrations. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

## Non-MVP (Stretch Goals)

### Functional Requirements

| # | Feature | Description | Specced | Implemented | Tested | Deployed | QA |
|---|---------|-------------|:---:|:---:|:---:|:---:|:---:|
| NMVP-FR-1 | User-scoped conversation history persisted across sessions, via RAG | Past conversations are stored per-user and retrieved (e.g., via a retrieval-augmented-generation pipeline) so a user can reference their own earlier sessions, beyond the single-session memory in MVP-FR-7. Each user only ever retrieves their own history. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-FR-2 | Self-service onboarding workflow for linking JIRA/GitHub accounts | Replaces the static MVP identity mapping (MVP-FR-8) with a flow where new team members link their own JIRA and GitHub accounts to their Azure identity. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-FR-3 | Expandable rich chat components | Upgrades MVP-FR-4's plain type+name link into an expandable component that also surfaces summary info (e.g., ticket status, PR description) inline in the chat, without requiring a click-through. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-FR-4 | Self-serve organization signup/onboarding flow | Arbitrary new organizations can sign up and provision their own tenant, self-serve — turning the app from a single-org deployment into multi-tenant SaaS. Pairs with NMVP-NFR-6 (RBAC + multi-tenancy); distinct from NMVP-FR-2, which is about linking JIRA/GitHub, not organization/account creation. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-FR-5 | Write access to JIRA/GitHub via MCP servers | Beyond read-only data fetching, the system can take write actions against JIRA and GitHub (e.g., commenting on a ticket, opening a PR) through MCP servers. Guardrails around write actions (confirmation/approval step, scoping, tie-in to the audit log at NMVP-NFR-3) are explicitly out of scope for now and left as an open design question for whenever this is picked up. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-FR-6 | Expanded query understanding (multiple question formats) | Broadens MVP-FR-5's parsing to robustly handle varied phrasings and intents beyond the rubric's canonical example queries. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-FR-7 | UI/UX polish pass | A dedicated visual/interaction design pass on the chat interface (styling, layout, branding), beyond MVP's functional-only bar. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-FR-8 | Additional insights in response synthesis | Enriches MVP-FR-11's core answer with secondary metadata — e.g., JIRA priority/story points/time estimates, GitHub PR review status — rather than just the bare activity summary. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-FR-9 | Ambiguous-name disambiguation | If a query's extracted name (MVP-FR-5) matches multiple team members, the system asks a clarifying question or lists candidates rather than silently guessing which one was meant. Not needed at MVP's 3-user roster (MVP-NFR-7), but a real gap once the roster grows. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

### Non-Functional Requirements

| # | Feature | Description | Specced | Implemented | Tested | Deployed | QA |
|---|---------|-------------|:---:|:---:|:---:|:---:|:---:|
| NMVP-NFR-1 | Rate-limiting/quota protection | Throttles or queues outbound calls to JIRA, GitHub, and OpenRouter to avoid hitting rate limits or incurring unexpected cost under load. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-NFR-2 | Proper secrets vaulting | Upgrades MVP-NFR-9's env-var-based configuration to a managed secrets store (e.g., Azure Key Vault), adding rotation and access control on top of "not hardcoded." | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-NFR-3 | Logging/audit trail of queries and AI responses | Records what was asked and what the AI answered, for debugging, compliance, and abuse monitoring. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-NFR-4 | Caching of JIRA/GitHub responses | Reduces latency and third-party API call volume by caching recently-fetched activity data. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-NFR-5 | Advanced validation of AI inputs/outputs | Content moderation and prompt-injection defenses layered on top of MVP-NFR-4's basic malformed-input/output checks. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-NFR-6 | RBAC + organization multi-tenancy | Access-control model with per-role permissions and per-tenant data isolation, superseding MVP-NFR-6's flat model. Requires the signup/onboarding flow at NMVP-FR-4. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-NFR-7 | GitHub Actions CI/CD pipeline running automated tests | Wires the test suite from MVP-NFR-8 into a CI/CD pipeline so tests run automatically on every push/PR, gating deploys on passing tests. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-NFR-8 | Concurrent/parallel data fetching | JIRA and GitHub data are fetched in parallel rather than sequentially, reducing end-to-end response latency. Distinct from caching (NMVP-NFR-4), which avoids redundant fetches altogether. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-NFR-9 | Tenant data isolation | Explicit guarantee that one organization's chat history, JIRA/GitHub identity mappings, and seed data are never queryable by another tenant. Called out separately from NMVP-NFR-6 (RBAC + multi-tenancy) since isolation is the property that actually has to be verified, not just assumed from RBAC existing. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-NFR-10 | Per-tenant usage/cost tracking for OpenRouter | Tracks AI usage (tokens/cost) broken out per organization, so spend is visible once orgs are self-serve (NMVP-FR-4) and paying customers rather than a single demo tenant. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| NMVP-NFR-11 | Accessibility (a11y) | The UI is usable via screen reader and keyboard navigation, meeting basic WCAG expectations. Distinct from NMVP-FR-7 (UI/UX polish pass), which is aesthetic and doesn't automatically deliver accessibility. | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
