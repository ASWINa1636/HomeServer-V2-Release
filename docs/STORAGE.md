# Storage

The backend's sole default root is `/data`, backed by the host path in `HOST_DATA_PATH` (default `./data`). Per-user content is placed below `users/<database-user-id>`. The frontend never supplies arbitrary host paths; it sends paths relative to its own root. The backend resolves paths and rejects traversal outside the mounted root.

To use another disk, mount an already-mounted host directory into the backend service, for example `/mnt/media:/data/media:rw`. Ensure the backend's configured non-root `APP_UID`/`APP_GID` can access it. The app does not format drives, move existing files, or delete files at startup. Keep backups of the bind-mounted data and PostgreSQL named volume.

Current UI reports file totals, not filesystem capacity statistics. Selecting among named storage roots and quotas is not implemented yet. Filesystem permissions, read-only mounts, and free space can still cause operations to fail; the API returns an error rather than changing mount permissions.
