"""Standalone manual connectivity check for the GitHub REST API (timeline.md step 5, Phase A).

Not part of the app - reads .env directly and prints raw-ish results for manual
eyeballing, ahead of building the real app/integrations/github_client.py module.

Usage: .venv/bin/python utils/github_connect_check.py
"""

import sys
from pathlib import Path

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env[key.strip()] = value.strip()
    return env


def main() -> None:
    env = load_env(REPO_ROOT / ".env")

    token = env["Autonomized_Test_1_Github_PAT"]
    repo = "Autonomized1/Autonomized_Test_Project_1"

    if not token:
        print("Missing Test_1 GitHub PAT in .env", file=sys.stderr)
        sys.exit(1)

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    print("== GET /user ==")
    resp = httpx.get("https://api.github.com/user", headers=headers, timeout=10)
    print(resp.status_code)
    print(resp.text[:1000])
    resp.raise_for_status()

    print(f"\n== GET /repos/{repo}/commits ==")
    resp = httpx.get(
        f"https://api.github.com/repos/{repo}/commits",
        headers=headers,
        params={"per_page": 10},
        timeout=10,
    )
    print(resp.status_code)
    print(resp.text[:2000])
    if resp.status_code == 409:
        print("(repo has no commits yet - expected until Phase B dummy data is created)")
    else:
        resp.raise_for_status()

    print(f"\n== GET /repos/{repo}/pulls (state=all) ==")
    resp = httpx.get(
        f"https://api.github.com/repos/{repo}/pulls",
        headers=headers,
        params={"state": "all", "per_page": 10},
        timeout=10,
    )
    print(resp.status_code)
    print(resp.text[:2000])
    resp.raise_for_status()

    print("\nGitHub connectivity OK.")


if __name__ == "__main__":
    main()
