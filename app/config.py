from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str
    app_env: str = "development"

    jira_base_url: str
    jira_project_key: str
    jira_email: str
    jira_api_token: str

    github_token: str
    github_repo: str

    openrouter_api_key: str

    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str
    azure_redirect_uri: str


@lru_cache
def get_settings() -> Settings:
    return Settings()
