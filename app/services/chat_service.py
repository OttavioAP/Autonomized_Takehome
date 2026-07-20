"""ChatService: the agentic loop tying pre-fetch, JiraTool/GithubTool, and
llm_router.query() together (chat.md's ChatService section). Constructed with
session/conversation_id passed in explicitly - never calls Depends() or commits,
per CLAUDE.md's transaction-ownership rule (the route commits once the generator
driving run() is exhausted).
"""

import re
from collections.abc import AsyncIterator
from uuid import UUID

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.db.models.activity_item import ActivityItem as ActivityItemModel
from app.db.models.message import MessageRole
from app.db.models.team_member import TeamMember
from app.prompts.loader import load_prompt
from app.repositories import (
    activity_item_repo,
    conversation_repo,
    message_citation_repo,
    message_repo,
    team_member_repo,
)
from app.schemas.chat import (
    ActivityItemOut,
    ActivityKind,
    CiteErrorEvent,
    CiteEvent,
    ErrorEvent,
    SSEEnvelope,
    TokenEvent,
    ToolStatusEvent,
)
from app.services.chat_errors import ToolExecutionError, UpstreamProviderError
from app.services.llm_router import (
    ChatMessage,
    LLMModel,
    StreamDone,
    TextDelta,
    ToolCall,
    ToolCallDelta,
    build_client,
    query,
)
from app.services.pre_fetch import DiscoveredScope, discover_scope
from app.services.token_store import get_github_token, get_jira_tokens
from app.services.tools.base import ActivityTool
from app.services.tools.github_tool import GithubTool, GithubToolParams
from app.services.tools.jira_tool import JiraTool, JiraToolParams

_CITE_SENTINEL_RE = re.compile(r"\{\{cite:(\d+):([0-9a-fA-F-]{36})\}\}")
# A trailing prefix that could still grow into a complete sentinel with more incoming
# text - used to decide how much of the buffer is safe to flush as plain text right
# now. Must match every proper prefix of "{{cite:<digits>:<uuid>}}", starting from a
# lone "{" - OpenRouter really does split deltas mid-sentinel, including right after
# the opening "{{" AND right before the final "}" of the closing "}}" (both confirmed
# live), so a bare "{{"/"{" tail and a "...uuid}" tail (one closing brace present, the
# second not yet) must both be held back rather than flushed. The single trailing "}"
# is only matched when a complete "{{cite:<digits>:<uuid>" precedes it, so ordinary
# prose ending in "}" is never wrongly held back.
_PARTIAL_SENTINEL_RE = re.compile(
    r"\{(\{(c(i(t(e(:(\d+(:([0-9a-fA-F-]{36}\}?|[0-9a-fA-F-]{0,35}))?)?)?)?)?)?)?)?$"
)

_TOOLS: dict[str, ActivityTool] = {
    JiraTool().name: JiraTool(),
    GithubTool().name: GithubTool(),
}


class CitationStreamParser:
    """Stateful rolling-buffer scanner for `{{cite:ordinal:uuid}}` sentinels. Consumes
    TextDelta.text fragments as they arrive and yields (plain_text, citation) pairs -
    citation is (ordinal, uuid_str) when a sentinel was matched, else None (plain_text
    then carries the text span instead). Handles a sentinel split across delta
    boundaries by holding back a buffer tail that could still complete into a match,
    rather than requiring the whole thing to land in one chunk.
    """

    def __init__(self) -> None:
        self._buffer = ""

    def feed(self, text: str) -> list[tuple[str, tuple[int, str] | None]]:
        self._buffer += text
        return self._drain(final=False)

    def flush(self) -> list[tuple[str, tuple[int, str] | None]]:
        """Call once the stream ends - anything left in the buffer is plain text
        (e.g. a literal "{{" in the model's prose that never completed into a
        sentinel)."""
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> list[tuple[str, tuple[int, str] | None]]:
        events: list[tuple[str, tuple[int, str] | None]] = []
        while True:
            match = _CITE_SENTINEL_RE.search(self._buffer)
            if match is not None:
                plain = self._buffer[: match.start()]
                if plain:
                    events.append((plain, None))
                events.append(("", (int(match.group(1)), match.group(2))))
                self._buffer = self._buffer[match.end() :]
                continue

            if final:
                if self._buffer:
                    events.append((self._buffer, None))
                self._buffer = ""
                return events

            partial = _PARTIAL_SENTINEL_RE.search(self._buffer)
            if partial is not None and partial.start() > 0:
                plain = self._buffer[: partial.start()]
                self._buffer = self._buffer[partial.start() :]
                if plain:
                    events.append((plain, None))
            elif partial is None:
                if self._buffer:
                    events.append((self._buffer, None))
                self._buffer = ""
            return events


class _ResolvedCredentials(BaseModel):
    """Everything a tool call might need, resolved once per ChatService.run() call -
    JIRA fields are None when the user hasn't connected JIRA (mirrors pre_fetch.py's
    own per-provider best-effort shape)."""

    team_member_id: UUID
    jira_access_token: str | None = None
    jira_refresh_token: str | None = None
    jira_cloud_id: str | None = None
    jira_site_url: str | None = None
    github_access_token: str | None = None


def _activity_item_out(row: ActivityItemModel) -> ActivityItemOut:
    # row.kind is the StrEnum's stored .value (a plain str column) - coerce back to the
    # ActivityKind member ActivityItemOut expects.
    return ActivityItemOut(id=row.id, kind=ActivityKind(row.kind), label=row.label, url=row.url)


def _tool_status_message(call: ToolCall) -> str:
    if call.name == JiraTool().name:
        return "Checking JIRA tickets…"
    if call.name == GithubTool().name:
        return "Checking GitHub activity…"
    return f"Running {call.name}…"


class ChatService:
    def __init__(self, session: AsyncSession, conversation_id: UUID) -> None:
        self._session = session
        self._conversation_id = conversation_id

    async def run(self, query_text: str) -> AsyncIterator[SSEEnvelope]:
        conversation = await conversation_repo.get_by_id(self._session, self._conversation_id)
        if conversation is None:
            raise ValueError(f"No conversations row for id={self._conversation_id}")

        team_members = await team_member_repo.list_all(self._session)
        team_member = next(
            (tm for tm in team_members if tm.id == conversation.team_member_id), None
        )
        if team_member is None:
            raise ValueError(f"No team_members row for id={conversation.team_member_id}")

        await message_repo.create(
            self._session, self._conversation_id, MessageRole.USER, query_text
        )

        own_activity_rows = await activity_item_repo.list_for_conversation(
            self._session, self._conversation_id
        )
        settings = get_settings()
        credentials = await self._resolve_credentials(team_member, settings)
        scope = await self._discover_scope_for_prompt(credentials)

        messages: list[ChatMessage] = [
            ChatMessage(
                role="system",
                content=self._build_system_prompt(
                    team_members, team_member, own_activity_rows, scope
                ),
            ),
            ChatMessage(role="user", content=query_text),
        ]

        assistant_text_parts: list[str] = []
        pending_citations: list[tuple[int, ActivityItemOut]] = []
        parser = CitationStreamParser()

        try:
            async with build_client(settings.openrouter_api_key) as llm_client:
                for round_num in range(settings.max_tool_call_rounds + 1):
                    forced_final_round = round_num == settings.max_tool_call_rounds
                    tools = None if forced_final_round else [t.definition for t in _TOOLS.values()]
                    if forced_final_round:
                        messages.append(
                            ChatMessage(role="system", content=load_prompt("tool_limit_reached.md"))
                        )

                    tool_calls_made = False
                    stream_stopped = False
                    async for event in query(llm_client, LLMModel.CAPABLE, messages, tools=tools):
                        if isinstance(event, TextDelta):
                            assistant_text_parts.append(event.text)
                            async for envelope in self._process_text_delta(
                                parser.feed(event.text), pending_citations
                            ):
                                yield envelope
                        elif isinstance(event, ToolCallDelta):
                            tool_calls_made = True
                            messages.append(
                                ChatMessage(role="assistant", content=None, tool_calls=event.calls)
                            )
                            for call in event.calls:
                                yield SSEEnvelope(
                                    event="tool-status",
                                    data=ToolStatusEvent(message=_tool_status_message(call)),
                                )
                                result_text = await self._execute_tool_call(call, credentials)
                                messages.append(
                                    ChatMessage(
                                        role="tool", content=result_text, tool_call_id=call.id
                                    )
                                )
                        elif isinstance(event, StreamDone) and event.finish_reason == "stop":
                            async for envelope in self._process_text_delta(
                                parser.flush(), pending_citations
                            ):
                                yield envelope
                            stream_stopped = True

                    if forced_final_round or stream_stopped or not tool_calls_made:
                        break
        except httpx.HTTPStatusError as exc:
            yield SSEEnvelope(event="error", data=ErrorEvent(detail=f"OpenRouter error: {exc}"))
            return
        except UpstreamProviderError as exc:
            yield SSEEnvelope(event="error", data=ErrorEvent(detail=str(exc)))
            return

        final_text = "".join(assistant_text_parts)
        assistant_message = await message_repo.create(
            self._session, self._conversation_id, MessageRole.ASSISTANT, final_text
        )
        for ordinal, item in pending_citations:
            await message_citation_repo.create(
                self._session, assistant_message.id, item.id, ordinal
            )

        title = query_text[:80] if conversation.title is None else None
        await conversation_repo.update(self._session, self._conversation_id, title=title)

    async def _process_text_delta(
        self,
        events: list[tuple[str, tuple[int, str] | None]],
        pending_citations: list[tuple[int, ActivityItemOut]],
    ) -> AsyncIterator[SSEEnvelope]:
        for plain, citation in events:
            if plain:
                yield SSEEnvelope(event="token", data=TokenEvent(text=plain))
            if citation is not None:
                ordinal, uuid_str = citation
                yield await self._validate_citation(ordinal, uuid_str, pending_citations)

    async def _validate_citation(
        self,
        ordinal: int,
        uuid_str: str,
        pending_citations: list[tuple[int, ActivityItemOut]],
    ) -> SSEEnvelope:
        known_items = await activity_item_repo.list_for_conversation(
            self._session, self._conversation_id
        )
        matched = next(
            (row for row in known_items if str(row.id).lower() == uuid_str.lower()), None
        )
        if matched is None:
            return SSEEnvelope(event="cite-error", data=CiteErrorEvent(ordinal=ordinal))
        item_out = _activity_item_out(matched)
        pending_citations.append((ordinal, item_out))
        return SSEEnvelope(event="cite", data=CiteEvent(ordinal=ordinal, item=item_out))

    async def _execute_tool_call(self, call: ToolCall, credentials: _ResolvedCredentials) -> str:
        tool = _TOOLS.get(call.name)
        if tool is None:
            return f"Error: unknown tool {call.name!r}"

        try:
            params = call.parsed_arguments(tool.Params)
        except ValidationError as exc:
            return f"Error: invalid arguments for {call.name}: {exc}"

        try:
            if isinstance(tool, JiraTool):
                if credentials.jira_access_token is None or credentials.jira_cloud_id is None:
                    return "Error: JIRA is not connected for this user."
                assert isinstance(params, JiraToolParams)
                results = await tool.execute(
                    self._session,
                    self._conversation_id,
                    params,
                    team_member_id=str(credentials.team_member_id),
                    access_token=credentials.jira_access_token,
                    refresh_token=credentials.jira_refresh_token or "",
                    cloud_id=credentials.jira_cloud_id,
                    site_url=credentials.jira_site_url or "",
                    jira_oauth_client_id=get_settings().jira_oauth_client_id,
                    jira_oauth_client_secret=get_settings().jira_oauth_client_secret,
                )
            else:
                if credentials.github_access_token is None:
                    return "Error: GitHub is not connected for this user."
                assert isinstance(params, GithubToolParams)
                results = await tool.execute(
                    self._session,
                    self._conversation_id,
                    params,
                    access_token=credentials.github_access_token,
                )
        except ToolExecutionError as exc:
            return f"Error: {exc}"

        if not results:
            return "No matching activity found."
        return "\n".join(f"- {item.kind.value} {item.label} (id={item.id})" for item in results)

    async def _resolve_credentials(
        self, team_member: TeamMember, settings: Settings
    ) -> _ResolvedCredentials:
        creds = _ResolvedCredentials(team_member_id=team_member.id)
        jira_tokens = await get_jira_tokens(team_member.id)
        if jira_tokens is not None and team_member.jira_cloud_id and team_member.jira_site_url:
            creds.jira_access_token = jira_tokens.access_token
            creds.jira_refresh_token = jira_tokens.refresh_token
            creds.jira_cloud_id = team_member.jira_cloud_id
            creds.jira_site_url = team_member.jira_site_url
        creds.github_access_token = await get_github_token(team_member.id)
        return creds

    async def _discover_scope_for_prompt(
        self, credentials: _ResolvedCredentials
    ) -> DiscoveredScope:
        from app.integrations import github_client, jira_client

        jira_http_client: httpx.AsyncClient | None = None
        github_http_client: httpx.AsyncClient | None = None
        if credentials.jira_access_token and credentials.jira_cloud_id:
            jira_http_client = jira_client.build_client(
                credentials.jira_access_token, credentials.jira_cloud_id
            )
        if credentials.github_access_token:
            github_http_client = github_client.build_client(credentials.github_access_token)

        try:
            # discover_scope() swallows per-provider HTTPStatusError itself (best-effort,
            # same posture as pre_fetch.run) - this just owns closing the clients it built.
            return await discover_scope(jira_http_client, github_http_client)
        finally:
            if jira_http_client is not None:
                await jira_http_client.aclose()
            if github_http_client is not None:
                await github_http_client.aclose()

    def _build_system_prompt(
        self,
        team_members: list[TeamMember],
        current_user: TeamMember,
        own_activity_rows: list[ActivityItemModel],
        scope: DiscoveredScope,
    ) -> str:
        roster = "\n".join(
            f"- {tm.display_name} (jira: {tm.jira_account_email}, github: {tm.github_login})"
            for tm in team_members
        )
        own_activity = (
            "\n".join(f"- {row.kind} {row.label} (id={row.id})" for row in own_activity_rows)
            or "(none found)"
        )
        jira_projects = (
            "\n".join(f"- {p.key}: {p.name}" for p in scope.jira_projects) or "(none discovered)"
        )
        jira_people = (
            "\n".join(f"- {p.display_name} (account_id={p.account_id})" for p in scope.jira_people)
            or "(none discovered)"
        )
        github_repos = (
            "\n".join(f"- {r.full_name}" for r in scope.github_repos) or "(none discovered)"
        )
        github_collaborators = (
            "\n".join(f"- {c.login}" for c in scope.github_collaborators) or "(none discovered)"
        )
        template = load_prompt("chat_system_prompt.md")
        return (
            template.replace("{{ roster }}", roster)
            .replace("{{ current_user_display_name }}", current_user.display_name)
            .replace("{{ own_activity }}", own_activity)
            .replace("{{ jira_projects }}", jira_projects)
            .replace("{{ jira_people }}", jira_people)
            .replace("{{ github_repos }}", github_repos)
            .replace("{{ github_collaborators }}", github_collaborators)
        )
