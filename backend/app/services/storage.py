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

import json
import logging
import os
import shutil
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from fastapi import HTTPException
from sqlalchemy.orm import Session as DBSession

from app.core.config import settings
from app.models.entities import StorageLocation, ServerConfig

logger = logging.getLogger(__name__)

RPC_DIR = Path(settings.storage_root) / ".hs_storage_rpc"


def get_host_helper_status() -> dict[str, Any]:
    """
    Checks if the host storage helper daemon is running and healthy.
    Communication is via atomic heartbeat JSON in RPC_DIR.
    """
    heartbeat_file = RPC_DIR / "helper_heartbeat.json"
    if not heartbeat_file.exists():
        return {
            "online": False,
            "details": None,
            "instructions": "Host helper daemon is not running. Run './scripts/manage-storage.sh daemon-start' on the host computer.",
        }

    try:
        content = json.loads(heartbeat_file.read_text(encoding="utf-8"))
        mtime = heartbeat_file.stat().st_mtime
        age = time.time() - mtime
        if age > 15.0:
            return {
                "online": False,
                "details": content,
                "instructions": f"Host helper heartbeat is stale ({int(age)}s old). Restart daemon with './scripts/manage-storage.sh daemon-start'.",
            }
        return {
            "online": True,
            "details": content,
            "instructions": None,
        }
    except Exception as e:
        return {
            "online": False,
            "details": None,
            "instructions": f"Failed to read helper heartbeat: {e}",
        }


def send_host_helper_rpc(action: str, params: dict[str, Any], timeout_seconds: float = 6.0) -> dict[str, Any]:
    """
    Sends a synchronous JSON RPC request to the host storage helper via shared RPC directory.
    Guarantees no arbitrary shell execution inside container or Docker socket exposure.
    """
    status = get_host_helper_status()
    if not status["online"]:
        raise HTTPException(
            503,
            f"Host Storage Helper is offline. {status['instructions'] or 'Start helper on host to browse or mount host folders.'}",
        )

    RPC_DIR.mkdir(parents=True, exist_ok=True)
    req_id = uuid.uuid4().hex[:12]
    req_file = RPC_DIR / f"request_{req_id}.json"
    resp_file = RPC_DIR / f"response_{req_id}.json"

    req_payload = {
        "id": req_id,
        "action": action,
        "params": params,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        req_file.write_text(json.dumps(req_payload), encoding="utf-8")
    except Exception as e:
        raise HTTPException(500, f"Failed to submit host helper request: {e}")

    start = time.time()
    while time.time() - start < timeout_seconds:
        if resp_file.exists():
            try:
                resp_data = json.loads(resp_file.read_text(encoding="utf-8"))
                resp_file.unlink(missing_ok=True)
                if resp_data.get("status") == "error":
                    raise HTTPException(400, resp_data.get("error", "Host helper action failed"))
                return resp_data.get("result", {})
            except HTTPException:
                raise
            except Exception as e:
                resp_file.unlink(missing_ok=True)
                raise HTTPException(500, f"Invalid host helper response: {e}")
        time.sleep(0.08)

    # Clean up request if timed out
    req_file.unlink(missing_ok=True)
    raise HTTPException(504, f"Host helper timed out processing action '{action}' after {timeout_seconds}s")


def get_authorized_roots(db: DBSession | None = None) -> dict[str, dict[str, Any]]:
    """
    Returns authorized container filesystem roots.
    Default root is settings.storage_root (/data).
    Additional authorized roots can be registered by administrators in storage_locations.
    """
    base_root = Path(settings.storage_root).resolve()
    roots = {
        "default": {
            "key": "default",
            "name": "Primary Storage (/data)",
            "path": base_root,
            "container_path": str(base_root),
            "is_system": True,
        }
    }

    if db:
        locations = db.query(StorageLocation).filter(StorageLocation.root_key != "default").all()
        for loc in locations:
            if loc.target_path:
                p = Path(loc.target_path).resolve()
                roots[f"loc_{loc.id}"] = {
                    "key": f"loc_{loc.id}",
                    "name": loc.name,
                    "path": p,
                    "container_path": str(p),
                    "is_system": False,
                    "location_id": loc.id,
                }
    return roots


def safe_resolve_in_root(root_path: Path, relative_path: str = "") -> Path:
    """
    Resolves relative_path inside root_path, guaranteeing no traversal escapes.
    """
    if "\\" in relative_path or "\x00" in relative_path:
        raise HTTPException(400, "Invalid path: forbidden characters")
    pure = PurePosixPath(relative_path or ".")
    if pure.is_absolute() or any(part in ("..", "") for part in pure.parts):
        raise HTTPException(400, "Invalid path: directory traversal attempt")
    
    target = (root_path / Path(*pure.parts)).resolve()
    if not target.is_relative_to(root_path):
        raise HTTPException(400, "Invalid path: target escapes authorized root")
    return target


def measure_storage(target_path: Path) -> dict[str, Any]:
    """
    Measures capacity and availability for a container path.
    Does not use fabricated numbers.
    """
    exists = target_path.exists()
    is_dir = target_path.is_dir() if exists else False
    
    if not exists or not is_dir:
        return {
            "exists": False,
            "is_dir": False,
            "total_bytes": None,
            "used_bytes": None,
            "free_bytes": None,
            "percent_used": None,
            "readable": False,
            "writable": False,
            "status": "missing",
            "error": "Directory does not exist or is not a directory" if not exists else "Target is not a directory",
        }

    readable = os.access(target_path, os.R_OK)
    writable = os.access(target_path, os.W_OK)
    
    # Verify write access by attempting to create and remove a test file
    test_write_ok = False
    if writable:
        test_file = target_path / f".__hs_test_write_{uuid.uuid4().hex[:8]}__"
        try:
            test_file.write_text("ok")
            test_file.unlink(missing_ok=True)
            test_write_ok = True
        except Exception:
            test_write_ok = False
            writable = False

    total = None
    used = None
    free = None
    percent = None
    try:
        usage = shutil.disk_usage(target_path)
        total = usage.total
        free = usage.free
        used = usage.used
        if total > 0:
            percent = round((used / total) * 100, 1)
    except Exception:
        pass

    if not readable:
        status = "unreadable"
    elif not test_write_ok:
        status = "read_only"
    elif free is not None and free < 10 * 1024 * 1024:  # < 10MB
        status = "full"
    elif free is not None and free < 1024 * 1024 * 1024:  # < 1GB
        status = "low_space"
    else:
        status = "available"

    return {
        "exists": True,
        "is_dir": is_dir,
        "total_bytes": total,
        "used_bytes": used,
        "free_bytes": free,
        "percent_used": percent,
        "readable": readable,
        "writable": test_write_ok,
        "status": status,
        "error": None if status in ("available", "low_space") else f"Storage status: {status}",
    }


def measure_storage_location(loc: StorageLocation) -> dict[str, Any]:
    """
    Measures a StorageLocation, accurately distinguishing host path from container path.
    Never marks a host directory as available unless it is actually mounted inside the container.
    """
    # 1. Host bind mount check
    if loc.host_path:
        container_path = Path(loc.target_path).resolve() if loc.target_path else None
        if not container_path or not container_path.exists():
            return {
                "exists": False,
                "is_dir": False,
                "total_bytes": None,
                "used_bytes": None,
                "free_bytes": None,
                "percent_used": None,
                "readable": False,
                "writable": False,
                "status": "unmounted",
                "mount_status": "unmounted",
                "error": f"Host directory '{loc.host_path}' is not mounted into container at '{loc.target_path}'.",
            }
        # Path exists inside container, measure actual access
        metrics = measure_storage(container_path)
        if metrics["writable"]:
            mount_status = "mounted_and_writable"
        elif metrics["readable"]:
            mount_status = "mounted_read_only"
        else:
            mount_status = "unreadable"
        metrics["mount_status"] = mount_status
        return metrics

    # 2. Standard container directory or root
    if loc.root_key == "default":
        root = Path(settings.storage_root).resolve()
    elif loc.target_path:
        root = Path(loc.target_path).resolve()
    else:
        root = Path(settings.storage_root).resolve()

    target = safe_resolve_in_root(root, loc.relative_path) if loc.relative_path else root
    metrics = measure_storage(target)
    metrics["mount_status"] = "mounted_and_writable" if metrics["writable"] else ("mounted_read_only" if metrics["readable"] else "missing")
    return metrics


def get_active_storage_root(db: DBSession) -> tuple[Path, StorageLocation | None]:
    """
    Returns the active default destination directory and its StorageLocation record.
    If the configured default storage is an unmounted host directory or unreadable,
    logs a warning and safely falls back to /data.
    """
    default_loc = db.query(StorageLocation).filter_by(is_default=True).first()
    if default_loc:
        base: Path | None = None
        if default_loc.host_path:
            # Check if host directory is mounted in container
            target_p = Path(default_loc.target_path).resolve() if default_loc.target_path else None
            if target_p and target_p.exists() and os.access(target_p, os.W_OK):
                base = target_p
            else:
                logger.warning(
                    f"Default storage location '{default_loc.name}' (host: {default_loc.host_path}) is not mounted or not writable at {default_loc.target_path}. Falling back to primary storage."
                )
        elif default_loc.root_key == "default":
            base = Path(settings.storage_root).resolve()
        elif default_loc.target_path:
            p = Path(default_loc.target_path).resolve()
            if p.exists() and os.access(p, os.W_OK):
                base = p

        if base:
            if default_loc.relative_path:
                target = safe_resolve_in_root(base, default_loc.relative_path)
            else:
                target = base
            target.mkdir(parents=True, exist_ok=True)
            return target, default_loc

    base = Path(settings.storage_root).resolve()
    base.mkdir(parents=True, exist_ok=True)
    return base, None
