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
import tempfile
from pathlib import Path
from app.api import auth
from app.models.entities import StorageLocation
from app.services.storage import measure_storage, measure_storage_location


def setup_owner(client, monkeypatch):
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    res = client.get("/api/v1/auth/bootstrap-status").json()
    if res.get("available"):
        owner = {
            "full_name": "Admin Storage",
            "email": "admin_storage@example.com",
            "username": "storageadmin",
            "password": "strong-password-1234",
        }
        client.post("/api/v1/auth/bootstrap", json=owner)
        client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]})
        client.post("/api/v1/auth/login", json={"identifier": "storageadmin", "password": owner["password"]})
    else:
        login_res = client.post("/api/v1/auth/login", json={"identifier": "storageadmin", "password": "strong-password-1234"})
        if login_res.status_code != 200:
            user = {
                "full_name": "Storage Admin",
                "email": "storageadmin@example.com",
                "username": "storageadmin",
                "password": "strong-password-1234",
            }
            client.post("/api/v1/auth/register", json=user)
            client.post("/api/v1/auth/verify", json={"email": user["email"], "code": codes[-1]})
            client.post("/api/v1/auth/login", json={"identifier": "storageadmin", "password": user["password"]})


def test_storage_status_returns_real_metrics(client, monkeypatch):
    setup_owner(client, monkeypatch)
    res = client.get("/api/v1/storage/status")
    assert res.status_code == 200
    data = res.json()
    assert "current_location" in data
    assert "health" in data
    assert "total_bytes" in data
    assert "used_bytes" in data
    assert "free_bytes" in data
    assert data["readable"] is True
    assert data["writable"] is True


def test_storage_locations_and_test_button(client, monkeypatch):
    setup_owner(client, monkeypatch)
    res = client.get("/api/v1/storage/locations")
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert len(data["items"]) >= 1
    assert "authorized_roots" in data

    test_res = client.post("/api/v1/storage/test", json={"root_key": "default"})
    assert test_res.status_code == 200
    test_data = test_res.json()
    assert test_data["healthy"] is True
    assert test_data["status"] in ("available", "low_space")
    assert len(test_data["checks"]) >= 4


def test_storage_browse_and_mkdir_with_boundary_enforcement(client, monkeypatch):
    setup_owner(client, monkeypatch)
    browse_res = client.get("/api/v1/storage/browse", params={"root_key": "default", "path": ""})
    assert browse_res.status_code == 200
    browse_data = browse_res.json()
    assert browse_data["root_key"] == "default"
    assert "folders" in browse_data

    # Attempt path traversal outside root
    escape_res = client.get("/api/v1/storage/browse", params={"root_key": "default", "path": "../outside"})
    assert escape_res.status_code == 400

    # Create a new directory within storage
    mkdir_res = client.post("/api/v1/storage/mkdir", json={"root_key": "default", "path": "", "name": "test_folder_xyz"})
    assert mkdir_res.status_code == 201

    browse_res2 = client.get("/api/v1/storage/browse", params={"root_key": "default", "path": ""})
    assert any(f["name"] == "test_folder_xyz" for f in browse_res2.json()["folders"])


def test_add_and_set_default_storage_location(client, monkeypatch):
    setup_owner(client, monkeypatch)
    mk = client.post("/api/v1/storage/mkdir", json={"root_key": "default", "path": "", "name": "test_folder_sub"})
    assert mk.status_code == 201

    add_res = client.post(
        "/api/v1/storage/locations",
        json={
            "name": "Custom Subfolder Storage",
            "root_key": "default",
            "relative_path": "test_folder_sub",
            "is_default": False,
        },
    )

    assert add_res.status_code == 201
    loc_id = add_res.json()["id"]

    def_res = client.put(f"/api/v1/storage/locations/{loc_id}/default")
    assert def_res.status_code == 200
    assert def_res.json()["is_default"] is True

    status_res = client.get("/api/v1/storage/status")
    assert status_res.status_code == 200
    assert status_res.json()["current_location"]["name"] == "Custom Subfolder Storage"


def test_host_vs_container_path_handling_unmounted(client, monkeypatch):
    """
    Requirement 1 & 3:
    Host directory paths are never validated as though they were automatically accessible inside the container.
    Unavailable mounts are accurately marked unmounted.
    """
    setup_owner(client, monkeypatch)

    # Register a host path without auto-mounting (e.g. host helper offline or manual)
    add_res = client.post(
        "/api/v1/storage/locations",
        json={
            "name": "Host Data Server Test",
            "type": "host_path",
            "host_path": "/home/aswin/data-server",
            "auto_mount": False,
        },
    )
    assert add_res.status_code == 201
    loc_data = add_res.json()
    loc_id = loc_data["id"]

    assert loc_data["host_path"] == "/home/aswin/data-server"
    assert loc_data["target_path"] == "/srv/homeserver/host-data-server-test"
    assert loc_data["mount_status"] == "unmounted"
    assert loc_data["is_default"] is False

    # Check locations list accurately reflects unmounted status
    locs_res = client.get("/api/v1/storage/locations")
    assert locs_res.status_code == 200
    items = [it for it in locs_res.json()["items"] if it["id"] == loc_id]
    assert len(items) == 1
    unmounted_loc = items[0]
    assert unmounted_loc["mount_status"] == "unmounted"
    assert unmounted_loc["status"] == "unmounted"
    assert unmounted_loc["writable"] is False
    assert unmounted_loc["readable"] is False
    assert "not mounted into container" in (unmounted_loc.get("error") or "")

    # Attempting to set unmounted location as default must be rejected
    def_res = client.put(f"/api/v1/storage/locations/{loc_id}/default")
    assert def_res.status_code == 400
    assert "Cannot set as default" in def_res.json()["detail"]

    # Clean up
    del_res = client.delete(f"/api/v1/storage/locations/{loc_id}")
    assert del_res.status_code == 200


def test_read_only_storage_handling(client, monkeypatch, tmp_path):
    """
    Requirement 10: Read-only storage detection and restrictions.
    """
    ro_dir = tmp_path / "ro_storage"
    ro_dir.mkdir(parents=True)
    (ro_dir / "sample.txt").write_text("read only content")

    # Set read-only permissions
    os.chmod(ro_dir, 0o555)
    try:
        metrics = measure_storage(ro_dir)
        assert metrics["exists"] is True
        assert metrics["readable"] is True
        assert metrics["writable"] is False
        assert metrics["status"] == "read_only"
    finally:
        os.chmod(ro_dir, 0o777)


def test_file_upload_and_persistence_to_selected_storage(client, monkeypatch, tmp_path):
    """
    Requirement 8: Ensure all file uploads and downloads use the selected storage location.
    Verify actual persistence on disk.
    """
    setup_owner(client, monkeypatch)

    # Create a test storage mount directory
    custom_mount = tmp_path / "persistent_vault"
    custom_mount.mkdir(parents=True, exist_ok=True)

    add_res = client.post(
        "/api/v1/storage/locations",
        json={
            "name": "Persistent Vault",
            "type": "mounted_dir",
            "root_key": "custom",
            "target_path": str(custom_mount),
            "is_default": True,
        },
    )
    assert add_res.status_code == 201
    loc_id = add_res.json()["id"]

    # Verify status now reports Persistent Vault as default
    status_res = client.get("/api/v1/storage/status")
    assert status_res.status_code == 200
    assert status_res.json()["current_location"]["name"] == "Persistent Vault"

    # Upload a file via /api/v1/files/upload
    file_content = b"HomeServer V2 Storage Persistence Verification Payload 2026"
    upload_res = client.post(
        "/api/v1/files/upload",
        files={"files": ("verified_payload.txt", file_content, "text/plain")},
    )
    assert upload_res.status_code == 201

    # Verify physical persistence in custom_mount directory on disk
    found_files = list(custom_mount.rglob("verified_payload.txt"))
    assert len(found_files) == 1
    persisted_path = found_files[0]
    assert persisted_path.read_bytes() == file_content

    # Download file back via API
    dl_res = client.get("/api/v1/files/download", params={"path": "verified_payload.txt"})
    assert dl_res.status_code == 200
    assert dl_res.content == file_content
