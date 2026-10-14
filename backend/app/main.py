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

from collections import defaultdict, deque
from time import monotonic
from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from app.api import admin, auth, backups, files, network, setup, storage, workspaces
from app.core.config import settings
from app.core.database import engine
from app.models import entities  # noqa: F401

app = FastAPI(title=settings.app_name, version="2.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
allowed_hosts = [item.strip() for item in settings.trusted_hosts.split(",") if item.strip()]
app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts or ["localhost"])
_rate_hits: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def auth_rate_limits(request: Request, call_next):
    route = request.url.path
    limits = {
        "/api/v1/auth/register": (8, 3600),
        "/api/v1/auth/bootstrap": (3, 3600),
        "/api/v1/auth/login": (12, 900),
        "/api/v1/auth/verify": (10, 900),
        "/api/v1/auth/resend": (5, 3600),
        "/api/v1/auth/password-reset": (5, 3600),
    }
    if request.method == "POST" and route in limits:
        limit, window = limits[route]
        client_ip = request.headers.get("x-real-ip") or (request.client.host if request.client else "unknown")
        key = f"{client_ip}:{route}"
        now = monotonic()
        hits = _rate_hits[key]
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Try again later."})
        hits.append(now)
    return await call_next(request)


app.include_router(auth.router, prefix="/api/v1")
app.include_router(files.router, prefix="/api/v1")
app.include_router(setup.router, prefix="/api/v1")
app.include_router(workspaces.router, prefix="/api/v1")
app.include_router(storage.router, prefix="/api/v1")
app.include_router(admin.router, prefix="/api/v1")
app.include_router(network.router, prefix="/api/v1")
app.include_router(backups.router, prefix="/api/v1")




@app.get("/health/live", tags=["health"])
def live():
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
def ready():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ready", "database": "ok"}
