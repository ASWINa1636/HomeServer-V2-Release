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
from app.models.entities import AuditEvent, ServerConfig


def setup_owner(client, monkeypatch, codes=None):
    if codes is None:
        codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    res = client.get("/api/v1/auth/bootstrap-status").json()
    if res.get("available"):
        owner = {
            "full_name": "Network Admin",
            "email": "netadmin@example.com",
            "username": "netadmin",
            "password": "strong-password-1234",
        }
        client.post("/api/v1/auth/bootstrap", json=owner)
        client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]})
        client.post("/api/v1/auth/login", json={"identifier": "netadmin", "password": owner["password"]})


def setup_member(client, monkeypatch, codes=None):
    if codes is None:
        codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    member = {
        "full_name": "Regular Member",
        "email": "member@example.com",
        "username": "regmember",
        "password": "strong-password-1234",
    }
    client.post("/api/v1/auth/register", json=member)
    client.post("/api/v1/auth/verify", json={"email": member["email"], "code": codes[-1]})
    client.post("/api/v1/auth/login", json={"identifier": "regmember", "password": member["password"]})


def test_network_status_overview(client, monkeypatch):
    setup_owner(client, monkeypatch)
    resp = client.get("/api/v1/network/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "local" in data
    assert "tailscale" in data
    assert "public" in data
    assert data["local"]["default_port"] == 8081
    assert "is_configured" in data["tailscale"]
    assert "is_configured" in data["public"]


def test_tailscale_configure_and_reset(client, monkeypatch):
    setup_owner(client, monkeypatch)

    # 1. Invalid syntax returns error status and checks
    resp = client.post(
        "/api/v1/network/tailscale/configure",
        json={"target": "invalid space target", "port": 8081, "device_name": "bad-node"},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "connection_error"
    assert len(res_data["checks"]) > 0

    # 2. Configure a syntactically valid Tailscale node
    resp2 = client.post(
        "/api/v1/network/tailscale/configure",
        json={"target": "node.yak-zebra.ts.net", "port": 8081, "device_name": "homeserver"},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["is_configured"] is True
    assert data2["device_name"] == "homeserver"
    assert data2["port"] == 8081

    # 3. Check tailscale details endpoint
    ts_details = client.get("/api/v1/network/tailscale")
    assert ts_details.status_code == 200
    assert ts_details.json()["is_configured"] is True
    assert ts_details.json()["target"] == "node.yak-zebra.ts.net"

    # 4. Test reset
    reset_resp = client.post("/api/v1/network/tailscale/reset")
    assert reset_resp.status_code == 200
    assert reset_resp.json()["status"] == "not_configured"

    # Check that tailscale is now not configured
    ts_after = client.get("/api/v1/network/tailscale").json()
    assert ts_after["is_configured"] is False


def test_public_access_and_template_generation(client, monkeypatch):
    setup_owner(client, monkeypatch)

    resp = client.post(
        "/api/v1/network/public/configure",
        json={"domain": "cloud.myhomeserver.net", "method": "caddy"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["domain"] == "cloud.myhomeserver.net"
    assert data["method"] == "caddy"
    assert "checks" in data

    # Verify public access details
    pub_details = client.get("/api/v1/network/public")
    assert pub_details.status_code == 200
    assert pub_details.json()["is_configured"] is True
    assert pub_details.json()["domain"] == "cloud.myhomeserver.net"

    # Verify Caddyfile template generator
    caddy_resp = client.get("/api/v1/network/public/caddyfile")
    assert caddy_resp.status_code == 200
    caddyfile = caddy_resp.json()["caddyfile"]
    assert "cloud.myhomeserver.net" in caddyfile
    assert "reverse_proxy localhost:8081" in caddyfile
    assert "Strict-Transport-Security" in caddyfile

    # Verify Cloudflare config generator
    cf_resp = client.get("/api/v1/network/public/cloudflare")
    assert cf_resp.status_code == 200
    cf_yml = cf_resp.json()["config_yml"]
    assert "cloud.myhomeserver.net" in cf_yml
    assert "service: http://localhost:8081" in cf_yml


def test_ordinary_member_forbidden_from_network_configuration(client, monkeypatch):
    codes = []
    setup_owner(client, monkeypatch, codes)
    setup_member(client, monkeypatch, codes)

    # Member can view overall status
    status_resp = client.get("/api/v1/network/status")
    assert status_resp.status_code == 200

    # Member is blocked with 403 from modifying network
    ts_resp = client.post(
        "/api/v1/network/tailscale/configure",
        json={"target": "node.ts.net", "port": 8081},
    )
    assert ts_resp.status_code == 403

    pub_resp = client.post(
        "/api/v1/network/public/configure",
        json={"domain": "example.com", "method": "caddy"},
    )
    assert pub_resp.status_code == 403
