"""Seed a minimal first pass of dummy JIRA issues into KAN (timeline.md step 5, Phase B).

Narrative: issues mirror this project's own real timeline.md steps, assigned across
the 3 demo accounts (John=Test_1, Sarah=Test_2, Mike=Test_3) per local-dev-data/team_members.json.
Re-runnable: skips creating an issue if one with the same summary already exists.

Usage: .venv/bin/python utils/jira_seed_data.py
"""

import json
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://autonomizedtest1.atlassian.net"
PROJECT_KEY = "KAN"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


# (assignee display_name, summary, description, status_transition_name or None for default "To Do")
ISSUES = [
    (
        "Mike",
        "Stand up minimum structure/infra",
        "Scaffold the project structure and provision the minimum infrastructure needed "
        "for the chosen stack (repo layout, build tooling, cloud resources).",
        "Done",
    ),
    (
        "John",
        "Deploy hello world to Microsoft Azure",
        "Prove the deployment path end-to-end with a trivial app before any real feature "
        "work, so infra problems surface early.",
        "Done",
    ),
    (
        "Sarah",
        "Bare-minimum integrations",
        "Validate JIRA/GitHub API connectivity via local util scripts first, then evolve "
        "that into the actual MVP integration features with integration tests.",
        "In Progress",
    ),
]


def find_existing_issue(base_url: str, auth: tuple[str, str], summary: str) -> str | None:
    jql = f'project={PROJECT_KEY} AND summary~"{summary}"'
    resp = httpx.get(
        f"{base_url}/rest/api/3/search/jql",
        params={"jql": jql, "maxResults": 5, "fields": "summary"},
        auth=auth,
        timeout=10,
    )
    resp.raise_for_status()
    for issue in resp.json().get("issues", []):
        if issue.get("fields", {}).get("summary") == summary:
            return issue["id"]
    return None


def create_issue(
    base_url: str, auth: tuple[str, str], account_id: str, summary: str, description: str
) -> str:
    body = {
        "fields": {
            "project": {"key": PROJECT_KEY},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": description}]}
                ],
            },
            "issuetype": {"name": "Task"},
            "assignee": {"accountId": account_id},
        }
    }
    resp = httpx.post(f"{base_url}/rest/api/3/issue", auth=auth, json=body, timeout=10)
    resp.raise_for_status()
    return resp.json()["id"]


def transition_issue(base_url: str, auth: tuple[str, str], issue_id: str, status_name: str) -> None:
    resp = httpx.get(f"{base_url}/rest/api/3/issue/{issue_id}/transitions", auth=auth, timeout=10)
    resp.raise_for_status()
    target = status_name.lower()
    for t in resp.json()["transitions"]:
        if t["name"].lower() == target or t["to"]["name"].lower() == target:
            httpx.post(
                f"{base_url}/rest/api/3/issue/{issue_id}/transitions",
                auth=auth,
                json={"transition": {"id": t["id"]}},
                timeout=10,
            ).raise_for_status()
            return
    print(f"  (no transition to '{status_name}' found, leaving as default)")


def main() -> None:
    env = load_env(REPO_ROOT / ".env")
    team_members = json.loads((REPO_ROOT / "local-dev-data" / "team_members.json").read_text())
    by_name = {m["display_name"]: m for m in team_members}

    # Test_1 is the backend service credential; used to authenticate all calls here too.
    email = env["Autonomized_Test_1_Protonmail_Email"]
    token = env["Autonomized_Test_1_Jira_API_Key"]
    if not email or not token:
        print("Missing Test_1 JIRA credentials in .env", file=sys.stderr)
        sys.exit(1)
    auth = (email, token)

    # Resolve accountIds for each display name via /myself with each account's own creds
    email_to_n = {
        "Autonomized_Test_1@proton.me": 1,
        "Autonomized_Test_2@proton.me": 2,
        "Autonomized_Test_3@proton.me": 3,
    }
    account_ids: dict[str, str] = {}
    for name, member in by_name.items():
        n = email_to_n[member["jira_account_email"]]
        member_email = env[f"Autonomized_Test_{n}_Protonmail_Email"]
        member_token = env[f"Autonomized_Test_{n}_Jira_API_Key"]
        resp = httpx.get(
            f"{BASE_URL}/rest/api/3/myself", auth=(member_email, member_token), timeout=10
        )
        resp.raise_for_status()
        account_ids[name] = resp.json()["accountId"]

    for assignee, summary, description, status in ISSUES:
        existing = find_existing_issue(BASE_URL, auth, summary)
        if existing:
            print(f"SKIP (exists): {summary} [{existing}]")
            continue
        issue_id = create_issue(BASE_URL, auth, account_ids[assignee], summary, description)
        print(f"Created issue {issue_id}: {summary} (assignee={assignee})")
        if status and status != "To Do":
            transition_issue(BASE_URL, auth, issue_id, status)
            print(f"  -> transitioned to {status}")


if __name__ == "__main__":
    main()
