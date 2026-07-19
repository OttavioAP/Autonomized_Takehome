from app.config import get_settings
from app.integrations.jira_client import (
    build_client,
    find_account_id_by_email,
    get_issues_assigned_to,
)


async def test_get_issues_assigned_to_returns_seeded_issue() -> None:
    settings = get_settings()
    client = build_client(settings.jira_base_url, settings.jira_email, settings.jira_api_token)
    async with client:
        # John (Test_1) is seeded (utils/jira_seed_data.py) with "Deploy hello world to
        # Microsoft Azure", status Done.
        account_id = await find_account_id_by_email(client, settings.jira_email)
        assert account_id is not None

        issues = await get_issues_assigned_to(client, settings.jira_project_key, account_id)

    assert any(issue.summary == "Deploy hello world to Microsoft Azure" for issue in issues)
    seeded = next(i for i in issues if i.summary == "Deploy hello world to Microsoft Azure")
    assert seeded.status == "Done"
    assert seeded.assignee_account_id == account_id


async def test_find_account_id_by_email_unknown_user_returns_none() -> None:
    settings = get_settings()
    client = build_client(settings.jira_base_url, settings.jira_email, settings.jira_api_token)
    async with client:
        account_id = await find_account_id_by_email(client, "nonexistent-user@example.com")

    assert account_id is None


async def test_get_issues_assigned_to_unknown_account_returns_empty() -> None:
    settings = get_settings()
    client = build_client(settings.jira_base_url, settings.jira_email, settings.jira_api_token)
    async with client:
        issues = await get_issues_assigned_to(
            client, settings.jira_project_key, "000000:00000000-0000-0000-0000-000000000000"
        )

    assert issues == []
