# OpenRouter Integration Spec

Spec for adding OpenRouter as the LLM provider (MVP-NFR-3's OpenRouter leg): a single `app/services/llm_router.py` module providing a streaming, provider-abstracted query interface, plus a small model allowlist. This is provider plumbing only — no caller in the app invokes it yet (that's MVP-FR-11, response synthesis, and MVP-FR-12, streaming UI, both separate future features that will consume this).

## Design goal: provider abstraction, not just a thin OpenRouter wrapper

The defining requirement for this module: **callers of `llm_router` must not be able to tell which underlying LLM provider is being used.** If the project later switches from OpenRouter to calling Anthropic directly, every caller of `llm_router.query()` — response synthesis, future chat routes, anything else — should be unaffected. Only the internals of `llm_router.py` change.

This ruled out an earlier design that split the work into `app/integrations/openrouter_client.py` (a thin OpenRouter HTTP client, mirroring the `jira_client.py`/`github_client.py` pattern) plus `app/services/llm_router.py` (a thin wrapper resolving an enum and delegating to the client). That split makes sense for JIRA and GitHub because those *are* the fixed, named providers — there's nothing to abstract away. It does not make sense here: the abstraction boundary that actually matters is "provider is swappable," and splitting a provider-specific client from a pass-through router doesn't buy that — it's one seam pretending to be two files, with the enum resolution step floating awkwardly between them. Collapsing to a single file removes that awkwardness: there is one place that knows about OpenRouter, one enum, one public interface.

**Decision: single file, `app/services/llm_router.py`.** No `app/integrations/openrouter_client.py`.

## Scope boundaries

- **In scope**: authenticated, **streaming** chat completions against OpenRouter, from the start (not a non-streaming version added first and upgraded later — see rationale below); a fixed, named allowlist of models (not free-form model-string passthrough).
- **Out of scope**: response synthesis / prompt construction (MVP-FR-11), the SSE-to-browser streaming transport for the chat UI (MVP-FR-12 — this module supplies the upstream half, an async generator of text chunks; wiring that to `htmx-ext-sse` for the browser is separate, later work), embeddings usage (no caller yet — see note below), retry/backoff beyond `httpx` defaults, rate-limiting (NMVP-NFR-1, non-MVP), usage/cost tracking (NMVP-NFR-10, non-MVP).

### Why streaming from the start, not added later

MVP-FR-12 (token streaming, with time-to-first-token as a tracked latency target) is real, committed MVP scope, not a stretch goal. Building a non-streaming `chat_completion` first and adding a second streaming code path later would mean two response shapes for the same underlying call — exactly the kind of unrequested-but-then-retrofitted duplication CLAUDE.md's style rules warn against. `query()` returns a streaming interface from the first line of code; there is no non-streaming variant to maintain in parallel. A caller that wants the full text can just join the yielded chunks.

## `app/services/llm_router.py` (new)

First real file in `app/services/` (currently just `__init__.py`). Everything OpenRouter-specific — base URL, auth header shape, request/response wire format, SSE chunk parsing — lives here and only here.

**`LLMModel(str, Enum)`** — the model allowlist, and the *only* vocabulary callers use to pick a model. Member names are provider-agnostic (`FAST`, `CAPABLE`), not OpenRouter-flavored:
- `FAST = "google/gemini-2.5-flash"`
- `CAPABLE = "anthropic/claude-sonnet-4.5"`

The enum values are OpenRouter slugs today, but that's an internal detail of this file — nothing outside `llm_router.py` should format, construct, or inspect a slug string. If the provider changes, the enum values change; the member names (`FAST`/`CAPABLE`) and everything callers do with them do not.

**`EmbeddingModel(str, Enum)`** — same reasoning, for embeddings. One member for now (no caller yet, kept for allowlist symmetry with `LLMModel`):
- `DEFAULT = "openai/text-embedding-3-small"`

**`ChatMessage`** (Pydantic) — `role: Literal["system", "user", "assistant"]`, `content: str`. The caller-facing message shape for both input (conversation history so far) and internal request serialization.

**`async def query(client: httpx.AsyncClient, model: LLMModel, messages: list[ChatMessage]) -> AsyncIterator[str]`**
— the single public entry point.
- Resolves `model.value` to the OpenRouter slug internally.
- POSTs to `/chat/completions` with `"stream": true` and the resolved model string.
- Parses OpenRouter's SSE response (`data: {...}\n\n` chunks, `data: [DONE]` terminator — OpenAI-compatible streaming format) and yields each chunk's text delta (`choices[0].delta.content`) as it arrives, skipping chunks with no content delta (e.g. role-only or finish-reason-only chunks).
- Takes `client: httpx.AsyncClient` as an explicit argument, not self-constructed — same reasoning as the DB-session-ownership rule in CLAUDE.md (routes/callers own the resource lifecycle; this function is framework-agnostic and testable without hidden global state). Caller builds the client via a `build_client(api_key: str) -> httpx.AsyncClient` factory in this same file (base URL `https://openrouter.ai/api/v1`, `Authorization: Bearer <api_key>` header, timeout — streaming responses may run longer than the 10.0s used for jira/github, so this needs a larger or absent read timeout; confirm during implementation rather than guessing).
- Error handling: `resp.raise_for_status()` before iterating the stream, consistent with how jira/github clients propagate `httpx.HTTPStatusError` rather than wrapping it in a domain exception. Mid-stream errors (connection drop, malformed SSE chunk) are not specially handled in this pass — propagate whatever `httpx`/the async generator raises.
- No conversation-history storage, no system-prompt injection, no retry logic, no model-selection heuristics — `query()` is a thin typed pass-through from `LLMModel` to a stream of text. Conversation persistence (MVP-FR-7) and response synthesis (MVP-FR-11) are separate, later features that will call `query()`, not extend it.

## Testing

`tests/integrations/test_llm_router.py` (integrations directory, matching where jira/github tests live, even though this module is now in `app/services/` — it's still an outbound third-party integration test in spirit: live call against the real OpenRouter API, not mocked, consistent with MVP-NFR-8's existing pattern).

Cases:
- A `query()` call against `LLMModel.FAST` yields at least one non-empty chunk, and the joined chunks form a non-empty string.
- A malformed/unauthorized request surfaces as `httpx.HTTPStatusError`.

## Side effects / non-goals to flag explicitly

- `app/config.py`: add `openrouter_api_key: str` to `Settings` (already a placeholder in `.env.example`). No enums added to `config.py` — `LLMModel`/`EmbeddingModel` live in `llm_router.py` itself, since they're the router's own vocabulary, not shared app config.
- No new environment variables beyond `OPENROUTER_API_KEY`.
- No DB schema changes.
- No route/endpoint added — this is provider plumbing consumed by future features, not user-facing yet.
- Does not touch JIRA/GitHub clients or their tests.
- Model allowlist is intentionally small and hardcoded, not fetched from OpenRouter's `/models` endpoint.
- No `app/integrations/openrouter_client.py` — deliberately not created (see Design goal section above).

## Trackers to update once implemented

- `blueprints/requirements/features.md`: MVP-NFR-3 row — flip from "OpenRouter untouched"/specced-only to reflect OpenRouter auth implemented once code lands.
- `blueprints/specs/stack-and-infra.md`: no change needed — OpenRouter as the LLM choice is already recorded there.
- `CHANGELOG.md`: dated entry once implementation lands.
