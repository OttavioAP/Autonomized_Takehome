#!/usr/bin/env bash
# Shared config/helpers for scripts/azure/*.sh. Sourced, not executed directly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
AZ="${REPO_ROOT}/.venv-azure/bin/az"
STATE_FILE="${REPO_ROOT}/scripts/azure/.state"

LOCATION="${AZURE_LOCATION:-eastus}"
# Postgres Flexible Server and App Service plans hit a hard 0-VM compute quota
# in eastus on this subscription (confirmed via trial-and-error across
# eastus/eastus2/westus/westus2/centralus) — centralus is the region that
# actually has quota, so compute resources are pinned there regardless of
# LOCATION. The resource group and ACR stay in LOCATION (eastus) since ACR
# isn't subject to the same VM quota and grouping resources needs one region.
COMPUTE_LOCATION="${AZURE_COMPUTE_LOCATION:-centralus}"
APP_NAME_BASE="team-activity-monitor"

if [[ ! -x "${AZ}" ]]; then
  echo "Azure CLI not found at ${AZ}. Run: python3 -m venv .venv-azure && .venv-azure/bin/pip install azure-cli" >&2
  exit 1
fi

# Persist generated resource names across scripts so deploy.sh/teardown.sh
# target the same resources provision.sh created, without re-deriving them.
load_state() {
  if [[ -f "${STATE_FILE}" ]]; then
    # shellcheck disable=SC1090
    source "${STATE_FILE}"
  fi
}

save_state() {
  cat > "${STATE_FILE}" <<EOF
RESOURCE_GROUP="${RESOURCE_GROUP}"
PG_SERVER_NAME="${PG_SERVER_NAME}"
APP_SERVICE_PLAN="${APP_SERVICE_PLAN}"
WEBAPP_NAME="${WEBAPP_NAME}"
ACR_NAME="${ACR_NAME}"
LOCATION="${LOCATION}"
COMPUTE_LOCATION="${COMPUTE_LOCATION}"
EOF
}
