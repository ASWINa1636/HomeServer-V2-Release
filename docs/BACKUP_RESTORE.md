# Backup and restore

Back up the host data directory configured by `HOST_DATA_PATH` and the PostgreSQL volume `homeserver-v2-db-data`. Coordinate database backups with a consistent PostgreSQL dump; do not copy a live database volume as if it were a portable dump.

Example database dump (run from the project root with the V2 stack running):

```sh
docker compose exec -T homeserver-v2-db pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" > homeserver-v2.sql
```

Example restore requires a fresh V2 database and replaces its records; take a backup first and verify you selected the V2 service:

```sh
docker compose exec -T homeserver-v2-db psql -U "$POSTGRES_USER" "$POSTGRES_DB" < homeserver-v2.sql
```

Restore the matching data directory to the same host path and ownership. Test restoration on a separate V2 instance before relying on the backup. Do not use `docker compose down -v` for routine shutdown; it removes the persistent V2 database volume.
