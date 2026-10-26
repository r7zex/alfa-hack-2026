"""Runtime settings shared by local Python and Docker deployments."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from urllib.parse import urlsplit
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str = "alfa_hack"
    db_user: str = "alfa_demo"
    db_password: SecretStr
    session_cookie_name: str = "delora_session"
    csrf_cookie_name: str = "delora_csrf"
    session_ttl_seconds: int = Field(default=604800, ge=60, le=2592000)
    cookie_secure: bool = False
    demo_auth_enabled: bool = False
    auth_requests_per_minute: int = Field(default=30, ge=1, le=1000)
    auth_email_requests_per_minute: int = Field(default=10, ge=1, le=1000)
    pipeline_async_enabled: bool = True
    worker_poll_seconds: float = Field(default=0.5, ge=0.05, le=30)
    worker_lease_seconds: int = Field(default=60, ge=10, le=600)
    worker_max_attempts: int = Field(default=3, ge=1, le=10)
    worker_backoff_seconds: float = Field(default=1, ge=0, le=30)
    pipeline_step_delay_seconds: float = Field(default=0, ge=0, le=5)
    integration_timeout_seconds: float = Field(default=2, ge=0.1, le=30)
    signing_require_code: bool = True
    demo_signing_code_visible: bool = False
    signing_code_ttl_seconds: int = Field(default=180, ge=10, le=900)
    signing_code_max_attempts: int = Field(default=5, ge=1, le=10)
    signing_code_secret: SecretStr = SecretStr("")
    qwen_base_url: str = "http://127.0.0.1:11434/v1"
    qwen_api_key: SecretStr = SecretStr("")
    qwen_model: str = Field(default="qwen2.5:1.5b", min_length=1, max_length=120)
    qwen_reasoning_effort: Literal["auto", "none", "omit"] = "auto"
    qwen_require_api_key: bool = False
    assistant_enabled: bool = True
    assistant_timeout_seconds: int = Field(default=300, ge=5, le=600)
    assistant_requests_per_minute: int = Field(default=10, ge=1, le=60)
    assistant_max_turns: int = Field(default=50, ge=1, le=100)

    @field_validator("qwen_base_url")
    @classmethod
    def validate_qwen_url(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme not in ("http", "https")
            or not url.hostname
            or url.username
            or url.password
            or url.query
            or url.fragment
        ):
            raise ValueError(
                "QWEN_BASE_URL must be an HTTP(S) API base URL without credentials, query or fragment"
            )
        return value.rstrip("/")

    @property
    def assistant_available(self) -> bool:
        return self.assistant_enabled and (
            not self.qwen_require_api_key or bool(self.qwen_api_key.get_secret_value())
        )

    @property
    def database_url(self) -> str:
        # URL.create correctly escapes special characters in DB_PASSWORD.
        url = URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
        return url.render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
