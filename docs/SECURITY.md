# Security notes

- Never publish the API or PostgreSQL ports. The frontend is the only published application port. Mailpit's UI is loopback-only and development-profile-only.
- Set unique `SECRET_KEY`, database credentials, HTTPS public URL, and secure cookies for production. Do not use `.env.example` values.
- The local development example accepts hostnames flexibly for LAN use. In production, set `TRUSTED_HOSTS` to explicit domain/server hostnames; startup rejects a wildcard in production.
- Passwords use Argon2id. OTPs are six-digit cryptographic random values; only HMAC digests are stored. Challenges expire, are single-use, have attempt limits, and are invalidated when replaced. SMTP errors return a generic client error and do not include codes.
- Sessions use HttpOnly cookies and stored token digests. Authenticated unsafe requests require the separate CSRF token header. `SameSite=Lax` is the default.
- The first System Owner is claimed once. Registration cannot assign administrator roles. The setup and audit APIs enforce administrator checks.
- Files are confined to the configured data root after path resolution. Symlink entries are skipped and user directories are isolated. Mount only directories you intend the app to expose.
- Current rate limits are process-local and reset on restart. Do not scale out without shared throttling. Reverse-proxy deployments must configure trusted hosts and proxy behavior deliberately.

This is an initial implementation, not a security audit. Organization workspaces expose their shared directory to members, with read-only writes blocked. Fine-grained per-folder permissions across all operations, admin role workflows, multi-root storage selection, and robust distributed rate limiting still need implementation and review before production use.
