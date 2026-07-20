"""Page + conversation routes (chat.md's Routes section). All own their transaction
per CLAUDE.md - ChatService/pre_fetch/repositories never commit; these handlers do,
once at the end of the happy path. The session cookie identifies WHO is logged in;
the active conversation is carried in the URL path, not the session.
"""

import json
import logging
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api import oauth as oauth_routes
from app.auth.dependency import get_current_user
from app.db.models.session import UserSession
from app.db.models.team_member import TeamMember
from app.db.session import db
from app.repositories import conversation_repo, message_repo, team_member_repo
from app.services import pre_fetch
from app.services.chat_service import ChatService
from app.templating import templates

router = APIRouter()
logger = logging.getLogger(__name__)


async def _run_pre_fetch_background(conversation_id: uuid.UUID, team_member: TeamMember) -> None:
    """Fire-and-forget task body for the optimistic pre-fetch kicked off by
    conversation_view() - never awaited by the request, so any exception here would
    otherwise vanish silently into an unretrieved Task exception. Logged instead."""
    async with db.new_session() as session:
        try:
            await pre_fetch.run(session, conversation_id, team_member)
            await session.commit()
        except Exception:
            logger.exception("Background pre-fetch failed for conversation_id=%s", conversation_id)


async def _require_team_member(db_session: AsyncSession, current_user: UserSession) -> uuid.UUID:
    """Resolves the current Azure session to its team_members row, enforcing the same
    both-providers-connected gate app/api/auth.py's callback redirects through - any
    route below that reaches ChatService/pre-fetch can assume both tokens exist."""
    team_member = await team_member_repo.get_by_azure_upn(db_session, current_user.user_upn)
    if team_member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No team member record for this account"
        )
    return team_member.id


@router.get("/")
async def index(
    current_user: UserSession = Depends(get_current_user),
    db_session: AsyncSession = Depends(db.get_session),
):
    """No longer the conversation view itself - redirects into the user's most recent
    conversation, creating one if they have none (so a first-time user never hits a
    dead end). The oauth gate still applies before any conversation is reachable."""
    team_member = await team_member_repo.get_by_azure_upn(db_session, current_user.user_upn)
    if team_member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No team member record for this account"
        )
    if not await oauth_routes.both_connected(db_session, team_member.id):
        return RedirectResponse(url="/oauth/connect", status_code=302)

    conversation = await conversation_repo.get_most_recent(db_session, team_member.id)
    if conversation is None:
        conversation = await conversation_repo.create(db_session, team_member.id)
        await db_session.commit()
    return RedirectResponse(url=f"/conversations/{conversation.id}", status_code=302)


@router.get("/conversations/{conversation_id}")
async def conversation_view(
    request: Request,
    conversation_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    current_user: UserSession = Depends(get_current_user),
    db_session: AsyncSession = Depends(db.get_session),
):
    team_member_id = await _require_team_member(db_session, current_user)
    conversation = await conversation_repo.get_by_id(db_session, conversation_id)
    # Ownership check via team_member_id, not just existence - a UUID belonging to
    # another user 404s (not 403) so it's indistinguishable from a nonexistent id.
    if conversation is None or conversation.team_member_id != team_member_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    team_member = await team_member_repo.get_by_azure_upn(db_session, current_user.user_upn)
    assert team_member is not None
    if conversation.prefetched_at is None:
        # Optimistic, non-blocking: the page renders immediately rather than waiting
        # on live JIRA/GitHub round-trips. FastAPI's BackgroundTasks runs this after
        # the response is sent, on the same event loop but outside the request scope -
        # unlike a bare asyncio.create_task(), it isn't at risk of being cancelled the
        # moment the response completes. Runs against its own session (not db_session,
        # which belongs to a request scope this task outlives) and commits
        # independently once done. ChatService.run() doesn't require prefetched_at to
        # be set - it just reads whatever activity_items rows exist at chat time, so a
        # user who sends a message before this finishes gets a thinner "own activity"
        # context for that one turn at worst, not an error; the model can still
        # tool-call to compensate.
        background_tasks.add_task(_run_pre_fetch_background, conversation_id, team_member)

    messages = await message_repo.list_out_for_conversation(db_session, conversation_id)
    conversations = await conversation_repo.list_for_team_member(db_session, team_member_id)

    return templates.TemplateResponse(
        request=request,
        name="chat.html",
        context={
            "current_user": current_user,
            "conversation_id": conversation_id,
            "messages": messages,
            "conversations": conversations,
        },
    )


@router.post("/conversations")
async def create_conversation(
    current_user: UserSession = Depends(get_current_user),
    db_session: AsyncSession = Depends(db.get_session),
):
    team_member_id = await _require_team_member(db_session, current_user)
    conversation = await conversation_repo.create(db_session, team_member_id)
    await db_session.commit()
    return RedirectResponse(url=f"/conversations/{conversation.id}", status_code=302)


@router.post("/conversations/{conversation_id}/chat")
async def conversation_chat(
    conversation_id: uuid.UUID,
    query: str = Form(...),
    csrf_token: str = Form(...),
    current_user: UserSession = Depends(get_current_user),
    db_session: AsyncSession = Depends(db.get_session),
):
    if not secrets.compare_digest(current_user.csrf_token, csrf_token):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid CSRF token")

    team_member_id = await _require_team_member(db_session, current_user)
    conversation = await conversation_repo.get_by_id(db_session, conversation_id)
    if conversation is None or conversation.team_member_id != team_member_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")

    service = ChatService(db_session, conversation_id)

    async def event_stream():
        # The route owns the transaction (CLAUDE.md): ChatService never commits;
        # once its generator is exhausted, we commit the whole turn (user message +
        # assistant message + citations + conversation bump) atomically. An exception
        # mid-stream leaves the async-with in db.get_session() to close/discard.
        async for envelope in service.run(query):
            payload = json.dumps(envelope.data.model_dump(mode="json"))
            yield f"event: {envelope.event}\ndata: {payload}\n\n"
        await db_session.commit()

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/login")
async def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html", context={})


@router.get("/ping")
async def ping(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="_ping_result.html",
        context={"timestamp": datetime.now(UTC).isoformat()},
    )
