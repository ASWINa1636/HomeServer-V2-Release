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
from app.api import workspaces


def test_bootstrap_otp_verify_login_and_single_use(client, monkeypatch):
    sent = []
    monkeypatch.setattr(auth, "send_otp", lambda email, code, purpose: sent.append((email, code)))
    data = {"full_name": "Server Owner", "email": "owner@example.com", "username": "owner", "password": "a-long-test-password-123"}
    assert client.post("/api/v1/auth/register", json=data).status_code == 409
    response = client.post("/api/v1/auth/bootstrap", json=data)
    assert response.status_code == 202
    assert "code" not in response.json()
    assert client.post("/api/v1/auth/bootstrap", json={**data, "email": "other@example.com", "username": "other"}).status_code == 409
    assert client.post("/api/v1/auth/login", json={"identifier": data["email"], "password": data["password"]}).status_code == 403
    assert client.post("/api/v1/auth/verify", json={"email": data["email"], "code": "111111"}).status_code == 400
    assert client.post("/api/v1/auth/verify", json={"email": data["email"], "code": sent[0][1]}).status_code == 200
    assert client.post("/api/v1/auth/verify", json={"email": data["email"], "code": sent[0][1]}).status_code == 400
    assert client.post("/api/v1/auth/login", json={"identifier": "owner", "password": data["password"]}).status_code == 200


def test_registration_duplicate_and_email_login(client, monkeypatch):
    sent = []
    monkeypatch.setattr(auth, "send_otp", lambda email, code, purpose: sent.append(code))
    owner = {"full_name": "Initial Owner", "email": "initial-owner@example.com", "username": "initialowner", "password": "initial-owner-password-123"}
    assert client.post("/api/v1/auth/bootstrap", json=owner).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": sent[-1]}).status_code == 200
    body = {"full_name": "Ada Test", "email": "ada@example.com", "username": "ada", "password": "another-long-password-123"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 202
    assert client.post("/api/v1/auth/register", json=body).status_code == 409
    assert client.post("/api/v1/auth/verify", json={"email": body["email"], "code": sent[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": body["email"], "password": body["password"]}).status_code == 200


def test_email_delivery_failure_does_not_return_otp_or_leave_pending_account(client, monkeypatch):
    owner_codes = []
    def mail_stub(email, code, _purpose):
        if email == "initial-owner@example.com":
            owner_codes.append(code)
        else:
            raise OSError("mail unavailable")
    monkeypatch.setattr(auth, "send_otp", mail_stub)
    owner = {"full_name": "Initial Owner", "email": "initial-owner@example.com", "username": "initialowner", "password": "initial-owner-password-123"}
    assert client.post("/api/v1/auth/bootstrap", json=owner).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": owner_codes[-1]}).status_code == 200
    body = {"full_name": "Mail Failure", "email": "mailfailure@example.com", "username": "mailfailure", "password": "another-long-password-123"}
    response = client.post("/api/v1/auth/register", json=body)
    assert response.status_code == 503
    assert "code" not in response.text
    assert client.post("/api/v1/auth/register", json=body).status_code == 503


def test_password_reset_code_changes_password(client, monkeypatch):
    sent = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: sent.append(code))
    owner = {"full_name": "Initial Owner", "email": "initial-owner@example.com", "username": "initialowner", "password": "initial-owner-password-123"}
    assert client.post("/api/v1/auth/bootstrap", json=owner).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": sent[-1]}).status_code == 200
    body = {"full_name": "Password Owner", "email": "pwowner@example.com", "username": "pwowner", "password": "first-password-long-123"}
    assert client.post("/api/v1/auth/register", json=body).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": body["email"], "code": sent[-1]}).status_code == 200
    assert client.post("/api/v1/auth/password-reset", json={"email": body["email"]}).status_code == 202
    reset_code = sent[-1]
    assert client.post("/api/v1/auth/password-reset/confirm", json={"email": body["email"], "code": reset_code, "new_password": "replacement-password-123"}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "pwowner", "password": body["password"]}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"identifier": body["email"], "password": "replacement-password-123"}).status_code == 200


def test_invitation_only_registration_joins_workspace_after_email_verification(client, monkeypatch):
    codes, tokens = [], []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    monkeypatch.setattr(workspaces, "send_invitation", lambda _email, token: tokens.append(token))
    owner = {"full_name": "Workspace Owner", "email": "workspace-owner@example.com", "username": "workspaceowner", "password": "owner-password-long-123"}
    assert client.post("/api/v1/auth/bootstrap", json=owner).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": "workspaceowner", "password": owner["password"]}).status_code == 200
    workspace = client.post("/api/v1/organizations", json={"name": "Family"}).json()
    owner_file = client.post(f"/api/v1/files/upload?workspace_id={workspace['id']}", files=[("files", ("family-note.txt", b"shared workspace data", "text/plain"))])
    assert owner_file.status_code == 201
    invite = client.post(f"/api/v1/workspaces/{workspace['id']}/invitations", json={"email": "member@example.com", "role": "read_only"})
    assert invite.status_code == 201
    assert client.put("/api/v1/setup/", json={"server_name": "Family Server", "workspace_kind": "organization", "registration_policy": "invitation_only"}).status_code == 200
    member = {"full_name": "Family Member", "email": "member@example.com", "username": "familymember", "password": "member-password-long-123"}
    assert client.post("/api/v1/auth/register", json=member).status_code == 403
    assert client.post("/api/v1/auth/register", json={**member, "invitation_token": tokens[0]}).status_code == 202
    assert client.post("/api/v1/auth/verify", json={"email": member["email"], "code": codes[-1]}).status_code == 200
    assert client.post("/api/v1/auth/login", json={"identifier": member["email"], "password": member["password"]}).status_code == 200
    memberships = client.get("/api/v1/workspaces").json()["items"]
    assert any(item["id"] == workspace["id"] and item["role"] == "read_only" for item in memberships)
    shared_files = client.get("/api/v1/files", params={"workspace_id": workspace["id"]}).json()["items"]
    assert [item["name"] for item in shared_files] == ["family-note.txt"]
    assert client.post(f"/api/v1/files/upload?workspace_id={workspace['id']}", files=[("files", ("blocked.txt", b"blocked", "text/plain"))]).status_code == 403
