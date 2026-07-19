"""Azure AD OIDC confidential-client flow. Framework-agnostic: plain functions
taking config as arguments, no FastAPI imports. See blueprints/specs/stack-and-infra.md
for the architecture this implements.
"""

import secrets
from typing import Any

import httpx
from jose import jwt
from jose.exceptions import JWTError


class TokenValidationError(Exception):
    pass


def authority(tenant_id: str) -> str:
    return f"https://login.microsoftonline.com/{tenant_id}"


def issuer(tenant_id: str) -> str:
    return f"{authority(tenant_id)}/v2.0"


def build_authorize_url(tenant_id: str, client_id: str, redirect_uri: str, state: str) -> str:
    params = httpx.QueryParams(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "response_mode": "query",
            "scope": "openid profile email",
            "state": state,
        }
    )
    return f"{authority(tenant_id)}/oauth2/v2.0/authorize?{params}"


def generate_state() -> str:
    return secrets.token_urlsafe(32)


async def exchange_code_for_tokens(
    client: httpx.AsyncClient,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code: str,
) -> dict[str, Any]:
    resp = await client.post(
        f"{authority(tenant_id)}/oauth2/v2.0/token",
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "scope": "openid profile email",
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    return resp.json()


async def fetch_jwks(client: httpx.AsyncClient, tenant_id: str) -> dict[str, Any]:
    resp = await client.get(f"{authority(tenant_id)}/discovery/v2.0/keys")
    resp.raise_for_status()
    return resp.json()


def validate_id_token(
    id_token: str, jwks: dict[str, Any], tenant_id: str, client_id: str
) -> dict[str, Any]:
    """Validates signature, issuer, audience, and expiry. Raises TokenValidationError
    on any failure rather than returning a partially-trusted claims dict.
    """
    try:
        claims: dict[str, Any] = jwt.decode(
            id_token,
            jwks,
            algorithms=["RS256"],
            audience=client_id,
            issuer=issuer(tenant_id),
        )
    except JWTError as exc:
        raise TokenValidationError(str(exc)) from exc
    return claims
