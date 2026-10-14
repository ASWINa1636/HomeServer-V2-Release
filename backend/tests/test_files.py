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


def signed_in(client, monkeypatch, email, username):
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    if client.get("/api/v1/auth/bootstrap-status").json()["available"]:
        owner = {"full_name": "Initial Owner", "email": "owner@example.com", "username": "owner", "password": "initial-owner-password-123"}
        assert client.post("/api/v1/auth/bootstrap", json=owner).status_code == 202
        assert client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]}).status_code == 200
        assert client.post("/api/v1/auth/login", json={"identifier": "owner", "password": owner["password"]}).status_code == 200
        assert client.post("/api/v1/auth/logout").status_code == 204
    data = {"full_name": username.title(), "email": email, "username": username, "password": "test-password-long-enough"}
    assert client.post("/api/v1/auth/register", json=data).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": email, "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": username, "password": data["password"]}).status_code == 200


def test_upload_download_and_path_traversal_are_scoped(client, monkeypatch):
    signed_in(client, monkeypatch, "files@example.com", "files-user")
    result = client.post("/api/v1/files/upload", files=[("files", ("notes.txt", b"private data", "text/plain"))])
    assert result.status_code == 201
    assert result.json()["uploaded"][0]["size"] == len(b"private data")
    listing = client.get("/api/v1/files")
    assert listing.status_code == 200
    item = listing.json()["items"][0]
    assert item["path"] == "notes.txt"
    download = client.get("/api/v1/files/download", params={"path": item["path"]})
    assert download.status_code == 200
    assert download.content == b"private data"
    assert client.get("/api/v1/files", params={"path": "../outside"}).status_code == 400


def test_users_cannot_list_another_users_files(client, monkeypatch):
    signed_in(client, monkeypatch, "one@example.com", "oneuser")
    assert client.post("/api/v1/files/upload", files=[("files", ("secret.txt", b"one", "text/plain"))]).status_code == 201
    client.post("/api/v1/auth/logout")
    signed_in(client, monkeypatch, "two@example.com", "twouser")
    listing = client.get("/api/v1/files")
    assert listing.status_code == 200
    assert listing.json()["items"] == []


def test_owner_accessing_personal_workspace(client, monkeypatch):
    signed_in(client, monkeypatch, "personal_owner@example.com", "personalowner")
    workspaces = client.get("/api/v1/workspaces").json()["items"]
    personal = next(w for w in workspaces if w["kind"] == "personal" and w["role"] == "owner")
    
    # Upload
    res = client.post(f"/api/v1/files/upload?workspace_id={personal['id']}", files=[("files", ("test.txt", b"my private content", "text/plain"))])
    assert res.status_code == 201
    
    # List
    res = client.get(f"/api/v1/files?workspace_id={personal['id']}")
    assert res.status_code == 200
    assert any(item["name"] == "test.txt" for item in res.json()["items"])
    
    # Download
    res = client.get(f"/api/v1/files/download?path=test.txt&workspace_id={personal['id']}")
    assert res.status_code == 200
    assert res.content == b"my private content"

    # Create folder
    res = client.post("/api/v1/files/folders", json={"path": "", "new_name": "subfolder", "workspace_id": personal["id"]})
    assert res.status_code == 201

    # Rename
    res = client.put("/api/v1/files/rename", json={"path": "test.txt", "new_name": "test_renamed.txt", "workspace_id": personal["id"]})
    assert res.status_code == 200

    # Delete
    res = client.delete(f"/api/v1/files?path=test_renamed.txt&workspace_id={personal['id']}")
    assert res.status_code == 200


def test_organization_member_accessing_organization_workspace(client, monkeypatch):
    # Setup owner & org workspace
    signed_in(client, monkeypatch, "orgadmin@example.com", "orgadmin")
    org = client.post("/api/v1/organizations", json={"name": "Engineering Team"}).json()
    org_id = org["id"]

    # Invite new member
    sent_tokens = []
    from app.api import workspaces as ws_api
    monkeypatch.setattr(ws_api, "send_invitation", lambda email, token: sent_tokens.append(token))
    res = client.post(f"/api/v1/workspaces/{org_id}/invitations", json={"email": "engineer@example.com", "role": "member"})
    assert res.status_code == 201
    assert len(sent_tokens) == 1

    client.post("/api/v1/auth/logout")

    # Engineer accepts invite & registers
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    reg_data = {"full_name": "Staff Engineer", "email": "engineer@example.com", "username": "engineer", "password": "secure-pw-for-engineer"}
    res = client.post("/api/v1/auth/register", json=reg_data)
    assert res.status_code == 202
    res = client.post("/api/v1/auth/verify", json={"email": reg_data["email"], "code": codes[-1]})
    assert res.status_code == 200
    res = client.post("/api/v1/auth/login", json={"identifier": "engineer", "password": reg_data["password"]})
    assert res.status_code == 200

    # Engineer checks workspaces
    ws_list = client.get("/api/v1/workspaces").json()["items"]
    assert any(w["id"] == org_id and w["role"] == "member" for w in ws_list)

    # Engineer can browse organization workspace without owning personal workspace
    res = client.get(f"/api/v1/files?workspace_id={org_id}")
    assert res.status_code == 200
    assert res.json()["workspace_id"] == org_id

    # Engineer uploads file
    res = client.post(f"/api/v1/files/upload?workspace_id={org_id}", files=[("files", ("design.md", b"# Architecture", "text/markdown"))])
    assert res.status_code == 201

    # Engineer downloads file
    res = client.get(f"/api/v1/files/download?path=design.md&workspace_id={org_id}")
    assert res.status_code == 200
    assert res.content == b"# Architecture"


def test_user_without_membership_denied_access(client, monkeypatch):
    signed_in(client, monkeypatch, "private_owner@example.com", "privateowner")
    workspaces = client.get("/api/v1/workspaces").json()["items"]
    personal_ws = next(w for w in workspaces if w["kind"] == "personal" and w["role"] == "owner")
    org_ws = client.post("/api/v1/organizations", json={"name": "Restricted Org"}).json()

    client.post("/api/v1/auth/logout")

    # Separate outsider user
    signed_in(client, monkeypatch, "outsider@example.com", "outsider")

    # Outsider denied personal workspace
    res = client.get(f"/api/v1/files?workspace_id={personal_ws['id']}")
    assert res.status_code == 403
    assert res.json()["detail"] == "Personal workspace access required"

    # Outsider denied organization workspace
    res = client.get(f"/api/v1/files?workspace_id={org_ws['id']}")
    assert res.status_code == 403
    assert res.json()["detail"] == "Workspace access required"

    # Nonexistent workspace returns 404
    res = client.get("/api/v1/files?workspace_id=999999")
    assert res.status_code == 404


def test_read_only_member_browsing_and_downloading_files(client, monkeypatch):
    signed_in(client, monkeypatch, "orglead@example.com", "orglead")
    org = client.post("/api/v1/organizations", json={"name": "Audited Org"}).json()
    org_id = org["id"]

    # Upload a document
    res = client.post(f"/api/v1/files/upload?workspace_id={org_id}", files=[("files", ("handbook.pdf", b"Handbook contents", "application/pdf"))])
    assert res.status_code == 201

    # Invite read_only member
    from app.api import workspaces as ws_api
    monkeypatch.setattr(ws_api, "send_invitation", lambda email, token: None)
    res = client.post(f"/api/v1/workspaces/{org_id}/invitations", json={"email": "auditor@example.com", "role": "read_only"})
    assert res.status_code == 201

    client.post("/api/v1/auth/logout")

    # Register and sign in as auditor
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    reg_data = {"full_name": "Security Auditor", "email": "auditor@example.com", "username": "auditor", "password": "auditor-password-123"}
    assert client.post("/api/v1/auth/register", json=reg_data).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": reg_data["email"], "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "auditor", "password": reg_data["password"]}).status_code == 200

    # Auditor can list files
    res = client.get(f"/api/v1/files?workspace_id={org_id}")
    assert res.status_code == 200
    assert any(f["name"] == "handbook.pdf" for f in res.json()["items"])

    # Auditor can download file
    res = client.get(f"/api/v1/files/download?path=handbook.pdf&workspace_id={org_id}")
    assert res.status_code == 200
    assert res.content == b"Handbook contents"

    # Auditor can search
    res = client.get(f"/api/v1/files/search?q=handbook&workspace_id={org_id}")
    assert res.status_code == 200
    assert len(res.json()["items"]) == 1

    # Auditor cannot upload
    res = client.post(f"/api/v1/files/upload?workspace_id={org_id}", files=[("files", ("malicious.sh", b"echo evil", "text/plain"))])
    assert res.status_code == 403
    assert "read-only" in res.json()["detail"].lower()

    # Auditor cannot create folder
    res = client.post("/api/v1/files/folders", json={"path": "", "new_name": "newdir", "workspace_id": org_id})
    assert res.status_code == 403
    assert "read-only" in res.json()["detail"].lower()

    # Auditor cannot rename
    res = client.put("/api/v1/files/rename", json={"path": "handbook.pdf", "new_name": "handbook_renamed.pdf", "workspace_id": org_id})
    assert res.status_code == 403
    assert "read-only" in res.json()["detail"].lower()

    # Auditor cannot delete
    res = client.delete(f"/api/v1/files?path=handbook.pdf&workspace_id={org_id}")
    assert res.status_code == 403
    assert "read-only" in res.json()["detail"].lower()


def test_member_uploading_and_managing_permitted_files(client, monkeypatch):
    signed_in(client, monkeypatch, "manager@example.com", "manager")
    org = client.post("/api/v1/organizations", json={"name": "Collab Workspace"}).json()
    org_id = org["id"]

    # Invite regular member
    from app.api import workspaces as ws_api
    monkeypatch.setattr(ws_api, "send_invitation", lambda email, token: None)
    res = client.post(f"/api/v1/workspaces/{org_id}/invitations", json={"email": "collab_member@example.com", "role": "member"})
    assert res.status_code == 201

    client.post("/api/v1/auth/logout")

    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    reg_data = {"full_name": "Collab Member", "email": "collab_member@example.com", "username": "collabmember", "password": "collab-password-123"}
    assert client.post("/api/v1/auth/register", json=reg_data).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": reg_data["email"], "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "collabmember", "password": reg_data["password"]}).status_code == 200

    # Member uploads
    res = client.post(f"/api/v1/files/upload?workspace_id={org_id}", files=[("files", ("tasks.txt", b"item 1\nitem 2", "text/plain"))])
    assert res.status_code == 201

    # Member creates folder
    res = client.post("/api/v1/files/folders", json={"path": "", "new_name": "projects", "workspace_id": org_id})
    assert res.status_code == 201

    # Member moves file
    res = client.post(f"/api/v1/files/move?destination=projects", json={"path": "tasks.txt", "workspace_id": org_id})
    assert res.status_code == 200

    # Member renames file
    res = client.put("/api/v1/files/rename", json={"path": "projects/tasks.txt", "new_name": "tasks_v2.txt", "workspace_id": org_id})
    assert res.status_code == 200

    # Member deletes file
    res = client.delete(f"/api/v1/files?path=projects/tasks_v2.txt&workspace_id={org_id}")
    assert res.status_code == 200


def test_switching_between_accessible_workspaces(client, monkeypatch):
    signed_in(client, monkeypatch, "multispace@example.com", "multispace")
    # User gets their personal workspace
    workspaces = client.get("/api/v1/workspaces").json()["items"]
    personal_ws = next(w for w in workspaces if w["kind"] == "personal")
    
    # User creates org workspace
    org_ws = client.post("/api/v1/organizations", json={"name": "Multi Org"}).json()

    # Upload to personal
    client.post(f"/api/v1/files/upload?workspace_id={personal_ws['id']}", files=[("files", ("only_personal.txt", b"my stuff", "text/plain"))])
    # Upload to org
    client.post(f"/api/v1/files/upload?workspace_id={org_ws['id']}", files=[("files", ("only_org.txt", b"team stuff", "text/plain"))])

    # Switching to personal
    personal_files = client.get(f"/api/v1/files?workspace_id={personal_ws['id']}").json()["items"]
    assert any(f["name"] == "only_personal.txt" for f in personal_files)
    assert not any(f["name"] == "only_org.txt" for f in personal_files)

    # Switching to org
    org_files = client.get(f"/api/v1/files?workspace_id={org_ws['id']}").json()["items"]
    assert any(f["name"] == "only_org.txt" for f in org_files)
    assert not any(f["name"] == "only_personal.txt" for f in org_files)


def test_preventing_cross_workspace_file_access_by_changing_api_parameters(client, monkeypatch):
    # User A setup
    signed_in(client, monkeypatch, "victim@example.com", "victim")
    workspaces = client.get("/api/v1/workspaces").json()["items"]
    victim_ws = next(w for w in workspaces if w["kind"] == "personal")
    client.post(f"/api/v1/files/upload?workspace_id={victim_ws['id']}", files=[("files", ("confidential.key", b"super-secret-key", "text/plain"))])
    client.post("/api/v1/auth/logout")

    # Attacker setup
    signed_in(client, monkeypatch, "attacker@example.com", "attacker")

    # Attacker tries reading confidential.key by passing victim_ws['id']
    res = client.get(f"/api/v1/files/download?path=confidential.key&workspace_id={victim_ws['id']}")
    assert res.status_code == 403

    # Attacker tries listing victim_ws
    res = client.get(f"/api/v1/files?workspace_id={victim_ws['id']}")
    assert res.status_code == 403

    # Attacker tries uploading to victim_ws
    res = client.post(f"/api/v1/files/upload?workspace_id={victim_ws['id']}", files=[("files", ("trojan.exe", b"malware", "application/octet-stream"))])
    assert res.status_code == 403

    # Attacker tries creating folder in victim_ws
    res = client.post("/api/v1/files/folders", json={"path": "", "new_name": "hacked", "workspace_id": victim_ws["id"]})
    assert res.status_code == 403

    # Attacker tries renaming in victim_ws
    res = client.put("/api/v1/files/rename", json={"path": "confidential.key", "new_name": "pwned.key", "workspace_id": victim_ws["id"]})
    assert res.status_code == 403

    # Attacker tries deleting in victim_ws
    res = client.delete(f"/api/v1/files?path=confidential.key&workspace_id={victim_ws['id']}")
    assert res.status_code == 403

    # Attacker tries searching in victim_ws
    res = client.get(f"/api/v1/files/search?q=confidential&workspace_id={victim_ws['id']}")
    assert res.status_code == 403
