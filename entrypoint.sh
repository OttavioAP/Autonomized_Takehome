#!/bin/sh
# Runs on every container boot, local and deployed alike: migrations always
# apply before the app starts serving traffic, so there is no separate "did
# someone remember to migrate prod" step to forget. Single-instance deployment
# (see blueprints/deployment.md) - safe to run unconditionally without a
# leader-election/lock story that multi-replica setups would need.
#
# scripts/seed.py runs here for the same reason, not as a deploy.yml CI step:
# Postgres Flexible Server's firewall only allows Azure-internal traffic, which a
# GitHub-hosted runner can't reach (see blueprints/deployment.md's "Bug #3" -
# migrations hit this exact issue first). scripts/seed.py is idempotent
# (ON CONFLICT DO NOTHING on each table's natural key), so running it
# unconditionally on every boot is safe - it was never run against the real
# production database before this, only CI's throwaway test container, which is
# why prod's team_members table was empty and no Azure login could resolve to a
# team member.
set -eu

alembic upgrade head
python scripts/seed.py
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --proxy-headers \
    "--forwarded-allow-ips=*"
