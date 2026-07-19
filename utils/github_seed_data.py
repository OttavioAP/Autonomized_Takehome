"""Seed a minimal first pass of dummy GitHub activity into Shared_Repo_1 (step 5, Phase B).

Narrative: commits/PRs mirror this project's own real timeline.md steps, attributed to
the 3 demo accounts (John=Test_1, Sarah=Test_2, Mike=Test_3) via each account's own PAT,
backdated to roughly match this project's actual CHANGELOG dates.
Re-runnable: skips creating a file/commit if that path already exists on the target branch.

Usage: .venv/bin/python utils/github_seed_data.py
"""

import base64
import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO = "Autonomized1/Autonomized_Test_Project_1"
API = "https://api.github.com"


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


def put_file(
    token: str,
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
        f"{API}/repos/{REPO}/contents/{path}", headers=headers_for(token), json=body, timeout=15
    )
    resp.raise_for_status()
    return resp.json()


def get_file_sha(token: str, path: str, ref: str) -> str | None:
    resp = httpx.get(
        f"{API}/repos/{REPO}/contents/{path}",
        headers=headers_for(token),
        params={"ref": ref},
        timeout=10,
    )
    if resp.status_code == 200:
        return resp.json()["sha"]
    return None


def create_branch(token: str, branch: str, from_sha: str) -> None:
    resp = httpx.post(
        f"{API}/repos/{REPO}/git/refs",
        headers=headers_for(token),
        json={"ref": f"refs/heads/{branch}", "sha": from_sha},
        timeout=10,
    )
    if resp.status_code not in (201, 422):  # 422 = ref already exists
        resp.raise_for_status()


def get_branch_sha(token: str, branch: str) -> str | None:
    resp = httpx.get(
        f"{API}/repos/{REPO}/git/ref/heads/{branch}", headers=headers_for(token), timeout=10
    )
    if resp.status_code == 200:
        return resp.json()["object"]["sha"]
    return None


def existing_open_pr(token: str, head: str) -> dict | None:
    resp = httpx.get(
        f"{API}/repos/{REPO}/pulls",
        headers=headers_for(token),
        params={"state": "all", "head": f"Autonomized1:{head}"},
        timeout=10,
    )
    resp.raise_for_status()
    prs = resp.json()
    return prs[0] if prs else None


def open_pr(token: str, title: str, body: str, head: str, base: str) -> dict:
    resp = httpx.post(
        f"{API}/repos/{REPO}/pulls",
        headers=headers_for(token),
        json={"title": title, "body": body, "head": head, "base": base},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def main() -> None:
    env = load_env(REPO_ROOT / ".env")
    accounts = {
        "John": {
            "token": env["Autonomized_Test_1_Github_PAT"],
            "name": "John (Autonomized_Test_1)",
            "email": "Autonomized_Test_1@proton.me",
        },
        "Sarah": {
            "token": env["Autonomized_Test_2_Github_PAT"],
            "name": "Sarah (Autonomized_Test_2)",
            "email": "Autonomized_Test_2@proton.me",
        },
        "Mike": {
            "token": env["Autonomized_Test_3_Github_PAT"],
            "name": "Mike (Autonomized_Test_3)",
            "email": "Autonomized_Test_3@proton.me",
        },
    }
    for name, acc in accounts.items():
        if not acc["token"]:
            print(f"Missing GitHub PAT for {name}", file=sys.stderr)
            sys.exit(1)

    # 1. Mike commits infra scaffold to main (bootstraps the empty repo)
    mike = accounts["Mike"]
    existing_sha = get_file_sha(mike["token"], "infra/README.md", "main")
    if existing_sha:
        print("SKIP (exists): infra/README.md on main")
    else:
        put_file(
            mike["token"],
            "infra/README.md",
            "# Infra\n\nMinimum project structure and infra scaffolding.\n",
            "Stand up minimum structure/infra",
            "main",
            mike["name"],
            mike["email"],
            "2026-07-17T15:00:00Z",
        )
        print("Committed infra/README.md to main (Mike)")

    main_sha = get_branch_sha(mike["token"], "main")
    assert main_sha, "main branch should exist after first commit"

    # 2. John commits hello-world deploy proof to main
    john = accounts["John"]
    existing_sha = get_file_sha(john["token"], "deploy/hello_world.md", "main")
    if existing_sha:
        print("SKIP (exists): deploy/hello_world.md on main")
    else:
        put_file(
            john["token"],
            "deploy/hello_world.md",
            "# Hello World Deploy\n\nProves the Azure deployment path end-to-end.\n",
            "Deploy hello world to Microsoft Azure",
            "main",
            john["name"],
            john["email"],
            "2026-07-18T12:00:00Z",
        )
        print("Committed deploy/hello_world.md to main (John)")

    # 3. Sarah opens a PR from a feature branch for the integrations work (in progress)
    sarah = accounts["Sarah"]
    branch = "sarah/bare-minimum-integrations"
    main_sha = get_branch_sha(sarah["token"], "main")
    assert main_sha, "main branch should exist after earlier commits"
    create_branch(sarah["token"], branch, main_sha)

    existing_sha = get_file_sha(sarah["token"], "integrations/README.md", branch)
    if existing_sha:
        print(f"SKIP (exists): integrations/README.md on {branch}")
    else:
        put_file(
            sarah["token"],
            "integrations/README.md",
            "# Integrations\n\nJIRA/GitHub connectivity check scripts (WIP).\n",
            "Bare-minimum integrations: add connectivity check scripts",
            branch,
            sarah["name"],
            sarah["email"],
            "2026-07-19T10:00:00Z",
        )
        print(f"Committed integrations/README.md to {branch} (Sarah)")

    pr = existing_open_pr(sarah["token"], branch)
    if pr:
        print(f"SKIP (exists): PR #{pr['number']} for {branch}")
    else:
        pr = open_pr(
            sarah["token"],
            "Bare-minimum integrations: add connectivity check scripts",
            "Validates JIRA/GitHub API connectivity via local util scripts (timeline.md step 5).",
            branch,
            "main",
        )
        print(f"Opened PR #{pr['number']}: {pr['title']}")


if __name__ == "__main__":
    main()
