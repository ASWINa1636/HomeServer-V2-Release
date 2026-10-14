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
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, text
from sqlalchemy.orm import Session as DBSession
from app.api.deps import current_user
from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password, verify_password, make_otp, protected_digest, random_token
from app.models.entities import AuditEvent, Challenge, Invitation, Membership, ServerConfig, Session, User, Workspace, now_utc
from app.services.email import send_otp

router = APIRouter(prefix="/auth", tags=["authentication"])


def _bootstrap_available(db: DBSession) -> bool:
    return db.query(User).filter(User.role.in_(("system_owner", "system_admin"))).count() == 0


class Registration(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    username: str = Field(min_length=3, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=128)
    invitation_token: str | None = Field(default=None, max_length=256)


class LoginInput(BaseModel):
    identifier: str
    password: str


class CodeInput(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


class EmailInput(BaseModel):
    email: EmailStr


class ResetInput(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")
    new_password: str = Field(min_length=12, max_length=128)


class PolicyInput(BaseModel):
    policy: str = Field(pattern="^(open|invitation_only)$")


def _challenge(db: DBSession, user: User, purpose: str) -> str:
    now = now_utc()
    previous = db.query(Challenge).filter_by(user_id=user.id, purpose=purpose, consumed_at=None).order_by(Challenge.created_at.desc()).first()
    if previous:
        prev_created = previous.created_at.replace(tzinfo=timezone.utc) if previous.created_at.tzinfo is None else previous.created_at
        if (now - prev_created).total_seconds() < settings.otp_resend_seconds:
            raise HTTPException(429, "Please wait before requesting another code")
    db.query(Challenge).filter_by(user_id=user.id, purpose=purpose, consumed_at=None).update({"consumed_at": now})
    code = make_otp()
    db.add(Challenge(user_id=user.id, purpose=purpose, digest=protected_digest(code), expires_at=now + timedelta(minutes=settings.otp_minutes)))
    db.flush()
    return code


def _deliver(db: DBSession, user: User, purpose: str, label: str):
    code = _challenge(db, user, purpose)
    try:
        send_otp(user.email, code, label)
    except Exception as exc:
        db.rollback()
        # Do not reveal provider credentials, recipient details, or OTPs to clients.
        raise HTTPException(503, "Email delivery is unavailable. Check email delivery configuration and try again later.") from exc
    db.commit()


@router.get("/registration-policy")
def get_registration_policy(db: DBSession = Depends(get_db)):
    policy_row = db.get(ServerConfig, "registration_policy")
    policy = policy_row.value if policy_row else settings.registration_policy
    return {"policy": policy}


@router.put("/registration-policy")
def set_registration_policy(body: PolicyInput, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    if user.role not in ("system_owner", "system_admin"):
        raise HTTPException(403, "Administrator access required")
    row = db.get(ServerConfig, "registration_policy")
    if not row:
        row = ServerConfig(key="registration_policy", value=body.policy)
        db.add(row)
    else:
        row.value = body.policy
    db.add(AuditEvent(actor_user_id=user.id, action="server.registration_policy_updated", target=body.policy))
    db.commit()
    return {"policy": body.policy}


@router.post("/register", status_code=202)
def register(body: Registration, db: DBSession = Depends(get_db)):
    if _bootstrap_available(db):
        raise HTTPException(409, "Create and verify the initial server owner before user registration")
    policy_row = db.get(ServerConfig, "registration_policy")
    policy = policy_row.value if policy_row else settings.registration_policy
    invitation = None
    if body.invitation_token:
        invitation = db.query(Invitation).filter_by(token_hash=protected_digest(body.invitation_token), revoked_at=None).first()
        expiry = invitation.expires_at.replace(tzinfo=timezone.utc) if invitation and invitation.expires_at.tzinfo is None else (invitation.expires_at if invitation else None)
        if not invitation or expiry <= now_utc() or invitation.email != str(body.email).strip().lower():
            raise HTTPException(400, "Invitation is invalid, expired, or addressed to another email")
    if policy != "open" and not invitation:
        raise HTTPException(403, "Registration is invitation only. A valid invitation link is required.")
    email, username = str(body.email).strip().lower(), body.username.strip().lower()
    if db.query(User).filter(func.lower(User.email) == email).first() or db.query(User).filter(func.lower(User.username) == username).first():
        raise HTTPException(409, "Email address or username is already registered")
    user = User(full_name=body.full_name.strip(), email=email, username=username, password_hash=hash_password(body.password), role="member")
    db.add(user)
    try:
        db.flush()
        if invitation:
            invitation.pending_user_id = user.id
        _deliver(db, user, "verify", "Verify your email")
    except HTTPException:
        raise
    except Exception:
        db.rollback()
        raise HTTPException(409, "Email address or username is already registered")
    return {"message": "Check your email for a verification code", "email": email}


@router.post("/bootstrap", status_code=202)
def bootstrap(body: Registration, db: DBSession = Depends(get_db)):
    # Serialize first-run claims in PostgreSQL. The unique role check runs inside that lock.
    if db.bind.dialect.name == "postgresql":
        db.execute(text("SELECT pg_advisory_xact_lock(781293004)"))
    if not _bootstrap_available(db):
        raise HTTPException(409, "Initial administrator setup is already closed")
    email, username = str(body.email).strip().lower(), body.username.strip().lower()
    user = User(full_name=body.full_name.strip(), email=email, username=username, password_hash=hash_password(body.password), role="system_owner")
    db.add(user)
    try:
        db.flush()
        _deliver(db, user, "verify", "Verify your administrator email")
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(409, "Initial administrator could not be created") from exc
    return {"message": "Check your email for a verification code", "email": email}


@router.get("/bootstrap-status")
def bootstrap_status(db: DBSession = Depends(get_db)):
    return {"available": _bootstrap_available(db)}


def _verify_code(db: DBSession, user: User, purpose: str, code: str) -> Challenge:
    challenge = db.query(Challenge).filter_by(user_id=user.id, purpose=purpose, consumed_at=None).order_by(Challenge.created_at.desc()).first()
    if not challenge:
        raise HTTPException(400, "Code is invalid or expired")
    expires_at = challenge.expires_at.replace(tzinfo=timezone.utc) if challenge and challenge.expires_at.tzinfo is None else challenge.expires_at
    if expires_at <= now_utc():
        raise HTTPException(400, "Code is invalid or expired")
    if challenge.attempts >= settings.otp_max_attempts:
        raise HTTPException(429, "Too many failed attempts. Please request a new code.")
    if not secrets.compare_digest(challenge.digest, protected_digest(code)):
        challenge.attempts += 1
        db.commit()
        remaining = max(0, settings.otp_max_attempts - challenge.attempts)
        if remaining == 0:
            raise HTTPException(429, "Too many failed attempts. Please request a new code.")
        raise HTTPException(400, "Code is invalid or expired")
    challenge.consumed_at = now_utc()
    return challenge


@router.post("/verify", status_code=200)
def verify_email(body: CodeInput, db: DBSession = Depends(get_db)):
    email_clean = str(body.email).strip().lower()
    user = db.query(User).filter(func.lower(User.email) == email_clean).first()
    if not user or user.is_verified:
        raise HTTPException(400, "Code is invalid or expired")
    _verify_code(db, user, "verify", body.code)
    user.is_verified = True

    # Process pending invitations
    invitations = db.query(Invitation).filter(
        (Invitation.pending_user_id == user.id) | (func.lower(Invitation.email) == email_clean),
        Invitation.revoked_at.is_(None),
    ).all()
    for invitation in invitations:
        invitation_expiry = invitation.expires_at.replace(tzinfo=timezone.utc) if invitation.expires_at.tzinfo is None else invitation.expires_at
        if invitation_expiry > now_utc():
            if not db.query(Membership).filter_by(workspace_id=invitation.workspace_id, user_id=user.id).first():
                db.add(Membership(workspace_id=invitation.workspace_id, user_id=user.id, role=invitation.role))
            invitation.revoked_at = now_utc()

    # If user has no workspace membership yet (e.g. open registration or system owner), give them a personal workspace
    has_membership = db.query(Membership).filter_by(user_id=user.id).first() is not None
    if not has_membership or user.role == "system_owner":
        user_ws = db.query(Workspace).filter_by(owner_id=user.id, kind="personal").first()
        if not user_ws:
            workspace = Workspace(name=f"{user.full_name}'s workspace", kind="personal", owner_id=user.id)
            db.add(workspace)
            db.flush()
            db.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))

    db.commit()
    return {"message": "Email verified. You can now sign in.", "email": user.email}


@router.post("/resend", status_code=202)
def resend(body: EmailInput, db: DBSession = Depends(get_db)):
    user = db.query(User).filter_by(email=str(body.email).lower()).first()
    if user and not user.is_verified:
        _deliver(db, user, "verify", "Verify your email")
    return {"message": "If verification is pending, a code has been sent"}


def _set_session(response: Response, db: DBSession, user: User):
    raw, csrf = random_token(), random_token()
    record = Session(user_id=user.id, token_hash=protected_digest(raw), csrf_hash=protected_digest(csrf), expires_at=now_utc() + timedelta(days=settings.session_days))
    db.add(record)
    db.commit()
    options = dict(httponly=True, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=settings.session_days * 86400, path="/")
    response.set_cookie("hs_v2_session", raw, **options)
    response.set_cookie("hs_v2_csrf", csrf, httponly=False, secure=settings.cookie_secure, samesite=settings.cookie_samesite, max_age=settings.session_days * 86400, path="/")


@router.post("/login")
def login(body: LoginInput, response: Response, db: DBSession = Depends(get_db)):
    identifier = body.identifier.strip().lower()
    user = db.query(User).filter((func.lower(User.email) == identifier) | (func.lower(User.username) == identifier)).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(401, "Invalid username/email or password")
    if not user.is_verified:
        raise HTTPException(403, "Verify your email before signing in")
    if not user.is_active:
        raise HTTPException(403, "Your account has been deactivated. Please contact the administrator.")
    _set_session(response, db, user)
    return {"id": user.id, "name": user.full_name, "email": user.email, "username": user.username, "role": user.role}


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    token = request.cookies.get("hs_v2_session", "")
    record = db.query(Session).filter_by(token_hash=protected_digest(token), user_id=user.id).first()
    if record:
        record.revoked_at = now_utc()
        db.commit()
    response.delete_cookie("hs_v2_session", path="/")
    response.delete_cookie("hs_v2_csrf", path="/")


@router.get("/me")
def me(user: User = Depends(current_user)):
    return {"id": user.id, "name": user.full_name, "email": user.email, "username": user.username, "role": user.role}


@router.post("/password-reset", status_code=202)
def password_reset_request(body: EmailInput, db: DBSession = Depends(get_db)):
    user = db.query(User).filter_by(email=str(body.email).lower(), is_verified=True, is_active=True).first()
    if user:
        _deliver(db, user, "reset", "Reset your password")
    return {"message": "If the account exists, a reset code has been sent"}


@router.post("/password-reset/confirm")
def password_reset_confirm(body: ResetInput, db: DBSession = Depends(get_db)):
    user = db.query(User).filter_by(email=str(body.email).lower(), is_verified=True).first()
    if not user:
        raise HTTPException(400, "Code is invalid or expired")
    _verify_code(db, user, "reset", body.code)
    user.password_hash = hash_password(body.new_password)
    db.query(Session).filter_by(user_id=user.id, revoked_at=None).update({"revoked_at": now_utc()})
    db.commit()
    return {"message": "Password updated. Sign in with your new password."}


class ChangePassword(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)


@router.post("/password")
def change_password(body: ChangePassword, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    if not verify_password(body.current_password, user.password_hash):
        raise HTTPException(400, "Current password is incorrect")
    user.password_hash = hash_password(body.new_password)
    db.query(Session).filter(Session.user_id == user.id, Session.revoked_at.is_(None)).update({"revoked_at": now_utc()})
    db.commit()
    return {"message": "Password updated. Please sign in again."}
