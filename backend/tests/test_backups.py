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

from app.api import auth


def setup_owner(client, monkeypatch, codes=None):
    if codes is None:
        codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    res = client.get("/api/v1/auth/bootstrap-status").json()
    if res.get("available"):
        owner = {
            "full_name": "Backup Admin",
            "email": "backupadmin@example.com",
            "username": "backupadmin",
            "password": "strong-password-1234",
        }
        client.post("/api/v1/auth/bootstrap", json=owner)
        client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]})
        client.post("/api/v1/auth/login", json={"identifier": "backupadmin", "password": owner["password"]})


def setup_member(client, monkeypatch, codes=None):
    if codes is None:
        codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    member = {
        "full_name": "Backup Member",
        "email": "backupmember@example.com",
        "username": "backupmember",
        "password": "strong-password-1234",
    }
    client.post("/api/v1/auth/register", json=member)
    client.post("/api/v1/auth/verify", json={"email": member["email"], "code": codes[-1]})
    client.post("/api/v1/auth/login", json={"identifier": "backupmember", "password": member["password"]})


def test_backup_create_list_verify_and_delete(client, monkeypatch):
    setup_owner(client, monkeypatch)

    # 1. Trigger backup creation
    create_resp = client.post("/api/v1/backups/create")
    assert create_resp.status_code == 200
    b_data = create_resp.json()
    assert "backup_id" in b_data
    assert "filename" in b_data
    assert b_data["status"] == "verified"
    assert "sha256" in b_data
    assert len(b_data["sha256"]) == 64
    backup_id = b_data["backup_id"]

    # 2. List backups
    list_resp = client.get("/api/v1/backups")
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) >= 1
    found = [i for i in items if i["backup_id"] == backup_id]
    assert len(found) == 1

    # 3. Verify backup integrity
    verify_resp = client.post(f"/api/v1/backups/{backup_id}/verify")
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["valid"] is True
    assert v_data["expected_sha256"] == v_data["calculated_sha256"]

    # 4. Read restore runbook
    runbook_resp = client.get("/api/v1/backups/runbook")
    assert runbook_resp.status_code == 200
    assert "Disaster Recovery & Restore Runbook" in runbook_resp.json()["runbook"]

    # 5. Delete backup
    del_resp = client.delete(f"/api/v1/backups/{backup_id}")
    assert del_resp.status_code == 200
    after_list = client.get("/api/v1/backups").json()["items"]
    assert not any(i["backup_id"] == backup_id for i in after_list)


def test_system_diagnostics_endpoint(client, monkeypatch):
    setup_owner(client, monkeypatch)

    resp = client.get("/api/v1/admin/diagnostics")
    assert resp.status_code == 200
    data = resp.json()
    assert "overall_status" in data
    assert "checks" in data
    assert len(data["checks"]) >= 6

    check_names = [c["name"] for c in data["checks"]]
    assert "Backend Application Health" in check_names
    assert "Database Connectivity" in check_names
    assert "Storage Read & Write" in check_names


def test_ordinary_member_forbidden_from_backups_and_diagnostics(client, monkeypatch):
    codes = []
    setup_owner(client, monkeypatch, codes)
    setup_member(client, monkeypatch, codes)

    assert client.get("/api/v1/backups").status_code == 403
    assert client.post("/api/v1/backups/create").status_code == 403
    assert client.get("/api/v1/admin/diagnostics").status_code == 403
