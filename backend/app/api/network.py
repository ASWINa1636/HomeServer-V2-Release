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

from typing import Literal
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.api.deps import current_user, system_admin
from app.core.database import get_db
from app.models.entities import User
from app.services.networking import (
    generate_caddyfile,
    generate_cloudflare_config,
    get_public_access_config,
    get_tailscale_config,
    reset_tailscale_config,
    save_public_access_config,
    save_tailscale_config,
    verify_public_domain,
    verify_tailscale_address,
)

router = APIRouter(prefix="/network", tags=["network"])


class TailscaleConfigureIn(BaseModel):
    target: str = Field(..., min_length=1, max_length=255, description="Tailscale IP or MagicDNS domain")
    device_name: str = Field("", max_length=120)
    port: int = Field(8081, ge=1, le=65535)


class PublicAccessConfigureIn(BaseModel):
    domain: str = Field(..., min_length=3, max_length=255)
    method: Literal["caddy", "cloudflare", "external_proxy"] = "caddy"


@router.get("/status")
def overall_network_status(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    ts = get_tailscale_config(db)
    pub = get_public_access_config(db)
    return {
        "local": {
            "default_port": 8081,
            "guidance": "Connect other devices on your home Wi-Fi/LAN using http://<server-lan-ip>:8081",
        },
        "tailscale": {
            "is_configured": ts["is_configured"],
            "status": ts["status"],
            "target": ts["target"],
            "device_name": ts["device_name"],
            "url": ts["full_url"],
            "last_checked": ts["last_checked"],
        },
        "public": {
            "is_configured": pub["is_configured"],
            "domain": pub["domain"],
            "method": pub["method"],
            "status": pub["status"],
            "url": pub["public_url"],
            "last_checked": pub["last_checked"],
        },
    }


@router.get("/tailscale")
def get_tailscale_details(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return get_tailscale_config(db)


@router.post("/tailscale/configure")
def configure_tailscale(
    payload: TailscaleConfigureIn,
    user: User = Depends(system_admin),
    db: Session = Depends(get_db),
):
    return save_tailscale_config(
        db=db,
        target=payload.target,
        device_name=payload.device_name,
        port=payload.port,
        user_id=user.id,
    )


@router.post("/tailscale/verify")
def verify_tailscale(
    user: User = Depends(system_admin),
    db: Session = Depends(get_db),
):
    cfg = get_tailscale_config(db)
    if not cfg["is_configured"] or not cfg["target"]:
        raise HTTPException(400, "Tailscale is not configured yet. Enter a device name or IP first.")

    res = save_tailscale_config(
        db=db,
        target=cfg["target"],
        device_name=cfg["device_name"] or "",
        port=cfg["port"],
        user_id=user.id,
    )
    return res


@router.post("/tailscale/reset")
def reset_tailscale(
    user: User = Depends(system_admin),
    db: Session = Depends(get_db),
):
    return reset_tailscale_config(db=db, user_id=user.id)


@router.get("/public")
def get_public_access_details(
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    return get_public_access_config(db)


@router.post("/public/configure")
def configure_public_access(
    payload: PublicAccessConfigureIn,
    user: User = Depends(system_admin),
    db: Session = Depends(get_db),
):
    return save_public_access_config(
        db=db,
        domain=payload.domain,
        method=payload.method,
        user_id=user.id,
    )


@router.post("/public/verify")
def verify_public_access(
    user: User = Depends(system_admin),
    db: Session = Depends(get_db),
):
    cfg = get_public_access_config(db)
    if not cfg["is_configured"] or not cfg["domain"]:
        raise HTTPException(400, "Public domain is not configured yet.")

    return save_public_access_config(
        db=db,
        domain=cfg["domain"],
        method=cfg["method"],
        user_id=user.id,
    )


@router.get("/public/caddyfile")
def get_caddyfile_template(
    domain: str = "",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not domain:
        cfg = get_public_access_config(db)
        domain = cfg["domain"] or "homeserver.example.com"
    return {"caddyfile": generate_caddyfile(domain), "domain": domain}


@router.get("/public/cloudflare")
def get_cloudflare_template(
    domain: str = "",
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    if not domain:
        cfg = get_public_access_config(db)
        domain = cfg["domain"] or "homeserver.example.com"
    return {"config_yml": generate_cloudflare_config(domain), "domain": domain}
