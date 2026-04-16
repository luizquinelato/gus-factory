import os
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_env = os.getenv("APP_ENV", "prod")

# Resolve o .env a partir do arquivo, independente do cwd de execução.
# config.py → core/ → app/ → backend/ → services/ → project root
_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
_env_file     = _project_root / f".env.{_env}"


class Settings(BaseSettings):
    PROJECT_NAME: str = "SaaS Blueprint V1"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    ENVIRONMENT: str = _env

    # Database
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "saas_blueprint_v1"
    POSTGRES_PASSWORD: str = "saas_blueprint_v1"
    POSTGRES_DATABASE: str = "saas_blueprint_v1"
    SQL_ECHO: bool = False

    # Security
    JWT_SECRET_KEY: str = "dev-secret"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440
    INTERNAL_API_KEY: str = ""

    # Cache
    REDIS_URL: str = "redis://localhost:6379/0"

    # Auth service URL — sempre localhost (roda no host)
    AUTH_SERVICE_URL: str = "http://localhost:10100"

    # CORS
    FRONTEND_URL: str = "http://localhost:5177"
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:5177"]

    model_config = SettingsConfigDict(
        env_file=str(_env_file) if _env_file.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DATABASE}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
