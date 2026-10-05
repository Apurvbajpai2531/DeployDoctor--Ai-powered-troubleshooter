from functools import lru_cache
from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_NAME = "DeployDoctor"
APP_VERSION = "0.1.0"

# backend/app/config.py -> parents[2] is the project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """All configuration comes from environment variables (or a local .env file)."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds POSTGRES_* values used only by Docker Compose
    )

    # Common
    environment: str = "development"
    log_level: str = "INFO"

    # Groq AI
    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    ai_timeout_seconds: int = 30

    # Database (development): full URL
    database_url: str = ""

    # Database (production): injected by Elastic Beanstalk when RDS is attached
    rds_hostname: str = ""
    rds_port: str = "5432"
    rds_db_name: str = ""
    rds_username: str = ""
    rds_password: str = ""

    # Limits & security
    max_log_chars: int = 50000
    max_upload_bytes: int = 1048576
    rate_limit: str = "10/minute"
    cors_origins: str = "http://localhost:8000"
    upload_rate_limit: str = "30/minute"
    max_request_bytes: int = 2097152  # 2 MB; keep equal to nginx client_max_body_size
    # Reverse proxies in front of the app that append to X-Forwarded-For
    trusted_proxy_hops: int = 0

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def groq_configured(self) -> bool:
        return bool(self.groq_api_key.strip())

    @property
    def effective_database_url(self) -> str:
        """Prefer Elastic Beanstalk's RDS_* variables, fall back to DATABASE_URL."""
        if self.rds_hostname:
            user = quote_plus(self.rds_username)
            password = quote_plus(self.rds_password)
            return (
                f"postgresql://{user}:{password}"
                f"@{self.rds_hostname}:{self.rds_port}/{self.rds_db_name}"
            )
        return self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()
