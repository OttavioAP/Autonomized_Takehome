"""Azure Key Vault-backed OAuth token storage, keyed by team_member_id. Framework-agnostic:
plain functions taking config as arguments, no FastAPI imports. See
blueprints/plans/features/oauth-integration.md's "Token storage" section for the design
this implements.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID

from azure.core.credentials_async import AsyncTokenCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.identity.aio import ClientSecretCredential, DefaultAzureCredential
from azure.keyvault.secrets.aio import SecretClient
from pydantic import BaseModel

from app.config import get_settings

# JIRA access tokens live ~1 hour (Atlassian's own lifetime); this mirrors that as a Key
# Vault hygiene TTL, not a source of truth - refresh_access_token overwrites this secret
# with a fresh one on every use anyway.
JIRA_ACCESS_TOKEN_TTL = timedelta(hours=1)


class JiraTokens(BaseModel):
    access_token: str
    refresh_token: str


def _jira_access_name(team_member_id: UUID) -> str:
    return f"user-{team_member_id}-jira-access"


def _jira_refresh_name(team_member_id: UUID) -> str:
    return f"user-{team_member_id}-jira-refresh"


def _github_name(team_member_id: UUID) -> str:
    return f"user-{team_member_id}-github"


settings = get_settings()

# Keyed by event loop rather than a single module-level instance: SecretClient's aiohttp
# transport binds its connector to whichever loop is running when it's first used, so a
# client built under one loop breaks once that loop closes (e.g. each pytest-asyncio test
# function gets its own loop). Reused within a loop's lifetime, not reconstructed per call.
_clients: dict[asyncio.AbstractEventLoop, SecretClient] = {}


def _credential() -> AsyncTokenCredential:
    # CI has no Managed Identity and no az-login session, so it needs an explicit
    # service-principal credential - but EnvironmentCredential (part of
    # DefaultAzureCredential's fallback chain) always reads the fixed names
    # AZURE_CLIENT_ID/_SECRET/_TENANT_ID with no way to alias them, and those names
    # are already claimed by the unrelated SSO app registration's own credentials in
    # every container that also constructs Settings() (app/auth/oidc.py). Rather than
    # let a same-named var carry two different meanings depending on which job is
    # running, key_vault_client_id/_secret/_tenant_id are distinctly-named Settings
    # fields, unset (None) everywhere except CI, and ClientSecretCredential takes
    # them as constructor arguments instead of relying on fixed env var names at all.
    if (
        settings.key_vault_client_id
        and settings.key_vault_client_secret
        and settings.key_vault_tenant_id
    ):
        return ClientSecretCredential(
            tenant_id=settings.key_vault_tenant_id,
            client_id=settings.key_vault_client_id,
            client_secret=settings.key_vault_client_secret,
        )
    # exclude_environment_credential: without this, DefaultAzureCredential would still
    # try EnvironmentCredential first using the SSO app's AZURE_CLIENT_ID/_SECRET/
    # _TENANT_ID (see above) before ever reaching Managed Identity (prod) / the
    # az-login identity (local dev), which are the credentials that actually have a
    # Key Vault role assignment - the SSO app has none and every call would 403.
    return DefaultAzureCredential(exclude_environment_credential=True)


def _client() -> SecretClient:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None:
        client = SecretClient(vault_url=settings.key_vault_uri, credential=_credential())
        _clients[loop] = client
    return client


async def store_jira_tokens(team_member_id: UUID, access_token: str, refresh_token: str) -> None:
    expires_on = datetime.now(UTC) + JIRA_ACCESS_TOKEN_TTL
    await _client().set_secret(
        _jira_access_name(team_member_id), access_token, expires_on=expires_on
    )
    await _client().set_secret(_jira_refresh_name(team_member_id), refresh_token)


async def get_jira_tokens(team_member_id: UUID) -> JiraTokens | None:
    """Returns None if not connected (no secrets exist for this user)."""
    try:
        access = await _client().get_secret(_jira_access_name(team_member_id))
        refresh = await _client().get_secret(_jira_refresh_name(team_member_id))
    except ResourceNotFoundError:
        return None
    # A secret that exists but has no value would mean vault corruption, not "not
    # connected" - fail loudly rather than treating it the same as ResourceNotFoundError.
    assert access.value is not None
    assert refresh.value is not None
    return JiraTokens(access_token=access.value, refresh_token=refresh.value)


async def store_github_token(team_member_id: UUID, access_token: str) -> None:
    await _client().set_secret(_github_name(team_member_id), access_token)


async def get_github_token(team_member_id: UUID) -> str | None:
    """Returns None if not connected."""
    try:
        secret = await _client().get_secret(_github_name(team_member_id))
    except ResourceNotFoundError:
        return None
    assert secret.value is not None
    return secret.value


async def delete_jira_tokens(team_member_id: UUID) -> None:
    """No-op if nothing exists (idempotent disconnect)."""
    for name in (_jira_access_name(team_member_id), _jira_refresh_name(team_member_id)):
        try:
            await _client().delete_secret(name)
        except ResourceNotFoundError:
            pass


async def delete_github_token(team_member_id: UUID) -> None:
    """No-op if nothing exists (idempotent disconnect)."""
    try:
        await _client().delete_secret(_github_name(team_member_id))
    except ResourceNotFoundError:
        pass
