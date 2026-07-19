#!/usr/bin/env bash
# Builds the existing Dockerfile, pushes it to the ACR created by provision.sh,
# points the Web App at it, and injects app settings (env vars) read from .env.
# Requires provision.sh to have been run first (needs scripts/azure/.state).
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
source ./lib.sh

load_state
if [[ -z "${RESOURCE_GROUP:-}" ]]; then
  echo "No scripts/azure/.state found — run scripts/azure/provision.sh first." >&2
  exit 1
fi
PG_ADMIN_PASSWORD="$(cat "${STATE_FILE}.pgpass")"
PG_ADMIN_USER="pgadmin"
PG_HOST="${PG_SERVER_NAME}.postgres.database.azure.com"

# Read the app's real secrets from .env — never committed, never hardcoded here.
# Parsed line-by-line (not `source`d) so secret values containing $, `, #, etc.
# are treated as literal text rather than shell-evaluated.
ENV_FILE="${REPO_ROOT}/.env"
if [[ ! -f "${ENV_FILE}" ]]; then
  echo "No .env found at repo root — copy .env.example to .env and fill in real values first." >&2
  exit 1
fi
while IFS='=' read -r key value; do
  [[ -z "${key}" || "${key}" == \#* ]] && continue
  export "${key}=${value}"
done < <(grep -v '^\s*#' "${ENV_FILE}" | grep '=')

IMAGE_TAG="$(date +%Y%m%d%H%M%S)"
ACR_LOGIN_SERVER="$("${AZ}" acr show --name "${ACR_NAME}" --resource-group "${RESOURCE_GROUP}" --query loginServer -o tsv)"
IMAGE="${ACR_LOGIN_SERVER}/team-activity-monitor:${IMAGE_TAG}"

echo "== Building image ${IMAGE} =="
docker build -t "${IMAGE}" "${REPO_ROOT}"

echo "== Pushing to ACR (via az acr login) =="
"${AZ}" acr login --name "${ACR_NAME}"
docker push "${IMAGE}"

echo "== Pointing Web App at the new image =="
ACR_USERNAME="$("${AZ}" acr credential show --name "${ACR_NAME}" --query username -o tsv)"
ACR_PASSWORD="$("${AZ}" acr credential show --name "${ACR_NAME}" --query passwords[0].value -o tsv)"

"${AZ}" webapp config container set \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${WEBAPP_NAME}" \
  --container-image-name "${IMAGE}" \
  --container-registry-url "https://${ACR_LOGIN_SERVER}" \
  --container-registry-user "${ACR_USERNAME}" \
  --container-registry-password "${ACR_PASSWORD}" \
  --output none

echo "== Setting app configuration (env vars) =="
AZURE_DATABASE_URL="postgresql+asyncpg://${PG_ADMIN_USER}:${PG_ADMIN_PASSWORD}@${PG_HOST}:5432/team_activity_monitor?ssl=require"

"${AZ}" webapp config appsettings set \
  --resource-group "${RESOURCE_GROUP}" \
  --name "${WEBAPP_NAME}" \
  --settings \
    APP_ENV=production \
    DATABASE_URL="${AZURE_DATABASE_URL}" \
    OPENROUTER_API_KEY="${OPENROUTER_API_KEY:-}" \
    JIRA_BASE_URL="${JIRA_BASE_URL:-}" \
    JIRA_EMAIL="${JIRA_EMAIL:-}" \
    JIRA_API_TOKEN="${JIRA_API_TOKEN:-}" \
    GITHUB_TOKEN="${GITHUB_TOKEN:-}" \
    GITHUB_REPO="${GITHUB_REPO:-}" \
    WEBSITES_PORT=8000 \
  --output none

echo "== Restarting Web App =="
"${AZ}" webapp restart --resource-group "${RESOURCE_GROUP}" --name "${WEBAPP_NAME}" --output none

# The restart triggered above has twice been observed to race the new image's
# pull (log shows "Container pull image interrupted. Revert by terminate."),
# leaving the site unresponsive despite `az webapp show` reporting
# state=Running. A second restart reliably recovers it. Cheap insurance for a
# failure mode with no known root cause yet — see blueprints/deployment.md.
sleep 5
echo "== Restarting Web App again (works around an intermittent interrupted-pull-on-restart issue) =="
"${AZ}" webapp restart --resource-group "${RESOURCE_GROUP}" --name "${WEBAPP_NAME}" --output none

echo ""
echo "Deployed. URL: https://${WEBAPP_NAME}.azurewebsites.net"
echo "Tail logs with: ${AZ} webapp log tail --resource-group ${RESOURCE_GROUP} --name ${WEBAPP_NAME}"
