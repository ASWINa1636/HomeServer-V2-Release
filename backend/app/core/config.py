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

from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_name: str = "HomeServer V2"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://homeserver_v2:replace-me@db:5432/homeserver_v2"
    secret_key: str = ""
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    session_days: int = 14
    public_base_url: str = "http://localhost:8081"
    email_provider: str = "smtp"
    resend_api_key: str = ""
    smtp_host: str = "homeserver-v2-mailpit"
    smtp_port: int = 1025
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from: str = "HomeServer V2 <noreply@example.test>"
    smtp_starttls: bool = False
    otp_minutes: int = 5
    otp_resend_seconds: int = 60
    otp_max_attempts: int = 5
    registration_policy: str = "open"
    storage_root: str = "/data"
    max_upload_bytes: int = 104857600
    trusted_hosts: str = "*"

    @property
    def production(self) -> bool:
        return self.environment.lower() == "production"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    if settings.production and (len(settings.secret_key) < 32 or settings.secret_key.lower().startswith("replace-") or settings.secret_key == "change-me"):
        raise RuntimeError("SECRET_KEY must be a unique secret of at least 32 characters in production")
    if settings.production and "*" in settings.trusted_hosts.split(","):
        raise RuntimeError("TRUSTED_HOSTS must list the hostnames used in production")
    return settings


settings = get_settings()
