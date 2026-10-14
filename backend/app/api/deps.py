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

from datetime import datetime, timezone
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session as DBSession
from app.core.database import get_db
from app.core.security import protected_digest
from app.models.entities import Session, User, Membership, Workspace


def current_user(request: Request, db: DBSession = Depends(get_db)) -> User:
    token = request.cookies.get("hs_v2_session")
    if not token:
        raise HTTPException(401, "Sign in required")
    record = db.query(Session).filter_by(token_hash=protected_digest(token), revoked_at=None).first()
    expires_at = record.expires_at.replace(tzinfo=timezone.utc) if record and record.expires_at.tzinfo is None else (record.expires_at if record else None)
    if not record or expires_at <= datetime.now(timezone.utc):
        raise HTTPException(401, "Session expired")
    user = db.get(User, record.user_id)
    if not user or not user.is_active or not user.is_verified:
        raise HTTPException(401, "Sign in required")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("x-csrf-token", "")
        if not csrf or protected_digest(csrf) != record.csrf_hash:
            raise HTTPException(403, "CSRF token missing or invalid")
    return user


def system_admin(user: User = Depends(current_user)) -> User:
    if user.role not in ("system_owner", "system_admin"):
        raise HTTPException(403, "Administrator access required")
    return user


def personal_workspace(db: DBSession, user: User) -> Workspace:
    workspace = db.query(Workspace).filter_by(owner_id=user.id, kind="personal").first()
    if not workspace:
        workspace = Workspace(name=f"{user.full_name}'s files", kind="personal", owner_id=user.id)
        db.add(workspace)
        db.flush()
        db.add(Membership(workspace_id=workspace.id, user_id=user.id, role="owner"))
        db.flush()
    return workspace
