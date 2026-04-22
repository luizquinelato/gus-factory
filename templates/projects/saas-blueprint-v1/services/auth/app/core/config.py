import os
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

_env = os.getenv("APP_ENV", "prod")

# Resolve o .env a partir do arquivo, independente do cwd de execução.
# config.py → core/ → app/ → auth/ → services/ → project root
_project_root = Path(__file__).resolve().parent.parent.parent.parent.parent
_env_file     = _project_root / f".env.{_env}"


class Settings(BaseSettings):
    PROJECT_NAME: str = "SaaS Blueprint V1 Auth Service"
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
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 5      # Token curto — refresh automático mantém a sessão
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7        # Refresh token expira em 7 dias
    # Chave compartilhada entre backend e auth para proteger /token/validate
    # Deixar vazio desativa a verificação (dev). Em prod deve ser uma string aleatória longa.
    INTERNAL_API_KEY: str = ""

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
