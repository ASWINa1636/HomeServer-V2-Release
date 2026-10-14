#!/usr/bin/env bash
# HomeServer V2 — Shutdown Script
# Copyright 2026 Aswin A — Licensed under Apache 2.0
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_DIR"

echo "Stopping HomeServer V2 services..."
docker compose down
echo "All HomeServer V2 services have been stopped."
echo "  Your data and database are preserved."
echo "  Run scripts/start.sh to restart."
