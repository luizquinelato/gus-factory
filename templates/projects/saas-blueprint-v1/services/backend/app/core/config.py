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

    # @IF redis
    # Cache — porta 6385 (prod saas-blueprint-v1), sobreposta pelo .env
    REDIS_URL: str = "redis://localhost:6385/0"
    # @ENDIF redis

    # @IF etl
    # RabbitMQ
    RABBITMQ_HOST: str = "localhost"
    RABBITMQ_PORT: int = 5672
    RABBITMQ_USER: str = "guest"
    RABBITMQ_PASS: str = "guest"
    RABBITMQ_MANAGEMENT_PORT: int = 15672
    # @ENDIF etl

    # Auth service URL — sempre localhost (roda no host)
    AUTH_SERVICE_URL: str = "http://localhost:10100"

    # CORS — frontend principal (5177 prod / 5178 dev) + ETL (3344 prod / 3345 dev)
    FRONTEND_URL: str = "http://localhost:5177"
    ETL_FRONTEND_URL: str = "http://localhost:3344"
    BACKEND_CORS_ORIGINS: list[str] = [
        "http://localhost:5177",  # frontend prod
        "http://localhost:5178",  # frontend dev
        "http://localhost:3344",  # etl frontend prod
        "http://localhost:3345",  # etl frontend dev
    ]

    model_config = SettingsConfigDict(
        env_file=str(_env_file) if _env_file.exists() else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def database_url(self) -> str:
        """URL síncrona — usada apenas pelo migration runner e scripts."""
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DATABASE}"
        )

    @property
    def async_database_url(self) -> str:
        """URL assíncrona — usada pelo engine principal da aplicação (asyncpg)."""
        return (
            f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DATABASE}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
