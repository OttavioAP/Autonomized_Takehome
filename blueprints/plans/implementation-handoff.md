# Implementation Handoff Prompt

Paste this to the implementation agent to kick off Build Phase 0. Keep this
file as the canonical handoff — update it if the phase plan changes rather
than letting the prompt and `timeline.md` drift apart.

---

You're implementing the Team Activity Monitor's remaining MVP features. All
design work is done — three specs cover essentially the entire remaining
surface:

- `blueprints/plans/features/chat.md` — the chat feature end-to-end (schema,
  tools, agentic loop, routes, templates).
- `blueprints/plans/features/oauth-integration.md` — per-user JIRA/GitHub
  OAuth, replacing the old shared service-account model.
- `blueprints/plans/features/openrouter-integration.md` — the LLM provider
  layer, including tool-calling support.

Read all three fully before writing any code. They cross-reference each
other and were reconciled for consistency in a dedicated review pass (see
`CHANGELOG.md`'s "spec review + build timeline" entry) — treat them as
authoritative and internally consistent, not as three independent documents
to reconcile yourself.

Also read, in this order, before starting:
1. `CLAUDE.md` — binding invariants (routes own the DB transaction, services/
   repositories are plain functions, no auto-commit in the session dependency).
   These are not optional style preferences.
2. `blueprints/requirements/features.md` and `blueprints/requirements/timeline.md`
   — current status of every feature and the phase breakdown you're about to
   execute (`timeline.md`'s "Build Phases" section under step 9).
3. `blueprints/specs/stack-and-infra.md` — locked-in stack/architecture
   decisions. Don't re-decide anything already settled there.
4. `blueprints/deployment.md` — what's actually been provisioned in Azure so
   far (Postgres, App Service, ACR, Azure AD SSO app registration), and the
   real bugs/lessons hit getting CI/CD working. Read the "execution notes"
   sections; they document non-obvious gotchas (trailing-newline secrets,
   Postgres Flexible Server's firewall behavior, mixed-content/proxy-header
   issues) you will otherwise rediscover the hard way.

## How to work: phase by phase, with a hard gate between each

`timeline.md`'s Build Phases section lays out 9 phases (0 through 8) in
dependency order — do not reorder them; each depends on the one(s) before it
(OAuth before tools, schema before queries, tools before the agentic loop,
etc.). Work through them **one at a time**, in order. For each phase:

1. Implement the phase's scope as specced. If the spec is genuinely
   ambiguous or missing something you need to proceed (not just a detail you
   could reasonably infer), stop and ask rather than guessing — the specs
   were reviewed for exactly this, but no review catches everything.
2. Write tests for what you just built:
   - **Unit tests** for anything with no external dependency (e.g.
     `CitationStreamParser` against synthetic delta sequences).
   - **Integration tests** for anything touching a real external system
     (JIRA, GitHub, OpenRouter, Azure Key Vault) — against the **real** API,
     not mocked. This project has a deliberate no-mocks-for-integrations
     convention already (see `tests/integrations/`) — follow it, don't
     introduce mocking as a new pattern.
   - Match each phase's specific gate description in `timeline.md` — some
     phases call for a manual browser/curl check in addition to automated
     tests (OAuth's connect flow, the chat UI, anything genuinely hard to
     assert automatically). Do the manual check too, don't skip it because
     automated tests passed.
3. Run the **full** test suite (`make test`), not just the new tests — confirm
   you haven't broken anything upstream.
4. **Only if everything passes**: commit (following this repo's existing
   commit-message conventions — look at recent commits via `git log` for the
   style) and push to `main`.
5. Watch the triggered `deploy.yml` run (`gh run watch`, matching how this
   was done earlier in the project — see `CHANGELOG.md`'s CI-debugging
   entries for the pattern). **If the deploy fails, stop.** Do not start the
   next phase. Diagnose and fix the current phase's deploy failure first —
   check live logs if needed (`az webapp log tail`, per `blueprints/deployment.md`'s
   established pattern for that), fix, re-test, re-commit, re-push, re-watch,
   until it's actually green. Only then move to the next phase.
6. Update `blueprints/requirements/features.md`'s row(s) for whatever you
   just implemented (Specced was likely already ✅ from the spec review;
   flip Implemented/Tested/Deployed honestly, not aspirationally — see
   `CLAUDE.md`'s exact definitions), and add a dated `CHANGELOG.md` entry
   summarizing what changed and why, before moving to the next phase.

Do not batch multiple phases into one commit, and do not start Phase N+1's
code before Phase N's gate has fully passed (tests green, deploy green,
trackers updated). If you get partway through a phase and realize the
dependency order was wrong for some sub-piece, that's worth flagging, but the
overall phase sequence itself was derived deliberately from the feature
dependency tree in `timeline.md` — don't silently reorder it.

## Specific things worth internalizing before you start

- **No regex/NLP query parsing.** The model reads the team roster from its
  system prompt and resolves who's being asked about itself. Do not build a
  `query_parser.py` or any fuzzy-matching layer — `chat.md` is explicit that
  this is a deliberate design decision, not an oversight.
- **The LLM cites, it never constructs URLs.** Citation validation against a
  known-good `activity_items` set is a hard trust boundary — don't relax it
  for convenience.
- **Tool-call arguments are validated via Pydantic, not accepted as-is.**
  `ToolCall.parsed_arguments()` round-trips through the tool's own `Params`
  model; a `ValidationError` there is expected, handled behavior (MVP-NFR-4),
  not something to catch-and-ignore.
- **Tool-role messages are never persisted** — they're transient, in-memory
  only within one `ChatService.run()` call. Don't add a 4th `role` value to
  the `messages` table.
- **Azure Key Vault holds session-scoped OAuth tokens, not Postgres.** This
  is a deliberate, narrow MVP-scope exception to the project's otherwise
  vault-free posture — don't extend it to other secrets (`DATABASE_URL`,
  `OPENROUTER_API_KEY` stay as plain env vars) and don't skip it in favor of
  a plaintext column because it's more convenient; the spec exists because
  the tradeoff was discussed and decided deliberately.
- **The old JIRA/GitHub service-account credentials in `.env` are being
  purged** (or already have been, depending on when you're reading this —
  check `.env.example`'s current shape against `oauth-integration.md`'s
  `Settings` changes section to confirm). Don't resurrect the old
  Basic-auth/PAT client pattern; `oauth-integration.md`'s client rework is
  the only path forward for `jira_client.py`/`github_client.py`.
- **`utils/jira_seed_data.py`, `utils/github_seed_data.py`,
  `utils/*_connect_check.py` are exempt** from the OAuth rework — they're
  standalone scripts using the 3 demo accounts' real credentials directly to
  seed/validate data outside any user session, not part of the app's request
  path. Leave them as-is.

## If you get stuck

Ask. The specs were reviewed hard for internal consistency, but "consistent"
isn't the same as "omniscient" — if you hit a real gap, that's a legitimate
finding, not a failure to read carefully enough. Flag it, propose a resolution
if you have one, and wait rather than guessing on anything that affects
security (token handling, auth boundaries) or data integrity (citation
validation, transaction ownership).
