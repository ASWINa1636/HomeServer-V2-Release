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
            "full_name": "Admin Tester",
            "email": "admintester@example.com",
            "username": "admintester",
            "password": "strong-password-1234",
        }
        client.post("/api/v1/auth/bootstrap", json=owner)
        client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]})
        client.post("/api/v1/auth/login", json={"identifier": "admintester", "password": owner["password"]})
    else:
        login_res = client.post("/api/v1/auth/login", json={"identifier": "admintester", "password": "strong-password-1234"})
        if login_res.status_code != 200:
            user = {
                "full_name": "Admin Tester",
                "email": "admintester@example.com",
                "username": "admintester",
                "password": "strong-password-1234",
            }
            client.post("/api/v1/auth/register", json=user)
            client.post("/api/v1/auth/verify", json={"email": user["email"], "code": codes[-1]})
            client.post("/api/v1/auth/login", json={"identifier": "admintester", "password": user["password"]})



def test_admin_overview_returns_real_system_metrics(client, monkeypatch):
    setup_owner(client, monkeypatch)
    res = client.get("/api/v1/admin/overview")
    assert res.status_code == 200
    data = res.json()
    assert "server" in data
    assert "health" in data
    assert "system" in data
    assert "storage" in data
    assert "users" in data
    assert "security" in data

    # Verify real metrics
    assert data["health"]["app"] == "ok"
    assert data["health"]["database"] == "ok"
    assert data["server"]["version"] == "2.0.0"
    assert "uptime_seconds" in data["server"]
    assert "load_average" in data["system"]
    assert data["users"]["total"] >= 1


def test_admin_users_and_status_toggle(client, monkeypatch):
    setup_owner(client, monkeypatch)
    # Register an additional member
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    member_data = {
        "full_name": "Member To Suspend",
        "email": "suspend_me@example.com",
        "username": "suspendme",
        "password": "password-12345678",
    }
    client.post("/api/v1/auth/register", json=member_data)
    client.post("/api/v1/auth/verify", json={"email": member_data["email"], "code": codes[-1]})

    # Re-login as admin
    client.post("/api/v1/auth/login", json={"identifier": "admintester", "password": "strong-password-1234"})

    users_res = client.get("/api/v1/admin/users")
    assert users_res.status_code == 200
    users = users_res.json()["items"]
    target = next((u for u in users if u["email"] == "suspend_me@example.com"), None)
    assert target is not None
    assert target["is_active"] is True

    # Suspend user
    status_res = client.put(f"/api/v1/admin/users/{target['id']}/status", json={"is_active": False})
    assert status_res.status_code == 200
    assert status_res.json()["is_active"] is False

    # Audit log includes suspension event
    audit_res = client.get("/api/v1/admin/audit")
    assert audit_res.status_code == 200
    assert any("suspended" in a["action"] for a in audit_res.json()["items"])


def test_ordinary_member_forbidden_from_admin_endpoints(client, monkeypatch):
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    # Ensure owner exists
    setup_owner(client, monkeypatch, codes)
    client.post("/api/v1/auth/logout")


    # Sign in as non-admin member
    member = {
        "full_name": "Normal User",
        "email": "normal@example.com",
        "username": "normaluser",
        "password": "password-12345678",
    }
    client.post("/api/v1/auth/register", json=member)
    client.post("/api/v1/auth/verify", json={"email": member["email"], "code": codes[-1]})
    client.post("/api/v1/auth/login", json={"identifier": "normaluser", "password": member["password"]})

    # Try accessing admin endpoints
    assert client.get("/api/v1/admin/overview").status_code == 403
    assert client.get("/api/v1/admin/users").status_code == 403
    assert client.get("/api/v1/admin/audit").status_code == 403
