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

import smtplib
from email.message import EmailMessage
from html import escape
import httpx
from app.core.config import settings

try:
    import resend
except ImportError:
    resend = None


def send_email(to_email: str, subject: str, text_content: str, html_content: str) -> dict:
    """Shared email delivery dispatcher.
    Routes email delivery to either Resend or SMTP/Mailpit based on EMAIL_PROVIDER.
    Never logs secret API keys or OTP values.
    """
    provider = (settings.email_provider or "smtp").lower().strip()

    if provider == "resend":
        return _send_via_resend(to_email, subject, text_content, html_content)
    elif provider in ("smtp", "mailpit"):
        return _send_via_smtp(to_email, subject, text_content, html_content)
    else:
        raise ValueError(f"Unsupported EMAIL_PROVIDER: '{provider}'. Supported providers are 'resend' and 'smtp'.")


def _sanitize_error(msg: str, secret: str) -> str:
    if secret and secret in msg:
        return msg.replace(secret, "[REDACTED]")
    return msg


def _send_via_resend(to_email: str, subject: str, text_content: str, html_content: str) -> dict:
    api_key = (settings.resend_api_key or "").strip()
    if not api_key:
        raise RuntimeError("RESEND_API_KEY is not configured on the server")

    from_addr = settings.smtp_from or "HomeServer V2 <noreply@example.test>"

    # Use resend SDK if available
    if resend is not None:
        try:
            resend.api_key = api_key
            params: resend.Emails.SendParams = {
                "from": from_addr,
                "to": [to_email],
                "subject": subject,
                "text": text_content,
                "html": html_content,
            }
            resp = resend.Emails.send(params)
            msg_id = resp.get("id") if isinstance(resp, dict) else getattr(resp, "id", None)
            return {"provider": "resend", "id": msg_id or "sent"}
        except Exception as exc:
            err_msg = _sanitize_error(str(exc), api_key)
            raise RuntimeError(f"Resend delivery failed: {err_msg}") from None

    # Fallback to direct official Resend REST API via httpx
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "User-Agent": "HomeServer-V2/1.0",
    }
    payload = {
        "from": from_addr,
        "to": [to_email],
        "subject": subject,
        "text": text_content,
        "html": html_content,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post("https://api.resend.com/emails", headers=headers, json=payload)
            if resp.status_code >= 400:
                try:
                    err_json = resp.json()
                    err_msg = err_json.get("message") or err_json.get("error") or resp.text
                except Exception:
                    err_msg = resp.text
                err_msg = _sanitize_error(err_msg, api_key)
                raise RuntimeError(f"Resend delivery failed ({resp.status_code}): {err_msg}")
            data = resp.json()
            return {"provider": "resend", "id": data.get("id", "sent")}
    except Exception as exc:
        err_msg = _sanitize_error(str(exc), api_key)
        raise RuntimeError(f"Resend delivery failed: {err_msg}") from None


def _send_via_smtp(to_email: str, subject: str, text_content: str, html_content: str) -> dict:
    from_addr = settings.smtp_from or "HomeServer V2 <noreply@example.test>"
    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = from_addr
    message["To"] = to_email
    message.set_content(text_content)
    message.add_alternative(html_content, subtype="html")

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
        if settings.smtp_starttls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)

    return {"provider": "smtp", "id": "sent"}


def send_otp(email: str, code: str, purpose: str = "Verify your email") -> dict:
    subject = f"{purpose} — HomeServer V2"
    text_content = f"Your HomeServer V2 code is {code}. It expires in {settings.otp_minutes} minutes."
    html_content = (
        f"<p>Your HomeServer V2 code is <strong>{escape(code)}</strong>.</p>"
        f"<p>It expires in {settings.otp_minutes} minutes.</p>"
    )
    return send_email(email, subject, text_content, html_content)


def send_invitation(email: str, token: str) -> dict:
    link = f"{settings.public_base_url.rstrip('/')}/signup?token={token}"
    subject = "You are invited to HomeServer V2"
    text_content = (
        f"You have been invited to join HomeServer V2.\n\n"
        f"Complete your registration and join your workspace here:\n{link}\n\n"
        f"This invitation expires in 7 days."
    )
    html_content = (
        f'<p>You have been invited to join a <strong>HomeServer V2</strong> workspace.</p>'
        f'<p><a href="{escape(link)}" style="display:inline-block;padding:10px 18px;background:#2563eb;color:#ffffff;text-decoration:none;border-radius:6px;font-weight:600;">Accept Invitation &amp; Register</a></p>'
        f'<p>Or copy this URL into your browser:<br><code>{escape(link)}</code></p>'
        f'<p>This invitation expires in 7 days.</p>'
    )
    return send_email(email, subject, text_content, html_content)
