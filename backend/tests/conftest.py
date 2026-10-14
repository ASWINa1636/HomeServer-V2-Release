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

import os
import asyncio
os.environ.setdefault("DATABASE_URL", "sqlite+pysqlite:///./test_homeserver_v2.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-for-production")
os.environ.setdefault("STORAGE_ROOT", "/tmp/homeserver-v2-test-data")

import pytest
import httpx
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.core.database import Base, get_db
from app.main import app, _rate_hits


class DirectClient:
    """In-process ASGI client that avoids starting a lifespan worker thread."""
    def __init__(self, application):
        self.application = application
        self.cookies = httpx.Cookies()

    def request(self, method, url, **kwargs):
        async def send():
            headers = dict(kwargs.pop("headers", {}) or {})
            if method.upper() not in ("GET", "HEAD", "OPTIONS") and "hs_v2_csrf" in self.cookies:
                headers["x-csrf-token"] = self.cookies["hs_v2_csrf"]
            async with AsyncClient(transport=ASGITransport(app=self.application), base_url="http://localhost", cookies=self.cookies) as client:
                response = await client.request(method, url, headers=headers, **kwargs)
                self.cookies.update(response.cookies)
                return response
        return asyncio.run(send())

    def get(self, url, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url, **kwargs):
        return self.request("POST", url, **kwargs)

    def put(self, url, **kwargs):
        return self.request("PUT", url, **kwargs)

    def delete(self, url, **kwargs):
        return self.request("DELETE", url, **kwargs)


@pytest.fixture
def client(monkeypatch, tmp_path):
    _rate_hits.clear()
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    def override_db():
        db = TestingSession()
        try:
            yield db
        finally:
            db.close()
    app.dependency_overrides[get_db] = override_db
    monkeypatch.setattr("app.api.auth.send_otp", lambda *args, **kwargs: None)
    from app.core import config
    monkeypatch.setattr(config.settings, "storage_root", str(tmp_path))
    yield DirectClient(app)
    app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
