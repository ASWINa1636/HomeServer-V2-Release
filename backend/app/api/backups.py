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
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.api.deps import current_user, system_admin
from app.core.database import get_db
from app.models.entities import User
from app.services.backups import (
    create_backup,
    delete_backup,
    get_backups_dir,
    get_restore_runbook,
    list_backups,
    verify_backup,
)

router = APIRouter(prefix="/backups", tags=["backups"])


@router.get("")
def get_all_backups(
    user: User = Depends(system_admin),
):
    return {"items": list_backups()}


@router.post("/create")
def trigger_backup(
    user: User = Depends(system_admin),
    db: Session = Depends(get_db),
):
    return create_backup(db=db, user_id=user.id)


@router.post("/{backup_id}/verify")
def verify_backup_integrity(
    backup_id: str,
    user: User = Depends(system_admin),
):
    res = verify_backup(backup_id)
    if not res.get("valid"):
        raise HTTPException(400, res.get("error", "Backup verification failed"))
    return res


@router.delete("/{backup_id}")
def remove_backup(
    backup_id: str,
    user: User = Depends(system_admin),
    db: Session = Depends(get_db),
):
    ok = delete_backup(backup_id, user_id=user.id, db=db)
    if not ok:
        raise HTTPException(404, "Backup not found")
    return {"message": "Backup deleted successfully", "backup_id": backup_id}


@router.get("/runbook")
def get_runbook(
    user: User = Depends(current_user),
):
    return {"runbook": get_restore_runbook()}


@router.get("/{backup_id}/download")
def download_backup_archive(
    backup_id: str,
    user: User = Depends(system_admin),
):
    b_dir = get_backups_dir()
    filepath = os.path.join(b_dir, f"{backup_id}.tar.gz")
    if not os.path.isfile(filepath):
        raise HTTPException(404, "Backup archive not found")
    return FileResponse(
        filepath,
        filename=f"{backup_id}.tar.gz",
        media_type="application/gzip",
    )
