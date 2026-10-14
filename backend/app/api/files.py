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
import shutil
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session as DBSession
from app.api.deps import current_user, personal_workspace
from app.core.config import settings
from app.core.database import get_db
from app.models.entities import FileRecord, Membership, User, Workspace
from app.services.storage import get_active_storage_root

router = APIRouter(prefix="/files", tags=["files"])


def safe_target_in(base: Path, relative: str) -> Path:
    if "\\" in relative or "\x00" in relative:
        raise HTTPException(400, "Invalid path")
    pure = PurePosixPath(relative or ".")
    if pure.is_absolute() or any(part in ("..", "") for part in pure.parts):
        raise HTTPException(400, "Invalid path")
    target = (base / Path(*pure.parts)).resolve()
    if not target.is_relative_to(base):
        raise HTTPException(400, "Path escapes the configured storage root")
    return target


def safe_target(relative: str) -> Path:
    return safe_target_in(Path(settings.storage_root).resolve(), relative)


def workspace_root(db: DBSession, user: User, workspace_id: int | None = None) -> tuple[int, Path, str]:
    if workspace_id is not None:
        workspace = db.get(Workspace, workspace_id)
        if not workspace:
            raise HTTPException(404, "Workspace not found")
    else:
        # Default to owned personal workspace if available
        workspace = db.query(Workspace).filter_by(owner_id=user.id, kind="personal").first()
        if not workspace:
            # Fallback to first accessible workspace via membership
            first_mem = db.query(Membership).filter_by(user_id=user.id).first()
            if first_mem:
                workspace = db.get(Workspace, first_mem.workspace_id)
        if not workspace:
            raise HTTPException(404, "Workspace not found")

    membership = db.query(Membership).filter_by(workspace_id=workspace.id, user_id=user.id).first()
    is_owner = (workspace.owner_id == user.id)

    if not is_owner and not membership:
        if workspace.kind == "personal":
            raise HTTPException(403, "Personal workspace access required")
        raise HTTPException(403, "Workspace access required")

    role = membership.role if membership else ("owner" if workspace.kind == "personal" else "organization_admin")

    if workspace.kind == "personal":
        sub_rel = f"users/{workspace.owner_id}"
    else:
        sub_rel = f"workspaces/{workspace.id}"

    active_base, _ = get_active_storage_root(db)
    default_base = Path(settings.storage_root).resolve()
    root = safe_target_in(active_base, sub_rel)
    root.mkdir(parents=True, exist_ok=True)

    legacy_root = default_base / sub_rel
    if active_base != default_base and legacy_root.exists() and not any(root.iterdir()):
        try:
            for item in legacy_root.iterdir():
                dest = root / item.name
                if not dest.exists():
                    if item.is_dir():
                        shutil.copytree(item, dest)
                    else:
                        shutil.copy2(item, dest)
        except Exception:
            pass

    return workspace.id, root, role


def scoped_path(db: DBSession, user: User, relative: str, workspace_id: int | None = None) -> tuple[int, Path, str, Path]:
    workspace_id, root, role = workspace_root(db, user, workspace_id)
    if not relative or relative == ".":
        return workspace_id, root, role, root
    target = safe_target_in(root, relative)
    return workspace_id, target, role, root


def require_write(role: str):
    if role not in ("owner", "organization_admin", "member"):
        raise HTTPException(403, "This workspace is read-only for your account")



class PathInput(BaseModel):
    path: str = Field(max_length=1024)
    workspace_id: int | None = None


class RenameInput(BaseModel):
    path: str = Field(max_length=1024)
    new_name: str = Field(min_length=1, max_length=255)
    workspace_id: int | None = None


@router.get("")
def list_files(path: str = Query(default="", max_length=1024), workspace_id: int | None = Query(default=None), user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    wid, target, _role, root = scoped_path(db, user, path, workspace_id)
    if not target.exists():
        target.mkdir(parents=True, exist_ok=True)
    if not target.is_dir():
        raise HTTPException(400, "Path is not a folder")
    rows = []
    for item in sorted(target.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
        if item.is_symlink():
            continue
        stat = item.stat()
        rel = item.relative_to(root).as_posix()
        rows.append({"name": item.name, "path": rel, "kind": "folder" if item.is_dir() else "file", "size": 0 if item.is_dir() else stat.st_size, "modified_at": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()})
    return {"path": path, "workspace_id": wid, "items": rows, "total": len(rows)}


@router.post("/folders", status_code=201)
def create_folder(body: RenameInput, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    if body.new_name in (".", "..") or "/" in body.new_name or "\\" in body.new_name:
        raise HTTPException(400, "Folder name is invalid")
    wid, parent, role, root = scoped_path(db, user, body.path, body.workspace_id)
    require_write(role)
    if not parent.is_dir():
        raise HTTPException(404, "Parent folder not found")
    folder = parent / body.new_name
    if folder.exists():
        raise HTTPException(409, "An item with that name already exists")
    folder.mkdir()
    db.add(FileRecord(workspace_id=wid, relative_path=folder.relative_to(root).as_posix(), kind="folder"))
    db.commit()
    return {"name": folder.name, "path": folder.relative_to(root).as_posix(), "kind": "folder"}


@router.post("/upload", status_code=201)
async def upload(path: str = "", workspace_id: int | None = None, files: list[UploadFile] = File(...), user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    wid, folder, role, root = scoped_path(db, user, path, workspace_id)
    require_write(role)
    if not folder.is_dir():
        raise HTTPException(404, "Upload folder not found")
    results = []
    for upload_file in files:
        name = Path(upload_file.filename or "").name
        if not name or name in (".", ".."):
            raise HTTPException(400, "Invalid filename")
        destination = folder / name
        if destination.exists():
            raise HTTPException(409, f"{name} already exists")
        size = 0
        try:
            with destination.open("xb") as output:
                while chunk := await upload_file.read(1024 * 1024):
                    size += len(chunk)
                    if size > settings.max_upload_bytes:
                        raise HTTPException(413, "Upload exceeds configured size limit")
                    output.write(chunk)
        except Exception:
            destination.unlink(missing_ok=True)
            raise
        rel = destination.relative_to(root).as_posix()
        db.merge(FileRecord(workspace_id=wid, relative_path=rel, kind="file", size_bytes=size))
        results.append({"name": name, "size": size})
    db.commit()
    return {"uploaded": results}


@router.get("/download")
def download(path: str, workspace_id: int | None = None, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    _, target, _role, _root = scoped_path(db, user, path, workspace_id)
    if not target.is_file():
        raise HTTPException(404, "File not found")
    return FileResponse(target, filename=target.name, content_disposition_type="attachment")


@router.put("/rename")
def rename(body: RenameInput, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    if body.new_name in (".", "..") or "/" in body.new_name or "\\" in body.new_name:
        raise HTTPException(400, "Name is invalid")
    _, source, role, _root = scoped_path(db, user, body.path, body.workspace_id)
    require_write(role)
    if not source.exists():
        raise HTTPException(404, "Item not found")
    destination = source.with_name(body.new_name)
    if destination.exists():
        raise HTTPException(409, "An item with that name already exists")
    source.rename(destination)
    return {"name": destination.name}


@router.post("/move")
def move(body: PathInput, destination: str = Query(...), user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    _, source, role, _root = scoped_path(db, user, body.path, body.workspace_id)
    _, target_dir, target_role, _root2 = scoped_path(db, user, destination, body.workspace_id)
    require_write(role)
    require_write(target_role)
    if not source.exists() or not target_dir.is_dir():
        raise HTTPException(404, "Source or destination not found")
    target = target_dir / source.name
    if target.exists():
        raise HTTPException(409, "An item with that name already exists")
    if source.is_dir() and target_dir.is_relative_to(source):
        raise HTTPException(400, "Cannot move a folder into itself")
    shutil.move(str(source), str(target))
    return {"moved": target.name}


@router.delete("")
def delete_file(path: str, workspace_id: int | None = None, user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    _, target, role, _root = scoped_path(db, user, path, workspace_id)
    require_write(role)
    if not target.exists():
        raise HTTPException(404, "Item not found")
    if target.is_dir():
        shutil.rmtree(target)
    else:
        target.unlink()
    return {"deleted": True}


@router.get("/search")
def search(q: str = Query(min_length=1, max_length=200), workspace_id: int | None = Query(default=None), user: User = Depends(current_user), db: DBSession = Depends(get_db)):
    _, root, _role = workspace_root(db, user, workspace_id)
    matches = []
    for base, dirs, files in os.walk(root, followlinks=False):
        dirs[:] = [d for d in dirs if not (Path(base) / d).is_symlink()]
        for name in dirs + files:
            if q.casefold() in name.casefold():
                item = Path(base) / name
                if not item.is_symlink():
                    matches.append({"name": name, "path": item.relative_to(root).as_posix(), "kind": "folder" if item.is_dir() else "file"})
                    if len(matches) >= 500:
                        return {"items": matches, "truncated": True}
    return {"items": matches, "truncated": False}
