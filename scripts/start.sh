#!/usr/bin/env bash
# HomeServer V2 — Linux/macOS Startup Script
# Copyright 2026 Aswin A — Licensed under Apache 2.0
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================"
echo "  HomeServer V2 — Startup"
echo "============================================"
echo ""

# ── 1. Check Docker ──────────────────────────────
if ! command -v docker &> /dev/null; then
  echo "ERROR: Docker is not installed."
  echo "  Install Docker Desktop: https://docs.docker.com/get-docker/"
  echo "  Or Docker Engine:       https://docs.docker.com/engine/install/"
  exit 1
fi

if ! docker info > /dev/null 2>&1; then
  echo "ERROR: Docker daemon is not running."
  echo "  Start Docker Desktop or run: sudo systemctl start docker"
  exit 1
fi

echo "[OK] Docker is available."

# ── 2. Check Docker Compose ──────────────────────
if ! docker compose version > /dev/null 2>&1; then
  echo "ERROR: Docker Compose (v2) is not available."
  echo "  Docker Desktop includes Compose. For Linux:"
  echo "  https://docs.docker.com/compose/install/linux/"
  exit 1
fi

COMPOSE_VERSION=$(docker compose version --short 2>/dev/null || echo "unknown")
echo "[OK] Docker Compose $COMPOSE_VERSION detected."

# ── 3. Check .env ────────────────────────────────
cd "$PROJECT_DIR"

if [ ! -f .env ]; then
  cp .env.example .env
  echo ""
  echo "IMPORTANT: .env was created from .env.example."
  echo "  You MUST edit .env and set secure values for:"
  echo "    - SECRET_KEY          (unique random string, 32+ characters)"
  echo "    - POSTGRES_PASSWORD   (unique database password)"
  echo ""
  echo "  Generate a secret:  python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
  echo "  Or:                 openssl rand -base64 48"
  echo ""
  echo "  Edit .env, then re-run this script."
  exit 0
fi

# Validate required secrets are not placeholder values
source .env 2>/dev/null || true
if [ -z "${SECRET_KEY:-}" ] || [ "$SECRET_KEY" = "replace-with-a-unique-random-secret-at-least-32-characters" ]; then
  echo "ERROR: SECRET_KEY in .env is not set or is still the placeholder."
  echo "  Generate one:  python3 -c \"import secrets; print(secrets.token_urlsafe(48))\""
  exit 1
fi
if [ -z "${POSTGRES_PASSWORD:-}" ] || [ "$POSTGRES_PASSWORD" = "replace-with-a-unique-database-password" ]; then
  echo "ERROR: POSTGRES_PASSWORD in .env is not set or is still the placeholder."
  exit 1
fi

echo "[OK] .env validated."

# ── 4. Create data directory ─────────────────────
DATA_DIR="${HOST_DATA_PATH:-./data}"
mkdir -p "$DATA_DIR"
echo "[OK] Data directory: $DATA_DIR"

# ── 5. Build and start ───────────────────────────
echo ""
echo "Building and starting HomeServer V2 services..."
echo "  (First run may take a few minutes to download base images and build.)"
echo ""

docker compose up -d --build

echo ""
echo "Waiting for backend to become healthy..."
ATTEMPTS=0
MAX_ATTEMPTS=60
FRONTEND_PORT_VAL="${FRONTEND_PORT:-8081}"
until curl -sf "http://localhost:${FRONTEND_PORT_VAL}/health/ready" > /dev/null 2>&1; do
  ATTEMPTS=$((ATTEMPTS + 1))
  if [ $ATTEMPTS -ge $MAX_ATTEMPTS ]; then
    echo ""
    echo "WARNING: Backend did not become ready in time."
    echo "  Check logs: docker compose logs homeserver-v2-backend"
    exit 1
  fi
  sleep 3
  printf "."
done

echo ""
echo ""
echo "============================================"
echo "  HomeServer V2 is running!"
echo "============================================"
echo ""
echo "  Application:  ${PUBLIC_BASE_URL:-http://localhost:${FRONTEND_PORT_VAL}}"
echo "  Mailpit UI:   http://localhost:${MAILPIT_UI_PORT:-8025}  (dev email viewer)"
echo ""
echo "  First time? Open the application URL and create"
echo "  your administrator account on the setup page."
echo ""
echo "  Stop services:    docker compose down"
echo "  View logs:        docker compose logs -f"
echo "  Restart:          docker compose restart"
echo ""
