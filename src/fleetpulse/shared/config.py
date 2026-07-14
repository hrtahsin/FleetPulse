from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://fleetpulse:fleetpulse_dev@localhost:5432/fleetpulse"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(default="development-only-secret-change-me-123", min_length=32)
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)


@lru_cache
def get_settings() -> Settings:
    return Settings()
