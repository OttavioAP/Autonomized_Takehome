#!/usr/bin/env bash
# Deletes the entire resource group created by provision.sh, cascading to every
# resource inside it (Postgres, ACR, App Service plan/webapp, Key Vault). One
# command to clean up the whole throwaway deployment at the end of the week.
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

# Key Vault has soft-delete on by default, so `az group delete` above only
# soft-deletes it - it lingers (and keeps its name reserved tenant-wide) for
# the retention period unless purged. Purge is itself tenant-level, not
# resource-group-scoped (same reason AD cleanup below is separate from the
# group delete), and it has to wait until the group delete above has actually
# removed the vault, so poll for that first rather than racing it.
if [[ -n "${KEY_VAULT_NAME:-}" ]]; then
  echo "Waiting for resource group deletion to finish before purging the soft-deleted vault..."
  while "${AZ}" group show --name "${RESOURCE_GROUP}" --output none 2>/dev/null; do
    sleep 10
  done

  echo "Purging soft-deleted Key Vault ${KEY_VAULT_NAME}..."
  "${AZ}" keyvault purge --name "${KEY_VAULT_NAME}" --location "${LOCATION}" \
    || echo "  (already purged, not yet soft-deleted, or purge failed - continuing)"
fi

# AD users and app registrations are tenant-level, not resource-group-scoped, so
# `az group delete` above does not touch them - clean up separately. Pulled from
# .env (not scripts/azure/.state, which only tracks resource-group-scoped names).
ENV_FILE="${REPO_ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  AZURE_CLIENT_ID="$(grep -E '^AZURE_CLIENT_ID=' "${ENV_FILE}" | cut -d= -f2-)"
  JOHN_UPN="$(grep -E '^Azure_John_UPN=' "${ENV_FILE}" | cut -d= -f2-)"
  SARAH_UPN="$(grep -E '^Azure_Sarah_UPN=' "${ENV_FILE}" | cut -d= -f2-)"
  MIKE_UPN="$(grep -E '^Azure_Mike_UPN=' "${ENV_FILE}" | cut -d= -f2-)"

  if [[ -n "${AZURE_CLIENT_ID:-}" ]]; then
    echo "Deleting SSO app registration ${AZURE_CLIENT_ID}..."
    "${AZ}" ad app delete --id "${AZURE_CLIENT_ID}" || echo "  (already gone or delete failed, continuing)"
  fi

  for upn in "${JOHN_UPN:-}" "${SARAH_UPN:-}" "${MIKE_UPN:-}"; do
    if [[ -n "${upn}" ]]; then
      echo "Deleting Azure AD user ${upn}..."
      "${AZ}" ad user delete --id "${upn}" || echo "  (already gone or delete failed, continuing)"
    fi
  done
else
  echo "No .env found — skipping Azure AD user/app-registration cleanup." >&2
fi

rm -f "${STATE_FILE}" "${STATE_FILE}.pgpass"
echo "Local state files removed."
