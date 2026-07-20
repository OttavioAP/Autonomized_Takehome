# Handoff: add tool-calling support to `app/services/llm_router.py` (Phase 4)

Paste this whole file to a fresh Claude Code session opened at the repo root
(`/home/oz/Autonomized_Takehome`). It has no memory of any prior conversation
about this project — everything you need is below or in the referenced files.

## Context

This is the Team Activity Monitor project. `app/services/llm_router.py`
already exists and works (streaming chat completions against OpenRouter,
`LLMModel.FAST`/`LLMModel.CAPABLE`) but has NO tool-calling support — it
currently yields bare text (`AsyncIterator[str]`). You're upgrading it to
support tool calls, which a later phase's agentic loop (`ChatService`,
NOT part of this handoff) will depend on.

**Read first, in this order:**
1. `CLAUDE.md` — binding invariants (routes own the DB transaction;
   services are plain functions, no `Depends()`, no FastAPI imports —
   `llm_router.py` already follows this, keep it that way).
2. `implementation_log.md` — a running record of every decision, ambiguity,
   and bug found so far while implementing this project's Build Phases.
   Skim the whole file for context. **When you're done, append your own
   entry to this same file** (don't create a separate log) — record what
   you built, what you had to guess or assume, any bugs/gaps you found, and
   anything a future reader would need to know. Follow the file's existing
   structure (`## <phase/topic>` headers, most recent at the bottom). This
   file is shared across multiple agents working on this project in
   parallel right now — keep your entry self-contained and clearly labeled.
3. `blueprints/plans/features/openrouter-integration.md` — this is your
   spec, read the WHOLE file carefully. It documents exactly what changed
   from the current code and why (streaming tool-call-delta accumulation
   across fragmented SSE chunks is the trickiest part — read the `query()`
   bullet list under `app/services/llm_router.py` twice).
4. `blueprints/plans/implementation-handoff.md`'s "Best practices" section —
   pay special attention to: "Pydantic `BaseModel` for every data shape, not
   plain dataclasses or bare dicts" (every new type here must be a
   `BaseModel`), "Comment the WHY, liberally" (this file explicitly calls
   out "why tool-call argument fragments have to be accumulated across
   streaming deltas before parsing" as exactly the kind of comment worth
   leaving), "Errors are loud, never silent", "All magic numbers live in
   `config.py`" (there shouldn't be any new ones needed here, but check).
5. The actual current code: `app/services/llm_router.py` (the file you're
   modifying — read it in full first), `tests/integrations/
   test_llm_router.py` (the existing tests — 2 tests currently, you're
   adding a 3rd per the spec, and the first 2 must keep passing since
   `query()`'s signature/behavior for the no-tools case must stay
   backward-compatible other than the return type changing from bare `str`
   chunks to `TextDelta`/`StreamDone` events).

## What to build

Modify `app/services/llm_router.py` in place (do not create a new file —
the spec is explicit: single file, no `app/integrations/
openrouter_client.py`, see the spec's "Design goal" section for why).

### New types (all Pydantic `BaseModel`, per spec)

- `ToolDefinition`: `name: str`, `description: str`, `parameters:
  type[BaseModel]` — callers supply Pydantic model CLASSES (not JSON schema
  dicts); `query()`'s serialization step calls
  `parameters.model_json_schema()` internally.
- `ToolCall`: `id: str`, `name: str`, `arguments: str` (raw accumulated JSON
  string, unparsed) — plus a method `def parsed_arguments(self, as_type:
  type[BaseModelT]) -> BaseModelT` that does `as_type.model_validate_json
  (self.arguments)`, letting `ValidationError` propagate to the caller.
  You'll need a `TypeVar` bound to `BaseModel` for this generic method
  signature — check how other generic Pydantic patterns are typed in this
  codebase, or use a standard `BaseModelT = TypeVar("BaseModelT",
  bound=BaseModel)` module-level declaration.
- `TextDelta`: `text: str`
- `ToolCallDelta`: `calls: list[ToolCall]`
- `StreamDone`: `finish_reason: Literal["stop", "tool_calls", "length"]`
- `QueryEvent = TextDelta | ToolCallDelta | StreamDone` (a type alias, the
  discriminated union `query()` now yields)

### Modify existing types

- `ChatMessage`: currently `role: Literal["system", "user", "assistant"]`,
  `content: str`. Per spec, needs to become: `role: Literal["system",
  "user", "assistant", "tool"]`, `content: str | None`, `tool_calls:
  list[ToolCall] | None = None`, `tool_call_id: str | None = None`.

### Modify `query()`

Current signature: `query(client, model, messages) -> AsyncIterator[str]`.

New signature: `query(client: httpx.AsyncClient, model: LLMModel, messages:
list[ChatMessage], tools: list[ToolDefinition] | None = None) ->
AsyncIterator[QueryEvent]`.

Behavior changes (read the spec's full bullet list under `query()` — this
is the trickiest part of the whole handoff, do not skim it):
- Serialize `tools` into OpenRouter/OpenAI's wire shape when present:
  `[{"type": "function", "function": {"name", "description", "parameters":
  <schema>}}]`. Omit the `tools` key ENTIRELY (not an empty list) when
  `tools` is `None`/empty.
- Add `tool_choice: "auto"` to the request whenever `tools` is non-empty.
- Parse `choices[0].delta.tool_calls` fragments: the FIRST fragment at a
  given `index` carries `id` + `function.name`; EVERY fragment at that
  index (including the first) carries a piece of `function.arguments` to
  concatenate in order. Accumulate into a local `dict[int, {id, name,
  arguments_buffer}]` (or an equivalent small internal structure) across
  chunks — do NOT yield anything until the terminal chunk for that turn.
- When `finish_reason` is non-null (terminal chunk): if tool-call fragments
  were accumulated, yield ONE `ToolCallDelta` built from them (each
  `ToolCall.arguments` now a complete JSON string), THEN yield
  `StreamDone(finish_reason=...)`. If no tool calls were accumulated, yield
  `StreamDone` directly.
- Keep the existing `TextDelta` yielding behavior for `delta.content` —
  this part doesn't fundamentally change, just gets wrapped in the new
  `TextDelta` type instead of a bare string.
- Error handling unchanged: `resp.raise_for_status()` before iterating,
  propagate `httpx.HTTPStatusError` as-is.

## What NOT to build

- No `ChatService`, no agentic loop, no `CitationStreamParser` — that's
  `chat.md`'s separate, later work (Phase 5), which will CONSUME this
  module but isn't part of this handoff.
- No `JiraTool`/`GithubTool`/any tool implementations — separate work
  (Phase 3). This handoff only builds the generic `ToolDefinition`/
  `ToolCall` plumbing; it has no opinion on what any specific tool does.
- No changes to `EmbeddingModel`, `build_client`, or the base URL/auth
  header logic — those are unaffected by this change.
- No new config fields in `app/config.py` — the spec is explicit there are
  none needed for this module.

## Testing

`tests/integrations/test_llm_router.py` — real integration tests against
the live OpenRouter API, no mocks (this project has a deliberate
no-mocks-for-integrations convention). The existing 2 tests need to keep
passing (adjusted for the new return type — they currently just join text
chunks; you'll need to filter for `TextDelta` events and join `.text`
instead, and check the final event is a `StreamDone(finish_reason="stop")`).

Add a 3rd test per the spec's Testing section: a `query()` call against
`LLMModel.FAST` with one `ToolDefinition` (a trivial Pydantic params model,
e.g. a single required `city: str` field) and a user message that should
trigger it (e.g. "call the weather tool for Boston") should yield a
`ToolCallDelta` containing exactly one `ToolCall` whose `name` matches,
followed by `StreamDone(finish_reason="tool_calls")`; `parsed_arguments(...)`
against the trivial params model should succeed and the parsed field should
match what was asked for. The spec explicitly says: "Live-model-dependent...
accept some flakiness here rather than asserting exact behavior an LLM
doesn't strictly guarantee" — don't over-tighten this assertion.

Run:
```
sg docker -c "docker compose up -d --build"
sg docker -c "docker compose exec fastapi pytest tests/integrations/test_llm_router.py -v"
sg docker -c "make test"
sg docker -c "docker compose exec fastapi ruff check ."
sg docker -c "docker compose exec fastapi mypy app/"
```
(If `docker.sock` permission errors happen, prefix commands with `sg docker
-c "..."` as shown.) `OPENROUTER_API_KEY` should already be set in `.env` —
if it's missing, stop and report back rather than guessing a value.

## When done

Report back: what you built, whether all 3 tests (2 existing + 1 new) pass
against live OpenRouter, whether the full suite still passes, and anything
you had to guess or assume — especially anything about OpenRouter's actual
streaming tool-call chunk shape that you couldn't verify without live
testing (e.g. exact fragmentation behavior, whether `index` is always
present, edge cases in how multiple simultaneous tool calls in one turn are
distinguished).
