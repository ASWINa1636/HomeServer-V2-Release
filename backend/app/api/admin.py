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
import platform
import socket
import time
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import desc, func, text
from sqlalchemy.orm import Session as DBSession

from app.api.deps import current_user, system_admin
from app.core.config import settings
from app.core.database import engine, get_db
from app.models.entities import (
    AuditEvent,
    FileRecord,
    Invitation,
    Membership,
    ServerConfig,
    Session,
    StorageLocation,
    User,
    Workspace,
    now_utc,
)
from app.services.storage import get_active_storage_root, measure_storage

router = APIRouter(prefix="/admin", tags=["admin"])
_process_boot_time = time.time()


def get_real_uptime_seconds() -> float:
    try:
        with open("/proc/uptime", "r") as f:
            return float(f.readline().split()[0])
    except Exception:
        return time.time() - _process_boot_time


def get_system_memory() -> dict[str, int | None]:
    try:
        meminfo: dict[str, int] = {}
        with open("/proc/meminfo", "r") as f:
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    key = parts[0].strip()
                    val = parts[1].strip().split()[0]
                    if val.isdigit():
                        meminfo[key] = int(val) * 1024  # kB to bytes
        total = meminfo.get("MemTotal")
        avail = meminfo.get("MemAvailable", meminfo.get("MemFree"))
        used = total - avail if (total and avail) else None
        return {"total_bytes": total, "used_bytes": used, "available_bytes": avail}
    except Exception:
        return {"total_bytes": None, "used_bytes": None, "available_bytes": None}


def get_system_load() -> list[float]:
    try:
        return list(os.getloadavg())
    except Exception:
        return [0.0, 0.0, 0.0]


def get_db_migration_version(db: DBSession) -> str:
    try:
        row = db.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).fetchone()
        return str(row[0]) if row else "unknown"
    except Exception:
        return "unknown"


@router.get("/overview")
def admin_overview(
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Comprehensive real-time administrator metrics across health, storage, users,
    security, network, and system resources.
    """
    now = now_utc()

    # 1. Database Health Check
    db_ok = False
    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False

    # 2. Storage Health Check
    active_path, active_loc = get_active_storage_root(db)
    storage_metrics = measure_storage(active_path)

    # File totals
    total_file_records = db.query(FileRecord).filter_by(kind="file").count()
    total_file_bytes = db.query(func.coalesce(func.sum(FileRecord.size_bytes), 0)).scalar() or 0

    # Top 5 largest files
    largest_files_query = (
        db.query(FileRecord)
        .filter_by(kind="file")
        .order_by(desc(FileRecord.size_bytes))
        .limit(5)
        .all()
    )
    largest_files = [
        {
            "id": f.id,
            "path": f.relative_path,
            "size_bytes": f.size_bytes,
            "modified_at": f.modified_at.isoformat() if f.modified_at else None,
        }
        for f in largest_files_query
    ]

    # 3. Users and Workspaces Summary
    total_users = db.query(User).count()
    verified_users = db.query(User).filter_by(is_verified=True).count()
    active_users = db.query(User).filter_by(is_active=True).count()
    suspended_users = total_users - active_users

    roles_count = {
        "owners": db.query(User).filter_by(role="system_owner").count(),
        "admins": db.query(User).filter_by(role="system_admin").count(),
        "members": db.query(User).filter_by(role="member").count(),
    }

    total_orgs = db.query(Workspace).filter_by(kind="organization").count()
    total_workspaces = db.query(Workspace).count()

    pending_invitations = (
        db.query(Invitation)
        .filter(Invitation.revoked_at.is_(None), Invitation.expires_at > now)
        .count()
    )

    recent_users_query = db.query(User).order_by(desc(User.created_at)).limit(5).all()
    recent_users = [
        {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "username": u.username,
            "role": u.role,
            "is_verified": u.is_verified,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
        }
        for u in recent_users_query
    ]

    # 4. Security & Sessions
    active_sessions = (
        db.query(Session)
        .filter(Session.revoked_at.is_(None), Session.expires_at > now)
        .count()
    )

    recent_audits = (
        db.query(AuditEvent)
        .order_by(desc(AuditEvent.created_at))
        .limit(8)
        .all()
    )
    recent_audit_logs = [
        {
            "id": a.id,
            "actor_user_id": a.actor_user_id,
            "action": a.action,
            "target": a.target,
            "created_at": a.created_at.isoformat() if a.created_at else None,
        }
        for a in recent_audits
    ]

    # 5. Network & Config
    server_name_conf = db.get(ServerConfig, "server_name")
    server_name = server_name_conf.value if server_name_conf else "HomeServer V2"
    reg_policy_conf = db.get(ServerConfig, "registration_policy")
    reg_policy = reg_policy_conf.value if reg_policy_conf else settings.registration_policy

    tailscale_conf = db.get(ServerConfig, "tailscale_status")
    domain_conf = db.get(ServerConfig, "public_domain")

    # 6. System Resources
    mem = get_system_memory()
    uptime = get_real_uptime_seconds()
    load = get_system_load()
    migration_ver = get_db_migration_version(db)

    return {
        "server": {
            "name": server_name,
            "version": "2.0.0",
            "migration_version": migration_ver,
            "python_version": platform.python_version(),
            "hostname": socket.gethostname(),
            "environment": settings.environment,
            "uptime_seconds": uptime,
            "boot_time": datetime.fromtimestamp(time.time() - uptime, timezone.utc).isoformat(),
            "checked_at": now.isoformat(),
        },
        "health": {
            "app": "ok",
            "database": "ok" if db_ok else "unreachable",
            "storage": storage_metrics["status"],
            "overall": "healthy" if (db_ok and storage_metrics["writable"]) else "degraded",
        },
        "system": {
            "memory": mem,
            "load_average": load,
        },
        "storage": {
            "location_name": active_loc.name if active_loc else "Primary storage",
            "container_path": str(active_path),
            "status": storage_metrics["status"],
            "total_bytes": storage_metrics["total_bytes"],
            "used_bytes": storage_metrics["used_bytes"],
            "free_bytes": storage_metrics["free_bytes"],
            "percent_used": storage_metrics["percent_used"],
            "writable": storage_metrics["writable"],
            "readable": storage_metrics["readable"],
            "total_files": total_file_records,
            "total_file_bytes": total_file_bytes,
            "largest_files": largest_files,
        },
        "users": {
            "total": total_users,
            "verified": verified_users,
            "active": active_users,
            "suspended": suspended_users,
            "roles": roles_count,
            "pending_invitations": pending_invitations,
            "total_organizations": total_orgs,
            "total_workspaces": total_workspaces,
            "registration_policy": reg_policy,
            "recent_registrations": recent_users,
        },
        "security": {
            "active_sessions": active_sessions,
            "recent_audit_events": recent_audit_logs,
        },
        "network": {
            "local_url": settings.public_base_url,
            "tailscale_configured": tailscale_conf is not None,
            "public_domain": domain_conf.value if domain_conf else None,
        },
    }


class UpdateRoleInput(BaseModel):
    role: str = Field(pattern="^(member|system_admin)$")


class UpdateStatusInput(BaseModel):
    is_active: bool


@router.get("/users")
def list_admin_users(
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Lists detailed information for all users on the server.
    """
    users = db.query(User).order_by(User.id.asc()).all()
    res = []
    for u in users:
        workspaces_count = db.query(Membership).filter_by(user_id=u.id).count()
        personal_ws = db.query(Workspace).filter_by(owner_id=u.id, kind="personal").first()
        files_count = 0
        storage_bytes = 0
        if personal_ws:
            files_count = db.query(FileRecord).filter_by(workspace_id=personal_ws.id, kind="file").count()
            storage_bytes = (
                db.query(func.coalesce(func.sum(FileRecord.size_bytes), 0))
                .filter_by(workspace_id=personal_ws.id, kind="file")
                .scalar()
                or 0
            )

        res.append({
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "username": u.username,
            "role": u.role,
            "is_verified": u.is_verified,
            "is_active": u.is_active,
            "created_at": u.created_at.isoformat() if u.created_at else None,
            "workspaces_count": workspaces_count,
            "files_count": files_count,
            "storage_bytes": storage_bytes,
        })
    return {"items": res, "total": len(res)}


@router.put("/users/{user_id}/role")
def update_user_role(
    user_id: int,
    body: UpdateRoleInput,
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Promotes or demotes user role between member and system_admin.
    Cannot change system_owner.
    """
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.role == "system_owner":
        raise HTTPException(403, "The server owner role cannot be altered via this endpoint")
    if target.id == user.id:
        raise HTTPException(400, "You cannot alter your own administrative role")

    old_role = target.role
    target.role = body.role
    db.add(AuditEvent(actor_user_id=user.id, action="user.role_changed", target=f"{target.email}:{body.role}"))
    db.commit()
    return {"id": target.id, "email": target.email, "role": target.role}


@router.put("/users/{user_id}/status")
def update_user_status(
    user_id: int,
    body: UpdateStatusInput,
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Suspends or reactivates a user account.
    """
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == user.id:
        raise HTTPException(400, "You cannot suspend your own account")
    if target.role == "system_owner":
        raise HTTPException(403, "Cannot suspend the system owner")

    target.is_active = body.is_active
    action = "user.activated" if body.is_active else "user.suspended"
    db.add(AuditEvent(actor_user_id=user.id, action=action, target=target.email))
    db.commit()
    return {"id": target.id, "email": target.email, "is_active": target.is_active}


@router.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Removes a user account.
    """
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    if target.id == user.id:
        raise HTTPException(400, "You cannot delete your own account")
    if target.role == "system_owner":
        raise HTTPException(403, "Cannot delete the server owner account")

    email = target.email
    db.delete(target)
    db.add(AuditEvent(actor_user_id=user.id, action="user.deleted", target=email))
    db.commit()
    return {"deleted": True, "email": email}


class SetUserWorkspaceRoleInput(BaseModel):
    role: str = Field(pattern="^(organization_admin|member|read_only|none)$")


@router.get("/users/{user_id}/workspaces")
def get_user_workspaces(
    user_id: int,
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Lists all workspaces and the user's role/membership in each.
    """
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    all_workspaces = db.query(Workspace).order_by(Workspace.name.asc()).all()
    items = []
    for ws in all_workspaces:
        mem = db.query(Membership).filter_by(workspace_id=ws.id, user_id=target.id).first()
        is_owner = (ws.owner_id == target.id)
        effective_role = mem.role if mem else ("owner" if (is_owner and ws.kind == "personal") else ("organization_admin" if is_owner else None))
        items.append({
            "workspace_id": ws.id,
            "workspace_name": ws.name,
            "workspace_kind": ws.kind,
            "is_member": mem is not None or is_owner,
            "role": effective_role,
            "is_owner": is_owner or target.role == "system_owner",
        })
    return {"user_id": target.id, "email": target.email, "items": items}


@router.put("/users/{user_id}/workspaces/{workspace_id}")
def set_user_workspace_role(
    user_id: int,
    workspace_id: int,
    body: SetUserWorkspaceRoleInput,
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Assigns or updates a user's workspace membership role, or removes it.
    """
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(404, "User not found")
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")

    if target.id == workspace.owner_id or target.role == "system_owner":
        raise HTTPException(403, "Cannot alter the workspace owner or server owner role")

    mem = db.query(Membership).filter_by(workspace_id=workspace_id, user_id=target.id).first()

    if body.role == "none":
        if mem:
            db.delete(mem)
            db.add(AuditEvent(actor_user_id=user.id, action="workspace.member_removed", target=f"{workspace_id}:{target.email}"))
            db.commit()
        return {"user_id": target.id, "workspace_id": workspace_id, "role": None}

    if workspace.kind == "personal" and body.role == "organization_admin":
        raise HTTPException(400, "Organization admin role is only available for organization workspaces")

    if mem:
        mem.role = body.role
        db.add(AuditEvent(actor_user_id=user.id, action="workspace.member_role_changed", target=f"{workspace_id}:{target.email}:{body.role}"))
    else:
        db.add(Membership(workspace_id=workspace_id, user_id=target.id, role=body.role))
        db.add(AuditEvent(actor_user_id=user.id, action="workspace.member_added", target=f"{workspace_id}:{target.email}:{body.role}"))

    db.commit()
    return {"user_id": target.id, "workspace_id": workspace_id, "role": body.role}


@router.get("/audit")
def list_audit_logs(
    action: str | None = Query(default=None),
    limit: int = Query(default=100, le=500),
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Returns audit logs with optional action filtering.
    """
    q = db.query(AuditEvent)
    if action:
        q = q.filter(AuditEvent.action.ilike(f"%{action}%"))
    events = q.order_by(desc(AuditEvent.created_at)).limit(limit).all()

    items = []
    for e in events:
        actor_email = None
        if e.actor_user_id:
            actor = db.get(User, e.actor_user_id)
            actor_email = actor.email if actor else None
        items.append({
            "id": e.id,
            "actor_user_id": e.actor_user_id,
            "actor_email": actor_email,
            "action": e.action,
            "target": e.target,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        })
    return {"items": items, "total": len(items)}


@router.get("/diagnostics")
def run_system_diagnostics(
    user: User = Depends(system_admin),
    db: DBSession = Depends(get_db),
):
    """
    Runs live operational diagnostics across all HomeServer components.
    """
    import os
    import shutil
    import socket
    import time
    from app.services.networking import get_tailscale_config

    checks = []

    # 1. Backend application health
    checks.append({
        "name": "Backend Application Health",
        "category": "core",
        "status": "healthy",
        "detail": "FastAPI runtime is responsive and accepting requests",
        "corrective_action": None,
    })

    # 2. Database Connectivity & Query Latency
    db_status = "healthy"
    db_action = None
    try:
        t0 = time.perf_counter()
        db.execute(text("SELECT 1"))
        latency_ms = round((time.perf_counter() - t0) * 1000, 2)
        db_detail = f"PostgreSQL is healthy (query latency: {latency_ms} ms)"
    except Exception as e:
        db_status = "critical"
        db_detail = f"Database query failed: {str(e)}"
        db_action = "Check postgres container logs: docker logs homeserver-v2-db"

    checks.append({
        "name": "Database Connectivity",
        "category": "database",
        "status": db_status,
        "detail": db_detail,
        "corrective_action": db_action,
    })

    # 3. Storage Availability & Writability
    storage_root = getattr(settings, "storage_root", "/data")
    st_status = "healthy"
    st_action = None
    try:
        if not os.path.exists(storage_root):
            st_status = "critical"
            st_detail = f"Storage root '{storage_root}' does not exist"
            st_action = "Ensure Docker volume or bind mount for /data is configured"
        else:
            test_file = os.path.join(storage_root, f".diag_test_{int(time.time())}")
            with open(test_file, "w") as f:
                f.write("diag_ok")
            os.remove(test_file)
            usage = shutil.disk_usage(storage_root)
            free_gb = round(usage.free / (1024**3), 1)
            total_gb = round(usage.total / (1024**3), 1)
            pct_used = round((usage.used / usage.total) * 100, 1) if usage.total else 0
            if pct_used > 90:
                st_status = "warning"
                st_detail = f"Storage space low: {pct_used}% used ({free_gb} GB free of {total_gb} GB)"
                st_action = "Attach additional storage or remove unnecessary files"
            else:
                st_detail = f"Writable and healthy ({free_gb} GB free of {total_gb} GB, {pct_used}% used)"
    except Exception as e:
        st_status = "critical"
        st_detail = f"Storage test failed: {str(e)}"
        st_action = f"Check filesystem write permissions for container user on {storage_root}"

    checks.append({
        "name": "Storage Read & Write",
        "category": "storage",
        "status": st_status,
        "detail": st_detail,
        "corrective_action": st_action,
    })

    # 4. Email Delivery Service Connectivity
    mail_provider = getattr(settings, "email_provider", "smtp").lower()
    if mail_provider == "resend":
        if settings.resend_api_key and settings.resend_api_key.strip():
            mail_status = "healthy"
            mail_detail = "Resend API delivery is configured"
            mail_action = None
        else:
            mail_status = "warning"
            mail_detail = "EMAIL_PROVIDER is set to 'resend' but RESEND_API_KEY is not configured"
            mail_action = "Set RESEND_API_KEY in .env configuration"
        checks.append({
            "name": "Resend Email Service",
            "category": "mail",
            "status": mail_status,
            "detail": mail_detail,
            "corrective_action": mail_action,
        })
    else:
        smtp_status = "healthy"
        smtp_action = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2.0)
            res = s.connect_ex((settings.smtp_host, settings.smtp_port))
            s.close()
            if res == 0:
                smtp_detail = f"SMTP server is reachable at {settings.smtp_host}:{settings.smtp_port}"
            else:
                smtp_status = "warning"
                smtp_detail = f"Could not connect to SMTP server at {settings.smtp_host}:{settings.smtp_port}"
                smtp_action = "Verify SMTP_HOST and SMTP_PORT in .env configuration"
        except Exception as e:
            smtp_status = "warning"
            smtp_detail = f"SMTP connectivity probe failed: {str(e)}"
            smtp_action = "Check SMTP server reachability or Mailpit container"

        checks.append({
            "name": "SMTP Email Service",
            "category": "mail",
            "status": smtp_status,
            "detail": smtp_detail,
            "corrective_action": smtp_action,
        })

    # 5. Tailscale Status
    ts_cfg = get_tailscale_config(db)
    ts_status = "healthy" if ts_cfg["status"] == "connected" else ("warning" if ts_cfg["is_configured"] else "neutral")
    ts_detail = f"Tailscale is {ts_cfg['status']}" + (f" ({ts_cfg['full_url']})" if ts_cfg.get("full_url") else "")
    ts_action = None if ts_status == "healthy" else "Configure Tailscale in Network settings for secure remote access"

    checks.append({
        "name": "Tailscale Remote Access",
        "category": "network",
        "status": ts_status,
        "detail": ts_detail,
        "corrective_action": ts_action,
    })

    # 6. Security Posture
    sec_issues = []
    if not settings.cookie_secure and settings.environment == "production":
        sec_issues.append("COOKIE_SECURE is disabled")
    sec_status = "healthy" if not sec_issues else "warning"
    sec_detail = "Security settings are active and isolated" if not sec_issues else "; ".join(sec_issues)
    sec_action = None if not sec_issues else "Set COOKIE_SECURE=true when running behind an HTTPS reverse proxy"

    checks.append({
        "name": "Session & Security Posture",
        "category": "security",
        "status": sec_status,
        "detail": sec_detail,
        "corrective_action": sec_action,
    })

    overall = "critical" if any(c["status"] == "critical" for c in checks) else ("warning" if any(c["status"] == "warning" for c in checks) else "healthy")

    return {
        "overall_status": overall,
        "checks": checks,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }
