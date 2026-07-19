#!/usr/bin/env bash
# Deletes the entire resource group created by provision.sh, cascading to every
# resource inside it (Postgres, ACR, App Service plan/webapp). One command to
# clean up the whole throwaway deployment at the end of the week.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh

load_state
if [[ -z "${RESOURCE_GROUP:-}" ]]; then
  echo "No scripts/azure/.state found — nothing to tear down." >&2
  exit 1
fi

echo "About to delete resource group '${RESOURCE_GROUP}' and everything in it."
read -r -p "Type the resource group name to confirm: " CONFIRM
if [[ "${CONFIRM}" != "${RESOURCE_GROUP}" ]]; then
  echo "Confirmation did not match. Aborting." >&2
  exit 1
fi

"${AZ}" group delete --name "${RESOURCE_GROUP}" --yes --no-wait

echo "Deletion started (--no-wait). Check progress with:"
echo "  ${AZ} group show --name ${RESOURCE_GROUP}"

rm -f "${STATE_FILE}" "${STATE_FILE}.pgpass"
echo "Local state files removed."
