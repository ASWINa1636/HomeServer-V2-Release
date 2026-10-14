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

from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func
from sqlalchemy.orm import Session as DBSession
from app.api.deps import current_user, system_admin
from app.core.config import settings
from app.core.database import get_db
from app.core.security import protected_digest, random_token
from app.models.entities import AuditEvent, Invitation, Membership, Share, User, Workspace, now_utc
from app.services.email import send_invitation

router = APIRouter(tags=["workspaces", "invitations", "sharing"])


@router.get("/workspaces")
def workspaces(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    memberships = db.query(Membership).filter_by(user_id=user.id).all()
    seen = set()
    result = []
    for membership in memberships:
        workspace = db.get(Workspace, membership.workspace_id)
        if workspace and workspace.id not in seen:
            seen.add(workspace.id)
            result.append({"id": workspace.id, "name": workspace.name, "kind": workspace.kind, "role": membership.role})

    owned = db.query(Workspace).filter_by(owner_id=user.id).all()
    for workspace in owned:
        if workspace.id not in seen:
            seen.add(workspace.id)
            role = "owner" if workspace.kind == "personal" else "organization_admin"
            result.append({"id": workspace.id, "name": workspace.name, "kind": workspace.kind, "role": role})

    def sort_key(item):
        is_owned_personal = (item["kind"] == "personal" and item["role"] in ("owner", "system_owner"))
        return (0 if is_owned_personal else 1, item["name"].lower())

    result.sort(key=sort_key)
    return {"items": result}


class OrgInput(BaseModel):
    name: str = Field(min_length=2, max_length=120)


@router.post("/organizations", status_code=201)
def create_organization(body: OrgInput, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    workspace = Workspace(name=body.name.strip(), kind="organization", owner_id=user.id)
    db.add(workspace)
    db.flush()
    db.add(Membership(workspace_id=workspace.id, user_id=user.id, role="organization_admin"))
    db.add(AuditEvent(actor_user_id=user.id, action="organization.created", target=str(workspace.id)))
    db.commit()
    return {"id": workspace.id, "name": workspace.name, "role": "organization_admin"}


class InviteInput(BaseModel):
    email: EmailStr
    role: str = "member"


@router.post("/workspaces/{workspace_id}/invitations", status_code=201)
def create_invitation(workspace_id: int, body: InviteInput, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    member = db.query(Membership).filter_by(workspace_id=workspace_id, user_id=user.id).first()
    is_sys_admin = user.role in ("system_owner", "system_admin")
    if not is_sys_admin and (not member or member.role not in ("owner", "organization_admin")):
        raise HTTPException(403, "Workspace administrator access required")
    allowed_roles = ("organization_admin", "member", "read_only") if workspace.kind == "organization" else ("member", "read_only")
    if body.role not in allowed_roles:
        raise HTTPException(422, "Invitation role is not allowed")

    email_clean = str(body.email).strip().lower()

    # Check if target user is already a member
    existing_user = db.query(User).filter(func.lower(User.email) == email_clean).first()
    if existing_user:
        existing_membership = db.query(Membership).filter_by(workspace_id=workspace_id, user_id=existing_user.id).first()
        if existing_membership:
            if existing_membership.role == "owner" or existing_user.id == workspace.owner_id or existing_user.role == "system_owner":
                raise HTTPException(403, "Cannot alter the workspace owner or server owner role")
            if existing_user.id == user.id:
                raise HTTPException(400, "You cannot alter your own workspace role")
            if existing_membership.role == body.role:
                raise HTTPException(400, f"User is already a {body.role.replace('_', ' ')} in this workspace")
            
            old_role = existing_membership.role
            existing_membership.role = body.role
            db.add(AuditEvent(actor_user_id=user.id, action="workspace.member_role_changed", target=f"{workspace_id}:{existing_user.email}:{body.role}"))
            db.commit()
            return {
                "id": existing_membership.id,
                "workspace_id": workspace_id,
                "email": existing_user.email,
                "role": existing_membership.role,
                "delivery_status": "role_updated",
                "delivery_error": None,
                "invite_url": None,
                "message": f"Updated role of {existing_user.email} from {old_role.replace('_', ' ')} to {body.role.replace('_', ' ')}",
            }

    # Check for active unrevoked unexpired invitation
    active_inv = db.query(Invitation).filter(
        Invitation.workspace_id == workspace_id,
        func.lower(Invitation.email) == email_clean,
        Invitation.revoked_at.is_(None),
        Invitation.expires_at > now_utc(),
    ).first()
    if active_inv:
        if active_inv.role != body.role:
            old_role = active_inv.role
            active_inv.role = body.role
            db.add(AuditEvent(actor_user_id=user.id, action="invitation.role_changed", target=f"{workspace_id}:{email_clean}:{body.role}"))
            db.commit()
            return {
                "id": active_inv.id,
                "workspace_id": active_inv.workspace_id,
                "email": active_inv.email,
                "role": active_inv.role,
                "expires_at": active_inv.expires_at,
                "delivery_status": "role_updated",
                "delivery_error": None,
                "invite_url": f"{settings.public_base_url.rstrip('/')}/signup",
                "message": f"Updated invitation role from {old_role.replace('_', ' ')} to {body.role.replace('_', ' ')}",
            }
        raise HTTPException(409, "An active invitation for this email already exists in this workspace")

    raw = random_token()
    invitation = Invitation(
        workspace_id=workspace_id,
        email=email_clean,
        role=body.role,
        token_hash=protected_digest(raw),
        expires_at=now_utc() + timedelta(days=7),
        created_by=user.id,
        delivery_status="pending",
    )
    db.add(invitation)
    db.add(AuditEvent(actor_user_id=user.id, action="invitation.created", target=f"{workspace_id}:{email_clean}"))
    db.flush()

    invite_url = f"{settings.public_base_url.rstrip('/')}/signup?token={raw}"
    try:
        send_invitation(email_clean, raw)
        invitation.delivery_status = "sent"
        invitation.delivery_error = None
    except Exception as exc:
        invitation.delivery_status = "failed"
        provider_name = "Resend" if getattr(settings, "email_provider", "smtp").lower() == "resend" else "SMTP"
        invitation.delivery_error = f"{provider_name} error: {str(exc)[:180]}"

    db.commit()
    return {
        "id": invitation.id,
        "workspace_id": invitation.workspace_id,
        "email": invitation.email,
        "role": invitation.role,
        "expires_at": invitation.expires_at,
        "delivery_status": invitation.delivery_status,
        "delivery_error": invitation.delivery_error,
        "invite_url": invite_url,
    }


@router.get("/invitations")
def list_invitations(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    memberships = db.query(Membership).filter(
        Membership.user_id == user.id,
        Membership.role.in_(["owner", "organization_admin", "system_owner", "system_admin"]),
    ).all()
    ids = [m.workspace_id for m in memberships]
    invitations = db.query(Invitation).filter(Invitation.workspace_id.in_(ids)).order_by(Invitation.id.desc()).all() if ids else []
    return {
        "items": [
            {
                "id": i.id,
                "workspace_id": i.workspace_id,
                "email": i.email,
                "role": i.role,
                "expires_at": i.expires_at,
                "revoked": i.revoked_at is not None,
                "delivery_status": getattr(i, "delivery_status", "sent") or "sent",
                "delivery_error": getattr(i, "delivery_error", None),
            }
            for i in invitations
        ]
    }


@router.post("/invitations/{invitation_id}/resend")
def resend_invitation(invitation_id: int, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    invitation = db.get(Invitation, invitation_id)
    if not invitation:
        raise HTTPException(404, "Invitation not found")
    member = db.query(Membership).filter_by(workspace_id=invitation.workspace_id, user_id=user.id).first()
    if not member or member.role not in ("owner", "organization_admin", "system_owner", "system_admin"):
        raise HTTPException(403, "Workspace administrator access required")
    if invitation.revoked_at is not None:
        raise HTTPException(400, "Cannot resend a revoked invitation")

    raw = random_token()
    invitation.token_hash = protected_digest(raw)
    invitation.expires_at = now_utc() + timedelta(days=7)
    invite_url = f"{settings.public_base_url.rstrip('/')}/signup?token={raw}"
    try:
        send_invitation(invitation.email, raw)
        invitation.delivery_status = "sent"
        invitation.delivery_error = None
    except Exception as exc:
        invitation.delivery_status = "failed"
        provider_name = "Resend" if getattr(settings, "email_provider", "smtp").lower() == "resend" else "SMTP"
        invitation.delivery_error = f"{provider_name} error: {str(exc)[:180]}"

    db.add(AuditEvent(actor_user_id=user.id, action="invitation.resent", target=str(invitation.id)))
    db.commit()
    return {
        "id": invitation.id,
        "delivery_status": invitation.delivery_status,
        "delivery_error": invitation.delivery_error,
        "invite_url": invite_url,
        "expires_at": invitation.expires_at,
    }


@router.post("/invitations/{invitation_id}/link")
def generate_invitation_link(invitation_id: int, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    invitation = db.get(Invitation, invitation_id)
    if not invitation:
        raise HTTPException(404, "Invitation not found")
    member = db.query(Membership).filter_by(workspace_id=invitation.workspace_id, user_id=user.id).first()
    if not member or member.role not in ("owner", "organization_admin", "system_owner", "system_admin"):
        raise HTTPException(403, "Workspace administrator access required")
    if invitation.revoked_at is not None:
        raise HTTPException(400, "Cannot generate link for a revoked invitation")

    raw = random_token()
    invitation.token_hash = protected_digest(raw)
    invitation.expires_at = now_utc() + timedelta(days=7)
    invite_url = f"{settings.public_base_url.rstrip('/')}/signup?token={raw}"
    db.add(AuditEvent(actor_user_id=user.id, action="invitation.link_generated", target=str(invitation.id)))
    db.commit()
    return {
        "id": invitation.id,
        "invite_url": invite_url,
        "expires_at": invitation.expires_at,
    }


@router.get("/invitations/verify-token")
def verify_invitation_token(token: str, db: DBSession = Depends(get_db)):
    if not token or len(token) < 10:
        raise HTTPException(400, "Invalid invitation token format")
    invitation = db.query(Invitation).filter_by(token_hash=protected_digest(token), revoked_at=None).first()
    if not invitation:
        raise HTTPException(400, "Invitation is invalid or has been revoked")
    expiry = invitation.expires_at.replace(tzinfo=timezone.utc) if invitation.expires_at.tzinfo is None else invitation.expires_at
    if expiry <= now_utc():
        raise HTTPException(400, "Invitation has expired")
    workspace = db.get(Workspace, invitation.workspace_id)
    return {
        "valid": True,
        "email": invitation.email,
        "role": invitation.role,
        "workspace_id": invitation.workspace_id,
        "workspace_name": workspace.name if workspace else "Workspace",
        "expires_at": invitation.expires_at,
    }


@router.delete("/invitations/{invitation_id}")
def revoke_invitation(invitation_id: int, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    invitation = db.get(Invitation, invitation_id)
    if not invitation:
        raise HTTPException(404, "Invitation not found")
    member = db.query(Membership).filter_by(workspace_id=invitation.workspace_id, user_id=user.id).first()
    if not member or member.role not in ("owner", "organization_admin", "system_owner", "system_admin"):
        raise HTTPException(403, "Workspace administrator access required")
    invitation.revoked_at = now_utc()
    db.add(AuditEvent(actor_user_id=user.id, action="invitation.revoked", target=str(invitation.id)))
    db.commit()
    return {"revoked": True}


class AcceptInvite(BaseModel):
    token: str


@router.post("/invitations/accept")
def accept_invitation(body: AcceptInvite, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    invitation = db.query(Invitation).filter_by(token_hash=protected_digest(body.token), revoked_at=None).first()
    if not invitation:
        raise HTTPException(400, "Invitation is invalid, expired, or addressed to another account")
    expiry = invitation.expires_at.replace(tzinfo=timezone.utc) if invitation.expires_at.tzinfo is None else invitation.expires_at
    if expiry <= now_utc() or invitation.email != user.email:
        raise HTTPException(400, "Invitation is invalid, expired, or addressed to another account")
    if not db.query(Membership).filter_by(workspace_id=invitation.workspace_id, user_id=user.id).first():
        db.add(Membership(workspace_id=invitation.workspace_id, user_id=user.id, role=invitation.role))
    invitation.revoked_at = now_utc()
    db.add(AuditEvent(actor_user_id=user.id, action="invitation.accepted", target=str(invitation.id)))
    db.commit()
    return {"workspace_id": invitation.workspace_id, "role": invitation.role}


class ShareInput(BaseModel):
    path: str = Field(min_length=1, max_length=1024)
    email: EmailStr
    permission: str = "read"


@router.post("/workspaces/{workspace_id}/shares", status_code=201)
def create_share(workspace_id: int, body: ShareInput, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    member = db.query(Membership).filter_by(workspace_id=workspace_id, user_id=user.id).first()
    if not member or member.role not in ("owner", "organization_admin", "system_owner", "system_admin"):
        raise HTTPException(403, "Workspace administrator access required")
    target_user = db.query(User).filter_by(email=str(body.email).lower(), is_verified=True).first()
    if not target_user or not db.query(Membership).filter_by(workspace_id=workspace_id, user_id=target_user.id).first():
        raise HTTPException(404, "Verified workspace member not found")
    if body.permission not in ("read", "upload", "modify", "delete", "share"):
        raise HTTPException(422, "Permission is invalid")
    share = Share(workspace_id=workspace_id, relative_path=body.path, subject_user_id=target_user.id, permission=body.permission, created_by=user.id)
    db.add(share)
    db.add(AuditEvent(actor_user_id=user.id, action="share.created", target=body.path))
    db.commit()
    return {"id": share.id, "email": target_user.email, "path": share.relative_path, "permission": share.permission}


@router.get("/audit")
def audit_events(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    if user.role not in ("system_owner", "system_admin"):
        raise HTTPException(403, "Administrator access required")
    events = db.query(AuditEvent).order_by(AuditEvent.created_at.desc()).limit(200).all()
    return {"items": [{"id": e.id, "actor_user_id": e.actor_user_id, "action": e.action, "target": e.target, "created_at": e.created_at} for e in events]}


class UpdateMemberRoleInput(BaseModel):
    role: str = Field(pattern="^(organization_admin|member|read_only)$")


@router.get("/workspaces/{workspace_id}/members")
def list_workspace_members(workspace_id: int, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    caller_member = db.query(Membership).filter_by(workspace_id=workspace_id, user_id=user.id).first()
    is_sys_admin = user.role in ("system_owner", "system_admin")
    if not is_sys_admin and not caller_member:
        raise HTTPException(403, "Workspace access required")

    memberships = db.query(Membership).filter_by(workspace_id=workspace_id).all()
    results = []
    for m in memberships:
        u = db.get(User, m.user_id)
        if u:
            results.append({
                "id": u.id,
                "membership_id": m.id,
                "full_name": u.full_name,
                "email": u.email,
                "username": u.username,
                "role": m.role,
                "is_owner": (m.role == "owner" or u.id == workspace.owner_id or u.role == "system_owner"),
            })
    return {"items": results, "workspace_kind": workspace.kind}


@router.put("/workspaces/{workspace_id}/members/{user_id}/role")
def update_workspace_member_role(
    workspace_id: int,
    user_id: int,
    body: UpdateMemberRoleInput,
    user: User = Depends(current_user),
    db: DBSession = Depends(get_db),
):
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    caller_member = db.query(Membership).filter_by(workspace_id=workspace_id, user_id=user.id).first()
    is_sys_admin = user.role in ("system_owner", "system_admin")
    if not is_sys_admin and (not caller_member or caller_member.role not in ("owner", "organization_admin")):
        raise HTTPException(403, "Workspace administrator access required")

    target_user = db.get(User, user_id)
    if not target_user:
        raise HTTPException(404, "User not found")
    target_membership = db.query(Membership).filter_by(workspace_id=workspace_id, user_id=user_id).first()
    if not target_membership:
        raise HTTPException(404, "User is not a member of this workspace")

    if target_user.id == user.id:
        raise HTTPException(400, "You cannot alter your own workspace role")
    if target_membership.role == "owner" or target_user.id == workspace.owner_id or target_user.role == "system_owner":
        raise HTTPException(403, "The workspace owner role cannot be altered")

    if workspace.kind == "personal" and body.role == "organization_admin":
        raise HTTPException(400, "Organization admin role is only available for organization workspaces")

    old_role = target_membership.role
    target_membership.role = body.role
    db.add(AuditEvent(actor_user_id=user.id, action="workspace.member_role_changed", target=f"{workspace_id}:{target_user.email}:{body.role}"))
    db.commit()
    return {
        "user_id": target_user.id,
        "workspace_id": workspace_id,
        "email": target_user.email,
        "role": target_membership.role,
        "old_role": old_role,
    }


@router.delete("/workspaces/{workspace_id}/members/{user_id}")
def remove_workspace_member(
    workspace_id: int,
    user_id: int,
    user: User = Depends(current_user),
    db: DBSession = Depends(get_db),
):
    workspace = db.get(Workspace, workspace_id)
    if not workspace:
        raise HTTPException(404, "Workspace not found")
    caller_member = db.query(Membership).filter_by(workspace_id=workspace_id, user_id=user.id).first()
    is_sys_admin = user.role in ("system_owner", "system_admin")
    if not is_sys_admin and (not caller_member or caller_member.role not in ("owner", "organization_admin")):
        raise HTTPException(403, "Workspace administrator access required")

    target_user = db.get(User, user_id)
    if not target_user:
        raise HTTPException(404, "User not found")
    target_membership = db.query(Membership).filter_by(workspace_id=workspace_id, user_id=user_id).first()
    if not target_membership:
        raise HTTPException(404, "User is not a member of this workspace")

    if target_user.id == user.id:
        raise HTTPException(400, "You cannot remove yourself from the workspace")
    if target_membership.role == "owner" or target_user.id == workspace.owner_id or target_user.role == "system_owner":
        raise HTTPException(403, "The workspace owner cannot be removed")

    db.delete(target_membership)
    db.add(AuditEvent(actor_user_id=user.id, action="workspace.member_removed", target=f"{workspace_id}:{target_user.email}"))
    db.commit()
    return {"removed": True, "user_id": user_id, "workspace_id": workspace_id}

