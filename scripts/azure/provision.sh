#!/usr/bin/env bash
# Provisions the throwaway Azure infra for the hello-world deploy:
# resource group + Postgres Flexible Server + ACR + App Service plan/webapp.
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
  save_state
  echo "Generated new resource names (saved to scripts/azure/.state):"
else
  echo "Reusing resource names from scripts/azure/.state:"
fi
echo "  RESOURCE_GROUP=${RESOURCE_GROUP}"
echo "  PG_SERVER_NAME=${PG_SERVER_NAME}"
echo "  APP_SERVICE_PLAN=${APP_SERVICE_PLAN}"
echo "  WEBAPP_NAME=${WEBAPP_NAME}"
echo "  ACR_NAME=${ACR_NAME}"
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

echo "== Postgres database =="
"${AZ}" postgres flexible-server db create \
  --resource-group "${RESOURCE_GROUP}" \
  --server-name "${PG_SERVER_NAME}" \
  --name team_activity_monitor \
  --output none

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

PG_HOST="${PG_SERVER_NAME}.postgres.database.azure.com"
DATABASE_URL="postgresql+asyncpg://${PG_ADMIN_USER}:${PG_ADMIN_PASSWORD}@${PG_HOST}:5432/team_activity_monitor?ssl=require"

echo ""
echo "Provisioning complete."
echo "  Web app URL (once deployed): https://${WEBAPP_NAME}.azurewebsites.net"
echo "  Postgres host: ${PG_HOST}"
echo "  DATABASE_URL (Azure): ${DATABASE_URL}"
echo ""
echo "Postgres admin password saved to scripts/azure/.state.pgpass (gitignored)."
echo "Run scripts/azure/deploy.sh next to build/push the real image and wire env vars."
