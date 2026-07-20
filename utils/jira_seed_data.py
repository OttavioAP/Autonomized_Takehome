"""Seed dummy JIRA issues across 3 projects (KAN + 2 new: MOB, DATA).

Narrative: KAN's issues mirror this project's own real timeline.md steps; MOB
("Mobile Companion App") and DATA ("Analytics Pipeline") are invented product
workstreams giving richer, varied real data across all 3 demo accounts
(John=Test_1, Sarah=Test_2, Mike=Test_3) per local-dev-data/team_members.json -
multiple projects/status/priority/type combos plus comment threads, so
scope-discovery's top-N lists and JIRA_COMMENT pills have real material to work
with instead of one thin project.

Re-runnable: skips creating a project if the key already exists, skips creating
an issue if one with the same summary already exists in its project, skips a
comment if its exact body is already present on the issue.

Usage: .venv/bin/python utils/jira_seed_data.py
"""

import json
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
BASE_URL = "https://autonomizedtest1.atlassian.net"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


# Each project: (key, name). Issues: (assignee, summary, description, issue_type,
# priority, status_transition_name or None for default "To Do",
# [(commenter_display_name, comment_text), ...])
PROJECTS = [
    ("KAN", "My Software Team"),
    ("MOB", "Mobile Companion App"),
    ("DATA", "Analytics Pipeline"),
]

ISSUES: dict[str, list[tuple]] = {
    "KAN": [
        (
            "Mike",
            "Stand up minimum structure/infra",
            "Scaffold the project structure and provision the minimum infrastructure "
            "needed for the chosen stack (repo layout, build tooling, cloud resources).",
            "Task",
            "Medium",
            "Done",
            [],
        ),
        (
            "John",
            "Deploy hello world to Microsoft Azure",
            "Prove the deployment path end-to-end with a trivial app before any real "
            "feature work, so infra problems surface early.",
            "Task",
            "Medium",
            "Done",
            [],
        ),
        (
            "Sarah",
            "Bare-minimum integrations",
            "Validate JIRA/GitHub API connectivity via local util scripts first, then "
            "evolve that into the actual MVP integration features with integration tests.",
            "Task",
            "Medium",
            "In Progress",
            [],
        ),
        (
            "Sarah",
            "Fix CI: lazy .env read in test_jira_client.py",
            "test_jira_client.py read Settings at import time, before pytest's env "
            "fixtures had a chance to inject the JIRA demo secrets CI needs.",
            "Task",
            "Medium",
            "In Progress",
            [("John", "Confirmed green on my end after this landed.")],
        ),
        (
            "Mike",
            "Production 500 on login: AZURE_CLIENT_ID hijacking Managed Identity resolution",
            "DefaultAzureCredential defaults managed_identity_client_id to "
            "AZURE_CLIENT_ID when unset - which is the SSO app registration's id, not "
            "a real user-assigned identity. Breaks Key Vault access in prod only.",
            "Bug",
            "High",
            "To Do",
            [
                (
                    "Mike",
                    "Repro'd via App Service log download - ManagedIdentityCredential "
                    "can't find a user-assigned identity matching that client id.",
                ),
                (
                    "John",
                    "Fix: pass managed_identity_client_id=None explicitly to force "
                    "system-assigned resolution instead of the env-var fallback.",
                ),
            ],
        ),
        (
            "John",
            "Chat UI polish: throbber, clickable pills, concurrent tool calls",
            "Add a send-to-first-token throbber, make activity pills read as clickable, "
            "and run same-round tool calls concurrently instead of sequentially.",
            "Story",
            "Medium",
            "Done",
            [],
        ),
        (
            "Sarah",
            "activity pill macro / resolve_citations markup duplication",
            "_activity_pill.html's Jinja macro and templating.py's resolve_citations "
            "filter both independently know how to render a pill - two copies of the "
            "same rendering logic, already caught drifting once.",
            "Bug",
            "Low",
            "To Do",
            [],
        ),
    ],
    "MOB": [
        (
            "John",
            "Onboarding flow: biometric login screen",
            "Add a biometric (Face ID / fingerprint) login option to the onboarding "
            "flow as an alternative to password entry.",
            "Story",
            "High",
            "In Progress",
            [
                (
                    "Sarah",
                    "Design mock is in Figma, let me know if the touch targets "
                    "look right on smaller screens.",
                )
            ],
        ),
        (
            "Sarah",
            "Push notification service integration",
            "Wire up the push notification service so the app can receive activity "
            "alerts while backgrounded.",
            "Task",
            "Medium",
            "Done",
            [],
        ),
        (
            "Mike",
            "Offline sync drops last-write on reconnect",
            "When the app regains connectivity after being offline, the most recent "
            "local edit is sometimes silently dropped instead of syncing.",
            "Bug",
            "High",
            "In Progress",
            [
                (
                    "Mike",
                    "Repro: edit while offline, background the app before "
                    "reconnect completes, foreground again - edit is gone.",
                ),
                (
                    "John",
                    "Sounds like a race between the sync queue flush and the "
                    "app-lifecycle pause - worth checking the queue drain order.",
                ),
            ],
        ),
        (
            "John",
            "Add dark mode toggle to settings screen",
            "Expose a manual dark mode toggle in settings rather than only following "
            "system preference.",
            "Task",
            "Low",
            "To Do",
            [],
        ),
        (
            "Sarah",
            "Push notification badge count out of sync on iOS",
            "The app icon badge count can drift from the actual unread count after "
            "marking notifications read in-app.",
            "Bug",
            "Medium",
            "To Do",
            [],
        ),
        (
            "Mike",
            "Offline-first cache layer for activity feed",
            "Cache the activity feed locally so it renders instantly on cold start, "
            "then reconciles with the server in the background.",
            "Story",
            "Medium",
            "Done",
            [],
        ),
    ],
    "DATA": [
        (
            "Mike",
            "Nightly ingestion job for event stream",
            "Stand up a nightly batch job that ingests the raw event stream into the warehouse.",
            "Task",
            "Medium",
            "Done",
            [],
        ),
        (
            "John",
            "Flaky ETL job: intermittent timeout on large partitions",
            "The nightly ETL job times out roughly 1 in 5 runs, only on partitions "
            "above a few million rows.",
            "Bug",
            "High",
            "In Progress",
            [
                (
                    "John",
                    "Looks like it's the join step, not the initial read - "
                    "timing spikes correlate with partition row count.",
                ),
                (
                    "Sarah",
                    "Could be worth pre-aggregating before the join instead of "
                    "joining the full partition.",
                ),
            ],
        ),
        (
            "Sarah",
            "Build usage dashboard for weekly active users",
            "A dashboard tracking weekly active users, broken out by feature area.",
            "Story",
            "Medium",
            "To Do",
            [],
        ),
        (
            "Mike",
            "Add retry/backoff to ingestion job",
            "The ingestion job currently fails hard on a transient upstream error "
            "instead of retrying with backoff.",
            "Task",
            "Low",
            "Done",
            [],
        ),
        (
            "John",
            "Dashboard shows stale data after timezone change",
            "Switching the dashboard's timezone filter doesn't invalidate the cached "
            "query results, so figures can look stale until a hard refresh.",
            "Bug",
            "Medium",
            "To Do",
            [],
        ),
    ],
}


def find_existing_project(base_url: str, auth: tuple[str, str], key: str) -> bool:
    resp = httpx.get(f"{base_url}/rest/api/3/project/{key}", auth=auth, timeout=10)
    return resp.status_code == 200


def create_project(
    base_url: str, auth: tuple[str, str], key: str, name: str, lead_account_id: str
) -> None:
    body = {
        "key": key,
        "name": name,
        "projectTypeKey": "software",
        "projectTemplateKey": "com.pyxis.greenhopper.jira:gh-simplified-agility-kanban",
        "leadAccountId": lead_account_id,
    }
    # Project creation is slow on this instance (confirmed live: one request took
    # >10s to respond even though it succeeded server-side) - longer timeout than
    # every other call in this script.
    resp = httpx.post(f"{base_url}/rest/api/3/project", auth=auth, json=body, timeout=30)
    resp.raise_for_status()


def find_existing_issue(
    base_url: str, auth: tuple[str, str], project_key: str, summary: str
) -> str | None:
    jql = f'project={project_key} AND summary~"{summary}"'
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


# KAN predates MOB/DATA and was provisioned with a narrower team-managed issue-type
# set (Epic/Subtask/Task/Story only, no Bug - confirmed live) - MOB/DATA got the
# fuller default set including Bug/Feature. Rather than hand-edit ISSUES' KAN
# entries, remap at creation time so the same data drives every project.
_ISSUE_TYPE_FALLBACK = {"KAN": {"Bug": "Task"}}


def create_issue(
    base_url: str,
    auth: tuple[str, str],
    project_key: str,
    account_id: str,
    summary: str,
    description: str,
    issue_type: str,
    priority: str,
) -> str:
    issue_type = _ISSUE_TYPE_FALLBACK.get(project_key, {}).get(issue_type, issue_type)
    body = {
        "fields": {
            "project": {"key": project_key},
            "summary": summary,
            "description": {
                "type": "doc",
                "version": 1,
                "content": [
                    {"type": "paragraph", "content": [{"type": "text", "text": description}]}
                ],
            },
            "issuetype": {"name": issue_type},
            "priority": {"name": priority},
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


def existing_comment_bodies(base_url: str, auth: tuple[str, str], issue_id: str) -> set[str]:
    resp = httpx.get(f"{base_url}/rest/api/3/issue/{issue_id}/comment", auth=auth, timeout=10)
    resp.raise_for_status()
    bodies = set()
    for c in resp.json()["comments"]:
        for block in c["body"].get("content", []):
            for node in block.get("content", []):
                if node.get("type") == "text":
                    bodies.add(node["text"])
    return bodies


def add_comment(
    base_url: str, auth: tuple[str, str], issue_id: str, commenter_auth: tuple[str, str], text: str
) -> None:
    body = {
        "body": {
            "type": "doc",
            "version": 1,
            "content": [{"type": "paragraph", "content": [{"type": "text", "text": text}]}],
        }
    }
    resp = httpx.post(
        f"{base_url}/rest/api/3/issue/{issue_id}/comment",
        auth=commenter_auth,
        json=body,
        timeout=10,
    )
    resp.raise_for_status()


def main() -> None:
    env = load_env(REPO_ROOT / ".env")
    team_members = json.loads((REPO_ROOT / "local-dev-data" / "team_members.json").read_text())
    by_name = {m["display_name"]: m for m in team_members}

    # Test_1 is the backend service credential; used to authenticate project/issue
    # creation. Comments are posted with each commenter's own credentials so the
    # comment author is that person, not always Test_1.
    email = env["Autonomized_Test_1_Protonmail_Email"]
    token = env["Autonomized_Test_1_Jira_API_Key"]
    if not email or not token:
        print("Missing Test_1 JIRA credentials in .env", file=sys.stderr)
        sys.exit(1)
    auth = (email, token)

    email_to_n = {
        "Autonomized_Test_1@proton.me": 1,
        "Autonomized_Test_2@proton.me": 2,
        "Autonomized_Test_3@proton.me": 3,
    }
    account_ids: dict[str, str] = {}
    member_auths: dict[str, tuple[str, str]] = {}
    for name, member in by_name.items():
        n = email_to_n[member["jira_account_email"]]
        member_email = env[f"Autonomized_Test_{n}_Protonmail_Email"]
        member_token = env[f"Autonomized_Test_{n}_Jira_API_Key"]
        member_auths[name] = (member_email, member_token)
        resp = httpx.get(
            f"{BASE_URL}/rest/api/3/myself", auth=(member_email, member_token), timeout=10
        )
        resp.raise_for_status()
        account_ids[name] = resp.json()["accountId"]

    for key, name in PROJECTS:
        if find_existing_project(BASE_URL, auth, key):
            print(f"SKIP (project exists): {key}")
            continue
        create_project(BASE_URL, auth, key, name, account_ids["John"])
        print(f"Created project {key}: {name}")

    for project_key, issues in ISSUES.items():
        for assignee, summary, description, issue_type, priority, status, comments in issues:
            existing = find_existing_issue(BASE_URL, auth, project_key, summary)
            if existing:
                issue_id = existing
                print(f"SKIP (issue exists): [{project_key}] {summary} [{issue_id}]")
            else:
                issue_id = create_issue(
                    BASE_URL,
                    auth,
                    project_key,
                    account_ids[assignee],
                    summary,
                    description,
                    issue_type,
                    priority,
                )
                print(f"Created issue {issue_id}: [{project_key}] {summary} (assignee={assignee})")
                if status and status != "To Do":
                    transition_issue(BASE_URL, auth, issue_id, status)
                    print(f"  -> transitioned to {status}")

            if not comments:
                continue
            existing_bodies = existing_comment_bodies(BASE_URL, auth, issue_id)
            for commenter, text in comments:
                if text in existing_bodies:
                    print(f"  SKIP (comment exists): {text[:40]}...")
                    continue
                add_comment(BASE_URL, auth, issue_id, member_auths[commenter], text)
                print(f"  Added comment by {commenter}: {text[:40]}...")


if __name__ == "__main__":
    main()
