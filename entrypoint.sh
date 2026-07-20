#!/bin/sh
# Runs on every container boot, local and deployed alike: migrations always
# apply before the app starts serving traffic, so there is no separate "did
# someone remember to migrate prod" step to forget. Single-instance deployment
# (see blueprints/deployment.md) - safe to run unconditionally without a
# leader-election/lock story that multi-replica setups would need.
set -eu

alembic upgrade head
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --proxy-headers \
    "--forwarded-allow-ips=*"
