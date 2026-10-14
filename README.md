# HomeServer V2

[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

**Your private cloud server.** A self-hosted file management platform with workspaces, user management, storage administration, backup/restore, and network diagnostics — all running in Docker.

---

## Features

- **Private Cloud Storage** — Upload, browse, download, and manage files in isolated user workspaces
- **Multi-User Support** — User registration with email OTP verification, workspace invitations, and role-based permissions
- **Admin Dashboard** — System owner controls for user management, audit logs, registration policies, and diagnostics
- **Storage Management** — Add and manage multiple host storage locations with real-time disk usage monitoring
- **Backup & Restore** — Full database backup and restore from the admin panel
- **Network Diagnostics** — Built-in ping, DNS lookup, traceroute, and speed test tools
- **Security** — Argon2id password hashing, CSRF protection, rate limiting, and session management
- **Email Delivery** — Local dev emails via Mailpit, production emails via Resend or any SMTP provider

## Requirements

- **Docker Desktop** (Windows/macOS) or **Docker Engine + Docker Compose v2** (Linux)
- **Internet access** for the first run (to download Docker base images and dependencies)
- At least **2 GB RAM** and **5 GB disk space** available for Docker

> **No need to install Python, Node.js, or PostgreSQL.** Everything runs inside Docker containers.

## Quick Start

### 1. Download

Download the latest release ZIP from the [Releases page](https://github.com/ASWINa1636/HomeServer-V2-Release/releases/download/v2.0.0/HomeServer-V2-Release-v2.0.0.zip) and extract it.

### 2. Configure

```bash
cp .env.example .env
```

Edit `.env` and set **at minimum**:

| Variable | Description |
|---|---|
| `SECRET_KEY` | Unique random string (32+ characters). Generate: `python3 -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `POSTGRES_PASSWORD` | Unique database password. Generate: `openssl rand -base64 32` |

### 3. Start

**Linux / macOS:**
```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

**Windows (PowerShell):**
```powershell
.\scripts\start.ps1
```

**Or directly with Docker Compose:**
```bash
docker compose up -d --build
```

### 4. Open

Open **http://localhost:8081** in your browser and create your administrator account.

## Directory Structure

```
HomeServer-V2-Release/
├── LICENSE                    # Apache License 2.0
├── NOTICE                     # Copyright and third-party attribution
├── README.md                  # This file
├── .env.example               # Configuration template (copy to .env)
├── .gitignore                 # Git exclusions
├── docker-compose.yml         # Production Docker Compose
├── backend/                   # FastAPI backend
│   ├── Dockerfile             # Backend container build
│   ├── requirements.txt       # Python dependencies
│   ├── alembic.ini            # Database migration config
│   ├── app/                   # Application source code
│   │   ├── main.py            # FastAPI entrypoint
│   │   ├── api/               # API route handlers
│   │   ├── core/              # Configuration, database, security
│   │   ├── models/            # SQLAlchemy models
│   │   └── services/          # Email, storage, backup, networking
│   ├── migrations/            # Alembic database migrations
│   └── tests/                 # Backend test suite
├── frontend/                  # React/Vite frontend
│   ├── Dockerfile             # Multi-stage build (Node → Nginx)
│   ├── package.json           # Node.js dependencies
│   ├── nginx.conf             # Nginx reverse proxy config
│   ├── nginx-main.conf        # Nginx main process config
│   └── src/                   # TypeScript/React source
├── scripts/                   # Startup and management scripts
│   ├── start.sh               # Linux/macOS startup
│   ├── start.ps1              # Windows PowerShell startup
│   ├── stop.sh                # Linux/macOS shutdown
│   └── stop.ps1               # Windows PowerShell shutdown
└── docs/                      # Additional documentation
    ├── ARCHITECTURE.md
    ├── SECURITY.md
    ├── STORAGE.md
    ├── NETWORKING.md
    └── BACKUP_RESTORE.md
```

## Configuration Reference

All settings are configured through `.env`. See `.env.example` for the full list with descriptions.

| Variable | Default | Description |
|---|---|---|
| `ENVIRONMENT` | `development` | Set to `production` for production use |
| `SECRET_KEY` | *(required)* | Session signing secret |
| `POSTGRES_PASSWORD` | *(required)* | Database password |
| `FRONTEND_PORT` | `8081` | Host port for the web interface |
| `PUBLIC_BASE_URL` | `http://localhost:8081` | Public URL (used in emails) |
| `EMAIL_PROVIDER` | `smtp` | `smtp` for Mailpit/SMTP, `resend` for Resend API |
| `HOST_DATA_PATH` | `./data` | Host directory for uploaded files |
| `REGISTRATION_POLICY` | `open` | `open` or `invitation_only` |
| `COOKIE_SECURE` | `false` | Set `true` when using HTTPS |
| `TRUSTED_HOSTS` | `localhost,127.0.0.1,frontend` | Allowed hostnames |

## Persistent Data

| Data | Location | Type |
|---|---|---|
| PostgreSQL database | `homeserver-v2-db-data` Docker volume | Named volume |
| Uploaded files | `./data/` (configurable via `HOST_DATA_PATH`) | Bind mount |

Data persists across restarts and upgrades. To completely reset, run:
```bash
docker compose down -v    # Removes containers AND database volume
rm -rf ./data             # Removes uploaded files
```

## Stopping & Restarting

```bash
# Stop all services (data is preserved)
docker compose down

# Or use the provided scripts
./scripts/stop.sh          # Linux/macOS
.\scripts\stop.ps1         # Windows

# Restart
docker compose up -d --build
```

## Updating

1. Download the new release ZIP
2. Extract and replace files (keep your `.env` and `data/` directory)
3. Run `docker compose up -d --build` to rebuild with updated code

## Troubleshooting

| Issue | Solution |
|---|---|
| Port 8081 is in use | Change `FRONTEND_PORT` in `.env` |
| Backend not ready | Run `docker compose logs homeserver-v2-backend` to see errors |
| Database connection error | Ensure PostgreSQL started: `docker compose logs homeserver-v2-db` |
| Email not arriving | Check Mailpit at `http://localhost:8025` (dev mode) |
| Permission denied on data | Ensure `APP_UID`/`APP_GID` in `.env` match your host user |
| Compose version error | Update Docker: `docker compose version` should show v2.x+ |
| First build is slow | Normal — Docker downloads base images (~1 GB total) on first run |

### Useful Commands

```bash
# View all service logs
docker compose logs -f

# View specific service logs
docker compose logs -f homeserver-v2-backend

# Check service health
docker compose ps

# Rebuild a specific service
docker compose build homeserver-v2-backend
docker compose up -d homeserver-v2-backend

# Access database shell
docker compose exec homeserver-v2-db psql -U homeserver_v2

# Run backend tests
docker compose exec homeserver-v2-backend python -m pytest tests/ -v
```

## Production Checklist

- [ ] Set `ENVIRONMENT=production` in `.env`
- [ ] Generate unique `SECRET_KEY` and `POSTGRES_PASSWORD`
- [ ] Configure HTTPS reverse proxy (e.g., Nginx, Caddy, Traefik)
- [ ] Set `COOKIE_SECURE=true` and `COOKIE_SAMESITE=lax`
- [ ] Set `PUBLIC_BASE_URL` to your HTTPS domain
- [ ] Set `TRUSTED_HOSTS` to your domain name(s)
- [ ] Configure real email delivery (`EMAIL_PROVIDER=resend` or external SMTP)
- [ ] Back up `.env` and `data/` directory regularly
- [ ] Consider setting `REGISTRATION_POLICY=invitation_only`

## License

Copyright 2026 Aswin A

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

> <http://www.apache.org/licenses/LICENSE-2.0>

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.

See [NOTICE](NOTICE) for third-party dependency licenses and attributions.
