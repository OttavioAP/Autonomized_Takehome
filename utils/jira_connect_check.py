"""Standalone manual connectivity check for the JIRA REST API (timeline.md step 5, Phase A).

Not part of the app - reads .env directly and prints raw-ish results for manual
eyeballing, ahead of building the real app/integrations/jira_client.py module.

Usage: .venv/bin/python utils/jira_connect_check.py
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

    base_url = "https://autonomizedtest1.atlassian.net"
    project_key = "KAN"
    email = env["Autonomized_Test_1_Protonmail_Email"]
    api_token = env["Autonomized_Test_1_Jira_API_Key"]

    if not email or not api_token:
        print("Missing Test_1 email or JIRA API token in .env", file=sys.stderr)
        sys.exit(1)

    auth = (email, api_token)

    print(f"== GET /rest/api/3/myself ({base_url}) ==")
    resp = httpx.get(f"{base_url}/rest/api/3/myself", auth=auth, timeout=10)
    print(resp.status_code)
    print(resp.text[:1000])
    resp.raise_for_status()

    print(f"\n== GET /rest/api/3/project/{project_key} ==")
    resp = httpx.get(f"{base_url}/rest/api/3/project/{project_key}", auth=auth, timeout=10)
    print(resp.status_code)
    print(resp.text[:1000])
    resp.raise_for_status()

    print(f"\n== GET /rest/api/3/search/jql?jql=project={project_key} ==")
    resp = httpx.get(
        f"{base_url}/rest/api/3/search/jql",
        params={"jql": f"project={project_key}", "maxResults": 10},
        auth=auth,
        timeout=10,
    )
    print(resp.status_code)
    print(resp.text[:2000])
    resp.raise_for_status()

    print("\nJIRA connectivity OK.")


if __name__ == "__main__":
    main()
