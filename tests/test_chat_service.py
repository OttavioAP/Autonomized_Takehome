"""Live integration test for ChatService.run() (chat.md's ChatService section, Phase
5's gate): a full agentic-loop run against real OpenRouter + real GitHub data,
asserting a real citation round-trips - the model cites a real activity_items UUID,
the service validates it against this conversation's item set, and a cite envelope
(not cite-error) comes back with a message_citations row persisted.

GitHub-only: no real JIRA 3LO token exists in this session (same gap as
tests/test_tools.py's skipped JiraTool test), so this exercises the GitHub tool path
end to end. Live-model-dependent - the model has to actually choose to cite - so this
accepts some flakiness rather than asserting exact prose, consistent with
tests/integrations/test_llm_router.py's own stance on live tool-call tests.
"""

import os
from pathlib import Path

from app.db.session import db
from app.repositories import (
    conversation_repo,
    message_citation_repo,
    message_repo,
    team_member_repo,
)
from app.schemas.chat import CiteEvent, TokenEvent
from app.services import token_store
from app.services.chat_service import ChatService

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def _github_token() -> str:
    return (
        os.environ.get("Autonomized_Test_1_Github_PAT")
        or _load_env(REPO_ROOT / ".env")["Autonomized_Test_1_Github_PAT"]
    )


async def test_run_streams_tokens_and_round_trips_a_real_citation() -> None:
    async for session in db.get_session():
        john = await team_member_repo.get_by_azure_upn(
            session, "john@ottavioantperuzzigmail.onmicrosoft.com"
        )
        assert john is not None
        conversation = await conversation_repo.create(session, john.id)
        await session.commit()
    assert john is not None

    await token_store.store_github_token(john.id, _github_token())
    try:
        events = []
        async for session in db.get_session():
            service = ChatService(session, conversation.id)
            # Sarah (github "autonomized2") has the seeded PR in the demo repo. The
            # explicit "with a citation sentinel" phrasing reliably drives the model
            # to actually cite (softer phrasings sometimes don't) - so this test
            # genuinely exercises the round-trip rather than passing vacuously when the
            # model chooses not to cite.
            # The natural rubric phrasing - deliberately NOT "with a citation sentinel".
            # With the strengthened system prompt + the fixed CitationStreamParser this
            # reliably cites Sarah's seeded PR (verified 5/5 live); if it ever regresses
            # to not citing, that's a real product defect worth surfacing, not test flake
            # to paper over.
            async for envelope in service.run("What is Sarah working on these days?"):
                events.append(envelope)
            await session.commit()

        event_names = {e.event for e in events}
        # The model streamed a real answer and actually reached for the GitHub tool.
        assert "token" in event_names
        assert "tool-status" in event_names
        # A cite-error would mean the model emitted a UUID that failed validation - the
        # exact failure the citation trust boundary exists to prevent. A raw sentinel
        # leaking as a token (the parser bug this test's fixture in test_citation_parser
        # now guards against) would show up as a token containing "{{cite".
        assert "cite-error" not in event_names
        leaked = any(isinstance(e.data, TokenEvent) and "{{cite" in e.data.text for e in events)
        assert not leaked, "a citation sentinel leaked through as a raw token"

        cite_data = [e.data for e in events if isinstance(e.data, CiteEvent)]
        assert cite_data, "model did not cite Sarah's PR on the natural query"

        async for session in db.get_session():
            messages = await message_repo.list_for_conversation(session, conversation.id)
            assistant_messages = [m for m in messages if m.role.value == "assistant"]
            assert assistant_messages
            citations = await message_citation_repo.list_for_message(
                session, assistant_messages[-1].id
            )
        assert len(citations) == len(cite_data)
        assert {c.ordinal for c in citations} == {d.ordinal for d in cite_data}
    finally:
        await token_store.delete_github_token(john.id)


async def test_validate_citation_valid_uuid_yields_cite_event() -> None:
    """Deterministic citation-round-trip: a sentinel referencing a real activity_items
    UUID validates and produces a cite envelope (not cite-error), independent of any
    model behavior. This is the citation trust boundary's happy path, asserted without
    live-model flakiness."""
    from app.repositories import activity_item_repo
    from app.schemas.chat import ActivityKind
    from app.schemas.chat import CiteEvent as CiteEventSchema
    from app.services.chat_service import ChatService as ChatServiceClass

    async for session in db.get_session():
        john = await team_member_repo.get_by_azure_upn(
            session, "john@ottavioantperuzzigmail.onmicrosoft.com"
        )
        assert john is not None
        conversation = await conversation_repo.create(session, john.id)
        item = await activity_item_repo.upsert(
            session,
            conversation_id=conversation.id,
            kind=ActivityKind.GITHUB_PR.value,
            external_id="999",
            label="PR #999",
            url="https://example.com/pr/999",
        )
        await session.commit()

        service = ChatServiceClass(session, conversation.id)
        pending: list[tuple[int, object]] = []
        envelope = await service._validate_citation(1, str(item.id), pending)  # type: ignore[arg-type]

    assert isinstance(envelope.data, CiteEventSchema)
    assert envelope.data.ordinal == 1
    assert envelope.data.item.id == item.id
    assert len(pending) == 1


async def test_validate_citation_unknown_uuid_yields_cite_error() -> None:
    """The trust boundary's failure path: a well-formed but unknown UUID (hallucinated
    or from another conversation) yields cite-error, never a rendered pill."""
    import uuid as uuid_module

    from app.schemas.chat import CiteErrorEvent as CiteErrorEventSchema
    from app.services.chat_service import ChatService as ChatServiceClass

    async for session in db.get_session():
        john = await team_member_repo.get_by_azure_upn(
            session, "john@ottavioantperuzzigmail.onmicrosoft.com"
        )
        assert john is not None
        conversation = await conversation_repo.create(session, john.id)
        await session.commit()

        service = ChatServiceClass(session, conversation.id)
        pending: list[tuple[int, object]] = []
        envelope = await service._validate_citation(1, str(uuid_module.uuid4()), pending)  # type: ignore[arg-type]

    assert isinstance(envelope.data, CiteErrorEventSchema)
    assert envelope.data.ordinal == 1
    assert pending == []
