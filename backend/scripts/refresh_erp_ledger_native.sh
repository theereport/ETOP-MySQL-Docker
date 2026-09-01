#!/bin/bash
# Runs the AP ERP ledger refresh (open ledger + GL division scan) natively,
# outside Docker, then writes the results into the live Dockerized etop-db.
#
# Why: Docker Desktop's Hyper-V backend on this machine doesn't reliably
# route container traffic through the Barracuda VPN client's split-tunnel
# route to the MaddenCo ERP server - a native connection reaches it in a
# few seconds, the same query from inside a container can take 1-4+
# minutes and sometimes gets killed outright. Confirmed 2026-09-01. See
# DEPLOYMENT.md's "AP ERP ledger refresh" section and
# docker-compose.native-refresh.yml.
#
# This script temporarily publishes etop-db's port to localhost, runs the
# refresh from the native backend/.venv, then reverts the port - it does
# not leave etop-db's port published.
set -euo pipefail
cd "$(dirname "$0")/../.."

COMPOSE="docker compose --env-file backend/.env.compose"

cleanup() {
    echo "Reverting etop-db to its normal (no published port) configuration..."
    $COMPOSE up -d etop-db >/dev/null
}
trap cleanup EXIT

echo "Temporarily publishing etop-db's port (127.0.0.1:3307)..."
$COMPOSE -f docker-compose.yml -f docker-compose.native-refresh.yml up -d etop-db

echo "Waiting for etop-db to report healthy..."
for _ in $(seq 1 30); do
    HEALTH=$(docker inspect etop-etop-db-1 --format '{{.State.Health.Status}}' 2>/dev/null || echo "")
    if [ "$HEALTH" = "healthy" ]; then
        break
    fi
    sleep 2
done
if [ "$HEALTH" != "healthy" ]; then
    echo "etop-db did not become healthy in time." >&2
    exit 1
fi

if [ ! -x "backend/.venv/Scripts/python.exe" ]; then
    echo "backend/.venv not found - set up the backend virtualenv first (see DEPLOYMENT.md)." >&2
    exit 1
fi

echo "Running the refresh natively against the live etop-db..."
# Run in a subshell so `cd` here doesn't affect the cleanup trap below -
# that trap must still resolve backend/.env.compose relative to the repo
# root, not backend/.
(
    cd backend
    ETOP_DB_HOST=127.0.0.1 ETOP_DB_PORT=3307 .venv/Scripts/python.exe -c "
import json
from modules.accounts_payable.service import accounts_payable_service

result = accounts_payable_service.refresh_erp_ledger(background=False)
print(json.dumps(result, indent=2, default=str))
"
)
