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

Also read, in this order:
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
5. The actual current state of the repo — `app/`, `tests/`, `migrations/`,
   `.env.example` — not just what the specs say should exist. The specs were
   written and reviewed carefully, but they describe an earlier snapshot of
   the codebase; confirm what's actually there before assuming a spec's
   description of "existing" code is still accurate.

## Phase -1: review and question, before writing any code

The three specs (`chat.md`, `oauth-integration.md`, `openrouter-integration.md`)
went through a dedicated cross-consistency review before this handoff (see
`CHANGELOG.md`'s "spec review + build timeline" entry) — eight real
inconsistencies were found and fixed in that pass. Treat the specs as a
strong, deliberately-reconciled starting point, **not as guaranteed complete
or free of remaining ambiguity.** That review was thorough but not
omniscient, and it happened before any of this was actually built — a spec
that reads as internally consistent on paper can still turn out to be wrong,
underspecified, or inconsistent with the real codebase once you're actually
implementing against it.

Before writing any code:

1. Read all three specs fully, plus everything in the numbered reading list
   above, plus the actual current code.
2. Actively look for problems, not just comprehension gaps: contradictions
   between specs, a spec assuming code/schema that doesn't actually exist yet
   or exists in a different shape than described, an underspecified detail
   you'd have to guess at to proceed, a design decision that doesn't hold up
   against something you notice in the real codebase. Assume there may still
   be things the review pass missed — your job here is to find them, not to
   assume their absence.
3. Write down every question and every suspected inconsistency you find,
   however small. Do not silently resolve ambiguity by picking whichever
   interpretation is easiest to implement — surface it.
4. **Stop and ask before writing any implementation code.** Present your full
   list of questions/findings in one batch, not one at a time as you encounter
   them. Wait for answers. This is a deliberate, one-time gate before Phase 0
   — not something to repeat before every subsequent phase (ordinary
   phase-level ambiguity, once this initial gate has passed, is handled by
   the "ask rather than guess" rule under each phase below, but it should be
   much rarer after this pass than before it).

Do not treat this as a formality to rush through. An hour spent here finding
a real inconsistency is cheaper than discovering it three phases deep with
schema/API decisions already built on top of the wrong assumption.

## How to work: phase by phase, with a hard gate between each

`timeline.md`'s Build Phases section lays out 9 phases (0 through 8) in
dependency order — do not reorder them; each depends on the one(s) before it
(OAuth before tools, schema before queries, tools before the agentic loop,
etc.). Work through them **one at a time**, in order. For each phase:

1. Implement the phase's scope as specced. Phase -1 above should have already
   surfaced most ambiguity, but if you hit something genuinely underspecified
   mid-phase that you didn't catch earlier (not just a detail you could
   reasonably infer), stop and ask rather than guessing — this should be rarer
   now than it would have been without Phase -1, not zero.
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
- **The old JIRA/GitHub service-account credentials have been purged from
  `.env.example`** (10 vars remain: Postgres, `APP_ENV`, `DATABASE_URL`,
  `OPENROUTER_API_KEY`, and the 4 Azure AD SSO vars). Don't resurrect the old
  Basic-auth/PAT client pattern or re-add `JIRA_BASE_URL`/`JIRA_API_TOKEN`/
  `GITHUB_TOKEN`/etc.; `oauth-integration.md`'s client rework is the only path
  forward for `jira_client.py`/`github_client.py`. The real (non-example)
  `.env` still carries the 3 demo accounts' actual credentials for
  `utils/`'s scripts (see next bullet) — that's intentional, not a leftover
  to clean up.
- **`utils/jira_seed_data.py`, `utils/github_seed_data.py`,
  `utils/*_connect_check.py` are exempt** from the OAuth rework — they're
  standalone scripts using the 3 demo accounts' real credentials directly to
  seed/validate data outside any user session, not part of the app's request
  path. Leave them as-is.

## If you get stuck mid-phase

Ask, the same way as Phase -1: a real gap found mid-implementation is a
legitimate finding, not a failure to have read carefully enough at the start.
Flag it, propose a resolution if you have one, and wait rather than guessing
— especially on anything touching security (token handling, auth boundaries)
or data integrity (citation validation, transaction ownership).
