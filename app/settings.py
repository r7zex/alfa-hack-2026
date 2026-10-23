"""Runtime settings shared by local Python and Docker deployments."""

from functools import lru_cache

from pydantic import Field, SecretStr
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
