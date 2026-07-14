from functools import lru_cache
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "postgresql+asyncpg://fleetpulse:fleetpulse_dev@localhost:5432/fleetpulse"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(default="development-only-secret-change-me-123", min_length=32)
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_issuer: str = "fleetpulse-api"
    jwt_audience: str = "fleetpulse-web"
    access_token_ttl_minutes: int = Field(default=15, ge=1, le=60)
    refresh_token_ttl_days: int = Field(default=30, ge=1, le=90)

    @model_validator(mode="after")
    def require_production_secret(self) -> "Settings":
        if self.environment == "production" and self.jwt_secret.startswith("development-"):
            raise ValueError("JWT_SECRET must be configured for production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
