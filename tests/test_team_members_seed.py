import json
from pathlib import Path

from sqlalchemy import select

from app.db.models.team_member import TeamMember
from app.db.session import db

FIXTURE_PATH = Path(__file__).resolve().parent.parent / "local-dev-data" / "team_members.json"


async def test_seeded_team_members_match_fixture() -> None:
    """Phase 1 step 0's gate: seed -> query back -> matches fixture."""
    fixture_rows = {row["azure_upn"]: row for row in json.loads(FIXTURE_PATH.read_text())}

    async for session in db.get_session():
        result = await session.execute(select(TeamMember))
        seeded = {tm.azure_upn: tm for tm in result.scalars()}

    assert seeded.keys() == fixture_rows.keys()
    for upn, expected in fixture_rows.items():
        actual = seeded[upn]
        assert actual.display_name == expected["display_name"]
        assert actual.jira_account_email == expected["jira_account_email"]
        assert actual.github_login == expected["github_login"]
        assert actual.jira_cloud_id is None
