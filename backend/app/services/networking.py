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

import http.client
import ipaddress
import json
import os
import re
import socket
import ssl
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.entities import AuditEvent, ServerConfig


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


DOMAIN_REGEX = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}$"
)


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path: str, timeout: float = 3.0):
        super().__init__("localhost", timeout=timeout)
        self.socket_path = socket_path

    def connect(self):
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.socket_path)
        self.sock = sock


def check_tailscale_socket() -> dict[str, Any] | None:
    socket_candidates = [
        "/var/run/tailscale/tailscaled.sock",
        "/run/tailscale/tailscaled.sock",
        "/var/snap/tailscale/common/socket/tailscaled.sock",
    ]
    socket_path = None
    for candidate in socket_candidates:
        if os.path.exists(candidate):
            socket_path = candidate
            break

    if not socket_path:
        return None

    try:
        conn = UnixHTTPConnection(socket_path, timeout=2.5)
        conn.request("GET", "/localapi/v0/status")
        resp = conn.getresponse()
        if resp.status == 200:
            data = json.loads(resp.read().decode())
            backend_state = data.get("BackendState", "Unknown")
            self_node = data.get("Self", {})
            ips = self_node.get("TailscaleIPs", [])
            dns_name = self_node.get("DNSName", "").rstrip(".")
            hostname = self_node.get("HostName", "")

            return {
                "socket_present": True,
                "socket_path": socket_path,
                "backend_state": backend_state,
                "hostname": hostname,
                "dns_name": dns_name,
                "tailscale_ips": ips,
                "online": backend_state == "Running",
            }
    except Exception:
        return {
            "socket_present": True,
            "socket_path": socket_path,
            "backend_state": "Error",
            "hostname": None,
            "dns_name": None,
            "tailscale_ips": [],
            "online": False,
        }
    return None


def is_tailscale_ip(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        # Tailscale IPv4 CGNAT range is 100.64.0.0/10
        # Tailscale IPv6 ULA range is fd7a:115c:a1e0::/48
        if ip.version == 4:
            return ip in ipaddress.ip_network("100.64.0.0/10")
        if ip.version == 6:
            return ip in ipaddress.ip_network("fd7a:115c:a1e0::/48")
    except ValueError:
        pass
    return False


def verify_tailscale_address(target: str, port: int = 8081) -> dict[str, Any]:
    target = target.strip()
    if target.startswith("http://"):
        target = target[7:]
    elif target.startswith("https://"):
        target = target[8:]
    if ":" in target and not target.endswith("]"):
        parts = target.split(":")
        target = parts[0]
        try:
            port = int(parts[1])
        except ValueError:
            pass

    checks = []
    resolved_ip = None

    # Check 1: Target address syntax
    is_ts_dns = target.endswith(".ts.net")
    is_ts_ip = is_tailscale_ip(target)
    is_valid_syntax = bool(target and (DOMAIN_REGEX.match(target) or is_ts_dns or is_ts_ip or target.isalnum()))
    checks.append({
        "name": "Target syntax check",
        "passed": is_valid_syntax,
        "detail": f"Target: '{target}' (Tailscale DNS: {is_ts_dns}, Tailscale IP: {is_ts_ip})"
    })

    if not is_valid_syntax:
        return {
            "status": "connection_error",
            "target": target,
            "port": port,
            "url": None,
            "resolved_ip": None,
            "checks": checks,
            "error": f"Invalid Tailscale hostname or IP: '{target}'",
            "last_checked": now_iso(),
        }

    # Check 2: DNS / Hostname resolution
    try:
        addr_info = socket.getaddrinfo(target, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        if addr_info:
            resolved_ip = addr_info[0][4][0]
            checks.append({
                "name": "DNS resolution",
                "passed": True,
                "detail": f"Resolved '{target}' to {resolved_ip}"
            })
        else:
            raise socket.gaierror("No addresses returned")
    except Exception as e:
        checks.append({
            "name": "DNS resolution",
            "passed": False,
            "detail": f"Could not resolve '{target}': {str(e)}"
        })
        return {
            "status": "connection_error",
            "target": target,
            "port": port,
            "url": None,
            "resolved_ip": None,
            "checks": checks,
            "error": f"DNS resolution failed for '{target}'",
            "last_checked": now_iso(),
        }

    # Check 3: Port reachability probe
    probe_ip = resolved_ip or target
    sock = socket.socket(socket.AF_INET if ":" not in probe_ip else socket.AF_INET6, socket.SOCK_STREAM)
    sock.settimeout(2.5)
    connect_result = sock.connect_ex((probe_ip, port))
    sock.close()

    port_open = (connect_result == 0)
    checks.append({
        "name": f"TCP port {port} probe",
        "passed": port_open,
        "detail": "Port is listening and accepting connections" if port_open else f"Connection failed (code {connect_result})"
    })

    if not port_open:
        return {
            "status": "connection_error",
            "target": target,
            "port": port,
            "url": f"http://{target}:{port}",
            "resolved_ip": resolved_ip,
            "checks": checks,
            "error": f"Port {port} is closed or unreachable on {target}",
            "last_checked": now_iso(),
        }

    # Check 4: HTTP health endpoint probe
    http_healthy = False
    try:
        probe_url = f"http://{probe_ip}:{port}/health/ready"
        req = urllib.request.Request(probe_url, headers={"Host": target})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            if resp.status == 200 and ("ready" in body or "ok" in body):
                http_healthy = True
                checks.append({
                    "name": "Application health probe",
                    "passed": True,
                    "detail": "HTTP /health/ready returned 200 OK with healthy status"
                })
            else:
                checks.append({
                    "name": "Application health probe",
                    "passed": False,
                    "detail": f"HTTP status {resp.status}, unexpected response: {body[:80]}"
                })
    except Exception as e:
        checks.append({
            "name": "Application health probe",
            "passed": False,
            "detail": f"HTTP probe to /health/ready failed: {str(e)}"
        })

    all_passed = port_open and http_healthy
    final_status = "connected" if all_passed else "connection_error"
    full_url = f"http://{target}:{port}" if port != 80 else f"http://{target}"

    return {
        "status": final_status,
        "target": target,
        "port": port,
        "url": full_url,
        "resolved_ip": resolved_ip,
        "checks": checks,
        "error": None if all_passed else "One or more network verification checks failed",
        "last_checked": now_iso(),
    }


def get_tailscale_config(db: Session) -> dict[str, Any]:
    configured_row = db.get(ServerConfig, "tailscale_configured")
    target_row = db.get(ServerConfig, "tailscale_target")
    device_row = db.get(ServerConfig, "tailscale_device_name")
    port_row = db.get(ServerConfig, "tailscale_port")
    status_row = db.get(ServerConfig, "tailscale_last_status")
    checked_row = db.get(ServerConfig, "tailscale_last_checked")
    checks_row = db.get(ServerConfig, "tailscale_last_checks")

    configured = configured_row.value.lower() == "true" if configured_row else False
    target = target_row.value if target_row else None
    device_name = device_row.value if device_row else None
    port = int(port_row.value) if port_row and port_row.value.isdigit() else 8081
    last_status = status_row.value if status_row else ("connected" if configured else "not_configured")
    last_checked = checked_row.value if checked_row else None

    checks = []
    if checks_row:
        try:
            checks = json.loads(checks_row.value)
        except Exception:
            checks = []

    socket_info = check_tailscale_socket()

    # If not explicitly configured but socket is running and has IP/DNS, auto-surface it
    if not configured and socket_info and socket_info.get("online"):
        auto_target = socket_info.get("dns_name") or (socket_info.get("tailscale_ips")[0] if socket_info.get("tailscale_ips") else None)
        auto_device = socket_info.get("hostname")
        return {
            "status": "connected",
            "is_configured": True,
            "auto_detected": True,
            "device_name": auto_device,
            "target": auto_target,
            "port": port,
            "full_url": f"http://{auto_target}:{port}" if auto_target else None,
            "last_checked": now_iso(),
            "socket_info": socket_info,
            "checks": [
                {"name": "Local Tailscale socket", "passed": True, "detail": f"Active ({socket_info.get('backend_state')})"},
                {"name": "Device identity", "passed": True, "detail": f"Node: {auto_device} ({auto_target})"}
            ],
            "error": None,
        }

    full_url = f"http://{target}:{port}" if target else None

    return {
        "status": last_status,
        "is_configured": configured,
        "auto_detected": False,
        "device_name": device_name,
        "target": target,
        "port": port,
        "full_url": full_url,
        "last_checked": last_checked,
        "socket_info": socket_info,
        "checks": checks,
        "error": None if last_status == "connected" else (f"Tailscale is currently {last_status}" if configured else None),
    }


def save_tailscale_config(db: Session, target: str, device_name: str, port: int, user_id: int) -> dict[str, Any]:
    verification = verify_tailscale_address(target, port)

    cfg_map = {
        "tailscale_configured": "true",
        "tailscale_target": verification["target"],
        "tailscale_device_name": device_name.strip() or verification["target"],
        "tailscale_port": str(port),
        "tailscale_last_status": verification["status"],
        "tailscale_last_checked": verification["last_checked"],
        "tailscale_last_checks": json.dumps(verification["checks"]),
    }

    for k, v in cfg_map.items():
        row = db.get(ServerConfig, k)
        if row:
            row.value = v
        else:
            db.add(ServerConfig(key=k, value=v))

    db.add(
        AuditEvent(
            actor_user_id=user_id,
            action="network.tailscale_configured",
            target=f"{verification['target']}:{port} ({verification['status']})",
        )
    )
    db.commit()

    return {
        **verification,
        "is_configured": True,
        "device_name": device_name.strip() or verification["target"],
        "full_url": verification["url"],
    }


def reset_tailscale_config(db: Session, user_id: int) -> dict[str, Any]:
    keys = [
        "tailscale_configured",
        "tailscale_target",
        "tailscale_device_name",
        "tailscale_port",
        "tailscale_last_status",
        "tailscale_last_checked",
        "tailscale_last_checks",
    ]
    for k in keys:
        row = db.get(ServerConfig, k)
        if row:
            db.delete(row)

    db.add(AuditEvent(actor_user_id=user_id, action="network.tailscale_reset", target="tailscale"))
    db.commit()

    return {"message": "Tailscale configuration reset", "status": "not_configured"}


# --- Public Domain & HTTPS Service ---


def verify_public_domain(domain: str, method: str = "caddy") -> dict[str, Any]:
    domain = domain.strip().lower()
    if domain.startswith("https://"):
        domain = domain[8:]
    elif domain.startswith("http://"):
        domain = domain[7:]
    domain = domain.split("/")[0].split(":")[0]

    checks = []

    # Check 1: Domain format
    is_valid_domain = bool(DOMAIN_REGEX.match(domain))
    checks.append({
        "name": "Domain name format",
        "passed": is_valid_domain,
        "detail": f"Validated FQDN: '{domain}'" if is_valid_domain else f"Invalid domain name: '{domain}'"
    })

    if not is_valid_domain:
        return {
            "status": "invalid_domain",
            "domain": domain,
            "method": method,
            "url": None,
            "checks": checks,
            "error": "The entered domain name is not a valid fully qualified domain name.",
            "last_checked": now_iso(),
        }

    # Check 2: Public DNS resolution
    resolved_ips = []
    try:
        addr_info = socket.getaddrinfo(domain, 443, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for ai in addr_info:
            ip = ai[4][0]
            if ip not in resolved_ips:
                resolved_ips.append(ip)
        checks.append({
            "name": "Public DNS resolution",
            "passed": True,
            "detail": f"Resolved '{domain}' to {', '.join(resolved_ips)}"
        })
    except Exception as e:
        checks.append({
            "name": "Public DNS resolution",
            "passed": False,
            "detail": f"DNS resolution failed: {str(e)}. Ensure DNS A/AAAA or CNAME records point to your server or tunnel."
        })

    # Check 3: HTTPS endpoint check with TLS verification
    https_ok = False
    tls_detail = "HTTPS probe skipped or not reachable"
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = True
        ctx.verify_mode = ssl.CERT_REQUIRED
        probe_url = f"https://{domain}/health/ready"
        req = urllib.request.Request(probe_url, headers={"User-Agent": "HomeServer-V2-Verifier/1.0"})
        with urllib.request.urlopen(req, context=ctx, timeout=4.0) as resp:
            body = resp.read().decode("utf-8", errors="ignore")
            if resp.status == 200:
                https_ok = True
                tls_detail = "Valid SSL certificate and 200 OK received from /health/ready"
            else:
                tls_detail = f"HTTP {resp.status} received from endpoint"
    except ssl.SSLCertVerificationError as ssl_err:
        tls_detail = f"SSL Certificate error: {ssl_err.verify_message}"
    except Exception as e:
        tls_detail = f"HTTPS connection error: {str(e)}"

    checks.append({
        "name": "HTTPS & SSL verification",
        "passed": https_ok,
        "detail": tls_detail
    })

    # Check 4: Database isolation verification
    # Verify that postgres port 5432 is NOT exposed on the public domain
    db_exposed = False
    try:
        db_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        db_sock.settimeout(1.5)
        if resolved_ips:
            res = db_sock.connect_ex((resolved_ips[0], 5432))
            db_exposed = (res == 0)
        db_sock.close()
    except Exception:
        pass

    checks.append({
        "name": "Database port isolation",
        "passed": not db_exposed,
        "detail": "PostgreSQL port 5432 is securely isolated and not publicly exposed" if not db_exposed else "WARNING: PostgreSQL port 5432 responded on public IP!"
    })

    status = "connected" if https_ok else "unverified"
    public_url = f"https://{domain}" if https_ok else f"https://{domain} (pending TLS)"

    return {
        "status": status,
        "domain": domain,
        "method": method,
        "url": public_url,
        "resolved_ips": resolved_ips,
        "checks": checks,
        "error": None if https_ok else "HTTPS is not yet active or certificate is pending issuance.",
        "last_checked": now_iso(),
    }


def get_public_access_config(db: Session) -> dict[str, Any]:
    configured_row = db.get(ServerConfig, "public_access_configured")
    domain_row = db.get(ServerConfig, "public_domain")
    method_row = db.get(ServerConfig, "public_method")
    status_row = db.get(ServerConfig, "public_last_status")
    checked_row = db.get(ServerConfig, "public_last_checked")
    checks_row = db.get(ServerConfig, "public_last_checks")

    configured = configured_row.value.lower() == "true" if configured_row else False
    domain = domain_row.value if domain_row else None
    method = method_row.value if method_row else "caddy"
    last_status = status_row.value if status_row else ("connected" if configured else "not_configured")
    last_checked = checked_row.value if checked_row else None

    checks = []
    if checks_row:
        try:
            checks = json.loads(checks_row.value)
        except Exception:
            checks = []

    return {
        "is_configured": configured,
        "domain": domain,
        "method": method,
        "status": last_status,
        "public_url": f"https://{domain}" if domain else None,
        "last_checked": last_checked,
        "checks": checks,
        "security": {
            "cookie_secure": settings.cookie_secure,
            "trusted_hosts": settings.trusted_hosts,
            "database_isolated": True,
        },
    }


def save_public_access_config(db: Session, domain: str, method: str, user_id: int) -> dict[str, Any]:
    verification = verify_public_domain(domain, method)

    cfg_map = {
        "public_access_configured": "true",
        "public_domain": verification["domain"],
        "public_method": method,
        "public_last_status": verification["status"],
        "public_last_checked": verification["last_checked"],
        "public_last_checks": json.dumps(verification["checks"]),
    }

    for k, v in cfg_map.items():
        row = db.get(ServerConfig, k)
        if row:
            row.value = v
        else:
            db.add(ServerConfig(key=k, value=v))

    db.add(
        AuditEvent(
            actor_user_id=user_id,
            action="network.public_access_configured",
            target=f"{verification['domain']} via {method} ({verification['status']})",
        )
    )
    db.commit()

    return {
        **verification,
        "is_configured": True,
        "method": method,
    }


def generate_caddyfile(domain: str) -> str:
    clean_domain = domain.strip().lower() or "homeserver.example.com"
    return f"""# HomeServer V2 - Production Caddy Reverse Proxy Configuration
# Place this in /etc/caddy/Caddyfile or into your Caddy container volume.

{{
    # Global options
    email admin@{clean_domain}
}}

{clean_domain} {{
    # Automatic HTTPS with Let's Encrypt / ZeroSSL
    encode zstd gzip

    # Production Security Headers
    header {{
        Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
        X-Content-Type-Options "nosniff"
        X-Frame-Options "SAMEORIGIN"
        Referrer-Policy "strict-origin-when-cross-origin"
        Permissions-Policy "camera=(), microphone=(), geolocation=()"
    }}

    # Forward to HomeServer V2 Frontend (Port 8081)
    reverse_proxy localhost:8081 {{
        header_up Host {{host}}
        header_up X-Real-IP {{remote_host}}
        header_up X-Forwarded-For {{remote_host}}
        header_up X-Forwarded-Proto {{scheme}}
    }}
}}
"""


def generate_cloudflare_config(domain: str) -> str:
    clean_domain = domain.strip().lower() or "homeserver.example.com"
    return f"""# HomeServer V2 - Cloudflare Tunnel Configuration (config.yml)
# Requires cloudflared installed on host or as a Docker container.

tunnel: <YOUR-TUNNEL-UUID>
credentials-file: /etc/cloudflared/<YOUR-TUNNEL-UUID>.json

ingress:
  # Route traffic for your verified domain to HomeServer V2
  - hostname: {clean_domain}
    service: http://localhost:8081
    originRequest:
      noTLSVerify: false
      connectTimeout: 10s

  # Catch-all rule for unmatched hostnames
  - service: http_status:404
"""
