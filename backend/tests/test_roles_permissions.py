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

import pytest
from app.api import auth, workspaces
from app.models.entities import Membership, User, Workspace


def setup_users(client, monkeypatch):
    """
    Sets up:
    - owner (system_owner)
    - alice (member initially)
    """
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))

    res = client.get("/api/v1/auth/bootstrap-status").json()
    if res.get("available"):
        owner = {"full_name": "Sys Owner", "email": "sysowner@example.com", "username": "sysowner", "password": "sysowner-password-123"}
        client.post("/api/v1/auth/bootstrap", json=owner)
        client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]})
    
    # Log in as owner
    client.post("/api/v1/auth/login", json={"identifier": "sysowner", "password": "sysowner-password-123"})

    # Register alice
    alice = {"full_name": "Alice User", "email": "alice@example.com", "username": "alice", "password": "alice-password-123"}
    client.post("/api/v1/auth/register", json=alice)
    client.post("/api/v1/auth/verify", json={"email": alice["email"], "code": codes[-1]})


def add_member_to_workspace(client, monkeypatch, workspace_id, email, password, username, role):
    sent_tokens = []
    monkeypatch.setattr(workspaces, "send_invitation", lambda _email, token: sent_tokens.append(token))
    res = client.post(f"/api/v1/workspaces/{workspace_id}/invitations", json={"email": email, "role": role})
    assert res.status_code in (200, 201)
    
    # Alice signs in and accepts invitation
    client.post("/api/v1/auth/login", json={"identifier": username, "password": password})
    accept_res = client.post("/api/v1/invitations/accept", json={"token": sent_tokens[-1]})
    assert accept_res.status_code == 200
    client.post("/api/v1/auth/logout")


def test_system_admin_separation_from_workspace_permissions(client, monkeypatch):
    """
    Requirement 2 & 6:
    Promoting a user to system_admin must NOT silently grant workspace write access.
    A user who is read_only in a workspace must remain read_only in that workspace
    even after being granted system_admin.
    """
    setup_users(client, monkeypatch)

    # Owner creates an organization workspace
    client.post("/api/v1/auth/login", json={"identifier": "sysowner", "password": "sysowner-password-123"})
    org = client.post("/api/v1/organizations", json={"name": "Secure Org"}).json()
    org_id = org["id"]

    # Add Alice to Secure Org as read_only
    add_member_to_workspace(client, monkeypatch, org_id, "alice@example.com", "alice-password-123", "alice", "read_only")

    # Owner logs back in
    client.post("/api/v1/auth/login", json={"identifier": "sysowner", "password": "sysowner-password-123"})

    # Get Alice user ID from admin users list
    users = client.get("/api/v1/admin/users").json()["items"]
    alice_data = next(u for u in users if u["email"] == "alice@example.com")
    assert alice_data["role"] == "member"

    # Promote Alice to system_admin via Admin User Directory
    promote_res = client.put(f"/api/v1/admin/users/{alice_data['id']}/role", json={"role": "system_admin"})
    assert promote_res.status_code == 200
    assert promote_res.json()["role"] == "system_admin"

    # Log in as Alice (now a system_admin)
    client.post("/api/v1/auth/login", json={"identifier": "alice", "password": "alice-password-123"})
    me = client.get("/api/v1/auth/me").json()
    assert me["role"] == "system_admin"

    # Alice inspects workspaces: in Secure Org, role is STILL read_only!
    ws_list = client.get("/api/v1/workspaces").json()["items"]
    sec_ws = next(w for w in ws_list if w["id"] == org_id)
    assert sec_ws["role"] == "read_only"

    # Alice can browse and download files in Secure Org
    browse_res = client.get(f"/api/v1/files?workspace_id={org_id}")
    assert browse_res.status_code == 200

    # Alice CANNOT upload files to Secure Org because her workspace role is read_only
    upload_res = client.post(f"/api/v1/files/upload?workspace_id={org_id}", files=[("files", ("test.txt", b"content", "text/plain"))])
    assert upload_res.status_code == 403
    assert "read-only" in upload_res.json()["detail"].lower()

    # Alice CANNOT create folders in Secure Org
    folder_res = client.post("/api/v1/files/folders", json={"path": "", "new_name": "new_folder", "workspace_id": org_id})
    assert folder_res.status_code == 403
    assert "read-only" in folder_res.json()["detail"].lower()


def test_bidirectional_role_transitions_and_workspace_admin(client, monkeypatch):
    """
    Requirement 5 & 10:
    Verify role changes in all directions:
    read_only -> member -> organization_admin -> read_only
    Enforcing permissions on backend.
    """
    setup_users(client, monkeypatch)

    # Owner creates organization workspace
    client.post("/api/v1/auth/login", json={"identifier": "sysowner", "password": "sysowner-password-123"})
    org = client.post("/api/v1/organizations", json={"name": "Lifecycle Org"}).json()
    org_id = org["id"]

    # Add Alice as read_only
    add_member_to_workspace(client, monkeypatch, org_id, "alice@example.com", "alice-password-123", "alice", "read_only")

    # Owner logs back in
    client.post("/api/v1/auth/login", json={"identifier": "sysowner", "password": "sysowner-password-123"})

    # Find Alice ID
    users = client.get("/api/v1/admin/users").json()["items"]
    alice_id = next(u for u in users if u["email"] == "alice@example.com")["id"]

    # 1. read_only -> member
    res = client.put(f"/api/v1/workspaces/{org_id}/members/{alice_id}/role", json={"role": "member"})
    assert res.status_code == 200
    assert res.json()["role"] == "member"

    # Login as Alice: can now upload and create folder
    client.post("/api/v1/auth/login", json={"identifier": "alice", "password": "alice-password-123"})
    up_res = client.post(f"/api/v1/files/upload?workspace_id={org_id}", files=[("files", ("file1.txt", b"hello", "text/plain"))])
    assert up_res.status_code == 201
    fld_res = client.post("/api/v1/files/folders", json={"path": "", "new_name": "folder1", "workspace_id": org_id})
    assert fld_res.status_code == 201

    # Rename & Delete work
    ren_res = client.put("/api/v1/files/rename", json={"path": "file1.txt", "new_name": "file1_renamed.txt", "workspace_id": org_id})
    assert ren_res.status_code == 200
    del_res = client.delete(f"/api/v1/files?path=file1_renamed.txt&workspace_id={org_id}")
    assert del_res.status_code == 200

    # 2. member -> organization_admin
    client.post("/api/v1/auth/login", json={"identifier": "sysowner", "password": "sysowner-password-123"})
    res2 = client.put(f"/api/v1/workspaces/{org_id}/members/{alice_id}/role", json={"role": "organization_admin"})
    assert res2.status_code == 200
    assert res2.json()["role"] == "organization_admin"

    # Login as Alice: has full workspace admin access
    client.post("/api/v1/auth/login", json={"identifier": "alice", "password": "alice-password-123"})
    ws_list = client.get("/api/v1/workspaces").json()["items"]
    assert next(w for w in ws_list if w["id"] == org_id)["role"] == "organization_admin"

    # Can upload
    up_res2 = client.post(f"/api/v1/files/upload?workspace_id={org_id}", files=[("files", ("admin_file.txt", b"admin content", "text/plain"))])
    assert up_res2.status_code == 201

    # Can list members
    members_res = client.get(f"/api/v1/workspaces/{org_id}/members")
    assert members_res.status_code == 200
    assert members_res.json()["workspace_kind"] == "organization"

    # 3. organization_admin -> read_only
    client.post("/api/v1/auth/login", json={"identifier": "sysowner", "password": "sysowner-password-123"})
    res3 = client.put(f"/api/v1/workspaces/{org_id}/members/{alice_id}/role", json={"role": "read_only"})
    assert res3.status_code == 200
    assert res3.json()["role"] == "read_only"

    # Login as Alice: write operations blocked again
    client.post("/api/v1/auth/login", json={"identifier": "alice", "password": "alice-password-123"})
    up_blocked = client.post(f"/api/v1/files/upload?workspace_id={org_id}", files=[("files", ("denied.txt", b"denied", "text/plain"))])
    assert up_blocked.status_code == 403
    assert "read-only" in up_blocked.json()["detail"].lower()


def test_personal_workspace_rejects_organization_admin(client, monkeypatch):
    """
    organization_admin is only valid for organization workspaces.
    """
    setup_users(client, monkeypatch)
    client.post("/api/v1/auth/login", json={"identifier": "sysowner", "password": "sysowner-password-123"})
    
    # Personal workspace
    workspaces_list = client.get("/api/v1/workspaces").json()["items"]
    personal = next(w for w in workspaces_list if w["kind"] == "personal")

    # Add Alice to personal workspace as member
    add_member_to_workspace(client, monkeypatch, personal["id"], "alice@example.com", "alice-password-123", "alice", "member")

    # Owner logs back in
    client.post("/api/v1/auth/login", json={"identifier": "sysowner", "password": "sysowner-password-123"})
    users = client.get("/api/v1/admin/users").json()["items"]
    alice_id = next(u for u in users if u["email"] == "alice@example.com")["id"]

    # Try setting role to organization_admin in personal workspace: must be rejected with 400
    res = client.put(f"/api/v1/workspaces/{personal['id']}/members/{alice_id}/role", json={"role": "organization_admin"})
    assert res.status_code == 400
    assert "organization workspaces" in res.json()["detail"].lower()


def test_admin_manage_user_workspaces_endpoint(client, monkeypatch):
    """
    Requirement 6: Provide clear way to grant workspace write access from Admin.
    GET /api/v1/admin/users/{user_id}/workspaces
    PUT /api/v1/admin/users/{user_id}/workspaces/{workspace_id}
    """
    setup_users(client, monkeypatch)
    client.post("/api/v1/auth/login", json={"identifier": "sysowner", "password": "sysowner-password-123"})

    org = client.post("/api/v1/organizations", json={"name": "Admin Managed Org"}).json()
    org_id = org["id"]

    users = client.get("/api/v1/admin/users").json()["items"]
    alice_id = next(u for u in users if u["email"] == "alice@example.com")["id"]

    # List user's workspaces
    res = client.get(f"/api/v1/admin/users/{alice_id}/workspaces")
    assert res.status_code == 200
    items = res.json()["items"]
    target_item = next(i for i in items if i["workspace_id"] == org_id)
    assert target_item["is_member"] is False

    # Directly grant organization_admin access via admin endpoint
    set_res = client.put(f"/api/v1/admin/users/{alice_id}/workspaces/{org_id}", json={"role": "organization_admin"})
    assert set_res.status_code == 200
    assert set_res.json()["role"] == "organization_admin"

    # Alice logs in and has organization_admin rights immediately
    client.post("/api/v1/auth/login", json={"identifier": "alice", "password": "alice-password-123"})
    ws = client.get("/api/v1/workspaces").json()["items"]
    org_ws = next(w for w in ws if w["id"] == org_id)
    assert org_ws["role"] == "organization_admin"

    up = client.post(f"/api/v1/files/upload?workspace_id={org_id}", files=[("files", ("data.bin", b"\x00\x01\x02", "application/octet-stream"))])
    assert up.status_code == 201

    # Remove membership via admin endpoint
    client.post("/api/v1/auth/login", json={"identifier": "sysowner", "password": "sysowner-password-123"})
    rem_res = client.put(f"/api/v1/admin/users/{alice_id}/workspaces/{org_id}", json={"role": "none"})
    assert rem_res.status_code == 200
    assert rem_res.json()["role"] is None

    # Alice logs in and no longer sees this workspace
    client.post("/api/v1/auth/login", json={"identifier": "alice", "password": "alice-password-123"})
    ws2 = client.get("/api/v1/workspaces").json()["items"]
    assert not any(w["id"] == org_id for w in ws2)
