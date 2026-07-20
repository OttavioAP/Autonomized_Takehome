#!/usr/bin/env bash
# Provisions the throwaway Azure infra for the hello-world deploy:
# resource group + Postgres Flexible Server + ACR + App Service plan/webapp +
# Key Vault (OAuth token storage, with the webapp's Managed Identity and the
# signed-in az user both granted access).
# Idempotent: safe to re-run, reuses scripts/azure/.state if present.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh

load_state

if [[ -z "${RESOURCE_GROUP:-}" ]]; then
  SUFFIX="$(openssl rand -hex 3)"
  RESOURCE_GROUP="${APP_NAME_BASE}-${SUFFIX}"
  PG_SERVER_NAME="${APP_NAME_BASE}-pg-${SUFFIX}"
  APP_SERVICE_PLAN="${APP_NAME_BASE}-plan-${SUFFIX}"
  WEBAPP_NAME="${APP_NAME_BASE}-${SUFFIX}"
  ACR_NAME="tamacr${SUFFIX}"
  # Key Vault names are capped at 24 chars and globally unique across Azure,
  # same constraint that forced ACR_NAME's short "tamacr" prefix above -
  # "${APP_NAME_BASE}-kv-${SUFFIX}" would blow past the limit.
  KEY_VAULT_NAME="tamkv${SUFFIX}"
  save_state
  echo "Generated new resource names (saved to scripts/azure/.state):"
else
  echo "Reusing resource names from scripts/azure/.state:"
  # Backfill for a .state file saved before Key Vault existed in this script -
  # RESOURCE_GROUP etc. are already set, but KEY_VAULT_NAME wasn't in that
  # older save_state call, so it's unbound here under `set -u` otherwise.
  if [[ -z "${KEY_VAULT_NAME:-}" ]]; then
    SUFFIX="$(openssl rand -hex 3)"
    KEY_VAULT_NAME="tamkv${SUFFIX}"
    save_state
    echo "  (backfilled KEY_VAULT_NAME, not present in existing .state)"
  fi
fi
echo "  RESOURCE_GROUP=${RESOURCE_GROUP}"
echo "  PG_SERVER_NAME=${PG_SERVER_NAME}"
echo "  APP_SERVICE_PLAN=${APP_SERVICE_PLAN}"
echo "  WEBAPP_NAME=${WEBAPP_NAME}"
echo "  ACR_NAME=${ACR_NAME}"
echo "  KEY_VAULT_NAME=${KEY_VAULT_NAME}"
echo "  LOCATION=${LOCATION}"

if [[ -z "${PG_ADMIN_PASSWORD:-}" ]]; then
  if [[ -f "${STATE_FILE}.pgpass" ]]; then
    PG_ADMIN_PASSWORD="$(cat "${STATE_FILE}.pgpass")"
  else
    PG_ADMIN_PASSWORD="$(openssl rand -base64 24 | tr -d '=+/')"
    echo "${PG_ADMIN_PASSWORD}" > "${STATE_FILE}.pgpass"
    chmod 600 "${STATE_FILE}.pgpass"
  fi
fi
PG_ADMIN_USER="pgadmin"

echo "== Resource group =="
"${AZ}" group create \
  --name "${RESOURCE_GROUP}" \
  --location "${LOCATION}" \
  --output none

echo "== Azure Container Registry =="
"${AZ}" acr create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${ACR_NAME}" \
  --sku Basic \
  --admin-enabled true \
  --output none

echo "== PostgreSQL Flexible Server (Postgres 16, Burstable B1ms, ${COMPUTE_LOCATION}) =="
# Unlike `group create`/`acr create` above (naturally idempotent, safe to
# re-POST), `flexible-server create` errors on a re-run against an existing
# server name - check first, same guard style as the Key Vault RBAC checks
# below. Found the hard way: this script had never actually been re-run since
# the very first provision until Key Vault was added here.
if [[ -z "$("${AZ}" postgres flexible-server show \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${PG_SERVER_NAME}" \
    --query name \
    --output tsv 2>/dev/null)" ]]; then
  "${AZ}" postgres flexible-server create \
    --resource-group "${RESOURCE_GROUP}" \
    --name "${PG_SERVER_NAME}" \
    --location "${COMPUTE_LOCATION}" \
    --admin-user "${PG_ADMIN_USER}" \
    --admin-password "${PG_ADMIN_PASSWORD}" \
    --sku-name Standard_B1ms \
    --tier Burstable \
    --version 16 \
    --storage-size 32 \
    --public-access 0.0.0.0 \
    --yes \
    --output none
else
  echo "  (already exists, skipping)"
fi

echo "== Postgres database =="
# Same non-idempotent-create gap as the server itself above.
if [[ -z "$("${AZ}" postgres flexible-server db show \
    --resource-group "${RESOURCE_GROUP}" \
    --server-name "${PG_SERVER_NAME}" \
    --name team_activity_monitor \
    --query name \
    --output tsv 2>/dev/null)" ]]; then
  "${AZ}" postgres flexible-server db create \
    --resource-group "${RESOURCE_GROUP}" \
    --server-name "${PG_SERVER_NAME}" \
    --name team_activity_monitor \
    --output none
else
  echo "  (already exists, skipping)"
fi

echo "== App Service plan (Linux, Basic B1, ${COMPUTE_LOCATION}) =="
"${AZ}" appservice plan create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${APP_SERVICE_PLAN}" \
  --location "${COMPUTE_LOCATION}" \
  --is-linux \
  --sku B1 \
  --output none

echo "== Web App (container-based, placeholder image until deploy.sh pushes the real one) =="
"${AZ}" webapp create \
  --resource-group "${RESOURCE_GROUP}" \
  --plan "${APP_SERVICE_PLAN}" \
  --name "${WEBAPP_NAME}" \
  --container-image-name mcr.microsoft.com/appsvc/staticsite:latest \
  --output none

echo "== Key Vault (OAuth token storage - see blueprints/plans/features/oauth-integration.md) =="
"${AZ}" keyvault create \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${KEY_VAULT_NAME}" \
  --location "${LOCATION}" \
  --enable-rbac-authorization true \
  --output none

KEY_VAULT_URI="$("${AZ}" keyvault show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${KEY_VAULT_NAME}" \
  --query properties.vaultUri \
  --output tsv)"
KEY_VAULT_ID="$("${AZ}" keyvault show \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${KEY_VAULT_NAME}" \
  --query id \
  --output tsv)"

echo "== App Service system-assigned Managed Identity =="
# `az webapp identity assign` is a PUT under the hood - re-running it against a
# webapp that already has a system-assigned identity is a no-op that returns
# the existing identity rather than erroring, so no separate existence check
# is needed here (unlike the role assignments below).
WEBAPP_PRINCIPAL_ID="$("${AZ}" webapp identity assign \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${WEBAPP_NAME}" \
  --query principalId \
  --output tsv)"

echo "== Key Vault RBAC: grant Key Vault Secrets Officer to the webapp's Managed Identity =="
# Role assignments are NOT idempotent - `az role assignment create` errors on
# an exact duplicate (assignee + role + scope), unlike the resource `create`
# commands above. Check-before-create, same idempotency philosophy as the
# "if RESOURCE_GROUP is empty" guard at the top of this script.
if [[ -z "$("${AZ}" role assignment list \
    --assignee-object-id "${WEBAPP_PRINCIPAL_ID}" \
    --role "Key Vault Secrets Officer" \
    --scope "${KEY_VAULT_ID}" \
    --query "[0].id" \
    --output tsv)" ]]; then
  "${AZ}" role assignment create \
    --assignee-object-id "${WEBAPP_PRINCIPAL_ID}" \
    --assignee-principal-type ServicePrincipal \
    --role "Key Vault Secrets Officer" \
    --scope "${KEY_VAULT_ID}" \
    --output none
else
  echo "  (already granted, skipping)"
fi

echo "== Key Vault RBAC: grant Key Vault Secrets Officer to the signed-in az identity (local dev) =="
# Local dev talks to the same real vault (no env-var/in-memory fallback - see
# oauth-integration.md's Token storage section), so the developer's own
# logged-in identity needs the same role the webapp's Managed Identity got above.
SIGNED_IN_USER_ID="$("${AZ}" ad signed-in-user show --query id --output tsv)"
if [[ -z "$("${AZ}" role assignment list \
    --assignee-object-id "${SIGNED_IN_USER_ID}" \
    --role "Key Vault Secrets Officer" \
    --scope "${KEY_VAULT_ID}" \
    --query "[0].id" \
    --output tsv)" ]]; then
  "${AZ}" role assignment create \
    --assignee-object-id "${SIGNED_IN_USER_ID}" \
    --assignee-principal-type User \
    --role "Key Vault Secrets Officer" \
    --scope "${KEY_VAULT_ID}" \
    --output none
else
  echo "  (already granted, skipping)"
fi

PG_HOST="${PG_SERVER_NAME}.postgres.database.azure.com"
DATABASE_URL="postgresql+asyncpg://${PG_ADMIN_USER}:${PG_ADMIN_PASSWORD}@${PG_HOST}:5432/team_activity_monitor?ssl=require"

echo ""
echo "Provisioning complete."
echo "  Web app URL (once deployed): https://${WEBAPP_NAME}.azurewebsites.net"
echo "  Postgres host: ${PG_HOST}"
echo "  DATABASE_URL (Azure): ${DATABASE_URL}"
echo "  Key Vault URI: ${KEY_VAULT_URI}"
echo ""
echo "Postgres admin password saved to scripts/azure/.state.pgpass (gitignored)."
echo "Run scripts/azure/deploy.sh next to build/push the real image and wire env vars."
echo "(deploy.sh still needs to wire KEY_VAULT_URI into the app's env vars - out of scope here.)"
