from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    app_env: str = "development"

    openrouter_api_key: str

    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str
    azure_redirect_uri: str

    jira_oauth_client_id: str
    jira_oauth_client_secret: str
    jira_oauth_redirect_uri: str

    github_oauth_client_id: str
    github_oauth_client_secret: str
    github_oauth_redirect_uri: str

    key_vault_uri: str

    # Optional, CI-only: a service-principal credential for token_store.py's Key Vault
    # calls, distinct from azure_client_id/_secret/_tenant_id above (the unrelated SSO
    # app registration). Needed because EnvironmentCredential always reads the fixed
    # names AZURE_CLIENT_ID/_SECRET/_TENANT_ID with no way to alias them, and those are
    # already claimed by the SSO app's own credentials in every container that also
    # constructs Settings() - so a same-named var can't safely carry both meanings at
    # once. None in local dev/prod, where DefaultAzureCredential's Managed Identity/
    # az-login fallback already works; only CI sets these three.
    key_vault_client_id: str | None = None
    key_vault_client_secret: str | None = None
    key_vault_tenant_id: str | None = None

    # Cutoff for pre-fetch's top-projects/top-repos/top-collaborators discovery
    # (oauth-integration.md's Scope discovery section) - one shared knob, not three.
    discovery_top_n: int = 10

    # JQL/commits `since` window for "recent activity" queries (chat.md's previously-
    # known "this week" gap) - 14, not 7, so activity from slightly over a week ago
    # isn't silently dropped before the model ever sees it; the model still narrows to
    # "this week" in its own prose from the real timestamps it gets back.
    activity_lookback_days: int = 14

    # ChatService's agentic tool-call loop bound (chat.md's ChatService section) -
    # Phase 5's field, distinct from discovery_top_n above (Phase 1's).
    max_tool_call_rounds: int = 5


@lru_cache
def get_settings() -> Settings:
    return Settings()
