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
from app.models.entities import Invitation, Membership, User


def test_invitation_creation_success(client, monkeypatch):
    sent_emails = []
    sent_tokens = []
    monkeypatch.setattr(workspaces, "send_invitation", lambda email, token: (sent_emails.append(email), sent_tokens.append(token)))

    owner = {"full_name": "Test Admin", "email": "admin@example.com", "username": "admin", "password": "secure-admin-password-123"}
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    assert client.post("/api/v1/auth/bootstrap", json=owner).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "admin", "password": owner["password"]}).status_code == 200

    ws = client.post("/api/v1/organizations", json={"name": "Dev Org"}).json()
    ws_id = ws["id"]

    # 1. Create invitation
    res = client.post(f"/api/v1/workspaces/{ws_id}/invitations", json={"email": "alice@example.com", "role": "member"})
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "alice@example.com"
    assert data["role"] == "member"
    assert data["delivery_status"] == "sent"
    assert "token=" in data["invite_url"]
    assert len(sent_emails) == 1
    assert sent_emails[0] == "alice@example.com"

    # Verify listing
    inv_list = client.get("/api/v1/invitations").json()
    assert len(inv_list["items"]) >= 1
    item = next(i for i in inv_list["items"] if i["id"] == data["id"])
    assert item["delivery_status"] == "sent"
    assert not item["revoked"]


def test_invitation_persisted_when_smtp_fails(client, monkeypatch):
    monkeypatch.setattr(workspaces, "send_invitation", lambda _email, _token: (_ for _ in ()).throw(OSError("SMTP server unreachable")))

    owner = {"full_name": "Test Admin", "email": "admin2@example.com", "username": "admin2", "password": "secure-admin-password-123"}
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    assert client.post("/api/v1/auth/bootstrap", json=owner).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "admin2", "password": owner["password"]}).status_code == 200

    ws = client.post("/api/v1/organizations", json={"name": "Dev Org 2"}).json()
    ws_id = ws["id"]

    # Create invitation with failing SMTP: must NOT rollback, must persist with delivery_status="failed"
    res = client.post(f"/api/v1/workspaces/{ws_id}/invitations", json={"email": "bob@example.com", "role": "read_only"})
    assert res.status_code == 201
    data = res.json()
    assert data["delivery_status"] == "failed"
    assert "SMTP error" in data["delivery_error"]
    assert "invite_url" in data  # Administrator can copy URL despite email failure!

    # Verify persisted in listing
    inv_list = client.get("/api/v1/invitations").json()
    item = next(i for i in inv_list["items"] if i["id"] == data["id"])
    assert item["delivery_status"] == "failed"
    assert not item["revoked"]

    # Admin can generate / copy link
    link_res = client.post(f"/api/v1/invitations/{data['id']}/link")
    assert link_res.status_code == 200
    assert "token=" in link_res.json()["invite_url"]

    # Admin can retry sending
    monkeypatch.setattr(workspaces, "send_invitation", lambda _email, _token: None)
    retry_res = client.post(f"/api/v1/invitations/{data['id']}/resend")
    assert retry_res.status_code == 200
    assert retry_res.json()["delivery_status"] == "sent"


def test_duplicate_and_expired_invitation_handling(client, monkeypatch):
    monkeypatch.setattr(workspaces, "send_invitation", lambda _email, _token: None)
    owner = {"full_name": "Test Admin", "email": "admin3@example.com", "username": "admin3", "password": "secure-admin-password-123"}
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    assert client.post("/api/v1/auth/bootstrap", json=owner).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "admin3", "password": owner["password"]}).status_code == 200

    ws = client.post("/api/v1/organizations", json={"name": "Dev Org 3"}).json()
    ws_id = ws["id"]

    inv1 = client.post(f"/api/v1/workspaces/{ws_id}/invitations", json={"email": "charlie@example.com", "role": "member"})
    assert inv1.status_code == 201

    # Duplicate active invitation must be rejected with 409
    dup = client.post(f"/api/v1/workspaces/{ws_id}/invitations", json={"email": "charlie@example.com", "role": "member"})
    assert dup.status_code == 409

    # Revoke invitation
    inv_id = inv1.json()["id"]
    rev = client.delete(f"/api/v1/invitations/{inv_id}")
    assert rev.status_code == 200

    # Now that it's revoked, a new invitation for that email can be created
    inv2 = client.post(f"/api/v1/workspaces/{ws_id}/invitations", json={"email": "charlie@example.com", "role": "member"})
    assert inv2.status_code == 201


def test_token_verification_and_otp_flow(client, monkeypatch):
    tokens = []
    monkeypatch.setattr(workspaces, "send_invitation", lambda _email, token: tokens.append(token))
    owner = {"full_name": "Test Admin", "email": "admin4@example.com", "username": "admin4", "password": "secure-admin-password-123"}
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    assert client.post("/api/v1/auth/bootstrap", json=owner).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "admin4", "password": owner["password"]}).status_code == 200

    ws = client.post("/api/v1/organizations", json={"name": "Dev Org 4"}).json()
    inv = client.post(f"/api/v1/workspaces/{ws['id']}/invitations", json={"email": "dave@example.com", "role": "member"}).json()

    # Public endpoint verify-token
    raw_token = tokens[-1]
    verify_res = client.get(f"/api/v1/invitations/verify-token?token={raw_token}")
    assert verify_res.status_code == 200
    assert verify_res.json()["valid"] is True
    assert verify_res.json()["email"] == "dave@example.com"
    assert verify_res.json()["workspace_name"] == "Dev Org 4"

    # Bad token
    assert client.get("/api/v1/invitations/verify-token?token=nonexistent-invalid-token").status_code == 400

    # Register dave
    dave_reg = {"full_name": "Dave User", "email": "dave@example.com", "username": "daveuser", "password": "daves-secure-password-123", "invitation_token": raw_token}
    reg_res = client.post("/api/v1/auth/register", json=dave_reg)
    assert reg_res.status_code == 202

    # Dave attempts login before OTP verification -> must be 403
    assert client.post("/api/v1/auth/login", json={"identifier": "daveuser", "password": dave_reg["password"]}).status_code == 403

    # Dave tries wrong OTP code
    assert client.post("/api/v1/auth/verify", json={"email": "dave@example.com", "code": "000000"}).status_code == 400

    # Dave enters correct OTP code
    dave_otp = codes[-1]
    assert client.post("/api/v1/auth/verify", json={"email": "dave@example.com", "code": dave_otp}).status_code == 200

    # Token cannot be re-verified or reused
    assert client.get(f"/api/v1/invitations/verify-token?token={raw_token}").status_code == 400

    # Dave logs in with username
    login_user = client.post("/api/v1/auth/login", json={"identifier": "daveuser", "password": dave_reg["password"]})
    assert login_user.status_code == 200
    assert login_user.json()["email"] == "dave@example.com"
    assert login_user.json()["role"] == "member"  # Role cannot be escalated!

    # Dave logs in with email
    login_email = client.post("/api/v1/auth/login", json={"identifier": "dave@example.com", "password": dave_reg["password"]})
    assert login_email.status_code == 200

    # Dave is member of ws
    dave_workspaces = client.get("/api/v1/workspaces").json()["items"]
    assert any(w["id"] == ws["id"] for w in dave_workspaces)


def test_registration_policy_enforcement(client, monkeypatch):
    owner = {"full_name": "Test Admin", "email": "admin5@example.com", "username": "admin5", "password": "secure-admin-password-123"}
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    assert client.post("/api/v1/auth/bootstrap", json=owner).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "admin5", "password": owner["password"]}).status_code == 200

    # Policy toggle by admin
    pol = client.get("/api/v1/auth/registration-policy").json()
    assert pol["policy"] in ("open", "invitation_only")

    # Set to invitation_only
    set_pol = client.put("/api/v1/auth/registration-policy", json={"policy": "invitation_only"})
    assert set_pol.status_code == 200
    assert set_pol.json()["policy"] == "invitation_only"

    # Attempt public signup without token
    eve = {"full_name": "Eve Hack", "email": "eve@example.com", "username": "evehack", "password": "eves-password-123"}
    assert client.post("/api/v1/auth/register", json=eve).status_code == 403

    # Switch back to open
    set_open = client.put("/api/v1/auth/registration-policy", json={"policy": "open"})
    assert set_open.status_code == 200

    # Public signup now succeeds
    assert client.post("/api/v1/auth/register", json=eve).status_code == 202


def test_tailscale_signup_flow_and_file_isolation(client, monkeypatch):
    tokens = []
    monkeypatch.setattr(workspaces, "send_invitation", lambda _email, token: tokens.append(token))
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))

    owner = {"full_name": "Tailscale Owner", "email": "tsowner@example.com", "username": "tsowner", "password": "ts-owner-password-123"}
    assert client.post("/api/v1/auth/bootstrap", json=owner).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "tsowner", "password": owner["password"]}).status_code == 200

    # Upload private file into owner's personal workspace
    workspaces_list = client.get("/api/v1/workspaces").json()["items"]
    owner_ws = workspaces_list[0]
    upload = client.post(f"/api/v1/files/upload?workspace_id={owner_ws['id']}", files=[("files", ("secret-plan.txt", b"top-secret-owner-content", "text/plain"))])
    assert upload.status_code == 201

    # Invite coworker into separate organization workspace
    corp_ws = client.post("/api/v1/organizations", json={"name": "Corporation"}).json()
    client.post(f"/api/v1/workspaces/{corp_ws['id']}/invitations", json={"email": "coworker@example.com", "role": "member"})

    token = tokens[-1]
    # Tailscale signup link simulated: /signup?token=<token>
    coworker = {"full_name": "Remote Coworker", "email": "coworker@example.com", "username": "remotecoworker", "password": "remote-password-123", "invitation_token": token}
    assert client.post("/api/v1/auth/register", json=coworker).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": coworker["email"], "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "remotecoworker", "password": coworker["password"]}).status_code == 200

    # Coworker tries to access owner's private files
    blocked = client.get("/api/v1/files", params={"workspace_id": owner_ws["id"]})
    assert blocked.status_code == 403

    # Coworker CAN access corporation workspace files
    corp_files = client.get("/api/v1/files", params={"workspace_id": corp_ws["id"]})
    assert corp_files.status_code == 200


def test_member_role_change_bidirectional_and_restrictions(client, monkeypatch):
    sent_tokens = []
    codes = []
    monkeypatch.setattr(workspaces, "send_invitation", lambda _email, token: sent_tokens.append(token))
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))

    # 1. Bootstrap system owner
    owner_info = {"full_name": "Org Admin", "email": "orgadmin@example.com", "username": "orgadmin", "password": "admin-password-123"}
    assert client.post("/api/v1/auth/bootstrap", json=owner_info).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": owner_info["email"], "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "orgadmin", "password": owner_info["password"]}).status_code == 200

    # 2. Create organization workspace
    ws = client.post("/api/v1/organizations", json={"name": "Engineering"}).json()
    ws_id = ws["id"]

    # 3. Invite user as read_only
    invite_res = client.post(f"/api/v1/workspaces/{ws_id}/invitations", json={"email": "dev@example.com", "role": "read_only"})
    assert invite_res.status_code == 201

    # 4. User registers & verifies
    dev_user = {"full_name": "Dev User", "email": "dev@example.com", "username": "devuser", "password": "dev-password-123", "invitation_token": sent_tokens[-1]}
    assert client.post("/api/v1/auth/register", json=dev_user).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": dev_user["email"], "code": codes[-1]}).status_code == 200

    # 5. Dev user logs in: verify role is read_only and write operations are blocked
    assert client.post("/api/v1/auth/login", json={"identifier": "devuser", "password": dev_user["password"]}).status_code == 200
    user_ws = client.get("/api/v1/workspaces").json()["items"]
    eng_ws = next(w for w in user_ws if w["id"] == ws_id)
    assert eng_ws["role"] == "read_only"

    # Write operations blocked for read_only
    blocked_up = client.post(f"/api/v1/files/upload?workspace_id={ws_id}", files=[("files", ("code.py", b"print(1)", "text/plain"))])
    assert blocked_up.status_code == 403
    assert "read-only" in blocked_up.json()["detail"].lower()

    blocked_mkdir = client.post("/api/v1/files/folders", json={"path": "", "new_name": "src", "workspace_id": ws_id})
    assert blocked_mkdir.status_code == 403

    # 6. Admin logs in to change role from read_only -> member
    assert client.post("/api/v1/auth/login", json={"identifier": "orgadmin", "password": owner_info["password"]}).status_code == 200

    # List members
    members = client.get(f"/api/v1/workspaces/{ws_id}/members").json()["items"]
    dev_member = next(m for m in members if m["email"] == "dev@example.com")
    assert dev_member["role"] == "read_only"

    # Change role via PUT /workspaces/{ws_id}/members/{dev_id}/role: read_only -> member
    change_res = client.put(f"/api/v1/workspaces/{ws_id}/members/{dev_member['id']}/role", json={"role": "member"})
    assert change_res.status_code == 200
    assert change_res.json()["role"] == "member"

    # 7. Dev user logs in: verify role changed to member and write operations succeed
    assert client.post("/api/v1/auth/login", json={"identifier": "devuser", "password": dev_user["password"]}).status_code == 200
    user_ws_updated = client.get("/api/v1/workspaces").json()["items"]
    eng_ws_updated = next(w for w in user_ws_updated if w["id"] == ws_id)
    assert eng_ws_updated["role"] == "member"

    # Write operations permitted now
    allowed_up = client.post(f"/api/v1/files/upload?workspace_id={ws_id}", files=[("files", ("code.py", b"print('hello world')", "text/plain"))])
    assert allowed_up.status_code == 201

    allowed_mkdir = client.post("/api/v1/files/folders", json={"path": "", "new_name": "src", "workspace_id": ws_id})
    assert allowed_mkdir.status_code == 201

    # 8. Admin logs in to change role back from member -> read_only via invite endpoint
    assert client.post("/api/v1/auth/login", json={"identifier": "orgadmin", "password": owner_info["password"]}).status_code == 200
    change_back = client.post(f"/api/v1/workspaces/{ws_id}/invitations", json={"email": "dev@example.com", "role": "read_only"})
    assert change_back.status_code in (200, 201)
    assert change_back.json()["delivery_status"] == "role_updated"
    assert change_back.json()["role"] == "read_only"

    # 9. Dev user logs in: write operations blocked again
    assert client.post("/api/v1/auth/login", json={"identifier": "devuser", "password": dev_user["password"]}).status_code == 200
    blocked_again = client.post(f"/api/v1/files/upload?workspace_id={ws_id}", files=[("files", ("patch.py", b"# patch", "text/plain"))])
    assert blocked_again.status_code == 403

    # 10. Privilege escalation checks
    # Non-admin dev user cannot alter owner or member roles
    dev_escalate = client.put(f"/api/v1/workspaces/{ws_id}/members/{dev_member['id']}/role", json={"role": "member"})
    assert dev_escalate.status_code in (400, 403)

