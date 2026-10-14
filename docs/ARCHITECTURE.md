# Architecture

HomeServer V2 is a standalone React/Vite browser app and FastAPI API backed by PostgreSQL. Nginx serves the SPA on host port 8081 and proxies `/api` and `/health` to the backend over `homeserver-v2-net`. The backend accesses only explicitly mounted `/data`; PostgreSQL persists in `homeserver-v2-db-data`. Mailpit runs only under the `development` Compose profile.

SQLAlchemy models cover users, challenges, sessions, workspaces, memberships, storage locations, file metadata, invitations, shares, server configuration, and audit events. Alembic applies append-only schema changes on backend startup. Static and user files live on the bind-mounted data root; the database stores account and workspace metadata.

Authentication uses opaque random session cookies stored as protected token digests in PostgreSQL, Argon2id password hashes, one-time email OTP challenges, and CSRF header validation for authenticated unsafe requests. The initial owner claim uses a PostgreSQL advisory transaction lock.

The current app is a single-instance foundation. In-memory throttling is local to a process. The shared-folder model and UI exist as an initial workflow; complete shared-file traversal and permission checks remain future work. Do not scale API replicas or treat this as a complete multi-tenant service until those gaps are addressed.
