"""Seed dummy GitHub activity across 3 repos (Autonomized_Test_Project_1 + 2 new:
mobile-companion-app, analytics-pipeline).

Narrative: Autonomized_Test_Project_1's activity mirrors this project's own real
timeline.md steps; mobile-companion-app and analytics-pipeline are invented
product workstreams (matching utils/jira_seed_data.py's MOB/DATA projects)
giving richer, varied real data across all 3 demo accounts (John=Test_1,
Sarah=Test_2, Mike=Test_3) - multiple repos, commits, PRs (open/merged), real
review decisions (APPROVED/CHANGES_REQUESTED), and PR comments, so
scope-discovery's top-N repo/contributor lists and GITHUB_COMMENT pills have
real material instead of one thin repo.

Mechanics: new repos are created under John's account (Autonomized1); Sarah/Mike
need an explicit collaborator invite (accepted with their own PAT - GitHub
invites are pending until accepted, an account doesn't become a real
collaborator just from being invited, confirmed live) before they can push
commits or open PRs against it.

Re-runnable: skips creating a repo if it already exists, skips a commit if that
file path already exists on the target branch, skips a PR if one already exists
for that branch, skips a review/comment if an equivalent one is already present.

Usage: .venv/bin/python utils/github_seed_data.py
"""

import base64
import sys
from datetime import datetime, timedelta
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
API = "https://api.github.com"
OWNER = "Autonomized1"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def headers_for(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def repo_exists(token: str, repo: str) -> bool:
    resp = httpx.get(f"{API}/repos/{repo}", headers=headers_for(token), timeout=10)
    return resp.status_code == 200


def create_repo(token: str, name: str, description: str) -> None:
    resp = httpx.post(
        f"{API}/user/repos",
        headers=headers_for(token),
        json={"name": name, "description": description, "private": True, "auto_init": True},
        timeout=15,
    )
    resp.raise_for_status()


def ensure_collaborator(owner_token: str, repo: str, login: str, collaborator_token: str) -> None:
    resp = httpx.get(
        f"{API}/repos/{repo}/collaborators", headers=headers_for(owner_token), timeout=10
    )
    resp.raise_for_status()
    if any(c["login"] == login for c in resp.json()):
        return
    resp = httpx.put(
        f"{API}/repos/{repo}/collaborators/{login}",
        headers=headers_for(owner_token),
        json={"permission": "push"},
        timeout=10,
    )
    resp.raise_for_status()
    # Pending until accepted with the invitee's own token - confirmed live, an
    # invite alone does not grant push access.
    resp = httpx.get(
        f"{API}/user/repository_invitations", headers=headers_for(collaborator_token), timeout=10
    )
    resp.raise_for_status()
    invite = next((i for i in resp.json() if i["repository"]["full_name"] == repo), None)
    if invite is None:
        raise RuntimeError(f"No pending invite found for {login} on {repo}")
    resp = httpx.patch(
        f"{API}/user/repository_invitations/{invite['id']}",
        headers=headers_for(collaborator_token),
        timeout=10,
    )
    resp.raise_for_status()
    print(f"  Added collaborator {login} on {repo}")


def put_file(
    token: str,
    repo: str,
    path: str,
    content: str,
    message: str,
    branch: str,
    author_name: str,
    author_email: str,
    date_iso: str,
    sha: str | None = None,
) -> dict:
    body = {
        "message": message,
        "content": base64.b64encode(content.encode()).decode(),
        "branch": branch,
        "author": {"name": author_name, "email": author_email, "date": date_iso},
        "committer": {"name": author_name, "email": author_email, "date": date_iso},
    }
    if sha:
        body["sha"] = sha
    resp = httpx.put(
        f"{API}/repos/{repo}/contents/{path}", headers=headers_for(token), json=body, timeout=15
    )
    resp.raise_for_status()
    return resp.json()


def get_file_sha(token: str, repo: str, path: str, ref: str) -> str | None:
    resp = httpx.get(
        f"{API}/repos/{repo}/contents/{path}",
        headers=headers_for(token),
        params={"ref": ref},
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json()["sha"]
    return None


def create_branch(token: str, repo: str, branch: str, from_sha: str) -> None:
    resp = httpx.post(
        f"{API}/repos/{repo}/git/refs",
        headers=headers_for(token),
        json={"ref": f"refs/heads/{branch}", "sha": from_sha},
        timeout=10,
    )
    if resp.status_code not in (201, 422):  # 422 = ref already exists
        resp.raise_for_status()


def get_branch_sha(token: str, repo: str, branch: str) -> str | None:
    resp = httpx.get(
        f"{API}/repos/{repo}/git/ref/heads/{branch}", headers=headers_for(token), timeout=10
    )
    if resp.status_code == 200:
        return resp.json()["object"]["sha"]
    return None


def find_pr(token: str, repo: str, head: str) -> dict | None:
    resp = httpx.get(
        f"{API}/repos/{repo}/pulls",
        headers=headers_for(token),
        params={"state": "all", "head": f"{OWNER}:{head}"},
        timeout=10,
    )
    resp.raise_for_status()
    prs = resp.json()
    return prs[0] if prs else None


def open_pr(token: str, repo: str, title: str, body: str, head: str, base: str) -> dict:
    resp = httpx.post(
        f"{API}/repos/{repo}/pulls",
        headers=headers_for(token),
        json={"title": title, "body": body, "head": head, "base": base},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def merge_pr(token: str, repo: str, pr_number: int) -> None:
    resp = httpx.put(
        f"{API}/repos/{repo}/pulls/{pr_number}/merge", headers=headers_for(token), timeout=10
    )
    resp.raise_for_status()


def existing_reviews(token: str, repo: str, pr_number: int) -> list[dict]:
    resp = httpx.get(
        f"{API}/repos/{repo}/pulls/{pr_number}/reviews", headers=headers_for(token), timeout=10
    )
    resp.raise_for_status()
    return resp.json()


def add_review(token: str, repo: str, pr_number: int, event: str, body: str) -> None:
    resp = httpx.post(
        f"{API}/repos/{repo}/pulls/{pr_number}/reviews",
        headers=headers_for(token),
        json={"event": event, "body": body},
        timeout=10,
    )
    resp.raise_for_status()


def existing_issue_comments(token: str, repo: str, issue_number: int) -> set[str]:
    resp = httpx.get(
        f"{API}/repos/{repo}/issues/{issue_number}/comments", headers=headers_for(token), timeout=10
    )
    resp.raise_for_status()
    return {c["body"] for c in resp.json()}


def add_issue_comment(token: str, repo: str, issue_number: int, body: str) -> None:
    resp = httpx.post(
        f"{API}/repos/{repo}/issues/{issue_number}/comments",
        headers=headers_for(token),
        json={"body": body},
        timeout=10,
    )
    resp.raise_for_status()


def seed_direct_commits(accounts: dict, repo: str, commits: list[tuple]) -> None:
    """commits: [(account_name, path, content, message, date_iso), ...] on main."""
    for name, path, content, message, date_iso in commits:
        acc = accounts[name]
        if get_file_sha(acc["token"], repo, path, "main"):
            print(f"  SKIP (exists): {path} on {repo}@main")
            continue
        put_file(
            acc["token"], repo, path, content, message, "main", acc["name"], acc["email"], date_iso
        )
        print(f"  Committed {path} to {repo}@main ({name})")


def seed_pr(
    accounts: dict,
    repo: str,
    author: str,
    branch: str,
    path: str,
    content: str,
    message: str,
    date_iso: str,
    pr_title: str,
    pr_body: str,
    merge: bool,
    reviews: list[tuple],  # [(reviewer_name, event, body), ...]
    comments: list[tuple],  # [(commenter_name, body), ...]
) -> None:
    acc = accounts[author]
    main_sha = get_branch_sha(acc["token"], repo, "main")
    assert main_sha, f"main branch should exist on {repo} before opening a PR"
    create_branch(acc["token"], repo, branch, main_sha)

    if get_file_sha(acc["token"], repo, path, branch):
        print(f"  SKIP (exists): {path} on {repo}@{branch}")
    else:
        put_file(
            acc["token"], repo, path, content, message, branch, acc["name"], acc["email"], date_iso
        )
        print(f"  Committed {path} to {repo}@{branch} ({author})")

    pr = find_pr(acc["token"], repo, branch)
    if pr is None:
        pr = open_pr(acc["token"], repo, pr_title, pr_body, branch, "main")
        print(f"  Opened PR #{pr['number']}: {pr['title']}")
    else:
        print(f"  SKIP (exists): PR #{pr['number']} for {branch}")
    pr_number = pr["number"]

    existing = existing_reviews(acc["token"], repo, pr_number)
    for reviewer_name, event, body in reviews:
        reviewer = accounts[reviewer_name]
        if any(r.get("user", {}).get("login") == reviewer["login"] for r in existing):
            print(f"  SKIP (review exists): {reviewer_name} on PR #{pr_number}")
            continue
        add_review(reviewer["token"], repo, pr_number, event, body)
        print(f"  Added review by {reviewer_name} ({event}) on PR #{pr_number}")

    existing_bodies = existing_issue_comments(acc["token"], repo, pr_number)
    for commenter_name, body in comments:
        if body in existing_bodies:
            print(f"  SKIP (comment exists): {body[:40]}...")
            continue
        add_issue_comment(accounts[commenter_name]["token"], repo, pr_number, body)
        print(f"  Added comment by {commenter_name} on PR #{pr_number}: {body[:40]}...")

    if merge and pr.get("state") != "closed":
        merge_pr(acc["token"], repo, pr_number)
        print(f"  Merged PR #{pr_number}")


def main() -> None:
    env = load_env(REPO_ROOT / ".env")
    accounts = {
        "John": {
            "token": env["Autonomized_Test_1_Github_PAT"],
            "login": "Autonomized1",
            "name": "John (Autonomized_Test_1)",
            "email": "Autonomized_Test_1@proton.me",
        },
        "Sarah": {
            "token": env["Autonomized_Test_2_Github_PAT"],
            "login": "autonomized2",
            "name": "Sarah (Autonomized_Test_2)",
            "email": "Autonomized_Test_2@proton.me",
        },
        "Mike": {
            "token": env["Autonomized_Test_3_Github_PAT"],
            "login": "autonomized3",
            "name": "Mike (Autonomized_Test_3)",
            "email": "Autonomized_Test_3@proton.me",
        },
    }
    for name, acc in accounts.items():
        if not acc["token"]:
            print(f"Missing GitHub PAT for {name}", file=sys.stderr)
            sys.exit(1)

    john = accounts["John"]

    # ---------- Repos ----------
    repos = [
        (
            "Autonomized_Test_Project_1",
            None,  # pre-existing, already has both collaborators from the original seed pass
        ),
        ("mobile-companion-app", "Companion mobile app for the Team Activity Monitor."),
        ("analytics-pipeline", "Analytics/ETL pipeline for team activity data."),
    ]
    for repo_name, description in repos:
        repo = f"{OWNER}/{repo_name}"
        if repo_exists(john["token"], repo):
            print(f"SKIP (repo exists): {repo}")
        else:
            assert description is not None, f"{repo} should already exist"
            create_repo(john["token"], repo_name, description)
            print(f"Created repo {repo}")
        if repo_name != "Autonomized_Test_Project_1":
            ensure_collaborator(john["token"], repo, "autonomized2", accounts["Sarah"]["token"])
            ensure_collaborator(john["token"], repo, "autonomized3", accounts["Mike"]["token"])

    now = datetime(2026, 7, 20, 12, 0, 0)

    # ==================== Autonomized_Test_Project_1 (top up) ====================
    repo = f"{OWNER}/Autonomized_Test_Project_1"
    print(f"\n== {repo} ==")
    seed_direct_commits(
        accounts,
        repo,
        [
            (
                "Mike",
                "ci/lazy_env_read_fix.md",
                "# CI fix\n\nLazy .env read in test_jira_client.py; inject JIRA demo secrets.\n",
                "Fix CI: lazy .env read in test_jira_client.py",
                (now - timedelta(days=3)).isoformat() + "Z",
            ),
            (
                "Mike",
                "prod/seed_on_boot.md",
                "# Seed on boot\n\nSeed prod DB on every boot, not just CI's test container.\n",
                "Seed production database on every boot",
                (now - timedelta(days=2)).isoformat() + "Z",
            ),
            (
                "John",
                "ui/throbber_and_pills.md",
                "# Chat UI polish\n\nThrobber, clickable pills, concurrent tool calls.\n",
                "Chat UI polish: throbber, clickable pills, concurrent tool calls",
                (now - timedelta(days=1)).isoformat() + "Z",
            ),
            (
                "John",
                "perf/optimistic_prefetch.md",
                "# Optimistic pre-fetch\n\nPre-fetch runs in the background, not blocking.\n",
                "Optimistic (non-blocking) pre-fetch",
                now.isoformat() + "Z",
            ),
        ],
    )
    # Review + comment on Sarah's pre-existing open PR (#1), then a new merged PR from Mike.
    existing_pr = find_pr(john["token"], repo, "sarah/bare-minimum-integrations")
    if existing_pr is not None:
        pr_number = existing_pr["number"]
        existing = existing_reviews(john["token"], repo, pr_number)
        if not any(r.get("user", {}).get("login") == john["login"] for r in existing):
            add_review(john["token"], repo, pr_number, "APPROVE", "Looks good, ship it.")
            print(f"  Added review by John (APPROVE) on PR #{pr_number}")
        existing_bodies = existing_issue_comments(john["token"], repo, pr_number)
        comment = "Nice, this unblocks the rest of Phase 3."
        if comment not in existing_bodies:
            add_issue_comment(accounts["Sarah"]["token"], repo, pr_number, comment)
            print(f"  Added comment by Sarah on PR #{pr_number}: {comment[:40]}...")
    seed_pr(
        accounts,
        repo,
        author="Mike",
        branch="mike/seed-prod-db-every-boot",
        path="prod/entrypoint_seed.md",
        content="# entrypoint.sh\n\nRuns scripts/seed.py after alembic upgrade head, every boot.\n",
        message="Seed production database on every boot, not just CI's test container",
        date_iso=(now - timedelta(days=2)).isoformat() + "Z",
        pr_title="Seed production database on every boot, not just CI's test container",
        pr_body="Fixes prod team_members never being seeded - see implementation_log.md.",
        merge=True,
        reviews=[("John", "APPROVE", "Confirmed this fixed the live 500 after deploy.")],
        comments=[],
    )

    # ==================== mobile-companion-app ====================
    repo = f"{OWNER}/mobile-companion-app"
    print(f"\n== {repo} ==")
    seed_direct_commits(
        accounts,
        repo,
        [
            (
                "John",
                "onboarding/biometric_login.md",
                "# Biometric login\n\nFace ID / fingerprint login screen for onboarding.\n",
                "Onboarding flow: scaffold biometric login screen",
                (now - timedelta(days=6)).isoformat() + "Z",
            ),
            (
                "John",
                "settings/dark_mode.md",
                "# Dark mode\n\nManual dark mode toggle in settings.\n",
                "Add dark mode toggle stub to settings screen",
                (now - timedelta(days=5)).isoformat() + "Z",
            ),
            (
                "Sarah",
                "notifications/push_service.md",
                "# Push notifications\n\nPush notification service integration.\n",
                "Push notification service integration",
                (now - timedelta(days=5)).isoformat() + "Z",
            ),
            (
                "Sarah",
                "notifications/badge_count.md",
                "# Badge count\n\nNotes on the badge-count sync investigation.\n",
                "Investigate push notification badge count drift on iOS",
                (now - timedelta(days=4)).isoformat() + "Z",
            ),
            (
                "Mike",
                "sync/offline_sync_notes.md",
                "# Offline sync\n\nInvestigation notes: last-write dropped on reconnect.\n",
                "Investigate offline sync drop on reconnect",
                (now - timedelta(days=4)).isoformat() + "Z",
            ),
        ],
    )
    seed_pr(
        accounts,
        repo,
        author="John",
        branch="john/biometric-login-screen",
        path="onboarding/biometric_login_screen.md",
        content="# Biometric login screen\n\nImplements the Face ID / fingerprint login option.\n",
        message="Biometric login screen",
        date_iso=(now - timedelta(days=3)).isoformat() + "Z",
        pr_title="Biometric login screen",
        pr_body="Adds a biometric login option to the onboarding flow.",
        merge=False,
        reviews=[
            (
                "Sarah",
                "REQUEST_CHANGES",
                "Touch target on the fallback PIN entry is too small on smaller screens - "
                "can we bump it up before merging?",
            )
        ],
        comments=[("Sarah", "Also, can we add a haptic on successful auth?")],
    )
    seed_pr(
        accounts,
        repo,
        author="Mike",
        branch="mike/offline-first-cache-layer",
        path="cache/offline_first_cache_layer.md",
        content="# Offline-first cache layer\n\nCaches the activity feed for instant cold start.\n",
        message="Offline-first cache layer for activity feed",
        date_iso=(now - timedelta(days=2)).isoformat() + "Z",
        pr_title="Offline-first cache layer for activity feed",
        pr_body="Activity feed renders from local cache instantly, then reconciles in the bg.",
        merge=True,
        reviews=[("John", "APPROVE", "Nice speedup on cold start, approved.")],
        comments=[],
    )

    # ==================== analytics-pipeline ====================
    repo = f"{OWNER}/analytics-pipeline"
    print(f"\n== {repo} ==")
    seed_direct_commits(
        accounts,
        repo,
        [
            (
                "Mike",
                "ingestion/nightly_job.md",
                "# Nightly ingestion job\n\nBatch job ingesting the event stream.\n",
                "Nightly ingestion job for event stream",
                (now - timedelta(days=7)).isoformat() + "Z",
            ),
            (
                "Mike",
                "ingestion/retry_backoff.md",
                "# Retry/backoff\n\nRetry with backoff on transient upstream errors.\n",
                "Add retry/backoff to ingestion job",
                (now - timedelta(days=6)).isoformat() + "Z",
            ),
            (
                "John",
                "etl/timeout_investigation.md",
                "# ETL timeout investigation\n\nFlaky timeout on large partitions, join step.\n",
                "Investigate flaky ETL job timeout on large partitions",
                (now - timedelta(days=5)).isoformat() + "Z",
            ),
            (
                "John",
                "etl/timezone_bug_notes.md",
                "# Timezone cache bug\n\nDashboard shows stale data after a tz filter change.\n",
                "Investigate dashboard stale-data bug after timezone change",
                (now - timedelta(days=4)).isoformat() + "Z",
            ),
            (
                "Sarah",
                "dashboard/wau_scaffold.md",
                "# WAU dashboard scaffold\n\nScaffold for the weekly active users dashboard.\n",
                "Scaffold usage dashboard for weekly active users",
                (now - timedelta(days=4)).isoformat() + "Z",
            ),
        ],
    )
    seed_pr(
        accounts,
        repo,
        author="Sarah",
        branch="sarah/usage-dashboard-wau",
        path="dashboard/usage_dashboard.md",
        content="# Usage dashboard\n\nWeekly active users, broken out by feature area.\n",
        message="Usage dashboard for weekly active users",
        date_iso=(now - timedelta(days=3)).isoformat() + "Z",
        pr_title="Usage dashboard for weekly active users",
        pr_body="Adds a WAU dashboard broken out by feature area.",
        merge=False,
        reviews=[
            ("Mike", "APPROVE", "Numbers match what I see in the raw event stream, approved.")
        ],
        comments=[("Mike", "Can we add a per-org breakdown in a follow-up?")],
    )
    seed_pr(
        accounts,
        repo,
        author="Mike",
        branch="mike/ingestion-retry-backoff",
        path="ingestion/retry_backoff_pr.md",
        content="# Retry/backoff\n\nWraps the ingestion job's upstream calls with retry+backoff.\n",
        message="Add retry/backoff to ingestion job",
        date_iso=(now - timedelta(days=2)).isoformat() + "Z",
        pr_title="Add retry/backoff to ingestion job",
        pr_body="Transient upstream errors no longer fail the job hard.",
        merge=True,
        reviews=[("John", "APPROVE", "This should cut down on the nightly failure alerts a lot.")],
        comments=[],
    )


if __name__ == "__main__":
    main()
