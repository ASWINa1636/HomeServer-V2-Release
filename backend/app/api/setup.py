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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession
from app.api.deps import current_user, system_admin
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import ServerConfig, User

router = APIRouter(prefix="/setup", tags=["setup"])


class SetupInput(BaseModel):
    server_name: str = Field(min_length=2, max_length=100)
    workspace_kind: str = "personal"
    registration_policy: str = "open"


@router.get("/status")
def setup_status(user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    if user.role not in ("system_owner", "system_admin"):
        raise HTTPException(403, "Administrator access required")
    done = db.get(ServerConfig, "initialized")
    return {"initialized": bool(done and done.value == "true"), "server_name": (db.get(ServerConfig, "server_name") or ServerConfig(key="server_name", value="HomeServer V2")).value}


@router.put("/")
def save_setup(body: SetupInput, user: User = Depends(system_admin), db: DBSession = Depends(get_db)):
    if body.workspace_kind not in ("personal", "organization"):
        raise HTTPException(422, "Workspace type must be personal or organization")
    if body.registration_policy not in ("open", "invitation_only"):
        raise HTTPException(422, "Registration policy is invalid")
    for key, value in {"server_name": body.server_name.strip(), "workspace_kind": body.workspace_kind, "registration_policy": body.registration_policy, "initialized": "true"}.items():
        row = db.get(ServerConfig, key)
        if row:
            row.value = value
        else:
            db.add(ServerConfig(key=key, value=value))
    db.commit()
    return {"initialized": True, "server_name": body.server_name.strip(), "registration_policy": body.registration_policy}


@router.get("/network")
def network_status(user: User = Depends(current_user)):
    return {"configured_url": None, "tailscale": {"configured": False, "connected": False, "address": None}, "guidance": "The address you used to open this page is reachable. Use the server host's verified LAN address with port 8081 for other local devices."}
