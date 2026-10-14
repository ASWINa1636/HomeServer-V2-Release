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

import os
import re
from pathlib import Path, PurePosixPath
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession

from app.api.deps import current_user, system_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import AuditEvent, StorageLocation, User
from app.services.storage import (
    get_authorized_roots,
    safe_resolve_in_root,
    measure_storage,
    measure_storage_location,
    get_active_storage_root,
    get_host_helper_status,
    send_host_helper_rpc,
)

router = APIRouter(prefix="/storage", tags=["storage"])


def slugify_name(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]", "-", name).strip("-").lower()
    return slug or "storage"


class CreateLocationInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    type: str = Field(default="auto")  # "host_path", "mounted_dir", "subfolder", "auto"
    host_path: str | None = Field(default=None, max_length=512)
    root_key: str = Field(default="default", max_length=64)
    relative_path: str = Field(default="", max_length=512)
    target_path: str = Field(default="", max_length=512)
    auto_mount: bool = True
    is_default: bool = False


class MkdirInput(BaseModel):
    root_key: str = "default"
    path: str = Field(default="", max_length=512)
    name: str = Field(min_length=1, max_length=255)


class TestStorageInput(BaseModel):
    location_id: int | None = None
    root_key: str | None = None
    relative_path: str | None = None


class HostPathValidateInput(BaseModel):
    path: str = Field(min_length=1, max_length=512)


@router.get("/helper/status")
def helper_status(user: User = Depends(current_user)):
    """
    Returns current health status and heartbeat of the host storage helper daemon.
    """
    return get_host_helper_status()


@router.get("/host/browse")
def host_browse(
    path: str = Query(default="", max_length=512),
    user: User = Depends(system_admin),
):
    """
    Enables administrator to browse actual directories on the host operating system.
    Communicates securely with the least-privilege host storage helper.
    """
    res = send_host_helper_rpc("browse", {"path": path})
    return res


@router.post("/host/validate")
def host_validate(
    body: HostPathValidateInput,
    user: User = Depends(system_admin),
):
    """
    Validates existence, permissions, and capacity of a folder on the host computer.
    """
    res = send_host_helper_rpc("validate", {"path": body.path})
    return res


@router.get("/status")
def storage_status(
    user: User = Depends(current_user),
    db: DBSession = Depends(get_db),
):
    """
    Returns general storage capacity and health statistics.
    Accessible to all authenticated users for quota and status awareness.
    """
    active_path, default_loc = get_active_storage_root(db)
    metrics = measure_storage(active_path)
    helper = get_host_helper_status()
    
    locations_count = db.query(StorageLocation).count()
    if locations_count == 0:
        locations_count = 1

    health = "healthy"
    if metrics["status"] in ("missing", "unreadable", "read_only", "full"):
        health = "critical"
    elif metrics["status"] == "low_space":
        health = "warning"

    return {
        "current_location": {
            "id": default_loc.id if default_loc else 0,
            "name": default_loc.name if default_loc else "Primary storage",
            "path": str(active_path),
            "host_path": default_loc.host_path if default_loc else "./data",
            "mount_status": default_loc.mount_status if default_loc else "mounted_and_writable",
            "is_default": True,
        },
        "total_bytes": metrics["total_bytes"],
        "used_bytes": metrics["used_bytes"],
        "free_bytes": metrics["free_bytes"],
        "percent_used": metrics["percent_used"],
        "readable": metrics["readable"],
        "writable": metrics["writable"],
        "status": metrics["status"],
        "health": health,
        "locations_count": locations_count,
        "helper_online": helper["online"],
    }


@router.get("/locations")
def list_storage_locations(
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Lists all configured storage locations with real filesystem measurements.
    Distinguishes host path from container path and reports mount status accurately.
    """
    locations = db.query(StorageLocation).order_by(StorageLocation.created_at.asc()).all()
    roots = get_authorized_roots(db)
    helper = get_host_helper_status()

    results = []
    # If no locations registered in DB, generate representation of primary /data
    if not locations:
        base_path = Path(settings.storage_root).resolve()
        metrics = measure_storage(base_path)
        results.append({
            "id": 0,
            "name": "Primary storage",
            "root_key": "default",
            "relative_path": "",
            "target_path": str(base_path),
            "host_path": "./data",
            "mount_status": "mounted_and_writable",
            "mount_type": "container_volume",
            "is_default": True,
            "status": metrics["status"],
            "total_bytes": metrics["total_bytes"],
            "used_bytes": metrics["used_bytes"],
            "free_bytes": metrics["free_bytes"],
            "percent_used": metrics["percent_used"],
            "writable": metrics["writable"],
            "readable": metrics["readable"],
        })
    else:
        for loc in locations:
            metrics = measure_storage_location(loc)
            results.append({
                "id": loc.id,
                "name": loc.name,
                "root_key": loc.root_key,
                "relative_path": loc.relative_path,
                "target_path": loc.target_path,
                "host_path": loc.host_path,
                "mount_status": metrics.get("mount_status", loc.mount_status),
                "mount_type": loc.mount_type,
                "is_default": loc.is_default,
                "status": metrics["status"],
                "total_bytes": metrics["total_bytes"],
                "used_bytes": metrics["used_bytes"],
                "free_bytes": metrics["free_bytes"],
                "percent_used": metrics["percent_used"],
                "writable": metrics["writable"],
                "readable": metrics["readable"],
                "error": metrics.get("error"),
            })

    return {
        "items": results,
        "helper_online": helper["online"],
        "helper_instructions": helper["instructions"],
        "authorized_roots": [
            {"key": r["key"], "name": r["name"], "container_path": r["container_path"]}
            for r in roots.values()
        ],
    }


@router.post("/locations", status_code=201)
def add_storage_location(
    body: CreateLocationInput,
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Registers a new storage location.
    Distinguishes host folder paths from container mount paths.
    If auto_mount is requested and helper is online, automatically adds Docker Compose bind mount.
    """
    # Option 1: Host Directory Selection
    if body.type == "host_path" or (body.host_path and body.host_path.strip()):
        raw_host = (body.host_path or "").strip()
        if not raw_host:
            raise HTTPException(422, "host_path is required when adding a host folder location")

        mount_slug = slugify_name(body.name)
        container_mount = f"/srv/homeserver/{mount_slug}"
        helper = get_host_helper_status()

        # Check if already registered
        existing = db.query(StorageLocation).filter(
            (StorageLocation.host_path == raw_host) | (StorageLocation.target_path == container_mount)
        ).first()

        if body.auto_mount and helper["online"]:
            # Validate host path first via helper
            val = send_host_helper_rpc("validate", {"path": raw_host})
            if not val.get("valid"):
                raise HTTPException(400, val.get("error", f"Invalid host directory '{raw_host}'"))

            clean_host = val["host_path"]

            # If user wants to make this location default, unset previous default
            if body.is_default:
                db.query(StorageLocation).update({"is_default": False})

            if existing:
                loc = existing
                loc.name = body.name.strip()
                loc.host_path = clean_host
                loc.target_path = container_mount
                loc.mount_status = "mounting"
                loc.mount_type = "host_bind"
                if body.is_default:
                    loc.is_default = True
            else:
                loc = StorageLocation(
                    name=body.name.strip(),
                    root_key=f"loc_{mount_slug}",
                    relative_path="",
                    target_path=container_mount,
                    host_path=clean_host,
                    mount_status="mounting",
                    mount_type="host_bind",
                    is_default=body.is_default,
                )
                db.add(loc)

            db.commit()
            db.refresh(loc)

            # Trigger helper attach mount in background RPC
            try:
                # Send attach RPC
                send_host_helper_rpc(
                    "attach_mount",
                    {"host_path": clean_host, "name": body.name, "make_default": body.is_default},
                    timeout_seconds=40.0,
                )
            except HTTPException:
                pass  # Container recreation may reset connection; frontend will poll status

            return {
                "id": loc.id,
                "name": loc.name,
                "host_path": loc.host_path,
                "target_path": loc.target_path,
                "mount_status": "mounting",
                "mount_type": "host_bind",
                "is_default": loc.is_default,
                "restarting": True,
                "message": "Mount configuration applied. Backend service is restarting with the new storage volume.",
            }

        else:
            # Helper offline or auto_mount=False
            # Host path cannot be marked as mounted or available!
            if existing:
                loc = existing
                loc.name = body.name.strip()
                loc.host_path = raw_host
                loc.target_path = container_mount
                loc.mount_status = "unmounted"
                loc.mount_type = "host_bind"
            else:
                loc = StorageLocation(
                    name=body.name.strip(),
                    root_key=f"loc_{mount_slug}",
                    relative_path="",
                    target_path=container_mount,
                    host_path=raw_host,
                    mount_status="unmounted",
                    mount_type="host_bind",
                    is_default=False,  # Cannot set unmounted folder as default
                )
                db.add(loc)

            db.commit()
            db.refresh(loc)

            return {
                "id": loc.id,
                "name": loc.name,
                "host_path": loc.host_path,
                "target_path": loc.target_path,
                "mount_status": "unmounted",
                "mount_type": "host_bind",
                "is_default": False,
                "restarting": False,
                "message": f"Host directory registered. Run './scripts/manage-storage.sh attach {raw_host}' on the host computer to mount it.",
            }

    # Option 2: Pre-mounted Container Directory or Subfolder
    roots = get_authorized_roots(db)
    root_info = roots.get(body.root_key)
    
    if body.type == "mounted_dir" or body.root_key == "custom":
        if not body.target_path:
            raise HTTPException(422, "target_path is required for pre-mounted container directory")
        custom_path = Path(body.target_path).resolve()
        if not custom_path.exists():
            raise HTTPException(
                400,
                f"Container directory '{body.target_path}' does not exist inside container. If this is a host directory, select 'Host Computer Folder' mode.",
            )
        if not custom_path.is_dir():
            raise HTTPException(400, f"'{body.target_path}' is not a directory")
        target_dir = custom_path
        mount_type = "container_volume"
        root_key = "custom"
        rel_path = ""
    elif root_info:
        root_path = root_info["path"]
        target_dir = safe_resolve_in_root(root_path, body.relative_path)
        mount_type = "container_volume"
        root_key = body.root_key
        rel_path = body.relative_path.strip()
    else:
        raise HTTPException(400, f"Authorized storage root '{body.root_key}' not found")

    metrics = measure_storage(target_dir)
    if not metrics["exists"]:
        raise HTTPException(400, "Directory does not exist inside container")
    if not metrics["writable"]:
        raise HTTPException(400, "Directory is not writable by HomeServer container process")

    if body.is_default:
        db.query(StorageLocation).update({"is_default": False})

    loc = StorageLocation(
        name=body.name.strip(),
        root_key=root_key,
        relative_path=rel_path,
        target_path=str(target_dir),
        host_path=None,
        mount_status="mounted_and_writable",
        mount_type=mount_type,
        is_default=body.is_default,
    )
    db.add(loc)
    db.add(AuditEvent(actor_user_id=user.id, action="storage.location_added", target=body.name.strip()))
    db.commit()
    db.refresh(loc)

    return {
        "id": loc.id,
        "name": loc.name,
        "root_key": loc.root_key,
        "relative_path": loc.relative_path,
        "target_path": loc.target_path,
        "host_path": None,
        "mount_status": "mounted_and_writable",
        "mount_type": loc.mount_type,
        "is_default": loc.is_default,
        "status": metrics["status"],
    }


@router.post("/locations/{location_id}/mount")
def mount_storage_location(
    location_id: int,
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Mounts an unmounted host location into the container via the host storage helper.
    """
    loc = db.get(StorageLocation, location_id)
    if not loc:
        raise HTTPException(404, "Storage location not found")
    if not loc.host_path:
        raise HTTPException(400, "Location does not have an associated host path")

    helper = get_host_helper_status()
    if not helper["online"]:
        raise HTTPException(503, "Host helper daemon is offline. Run './scripts/manage-storage.sh daemon-start' on host.")

    loc.mount_status = "mounting"
    db.commit()

    try:
        send_host_helper_rpc(
            "attach_mount",
            {"host_path": loc.host_path, "name": loc.name, "make_default": loc.is_default},
            timeout_seconds=40.0,
        )
    except HTTPException:
        pass

    return {
        "success": True,
        "restarting": True,
        "message": f"Attaching '{loc.host_path}' to container. Backend container is restarting...",
    }


@router.put("/locations/{location_id}/default")
def set_default_storage_location(
    location_id: int,
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Sets the active default storage destination for future file operations.
    Verifies that the target path is actually mounted and writable.
    """
    loc = db.get(StorageLocation, location_id)
    if not loc:
        if location_id == 0:
            db.query(StorageLocation).update({"is_default": False})
            loc = StorageLocation(
                name="Primary storage",
                root_key="default",
                relative_path="",
                target_path=str(Path(settings.storage_root).resolve()),
                host_path="./data",
                mount_status="mounted_and_writable",
                mount_type="container_volume",
                is_default=True,
            )
            db.add(loc)
            db.commit()
            return {"success": True, "id": loc.id, "name": loc.name, "is_default": True}
        raise HTTPException(404, "Storage location not found")

    metrics = measure_storage_location(loc)
    if not metrics.get("writable"):
        raise HTTPException(
            400,
            f"Cannot set as default: storage location is not mounted and writable (status: {metrics.get('status')}, mount_status: {metrics.get('mount_status')})",
        )

    db.query(StorageLocation).update({"is_default": False})
    loc.is_default = True
    loc.mount_status = "mounted_and_writable"
    db.add(AuditEvent(actor_user_id=user.id, action="storage.default_changed", target=loc.name))
    db.commit()

    return {"success": True, "id": loc.id, "name": loc.name, "is_default": True}


@router.delete("/locations/{location_id}")
def delete_storage_location(
    location_id: int,
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Removes a registered storage location.
    Does NOT delete files on disk.
    Cannot remove active default storage.
    """
    loc = db.get(StorageLocation, location_id)
    if not loc:
        raise HTTPException(404, "Storage location not found")
    if loc.is_default:
        raise HTTPException(400, "Cannot remove the active default storage location. Set another location as default first.")

    name = loc.name
    db.delete(loc)
    db.add(AuditEvent(actor_user_id=user.id, action="storage.location_removed", target=name))
    db.commit()
    return {"deleted": True, "name": name}


@router.get("/browse")
def browse_storage(
    root_key: str = Query(default="default"),
    path: str = Query(default="", max_length=512),
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Enables administrator to browse directories within authorized container roots.
    """
    roots = get_authorized_roots(db)
    root_info = roots.get(root_key)
    if not root_info:
        raise HTTPException(400, f"Unauthorized or unknown storage root '{root_key}'")

    root_path = root_info["path"]
    target = safe_resolve_in_root(root_path, path)

    if not target.exists():
        raise HTTPException(404, "Directory does not exist")
    if not target.is_dir():
        raise HTTPException(400, "Target is not a directory")

    rel = target.relative_to(root_path).as_posix() if target != root_path else ""
    crumbs = []
    if rel:
        parts = PurePosixPath(rel).parts
        accum = []
        for p in parts:
            accum.append(p)
            crumbs.append({"name": p, "path": "/".join(accum)})

    folders = []
    for item in sorted(target.iterdir(), key=lambda p: p.name.lower()):
        if item.is_symlink():
            continue
        if item.is_dir():
            if item.name.startswith(".__hs_") or item.name == ".hs_storage_rpc":
                continue
            item_rel = item.relative_to(root_path).as_posix()
            folders.append({
                "name": item.name,
                "path": item_rel,
                "can_write": os.access(item, os.W_OK),
            })

    metrics = measure_storage(target)

    return {
        "root_key": root_key,
        "root_name": root_info["name"],
        "container_path": str(target),
        "current_path": rel,
        "breadcrumbs": crumbs,
        "folders": folders,
        "can_write": metrics["writable"],
        "status": metrics["status"],
        "total_bytes": metrics["total_bytes"],
        "free_bytes": metrics["free_bytes"],
    }


@router.post("/mkdir", status_code=201)
def create_storage_directory(
    body: MkdirInput,
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    if body.name in (".", "..") or "/" in body.name or "\\" in body.name or "\x00" in body.name:
        raise HTTPException(400, "Invalid folder name")

    roots = get_authorized_roots(db)
    root_info = roots.get(body.root_key)
    if not root_info:
        raise HTTPException(400, f"Unauthorized or unknown storage root '{body.root_key}'")

    parent = safe_resolve_in_root(root_info["path"], body.path)
    if not parent.is_dir():
        raise HTTPException(404, "Parent directory does not exist")

    new_dir = parent / body.name
    if new_dir.exists():
        raise HTTPException(409, "Directory already exists")

    try:
        new_dir.mkdir()
    except PermissionError:
        raise HTTPException(403, "Permission denied creating directory on storage volume")
    except Exception as e:
        raise HTTPException(500, f"Failed to create directory: {e}")

    rel = new_dir.relative_to(root_info["path"]).as_posix()
    db.add(AuditEvent(actor_user_id=user.id, action="storage.directory_created", target=rel))
    db.commit()

    return {"name": new_dir.name, "path": rel, "success": True}


@router.post("/test")
def test_storage(
    body: TestStorageInput,
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Runs a live read/write/statvfs test on a storage location or path.
    Accurately reports container mount status and host path distinction.
    """
    roots = get_authorized_roots(db)
    target_path: Path | None = None
    target_label = ""
    host_path: str | None = None
    is_mounted = True

    if body.location_id is not None:
        loc = db.get(StorageLocation, body.location_id)
        if loc:
            target_label = loc.name
            host_path = loc.host_path
            if loc.target_path:
                target_path = Path(loc.target_path).resolve()
            elif loc.root_key == "default":
                target_path = Path(settings.storage_root).resolve()
            else:
                target_path = Path(settings.storage_root).resolve()
            if loc.relative_path and target_path.exists():
                target_path = safe_resolve_in_root(target_path, loc.relative_path)
        elif body.location_id == 0:
            target_label = "Primary storage"
            target_path = Path(settings.storage_root).resolve()
            host_path = "./data"
        else:
            raise HTTPException(404, "Storage location not found")
    elif body.root_key:
        root_info = roots.get(body.root_key)
        if not root_info:
            raise HTTPException(400, f"Unknown storage root '{body.root_key}'")
        target_label = root_info["name"]
        target_path = safe_resolve_in_root(root_info["path"], body.relative_path or "")
    else:
        target_label = "Primary storage"
        target_path = Path(settings.storage_root).resolve()
        host_path = "./data"

    metrics = measure_storage(target_path) if target_path else {"exists": False, "readable": False, "writable": False, "status": "missing", "total_bytes": None, "free_bytes": None, "used_bytes": None, "percent_used": None}

    checks = [
        {
            "name": "Host vs Container Mapping",
            "passed": True,
            "detail": f"Host: {host_path or 'Container volume'} → Container: {target_path}",
        },
        {
            "name": "Container Mount Exists",
            "passed": metrics["exists"],
            "detail": f"Path: {target_path}" if metrics["exists"] else f"Container path '{target_path}' not mounted",
        },
        {
            "name": "Read permission",
            "passed": metrics["readable"],
            "detail": "Readable by container process" if metrics["readable"] else "Permission denied",
        },
        {
            "name": "Write permission",
            "passed": metrics["writable"],
            "detail": "Verified by temporary test file write/unlink" if metrics["writable"] else "Not writable by container process",
        },
        {
            "name": "Capacity measurement",
            "passed": metrics["total_bytes"] is not None,
            "detail": f"{metrics['free_bytes']} bytes available" if metrics["free_bytes"] else "Capacity metric unavailable",
        },
    ]

    all_passed = all(c["passed"] for c in checks)

    return {
        "target": target_label,
        "path": str(target_path),
        "host_path": host_path,
        "status": metrics["status"] if metrics["exists"] else "unmounted",
        "healthy": all_passed,
        "total_bytes": metrics["total_bytes"],
        "free_bytes": metrics["free_bytes"],
        "used_bytes": metrics["used_bytes"],
        "percent_used": metrics["percent_used"],
        "checks": checks,
    }
