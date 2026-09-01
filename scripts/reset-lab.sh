#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"
DOCKER_DIR="$ROOT_DIR/.docker"

echo ""
echo "=============================================="
echo "  STARFALL DEFENCE CORPS ACADEMY"
echo "  Resetting fleet + range..."
echo "=============================================="
echo ""

echo "  Destroying existing fleet + range..."
docker compose -f "$DOCKER_DIR/docker-compose.yml" down -v 2>&1 | while read -r line; do
    echo "    $line"
done

# Clear the range's recorded scenarios + baseline so the next run re-arms with
# fresh nonce indicators.
rm -rf "$ROOT_DIR/.lab"/* 2>/dev/null || true

echo ""
echo "  Rebuilding fleet + range (re-arming the incident scenarios)..."
bash "$SCRIPT_DIR/setup-lab.sh"
