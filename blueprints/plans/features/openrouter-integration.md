# OpenRouter Integration Spec

Spec for adding OpenRouter as the LLM provider (MVP-NFR-3's OpenRouter leg): a single `app/services/llm_router.py` module providing a streaming, provider-abstracted query interface, plus a small model allowlist. This is provider plumbing only — no caller in the app invokes it yet (that's MVP-FR-11, response synthesis, and MVP-FR-12, streaming UI, both separate future features that will consume this).

**Revised** after `chat.md` specced an agentic tool-calling loop (`ChatService`) that depends on `llm_router.query()` supporting tool calls — the original design here only returned bare text chunks, with no way to represent "the model wants to call a tool" at all. Confirmed before revising, not assumed: OpenRouter's raw REST API supports the standard OpenAI-shaped `tools`/`tool_choice` request parameters combined with `stream: true` (`choices[].delta.tool_calls` in streaming chunks, same as OpenAI), and both allowlisted models (`anthropic/claude-sonnet-4.5`, `google/gemini-2.5-flash`) report `tools` in their `supported_parameters` via OpenRouter's live `/api/v1/models` endpoint — checked directly, not inferred from marketing copy. No need for a hand-rolled tool-calling loop against a non-tool-calling API, and no need to switch providers (e.g. to a direct OpenAI key) — OpenRouter already speaks this dialect natively for the models this project uses.

## Design goal: provider abstraction, not just a thin OpenRouter wrapper

The defining requirement for this module: **callers of `llm_router` must not be able to tell which underlying LLM provider is being used.** If the project later switches from OpenRouter to calling Anthropic directly, every caller of `llm_router.query()` — response synthesis, future chat routes, anything else — should be unaffected. Only the internals of `llm_router.py` change.

This ruled out an earlier design that split the work into `app/integrations/openrouter_client.py` (a thin OpenRouter HTTP client, mirroring the `jira_client.py`/`github_client.py` pattern) plus `app/services/llm_router.py` (a thin wrapper resolving an enum and delegating to the client). That split makes sense for JIRA and GitHub because those *are* the fixed, named providers — there's nothing to abstract away. It does not make sense here: the abstraction boundary that actually matters is "provider is swappable," and splitting a provider-specific client from a pass-through router doesn't buy that — it's one seam pretending to be two files, with the enum resolution step floating awkwardly between them. Collapsing to a single file removes that awkwardness: there is one place that knows about OpenRouter, one enum, one public interface.

**Decision: single file, `app/services/llm_router.py`.** No `app/integrations/openrouter_client.py`.

## Scope boundaries

- **In scope**: authenticated, **streaming** chat completions against OpenRouter, from the start (not a non-streaming version added first and upgraded later — see rationale below); a fixed, named allowlist of models (not free-form model-string passthrough); **tool calling**, combined with streaming, via typed Pydantic tool definitions (see below) — required by `chat.md`'s agentic loop, not optional plumbing.
- **Out of scope**: response synthesis / prompt construction (MVP-FR-11), the SSE-to-browser streaming transport for the chat UI (MVP-FR-12 — this module supplies the upstream half, an async generator of typed events; wiring that to `htmx-ext-sse` for the browser is separate, later work), the tool-call *execution* loop itself (deciding when/whether to call a tool, running it, deciding when to stop — that's `chat.md`'s `ChatService`; this module only round-trips typed events), embeddings usage (no caller yet — see note below), retry/backoff beyond `httpx` defaults, rate-limiting (NMVP-NFR-1, non-MVP), usage/cost tracking (NMVP-NFR-10, non-MVP).

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

**`ChatMessage`** (Pydantic) — `role: Literal["system", "user", "assistant", "tool"]`, `content: str | None`, `tool_calls: list[ToolCall] | None = None` (set on an `assistant` message that requested tools), `tool_call_id: str | None = None` (set on a `tool`-role message reporting a result back). The caller-facing message shape for both input (conversation history so far, including any tool-call round trips already completed) and internal request serialization. Revised from an earlier draft with only `role`/`content` — that shape had no way to represent a tool-call request or its result in history, which the agentic loop (`chat.md`'s `ChatService`) requires.

**`ToolDefinition`** (Pydantic) — `name: str`, `description: str`, `parameters: type[BaseModel]`. Callers supply tool definitions as **Pydantic model classes**, not hand-written JSON schema dicts — `query()`'s request-serialization step calls `parameters.model_json_schema()` internally to build the wire-format `tools` array. This is what answers MVP-NFR-4 (basic AI input/output validation) for the tool-calling path specifically: because the parameters type is a real Pydantic model, the *same* model is used both to generate the schema the LLM sees and, on the way back, to validate/parse whatever JSON arguments the LLM actually emits — `ToolCall.parsed_arguments(as_type)` (see below) round-trips through `as_type.model_validate_json(...)`, so a malformed or wrong-typed tool-call payload from the model raises a normal Pydantic `ValidationError` at the boundary rather than silently reaching `JiraTool`/`GithubTool.execute()` with bad data. `chat.md`'s `JiraTool`/`GithubTool` each define their own `Params` model (e.g. `JiraToolParams(jira_account_email: str, project_key: str)`) and pass it as `ToolDefinition.parameters`.

**`ToolCall`** (Pydantic) — `id: str`, `name: str`, `arguments: str` (raw accumulated JSON string, not yet parsed — parsing is the caller's job via `parsed_arguments`, since only the caller knows which `Params` type to validate against). `def parsed_arguments(self, as_type: type[BaseModelT]) -> BaseModelT` — thin wrapper over `as_type.model_validate_json(self.arguments)`, letting `ValidationError` propagate (caller/`ChatService` decides how to surface it — likely as a `ToolExecutionError` per `chat.md`'s error model, not a raised 500).

**Streaming event types** — `query()` no longer yields bare `str` (the earlier draft's shape couldn't represent "the model wants to call a tool," only "here is text"). New discriminated union:

```python
class TextDelta(BaseModel):
    text: str

class ToolCallDelta(BaseModel):
    """One or more tool calls the model has finished requesting (accumulated
    internally across streaming fragments - see below - and yielded once
    complete, not fragment-by-fragment)."""
    calls: list[ToolCall]

class StreamDone(BaseModel):
    """Terminal event. finish_reason distinguishes 'model produced a final
    text answer' from 'model wants tools then hasn't been given a chance to
    continue yet' - ChatService uses this to decide whether to loop."""
    finish_reason: Literal["stop", "tool_calls", "length"]

QueryEvent = TextDelta | ToolCallDelta | StreamDone
```

**`async def query(client: httpx.AsyncClient, model: LLMModel, messages: list[ChatMessage], tools: list[ToolDefinition] | None = None) -> AsyncIterator[QueryEvent]`**
— the single public entry point, revised signature (added `tools`, changed return type from `AsyncIterator[str]`).
- Resolves `model.value` to the OpenRouter slug internally.
- Serializes `tools` (if given) into OpenRouter/OpenAI's wire shape: `[{"type": "function", "function": {"name", "description", "parameters": <json schema from ToolDefinition.parameters.model_json_schema()>}}]`. Omits the `tools` key entirely when `tools` is `None`/empty — not an empty list, since some providers treat an empty `tools` array differently from its absence.
- POSTs to `/chat/completions` with `"stream": true`, the resolved model string, and `tool_choice: "auto"` whenever `tools` is non-empty (the model decides per-turn whether to call a tool or answer directly — matches `chat.md`'s loop, which expects either outcome each round).
- Parses OpenRouter's SSE response (`data: {...}\n\n` chunks, `data: [DONE]` terminator — OpenAI-compatible streaming format). Per delta:
  - `choices[0].delta.content` present and non-null → yield `TextDelta(text=...)` immediately, same as the original design.
  - `choices[0].delta.tool_calls` present → **do not yield yet**. Tool-call deltas arrive fragmented: the first fragment at a given `index` carries `id` and `function.name`, every fragment at that `index` (including the first) carries a piece of `function.arguments` to be concatenated in order. `query()` accumulates these into a local `dict[index, {id, name, arguments_buffer}]` across chunks.
  - `choices[0].finish_reason` present (non-null) → this is the terminal chunk for the current turn. If accumulated tool-call fragments exist, yield one `ToolCallDelta(calls=[...])` built from the accumulated buffers (each `ToolCall.arguments` now a complete JSON string), *then* yield `StreamDone(finish_reason=...)`. If no tool calls were accumulated, yield `StreamDone(finish_reason=...)` directly.
- Takes `client: httpx.AsyncClient` as an explicit argument, not self-constructed — same reasoning as the DB-session-ownership rule in CLAUDE.md (routes/callers own the resource lifecycle; this function is framework-agnostic and testable without hidden global state). Caller builds the client via a `build_client(api_key: str) -> httpx.AsyncClient` factory in this same file (base URL `https://openrouter.ai/api/v1`, `Authorization: Bearer <api_key>` header, timeout — streaming responses may run longer than the 10.0s used for jira/github, so this needs a larger or absent read timeout; confirm during implementation rather than guessing).
- Error handling: `resp.raise_for_status()` before iterating the stream, consistent with how jira/github clients propagate `httpx.HTTPStatusError` rather than wrapping it in a domain exception. Mid-stream errors (connection drop, malformed SSE chunk) are not specially handled in this pass — propagate whatever `httpx`/the async generator raises.
- No conversation-history storage, no system-prompt injection, no retry logic, no model-selection heuristics — `query()` is a thin typed pass-through from `LLMModel` (+ optional tool definitions) to a stream of typed events. Conversation persistence (MVP-FR-7) and response synthesis (MVP-FR-11) are separate, later features that will call `query()`, not extend it. The tool-call *execution* loop itself (deciding to call `JiraTool.execute()`, feeding the result back as a `tool`-role message, deciding when to stop looping) lives entirely in `chat.md`'s `ChatService` — `llm_router.py` only round-trips typed events, it has no opinion on what a tool call means or what to do with its result.

## Testing

`tests/integrations/test_llm_router.py` (integrations directory, matching where jira/github tests live, even though this module is now in `app/services/` — it's still an outbound third-party integration test in spirit: live call against the real OpenRouter API, not mocked, consistent with MVP-NFR-8's existing pattern).

Cases:
- A `query()` call against `LLMModel.FAST` with no `tools` yields at least one `TextDelta` with non-empty text, followed by a `StreamDone(finish_reason="stop")`.
- A malformed/unauthorized request surfaces as `httpx.HTTPStatusError`.
- A `query()` call against `LLMModel.FAST` with one `ToolDefinition` (a trivial Pydantic params model, e.g. a single required `city: str` field) and a user message that should trigger it (e.g. "call the weather tool for Boston") yields a `ToolCallDelta` containing exactly one `ToolCall` whose `name` matches, followed by `StreamDone(finish_reason="tool_calls")`; `parsed_arguments(...)` against the trivial params model succeeds and the parsed field matches what was asked for. Live-model-dependent (the model has to actually choose to call the tool) — accept some flakiness here rather than asserting exact behavior an LLM doesn't strictly guarantee, but this is the only way to verify the accumulation logic against real fragmented deltas rather than a synthetic/mocked stream.

## Side effects / non-goals to flag explicitly

- `app/config.py`: add `openrouter_api_key: str` to `Settings` (already a placeholder in `.env.example`). No enums added to `config.py` — `LLMModel`/`EmbeddingModel` live in `llm_router.py` itself, since they're the router's own vocabulary, not shared app config.
- No new environment variables beyond `OPENROUTER_API_KEY`.
- No DB schema changes.
- No route/endpoint added — this is provider plumbing consumed by future features, not user-facing yet.
- Does not touch JIRA/GitHub clients or their tests.
- Model allowlist is intentionally small and hardcoded, not fetched from OpenRouter's `/models` endpoint at runtime — but both allowlisted models' tool-calling support *was* verified once against that endpoint while writing this spec (see revision note above), not left as an assumption.
- No `app/integrations/openrouter_client.py` — deliberately not created (see Design goal section above).
- `ToolDefinition`/`ToolCall`/the `QueryEvent` union live in `llm_router.py` itself (this module's own vocabulary), not `app/schemas/chat.py` — `chat.md`'s `JiraTool`/`GithubTool` import them from here rather than `llm_router.py` importing anything from `chat.md`'s schemas, keeping the dependency direction one-way (tools depend on the LLM router's types, not the reverse).

## Trackers to update once implemented

- `blueprints/requirements/features.md`: MVP-NFR-3 row — flip from "OpenRouter untouched"/specced-only to reflect OpenRouter auth implemented once code lands.
- `blueprints/specs/stack-and-infra.md`: no change needed — OpenRouter as the LLM choice is already recorded there.
- `CHANGELOG.md`: dated entry once implementation lands.
