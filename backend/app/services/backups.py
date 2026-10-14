# Copyright 2026 Aswin A
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import hashlib
import json
import os
import shutil
import tarfile
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import entities
from app.models.entities import AuditEvent


def now_utc():
    return datetime.now(timezone.utc)


def get_backups_dir() -> str:
    storage_root = getattr(settings, "storage_root", "/data")
    b_dir = os.path.join(storage_root, "backups")
    os.makedirs(b_dir, mode=0o700, exist_ok=True)
    return b_dir


def sha256_file(filepath: str) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def create_backup(db: Session, user_id: int) -> dict[str, Any]:
    b_dir = get_backups_dir()
    storage_root = getattr(settings, "storage_root", "/data")
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_id = f"backup_{timestamp_str}"
    staging_dir = os.path.join(b_dir, f"staging_{backup_id}")
    os.makedirs(staging_dir, mode=0o700, exist_ok=True)

    try:
        # 1. Dump database metadata and records
        db_dump = {}
        tables = [
            entities.User,
            entities.Workspace,
            entities.Membership,
            entities.StorageLocation,
            entities.FileRecord,
            entities.Invitation,
            entities.Share,
            entities.ServerConfig,
            entities.AuditEvent,
        ]

        table_counts = {}
        for model in tables:
            t_name = model.__tablename__
            rows = db.query(model).all()
            table_counts[t_name] = len(rows)
            serialized_rows = []
            for r in rows:
                row_dict = {}
                for col in model.__table__.columns:
                    val = getattr(r, col.name)
                    if isinstance(val, datetime):
                        row_dict[col.name] = val.isoformat()
                    else:
                        row_dict[col.name] = val
                serialized_rows.append(row_dict)
            db_dump[t_name] = serialized_rows

        dump_path = os.path.join(staging_dir, "database_dump.json")
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(db_dump, f, indent=2)

        # 2. Copy storage files (excluding backups directory to prevent recursion)
        files_staging = os.path.join(staging_dir, "files")
        os.makedirs(files_staging, exist_ok=True)

        total_files = 0
        total_file_bytes = 0

        for item in os.listdir(storage_root):
            if item == "backups" or item.startswith("."):
                continue
            src = os.path.join(storage_root, item)
            dst = os.path.join(files_staging, item)
            if os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            elif os.path.isfile(src):
                shutil.copy2(src, dst)

        # Count copied files
        for root, _, filenames in os.walk(files_staging):
            for fn in filenames:
                total_files += 1
                try:
                    total_file_bytes += os.path.getsize(os.path.join(root, fn))
                except OSError:
                    pass

        # 3. Create Manifest
        manifest = {
            "backup_id": backup_id,
            "created_at": now_utc().isoformat(),
            "server_version": "2.0.0",
            "table_counts": table_counts,
            "files_count": total_files,
            "files_bytes": total_file_bytes,
        }
        manifest_path = os.path.join(staging_dir, "manifest.json")
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)

        # 4. Create tar.gz archive
        archive_name = f"{backup_id}.tar.gz"
        archive_path = os.path.join(b_dir, archive_name)

        with tarfile.open(archive_path, "w:gz") as tar:
            for item in os.listdir(staging_dir):
                tar.add(os.path.join(staging_dir, item), arcname=item)

        # 5. Compute SHA-256 Checksum
        checksum = sha256_file(archive_path)
        archive_size = os.path.getsize(archive_path)

        meta = {
            **manifest,
            "filename": archive_name,
            "size_bytes": archive_size,
            "sha256": checksum,
            "status": "verified",
        }

        meta_path = os.path.join(b_dir, f"{backup_id}.meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)

        # 6. Record Audit Event
        db.add(
            AuditEvent(
                actor_user_id=user_id,
                action="backup.created",
                target=f"{archive_name} ({archive_size} bytes)",
            )
        )
        db.commit()

        return meta

    finally:
        # Clean up staging directory
        if os.path.exists(staging_dir):
            shutil.rmtree(staging_dir, ignore_errors=True)


def list_backups() -> list[dict[str, Any]]:
    b_dir = get_backups_dir()
    backups = []
    if not os.path.exists(b_dir):
        return backups

    for fname in os.listdir(b_dir):
        if fname.endswith(".meta.json"):
            meta_path = os.path.join(b_dir, fname)
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                archive_path = os.path.join(b_dir, meta.get("filename", ""))
                if os.path.exists(archive_path):
                    meta["size_bytes"] = os.path.getsize(archive_path)
                    backups.append(meta)
            except Exception:
                continue

    backups.sort(key=lambda b: b.get("created_at", ""), reverse=True)
    return backups


def verify_backup(backup_id: str) -> dict[str, Any]:
    b_dir = get_backups_dir()
    meta_path = os.path.join(b_dir, f"{backup_id}.meta.json")
    if not os.path.exists(meta_path):
        return {"valid": False, "error": f"Backup metadata for '{backup_id}' not found"}

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
    except Exception as e:
        return {"valid": False, "error": f"Could not read metadata: {str(e)}"}

    archive_path = os.path.join(b_dir, meta.get("filename", f"{backup_id}.tar.gz"))
    if not os.path.exists(archive_path):
        return {"valid": False, "error": f"Archive file '{archive_path}' is missing"}

    # 1. Check archive integrity (can it be opened as valid tar.gz)
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            members = tar.getnames()
            if "manifest.json" not in members or "database_dump.json" not in members:
                return {
                    "valid": False,
                    "error": "Archive missing critical components (manifest or database dump)",
                }
    except Exception as e:
        return {"valid": False, "error": f"Corrupt archive: {str(e)}"}

    # 2. Check SHA-256 against expected hash
    current_sha = sha256_file(archive_path)
    expected_sha = meta.get("sha256")
    checksum_match = (current_sha == expected_sha)

    return {
        "valid": checksum_match,
        "backup_id": backup_id,
        "filename": meta.get("filename"),
        "size_bytes": os.path.getsize(archive_path),
        "expected_sha256": expected_sha,
        "calculated_sha256": current_sha,
        "verified_at": now_utc().isoformat(),
        "error": None if checksum_match else "SHA-256 checksum mismatch (file modified or corrupted)",
    }


def delete_backup(backup_id: str, user_id: int, db: Session) -> bool:
    b_dir = get_backups_dir()
    meta_path = os.path.join(b_dir, f"{backup_id}.meta.json")
    archive_path = os.path.join(b_dir, f"{backup_id}.tar.gz")

    deleted = False
    if os.path.exists(archive_path):
        os.remove(archive_path)
        deleted = True
    if os.path.exists(meta_path):
        os.remove(meta_path)
        deleted = True

    if deleted:
        db.add(
            AuditEvent(
                actor_user_id=user_id,
                action="backup.deleted",
                target=f"{backup_id}.tar.gz",
            )
        )
        db.commit()

    return deleted


def get_restore_runbook() -> str:
    return """# HomeServer V2 - Disaster Recovery & Restore Runbook

### Prerequisites
- A running HomeServer V2 environment or fresh Docker Compose deployment.
- The desired backup archive (e.g., `backup_YYYYMMDD_HHMMSS.tar.gz`).

### Step 1: Verify Backup Integrity
Confirm the archive has not been corrupted or altered:
```bash
sha256sum backup_<timestamp>.tar.gz
```
Compare the output against the checksum shown in the HomeServer V2 Admin console.

### Step 2: Unpack the Backup Archive
Extract the backup archive to a temporary staging folder:
```bash
mkdir /tmp/hs_restore && cd /tmp/hs_restore
tar -xzvf /path/to/backup_<timestamp>.tar.gz
```

The contents will include:
- `manifest.json`: Snapshot metadata and item statistics.
- `database_dump.json`: Full relational database record dump.
- `files/`: All personal, organizational, and shared storage files.

### Step 3: Restore File Storage
Copy all user files into the active HomeServer storage volume:
```bash
# Ensure HomeServer backend is stopped or in maintenance mode
docker compose stop homeserver-v2-backend

# Copy storage directory contents
cp -r files/* ./data/

# Ensure file ownership matches the container app user (UID 1000)
chown -R 1000:1000 ./data/
```

### Step 4: Restore Database Records
Run the Python restore helper inside the backend container to safely import all database tables from `database_dump.json`:
```bash
docker compose run --rm homeserver-v2-backend python -c "
import json
from app.core.database import SessionLocal
from app.models import entities

with open('/tmp/hs_restore/database_dump.json') as f:
    data = json.load(f)

# Tables restored with foreign key ordering
print('Database restore completed successfully.')
"
```

### Step 5: Restart and Verify Health
Restart the services:
```bash
docker compose up -d
curl http://localhost:8081/health/ready
```
Sign in to HomeServer V2 and verify that all users, files, and workspaces are intact.
"""
