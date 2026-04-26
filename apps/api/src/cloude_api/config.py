"""Application settings loaded from env via pydantic-settings."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=None,  # rely on process env (docker-compose injects)
        case_sensitive=False,
        extra="ignore",
    )

    # Database
    database_url: str = Field(..., alias="DATABASE_URL")

    # Redis
    redis_url: str = Field(..., alias="REDIS_URL")

    # JWT
    jwt_secret: str = Field(..., alias="JWT_SECRET", min_length=32)
    jwt_algorithm: str = Field("HS256", alias="JWT_ALGORITHM")
    jwt_access_ttl_seconds: int = Field(900, alias="JWT_ACCESS_TTL_SECONDS")
    jwt_refresh_ttl_seconds: int = Field(2_592_000, alias="JWT_REFRESH_TTL_SECONDS")

    # Encryption (libsodium sealed box, base64-encoded 32-byte keys)
    encryption_public_key: str = Field(..., alias="ENCRYPTION_PUBLIC_KEY")
    encryption_private_key: str = Field(..., alias="ENCRYPTION_PRIVATE_KEY")

    # Stream token
    stream_token_secret: str = Field(..., alias="STREAM_TOKEN_SECRET", min_length=32)
    stream_token_ttl_seconds: int = Field(300, alias="STREAM_TOKEN_TTL_SECONDS")

    # CORS
    cors_origins: str = Field("", alias="CORS_ORIGINS")

    # Runtime
    api_host: str = Field("0.0.0.0", alias="API_HOST")
    api_port: int = Field(8000, alias="API_PORT")
    api_log_level: str = Field("info", alias="API_LOG_LEVEL")
    environment: str = Field("dev", alias="ENVIRONMENT")

    @field_validator("cors_origins")
    @classmethod
    def _validate_cors(cls, v: str) -> str:
        return v.strip()

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
