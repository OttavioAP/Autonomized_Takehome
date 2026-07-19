#!/usr/bin/env bash
# Wrapper around `gh secret set` that always uses printf, never echo - echo
# appends a trailing newline that gets baked into the secret value, which has
# broken CI twice now (see blueprints/deployment.md's execution notes and the
# CHANGELOG entry for the AZURE_TENANT_ID incident). Use this instead of
# reaching for `gh secret set` directly when scripting secret updates.
#
# Usage: scripts/azure/set-secret.sh SECRET_NAME "value"
#        scripts/azure/set-secret.sh SECRET_NAME < value_from_a_command
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 SECRET_NAME [value]" >&2
  exit 1
fi

SECRET_NAME="$1"

if [[ $# -ge 2 ]]; then
  VALUE="$2"
  printf '%s' "${VALUE}" | gh secret set "${SECRET_NAME}"
else
  # Read from stdin, stripping any trailing newline so callers piping in
  # command output (which often ends in \n) don't reintroduce the same bug.
  VALUE="$(cat)"
  printf '%s' "${VALUE}" | gh secret set "${SECRET_NAME}"
fi

echo "Set ${SECRET_NAME}"
