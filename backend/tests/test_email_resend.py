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
from datetime import timedelta
from unittest.mock import MagicMock
from app.api import auth, workspaces
from app.core.config import settings
from app.models.entities import Challenge, Invitation, Membership, User, now_utc
from app.services import email as email_service


def test_send_email_via_resend_sdk_success(monkeypatch):
    sent_payloads = []
    
    mock_resend = MagicMock()
    mock_resend.Emails.send.side_effect = lambda params: (sent_payloads.append(params), {"id": "re_msg_12345"})[1]
    monkeypatch.setattr(email_service, "resend", mock_resend)
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_secret_api_key_xyz")
    monkeypatch.setattr(settings, "smtp_from", "HomeServer V2 <noreply@customdomain.com>")

    result = email_service.send_email(
        to_email="recipient@example.com",
        subject="Welcome to HomeServer",
        text_content="Your code is 123456",
        html_content="<p>Your code is 123456</p>",
    )

    assert result["provider"] == "resend"
    assert result["id"] == "re_msg_12345"
    assert len(sent_payloads) == 1
    assert sent_payloads[0]["from"] == "HomeServer V2 <noreply@customdomain.com>"
    assert sent_payloads[0]["to"] == ["recipient@example.com"]
    assert sent_payloads[0]["subject"] == "Welcome to HomeServer"
    assert "123456" in sent_payloads[0]["text"]
    assert mock_resend.api_key == "re_test_secret_api_key_xyz"


def test_send_email_via_resend_http_api_success(monkeypatch):
    # Test HTTP API fallback when resend package is not present
    monkeypatch.setattr(email_service, "resend", None)
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_secret_api_key_xyz")
    monkeypatch.setattr(settings, "smtp_from", "HomeServer V2 <noreply@customdomain.com>")

    captured_requests = []

    class MockResponse:
        status_code = 200
        def json(self):
            return {"id": "re_http_998877"}

    class MockClient:
        def __init__(self, *args, **kwargs):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def post(self, url, headers=None, json=None):
            captured_requests.append({"url": url, "headers": headers, "json": json})
            return MockResponse()

    monkeypatch.setattr(email_service.httpx, "Client", MockClient)

    result = email_service.send_email(
        to_email="user@testdomain.com",
        subject="HTTP Test",
        text_content="Plain text",
        html_content="<b>HTML</b>",
    )

    assert result["provider"] == "resend"
    assert result["id"] == "re_http_998877"
    assert len(captured_requests) == 1
    req = captured_requests[0]
    assert req["url"] == "https://api.resend.com/emails"
    assert req["headers"]["Authorization"] == "Bearer re_test_secret_api_key_xyz"
    assert req["json"]["to"] == ["user@testdomain.com"]
    assert req["json"]["from"] == "HomeServer V2 <noreply@customdomain.com>"


def test_resend_missing_api_key_raises_error(monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "")

    with pytest.raises(RuntimeError, match="RESEND_API_KEY is not configured"):
        email_service.send_email("test@example.com", "Test", "Text", "<p>Text</p>")


def test_resend_api_failure_redacts_api_key_and_raises(monkeypatch):
    api_key = "re_secret_very_private_key_123"
    mock_resend = MagicMock()
    mock_resend.Emails.send.side_effect = Exception(f"Unauthorized error with key {api_key}: invalid token")
    monkeypatch.setattr(email_service, "resend", mock_resend)
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", api_key)

    with pytest.raises(RuntimeError) as exc_info:
        email_service.send_email("test@example.com", "Test", "Text", "<p>Text</p>")

    err_str = str(exc_info.value)
    assert api_key not in err_str
    assert "[REDACTED]" in err_str


def test_resend_failure_during_signup_aborts_and_does_not_verify_account(client, monkeypatch):
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")

    mock_resend = MagicMock()
    mock_resend.Emails.send.side_effect = RuntimeError("Resend domain unverified: customdomain.com")
    monkeypatch.setattr(email_service, "resend", mock_resend)

    # First ensure owner bootstrap is done if available
    if client.get("/api/v1/auth/bootstrap-status").json()["available"]:
        # Mock successful send for bootstrap
        monkeypatch.setattr(auth, "send_otp", lambda *args, **kwargs: None)
        owner_data = {"full_name": "Sys Owner", "email": "sysowner@example.com", "username": "sysowner", "password": "secure-owner-pass-123"}
        assert client.post("/api/v1/auth/bootstrap", json=owner_data).status_code == 202
        # Restore failing resend
        monkeypatch.setattr(auth, "send_otp", lambda email, code, label: email_service.send_otp(email, code, label))

    reg_data = {"full_name": "Failed User", "email": "faileduser@example.com", "username": "faileduser", "password": "user-password-123"}
    resp = client.post("/api/v1/auth/register", json=reg_data)
    
    # Must fail with 503
    assert resp.status_code == 503
    assert "email delivery is unavailable" in resp.json()["detail"].lower()
    
    # Verify account was not created or verified
    verify_resp = client.post("/api/v1/auth/verify", json={"email": reg_data["email"], "code": "123456"})
    assert verify_resp.status_code == 400


def test_resend_invitation_failure_marks_delivery_failed(client, monkeypatch):
    # Setup signed-in owner
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    owner = {"full_name": "Org Admin", "email": "org_admin_resend@example.com", "username": "orgadminresend", "password": "secure-admin-pass-123"}
    if client.get("/api/v1/auth/bootstrap-status").json()["available"]:
        client.post("/api/v1/auth/bootstrap", json=owner)
    else:
        client.post("/api/v1/auth/register", json=owner)
    client.post("/api/v1/auth/verify", json={"email": owner["email"], "code": codes[-1]})
    client.post("/api/v1/auth/login", json={"identifier": "orgadminresend", "password": owner["password"]})

    org = client.post("/api/v1/organizations", json={"name": "Resend Org"}).json()
    org_id = org["id"]

    # Configure failing Resend
    monkeypatch.setattr(settings, "email_provider", "resend")
    monkeypatch.setattr(settings, "resend_api_key", "re_test_key")
    mock_resend = MagicMock()
    mock_resend.Emails.send.side_effect = RuntimeError("Domain not verified in Resend")
    monkeypatch.setattr(email_service, "resend", mock_resend)

    # Attempt to invite
    res = client.post(f"/api/v1/workspaces/{org_id}/invitations", json={"email": "invitee@example.com", "role": "member"})
    assert res.status_code == 201
    data = res.json()
    assert data["delivery_status"] == "failed"
    assert "Resend error" in data["delivery_error"]
    assert "Domain not verified" in data["delivery_error"]


def test_otp_expiry_enforcement(client, monkeypatch):
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    user_data = {"full_name": "Expiry Test", "email": "expiry@example.com", "username": "expiryuser", "password": "secure-password-123"}
    
    if client.get("/api/v1/auth/bootstrap-status").json()["available"]:
        client.post("/api/v1/auth/bootstrap", json=user_data)
    else:
        client.post("/api/v1/auth/register", json=user_data)
        
    correct_code = codes[-1]

    # Advance time past OTP expiry (e.g. 10 minutes in the future)
    future_time = now_utc() + timedelta(minutes=10)
    monkeypatch.setattr(auth, "now_utc", lambda: future_time)

    # Attempt verification with the actual code: should fail due to expiry
    res = client.post("/api/v1/auth/verify", json={"email": user_data["email"], "code": correct_code})
    assert res.status_code == 400
    assert "invalid or expired" in res.json()["detail"].lower()


def test_otp_incorrect_code_and_max_attempts(client, monkeypatch):
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    user_data = {"full_name": "Attempts Test", "email": "attempts@example.com", "username": "attemptsuser", "password": "secure-password-123"}
    
    if client.get("/api/v1/auth/bootstrap-status").json()["available"]:
        client.post("/api/v1/auth/bootstrap", json=user_data)
    else:
        client.post("/api/v1/auth/register", json=user_data)

    correct_code = codes[-1]
    
    # Try 4 wrong codes: should return 400
    for _ in range(settings.otp_max_attempts - 1):
        res = client.post("/api/v1/auth/verify", json={"email": user_data["email"], "code": "000000"})
        assert res.status_code == 400

    # 5th wrong attempt: should hit max attempts -> 429
    res = client.post("/api/v1/auth/verify", json={"email": user_data["email"], "code": "000000"})
    assert res.status_code == 429
    assert "too many failed attempts" in res.json()["detail"].lower()

    # Even with correct code now, should still be rejected with 429
    res = client.post("/api/v1/auth/verify", json={"email": user_data["email"], "code": correct_code})
    assert res.status_code == 429


def test_otp_resend_cooldown(client, monkeypatch):
    codes = []
    monkeypatch.setattr(auth, "send_otp", lambda _email, code, _purpose: codes.append(code))
    user_data = {"full_name": "Cooldown Test", "email": "cooldown@example.com", "username": "cooldownuser", "password": "secure-password-123"}
    
    if client.get("/api/v1/auth/bootstrap-status").json()["available"]:
        client.post("/api/v1/auth/bootstrap", json=user_data)
    else:
        client.post("/api/v1/auth/register", json=user_data)

    # Immediately requesting resend should hit cooldown -> 429
    res = client.post("/api/v1/auth/resend", json={"email": user_data["email"]})
    # resend endpoint calls _deliver which calls _challenge
    # Because resend endpoint wraps in 202 if pending, let's test calling register again or direct resend
    # Wait, in auth.py: resend calls _deliver which raises 429
    assert res.status_code == 429
    assert "please wait before requesting another code" in res.json()["detail"].lower()


def test_smtp_mailpit_preservation(monkeypatch):
    # Verify that EMAIL_PROVIDER=smtp uses smtplib.SMTP
    sent_messages = []

    class MockSMTP:
        def __init__(self, host, port, timeout=10):
            self.host = host
            self.port = port
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def starttls(self):
            pass
        def login(self, user, pwd):
            pass
        def send_message(self, msg):
            sent_messages.append(msg)

    monkeypatch.setattr(email_service.smtplib, "SMTP", MockSMTP)
    monkeypatch.setattr(settings, "email_provider", "smtp")
    monkeypatch.setattr(settings, "smtp_from", "HomeServer V2 <noreply@mailpit.test>")

    result = email_service.send_email(
        to_email="dev@example.test",
        subject="Mailpit Test",
        text_content="Local dev body",
        html_content="<p>Local dev body</p>",
    )

    assert result["provider"] == "smtp"
    assert len(sent_messages) == 1
    assert sent_messages[0]["To"] == "dev@example.test"
    assert sent_messages[0]["From"] == "HomeServer V2 <noreply@mailpit.test>"
    assert sent_messages[0]["Subject"] == "Mailpit Test"
